import json

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app import patient_overview as overview
from app.query_store import duckdb


@pytest.mark.parametrize('metadata, expected', [
    ({'days_from_baseline': '0'}, 0),
    ({'days_from_baseline': '-7'}, -7),
    ({'week_from_baseline': '2.5'}, 17.5),
    ({'days_from_baseline': 'NaN'}, None),
    ({'days_from_baseline': 'inf'}, None),
    ({'days_from_baseline': False}, None),
    ({'timepoint': 'week_2'}, None),
])
def test_relative_study_days_only_uses_explicit_finite_offsets(metadata, expected):
    assert overview.relative_study_days(metadata) == expected


def test_relative_sample_collection_metadata(tmp_path):
    assays = tmp_path / 'assays'
    assays.mkdir()
    (assays / 'values.csv').write_text('feature_id,S1\nf1,1\n')
    (assays / 'metadata.tsv').write_text(
        'sample_id\tpatient_id\ttimepoint\tweek_from_baseline\tspecimen_type\n'
        'S1\tP1\tweek_0\t0\tstool\n')
    (assays / 'manifest.json').write_text(json.dumps({'assays': [{
        'assay_id': 'a', 'modality': 'metabolomics', 'file': 'assays/values.csv',
        'patient_linkage': 'sample_metadata_file', 'patient_id_column': 'patient_id',
        'sample_metadata_file': 'assays/metadata.tsv'}]}))
    rows, warnings = overview.sample_inventory(tmp_path)
    assert not warnings
    assert rows[0]['days_from_baseline'] == 0
    assert rows[0]['visit'] == 'week_0'
    assert rows[0]['material'] == 'stool'
    assert rows[0]['collection_date'] == ''


def test_clinical_timeline_preserves_relative_time_without_inventing_dates(tmp_path):
    from app.bff import dashboard_summary
    clinical = tmp_path / 'clinical'
    clinical.mkdir()
    (clinical / 'records.json').write_text(json.dumps([
        {'id': 'P1:V1', 'patient_id': 'P1', 'visit_id': 'V1',
         'info': {'days_from_baseline': 0}},
        {'id': 'P1:V2', 'patient_id': 'P1', 'visit_id': 'V2',
         'info': {'week_from_baseline': 2}},
    ]))
    events = dashboard_summary(str(tmp_path))['timelines'][0]['events']
    assert [e['days_from_baseline'] for e in events] == [0, 14]
    assert all(not e['event_date'] for e in events)


def test_search_is_literal_bounded_and_supports_clarid(tmp_path, monkeypatch):
    path = str(tmp_path / 'patients.duckdb')
    con = duckdb.connect(path)
    con.execute('CREATE TABLE patients(patient_id TEXT, sex TEXT, visit_count INTEGER)')
    con.execute('CREATE TABLE patient_clarids(patient_id TEXT, human_id TEXT)')
    con.executemany('INSERT INTO patients VALUES (?, ?, ?)', [(f'SYN{i:03}', 'female', 1) for i in range(20)])
    con.execute("INSERT INTO patient_clarids VALUES ('SYN003', 'TEST-CLARID')")
    con.execute('CREATE TABLE patient_diseases(patient_id TEXT, disease TEXT)')
    con.execute("INSERT INTO patient_diseases VALUES ('SYN003', 'Crohn disease'), ('SYN004', 'Other')")
    con.close()
    monkeypatch.setattr(overview, 'ensure_query_store', lambda _: None)
    monkeypatch.setattr(overview, '_connect', lambda _: duckdb.connect(path, read_only=True))
    assert len(overview.lookup('unused', 'syn')) == 12
    assert overview.lookup('unused', 'clarid')[0]['patient_id'] == 'SYN003'
    assert overview.lookup('unused', "%') OR TRUE --") == []
    assert overview.lookup('unused', 'SYN00', exact=True) == []
    assert len(overview.lookup('unused', '', 20)) == 20
    assert overview.lookup('unused', '', 20, after='SYN018')[0]['patient_id'] == 'SYN019'
    assert overview.lookup('unused', '', 2, descending=True)[0]['patient_id'] == 'SYN019'
    assert overview.lookup('unused', '', 2, sort_by='clarid', descending=True)[0]['patient_id'] == 'SYN003'
    assert [r['patient_id'] for r in overview.lookup('unused', '', disease='crohn disease')] == ['SYN003']
    assert overview.lookup('unused', 'SYN004', disease='Crohn disease') == []
    assert overview.lookup('unused', '', disease="Crohn disease' OR TRUE --") == []
    rows = overview.lookup('unused', '', limit=1, disease=['Crohn disease', 'Other'], include_total=True)
    assert len(rows) == 1 and rows[0]['_total'] == 2


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


def test_browse_paginates_across_datasets_without_losing_duplicates(client, monkeypatch):
    monkeypatch.setattr(overview, 'sources', lambda *a: [('a', 'a', 'A'), ('b', 'b', 'B')])
    def lookup(root, term, limit, after=''):
        return [dict(patient_id=f'P{i:02}', diagnosis='Example diagnosis')
                for i in range(25) if f'P{i:02}' > after and term in f'P{i:02}'][:limit]
    monkeypatch.setattr(overview, 'lookup', lookup)
    params = dict(workspace='scope')
    results = []
    for _ in range(3):
        data = client.get('/patient-overview/search', params=params).json()
        assert len(data['matches']) <= 20
        results.extend((r['dataset_id'], r['patient_id']) for r in data['matches'])
        params = dict(workspace='scope', **(data['next'] or {}))
    assert data['next'] is None
    assert len(results) == len(set(results)) == 50
    assert results[25] == ('b', 'P00')
    assert client.get('/patient-overview/search', params=dict(workspace='scope', dataset_index=-1)).status_code == 422


def test_full_clinical_records_are_scoped_paginated_and_keep_source_values(client, monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(overview, 'sources', lambda *a: [('a', 'root-a', 'A')])
    monkeypatch.setattr(overview, 'ensure_query_store', lambda root: None)
    raw = {'id': 'P1:V1', 'info': {'days_from_baseline': 0},
           'measures': [{'measurementValue': {'quantity': {'value': 0}}}]}
    visits = [SimpleNamespace(visit_id=f'V{i}', event_date=None,
              provenance=SimpleNamespace(raw_bff=raw, source_file='/not-exposed'))
              for i in range(25)]
    visits.sort(key=lambda visit: visit.visit_id)  # Deliberately lexical input.
    monkeypatch.setattr(overview, 'get_patient_context',
                        lambda root, pid: SimpleNamespace(visits=visits) if pid == 'P1' else None)
    params = dict(workspace='scope', dataset_id='a', patient_id='P1')
    response = client.get('/patient-overview/clinical', params=params)
    payload = response.json()
    assert payload['total'] == 25 and payload['next_offset'] == 20
    assert len(payload['records']) == 20
    assert [r['visit_id'] for r in payload['records']] == [f'V{i}' for i in range(20)]
    assert payload['records'][0]['record'] == raw
    assert payload['records'][0]['days_from_baseline'] == 0
    assert '/not-exposed' not in response.text
    last = client.get('/patient-overview/clinical', params={**params, 'offset': 20}).json()
    assert len(last['records']) == 5 and last['next_offset'] is None
    assert [r['visit_id'] for r in last['records']] == [f'V{i}' for i in range(20, 25)]
    one = client.get('/patient-overview/clinical', params={**params, 'visit_id': 'V22'}).json()
    assert len(one['records']) == 1 and one['records'][0]['visit_id'] == 'V22'
    assert client.get('/patient-overview/clinical', params={**params, 'dataset_id': 'b'}).status_code == 403
    assert client.get('/patient-overview/clinical', params={**params, 'patient_id': 'other'}).status_code == 404


@pytest.mark.parametrize('status', [401, 403])
def test_search_and_detail_require_authorized_detailed_access(client, monkeypatch, status):
    def denied(*args): raise HTTPException(status, 'Denied')
    monkeypatch.setattr(overview, 'require_authenticated', denied if status == 401 else lambda _: {})
    monkeypatch.setattr(overview, '_require_detailed_assay_access', denied)
    assert client.get('/patient-overview/search', params=dict(workspace='a', q='P1')).status_code == status
    assert client.get('/patient-overview/timeline', params=dict(workspace='a')).status_code == status
    assert client.get('/patient-overview/coverage', params=dict(workspace='a')).status_code == status
    assert client.get('/patient-overview/detail', params=dict(workspace='a', dataset_id='a', patient_id='P1')).status_code == status


def test_coverage_is_dataset_scoped_and_includes_assay_only_patients(client, tmp_path, monkeypatch):
    from app import dicom
    path = str(tmp_path / 'coverage.duckdb')
    con = duckdb.connect(path)
    con.execute('CREATE TABLE patients(patient_id TEXT)')
    con.execute("INSERT INTO patients VALUES ('P1')")
    con.close()
    monkeypatch.setattr(overview, 'sources', lambda *a: [('a', 'root-a', 'A'), ('b', 'root-b', 'B')])
    monkeypatch.setattr(overview, 'ensure_query_store', lambda _: None)
    monkeypatch.setattr(overview, '_connect', lambda _: duckdb.connect(path, read_only=True))
    monkeypatch.setattr(dicom, 'dicom_studies', lambda _: [])
    monkeypatch.setattr(overview, 'sample_inventory', lambda root, **kw: ([
        dict(patient_id='P1', modality=m) for m in (['transcriptomics', 'methylation', 'proteomics'] if root == 'root-a' else ['serology'])
    ] + [dict(patient_id='P2', modality='transcriptomics')], ['Missing linkage']))
    payload = client.get('/patient-overview/coverage', params={'workspace':'scope'}).json()
    patients = payload['patients']
    assert len(patients) == 4
    assert patients[0]['modalities'] == ['clinical', 'methylation', 'proteomics', 'transcriptomics']
    assert patients[2]['modalities'] == ['clinical', 'serology']
    assert not patients[1]['has_clinical']
    assert len(payload['warnings']) == 2
