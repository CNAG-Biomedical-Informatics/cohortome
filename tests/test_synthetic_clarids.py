import csv
import json
import re
from pathlib import Path

import pytest

from scripts.generate_synthetic_clarids import FIXTURES, ROOT, subject_rows
from app.query_store import _read_subject_clarid_rows


@pytest.mark.parametrize('name', list(FIXTURES))
def test_synthetic_subject_identifiers_cover_fixture(name):
    root = ROOT / name
    source = subject_rows(root, FIXTURES[name])
    patient_ids = {row['unique_id'] for row in source}
    stored = _read_subject_clarid_rows(root, patient_ids)
    assert len(stored) == len(patient_ids)
    with (root / 'identifiers/clarid_subjects.csv').open() as handle:
        encoded = list(csv.DictReader(handle))
    assert [{key: str(row[key]) for key in source[0]} for row in encoded] == [
        {key: str(value) for key, value in row.items()} for row in source]
    assert all(row['clar_id'] and row['stub_id'] and row['condition_name'] for row in encoded)


def test_autoimmune_generator_uses_reviewed_sidecar():
    assert (ROOT / 'scripts/data/synthetic_autoimmune_clarid_subjects.csv').read_bytes() == (
        ROOT / 'synthetic_autoimmune_demo/identifiers/clarid_subjects.csv').read_bytes()


def test_older_prepared_clarids_remain_readable(tmp_path, monkeypatch):
    import duckdb
    from app import query_store
    database = tmp_path / 'identifiers.duckdb'
    query_store._build_query_store(str(ROOT / 'private_dataset'), database, tmp_path / 'meta.json', {})
    with duckdb.connect(str(database)) as con:
        con.execute('DROP INDEX idx_patient_clarids_human_id')
        con.execute('DROP INDEX idx_patient_clarids_stub_id')
        con.execute('ALTER TABLE patient_clarids DROP COLUMN condition_name')
    monkeypatch.setattr(query_store, 'ensure_query_store', lambda _: None)
    monkeypatch.setattr(query_store, '_connect', lambda _: duckdb.connect(str(database), read_only=True))
    identity = query_store.patient_clarid_inventory('fixture')['PRIV10001']
    assert identity['condition'] == 'G35'
    assert 'condition_name' not in identity
    assert query_store.resolve_patient_identifier('fixture', identity['human_id'])['clarid'] == identity


def test_fixture_numbers_and_all_sample_links_are_consistent():
    from app.query_store import _manifest_assay_sample_patient_links, _detect_matrix_delimiter
    from scripts.generate_synthetic_multimodal_fixture import patient_ids, build_hc_clinical_records
    assert patient_ids()[0][0] == 'SYN001'
    assert build_hc_clinical_records()[0]['patient_id'] == 'HC031'
    assert patient_ids(20000)[0][0] == 'SYN20001'
    assert build_hc_clinical_records(20000)[0]['patient_id'] == 'HC20031'
    assigned = set()
    study_uids = set()
    for name in FIXTURES:
        root = ROOT / name
        subjects = subject_rows(root, FIXTURES[name])
        patients = {row['unique_id'] for row in subjects}
        for row in subjects:
            number = int(re.search(r'\d+$', row['unique_id'])[0])
            assert number == row['subject_id']
            assert number not in assigned
            assigned.add(number)
        manifest = json.loads((root / 'assays/manifest.json').read_text())
        for item in manifest['assays']:
            with (root / item['file']).open() as handle:
                first = handle.readline()
            samples = next(csv.reader([first], delimiter=_detect_matrix_delimiter(first)))[1:]
            links = _manifest_assay_sample_patient_links(root, item, samples)
            assert not links['unlinked_sample_ids']
            assert set(links['links'].values()) <= patients
        dicom_manifest = root / 'assays/imaging/dicom_studies.json'
        if dicom_manifest.exists():
            import pydicom
            for study in json.loads(dicom_manifest.read_text())['studies']:
                assert study['patient_id'] in patients
                assert study['study_instance_uid'] not in study_uids
                study_uids.add(study['study_instance_uid'])
            for path in (root / 'assays/imaging/dicom').glob('*.dcm'):
                ds = pydicom.dcmread(path, stop_before_pixels=True)
                assert str(ds.PatientID) in patients
                assert ds.StudyInstanceUID in study_uids
