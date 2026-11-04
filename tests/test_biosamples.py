import csv
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


def test_origin_only_read_skips_clarid_join_but_reads_current_metadata(package, monkeypatch):
    from app import biosamples
    def unexpected(*args):
        pytest.fail('Origin filtering must not join clinical records and ClarID tables')
    monkeypatch.setattr(biosamples, '_attach_clarids', unexpected)
    assert len(read_biosamples(package, include_clarids=False)) == 3
    (package / 'biosamples.json').write_text('[]')
    assert read_biosamples(package, include_clarids=False) == []


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


def clarid_table(package):
    manifest = json.loads((package / 'manifest.json').read_text())
    manifest['identifiers'] = {'clarid_biosamples': {
        'entity': 'biosample', 'file': 'biosample_clarids.csv',
        'codebook_version': '0.04', 'tools_version': '0.05'}}
    (package / 'manifest.json').write_text(json.dumps(manifest))
    # Same genuine codebook-0.04 label for two distinct fictional specimens.
    return [dict(unique_id=sid, individual_id='P1', subject_id='41', project='CNAG-Test',
        species='Human', tissue='Blood', sample_type='Normal', assay='Whole Genome Sequencing',
        condition='C22.0', timepoint='Baseline', duration='P0D', batch='', replicate='',
        clar_id='CNAG_Test-HomSap-00041-BLO-NOR-WGS-C22.0-BSL-P0D',
        stub_id='CT0100fBNZ0N401B0D') for sid in ('S1', 'S2')]


def write_clarids(package, rows):
    with (package / 'biosample_clarids.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)


def test_biosample_clarids_share_labels_not_identity(package):
    write_clarids(package, clarid_table(package))
    assert validate_package(package)['valid']
    records = read_biosamples(package)
    assert records[0]['clarid'] == records[1]['clarid']
    assert records[0]['id'] != records[1]['id']
    assert records[0]['clarid']['subject_id'] == 41
    assert 'clarid' not in records[2]  # Partial coverage is allowed.
    test_assays_require_explicit_biosample_link(package)
    # The preceding test leaves no specimen link, even though sample ID matches.
    rows, _ = overview.sample_inventory(package)
    assert rows[0]['biosample_clarid'] is None
    (package / 'assays/samples.tsv').write_text('sample_id\tpatient_id\tbiosample_id\nS1\tP1\tS2\n')
    rows, warnings = overview.sample_inventory(package)
    assert not warnings
    assert rows[0]['biosample_id'] == 'S2'
    assert rows[0]['biosample_clarid'] == records[1]['clarid']


@pytest.mark.parametrize('change', ['duplicate', 'orphan', 'parent', 'number', 'missing', 'outside', 'no_biosamples'])
def test_invalid_biosample_clarids(package, change):
    rows = clarid_table(package)
    if change == 'duplicate': rows.append(rows[0])
    if change == 'orphan': rows[0]['unique_id'] = 'absent'
    if change == 'parent': rows[0]['individual_id'] = 'P2'
    if change == 'number': rows[1]['subject_id'] = '42'
    if change == 'missing': rows[0]['tissue'] = ''
    write_clarids(package, rows)
    manifest = json.loads((package / 'manifest.json').read_text())
    if change == 'outside': manifest['identifiers']['clarid_biosamples']['file'] = '../outside.csv'
    if change == 'no_biosamples': del manifest['biosamples']
    (package / 'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(PackageValidationError, match='Biosample input is invalid'):
        validate_package(package)


def test_biosample_numbers_match_existing_subjects(package):
    rows = clarid_table(package)
    write_clarids(package, rows)
    manifest = json.loads((package / 'manifest.json').read_text())
    manifest['identifiers']['clarid_subjects'] = dict(entity='subject', file='subjects.csv',
        codebook_version='0.04', tools_version='0.05')
    (package / 'manifest.json').write_text(json.dumps(manifest))
    (package / 'subjects.csv').write_text(
        'unique_id,subject_id,study,type,condition,sex,age_group,clar_id,stub_id\n'
        'P1,41,Test,Case,C22.0,Male,A40_49,human1,stub1\n'
        'P2,42,Test,Case,C22.0,Male,A40_49,human2,stub2\n')
    assert read_biosamples(package)[0]['clarid']['subject_id'] == 41
    for row in rows:
        row['subject_id'] = '43'
    write_clarids(package, rows)
    with pytest.raises(ValueError, match='Biosample input is invalid'):
        read_biosamples(package)
