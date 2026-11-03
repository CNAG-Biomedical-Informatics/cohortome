import json

import pytest

from app.biosamples import read_biosamples
from app.dataset_validation import validate_package, PackageValidationError
from app import patient_overview as overview


@pytest.fixture
def package(tmp_path):
    (tmp_path / 'clinical').mkdir()
    (tmp_path / 'clinical/individuals.json').write_text(json.dumps([{'id': 'P1'}, {'id': 'P2'}]))
    (tmp_path / 'manifest.json').write_text(json.dumps({
        'schema_version': 1, 'clinical': {'representation': 'person'},
        'biosamples': {'file': 'biosamples.json'}}))
    (tmp_path / 'biosamples.json').write_text(json.dumps([
        {'id': 'S1', 'individualId': 'P1', 'sampleOriginType': {'id': 'UBERON:0000178', 'label': 'blood'}},
        {'id': 'S2', 'individualId': 'P1'},
        {'id': 'S3', 'individualId': 'P2', 'sampleOriginType': {'id': 'UBERON:0002107', 'label': 'liver'}},
    ]))
    return tmp_path


def test_optional_and_validated(package, tmp_path):
    assert read_biosamples(package / 'absent') == []
    assert validate_package(package)['biosamples'] == 3
    assert read_biosamples(package)[1].get('sampleOriginType') is None


@pytest.mark.parametrize('change', ['duplicate', 'orphan', 'ontology', 'outside', 'clinical'])
def test_invalid_biosamples(package, change):
    path = package / 'biosamples.json'
    rows = json.loads(path.read_text())
    if change == 'duplicate': rows.append(rows[0])
    if change == 'orphan': rows[0]['individualId'] = 'not-a-patient'
    if change == 'ontology': rows[0]['sampleOriginType'] = 'blood'
    path.write_text(json.dumps(rows))
    if change in ('outside', 'clinical'):
        manifest = json.loads((package / 'manifest.json').read_text())
        manifest['biosamples']['file'] = '../outside.json' if change == 'outside' else 'clinical/individuals.json'
        (package / 'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(PackageValidationError, match='Biosample input is invalid'):
        validate_package(package)


def test_patient_search_origin_and_dataset_counts(package, monkeypatch):
    path = str(package / 'patients.duckdb')
    from app.query_store import duckdb
    con = duckdb.connect(path)
    con.execute('CREATE TABLE patients(patient_id TEXT, sex TEXT, visit_count INTEGER)')
    con.execute("INSERT INTO patients VALUES ('P1', '', 1), ('P2', '', 1)")
    con.close()
    monkeypatch.setattr(overview, 'ensure_query_store', lambda _: None)
    monkeypatch.setattr(overview, '_connect', lambda _: duckdb.connect(path, read_only=True))
    rows = overview.lookup(package, '', sample_origin='UBERON:0000178', include_total=True)
    assert [r['patient_id'] for r in rows] == ['P1']
    assert rows[0]['_total'] == 1
    assert overview.lookup(package, '', sample_origin="unknown' OR TRUE --") == []
    monkeypatch.setattr(overview, 'sources', lambda *a: [('a', package, 'A'), ('b', package, 'B')])
    options = overview.sample_origins(None, 'scope')
    assert options[0]['patient_count'] == 2  # Same source ID in two datasets is two patients.
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    app.include_router(overview.router)
    with TestClient(app) as client:
        response = client.get('/patient-overview/search', params={
            'workspace': 'scope', 'sample_origin': 'UBERON:0000178', 'sort_by': 'patient_id'})
        assert response.status_code == 200
        assert response.json()['total'] == 2
        assert [r['dataset_id'] for r in response.json()['matches']] == ['a', 'b']
        (package / 'biosamples.json').write_text('{}')
        assert client.get('/patient-overview/sample-origins', params={'workspace': 'scope'}).status_code == 409


def test_assays_require_explicit_biosample_link(package):
    folder = package / 'assays'
    folder.mkdir()
    (folder / 'values.csv').write_text('feature_id,S1\nf1,1\n')
    (folder / 'samples.tsv').write_text('sample_id\tpatient_id\tbiosample_id\nS1\tP1\tS1\n')
    (folder / 'manifest.json').write_text(json.dumps({'assays': [{
        'assay_id': 'a', 'modality': 'proteomics', 'file': 'assays/values.csv',
        'sample_metadata_file': 'assays/samples.tsv'}]}))
    rows, warnings = overview.sample_inventory(package)
    assert not warnings and rows[0]['material'] == 'blood'
    (folder / 'samples.tsv').write_text('sample_id\tpatient_id\nS1\tP1\n')
    rows, warnings = overview.sample_inventory(package)
    assert not warnings and rows[0]['material'] == ''
