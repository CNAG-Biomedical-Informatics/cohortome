import json

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app import patient_overview as overview
from app.query_store import duckdb


def test_search_is_literal_bounded_and_supports_clarid(tmp_path, monkeypatch):
    path = str(tmp_path / 'patients.duckdb')
    con = duckdb.connect(path)
    con.execute('CREATE TABLE patients(patient_id TEXT, sex TEXT, visit_count INTEGER)')
    con.execute('CREATE TABLE patient_clarids(patient_id TEXT, human_id TEXT)')
    con.executemany('INSERT INTO patients VALUES (?, ?, ?)', [(f'SYN{i:03}', 'female', 1) for i in range(20)])
    con.execute("INSERT INTO patient_clarids VALUES ('SYN003', 'TEST-CLARID')")
    con.close()
    monkeypatch.setattr(overview, 'ensure_query_store', lambda _: None)
    monkeypatch.setattr(overview, '_connect', lambda _: duckdb.connect(path, read_only=True))
    assert len(overview.lookup('unused', 'syn')) == 12
    assert overview.lookup('unused', 'clarid')[0]['patient_id'] == 'SYN003'
    assert overview.lookup('unused', "%') OR TRUE --") == []
    assert overview.lookup('unused', 'SYN00', exact=True) == []


def test_inventory_uses_headers_and_explicit_metadata_only(tmp_path):
    assays = tmp_path / 'assays'; assays.mkdir()
    (assays / 'matrix.csv').write_text('feature_id;S1;S2\ninvalid body deliberately not parsed\n')
    (assays / 'metadata.tsv').write_text('sample_id\tpatient_id\tvisit_id\tcollection_date\tmaterial\nS1\tP1\tbaseline\t2025-01-01\tBlood\nS2\tP2\t\t\t\nS3\tP1\t\t\t\n')
    item = dict(assay_id='rna', label='RNA', modality='transcriptomics',
                file='assays/matrix.csv', sample_metadata_file='assays/metadata.tsv')
    (assays / 'manifest.json').write_text(json.dumps({'assays': [item, dict(item, assay_id='unlinked', sample_metadata_file='')]}))
    rows, warnings = overview.sample_inventory(tmp_path, 'P1')
    assert [r['sample_id'] for r in rows] == ['S1']
    assert rows[0]['material'] == 'Blood'
    assert rows[0]['visit'] == 'baseline'
    assert len(warnings) == 1
    rows, _ = overview.sample_inventory(tmp_path, 'P2')
    assert rows[0]['material'] == ''
    assert overview.sample_inventory(tmp_path, 'absent')[0] == []
    (assays / 'metadata.tsv').write_text('sample_id\tpatient_id\nS1\tP1\nS1\tP2\n')
    assert overview.sample_inventory(tmp_path, 'P1')[0] == []


def test_missing_and_outside_files_are_warnings_not_records(tmp_path):
    (tmp_path / 'assays').mkdir()
    (tmp_path / 'assays/manifest.json').write_text(json.dumps({'assays': [dict(
        assay_id='bad', label='Unavailable assay', patient_linkage='exact_sample_id', file='../outside.csv')]}))
    rows, warnings = overview.sample_inventory(tmp_path, 'P1')
    assert not rows and len(warnings) == 1
    assert 'outside.csv' not in warnings[0]


@pytest.fixture
def client():
    app = FastAPI(); app.include_router(overview.router)
    with TestClient(app) as client:
        yield client


def test_duplicate_patient_ids_remain_dataset_scoped(client, monkeypatch):
    monkeypatch.setattr(overview, 'sources', lambda *a: [('a', 'root-a', 'A'), ('b', 'root-b', 'B')])
    monkeypatch.setattr(overview, 'lookup', lambda *a, **kw: [dict(patient_id='P1')])
    monkeypatch.setattr(overview, 'sample_inventory', lambda root, _: ([{'sample_id': root}], []))
    matches = client.get('/patient-overview/search', params=dict(workspace='scope', q='P1')).json()['matches']
    assert [m['dataset_id'] for m in matches] == ['a', 'b']
    result = client.get('/patient-overview/detail', params=dict(workspace='scope', dataset_id='b', patient_id='P1'))
    assert result.json()['samples'] == [{'sample_id': 'root-b'}]
    assert client.get('/patient-overview/detail', params=dict(workspace='scope', dataset_id='c', patient_id='P1')).status_code == 403


@pytest.mark.parametrize('status', [401, 403])
def test_search_and_detail_require_authorized_detailed_access(client, monkeypatch, status):
    def denied(*args): raise HTTPException(status, 'Denied')
    monkeypatch.setattr(overview, 'require_authenticated', denied if status == 401 else lambda _: {})
    monkeypatch.setattr(overview, '_require_detailed_assay_access', denied)
    assert client.get('/patient-overview/search', params=dict(workspace='a', q='P1')).status_code == status
    assert client.get('/patient-overview/timeline', params=dict(workspace='a')).status_code == status
    assert client.get('/patient-overview/detail', params=dict(workspace='a', dataset_id='a', patient_id='P1')).status_code == status
