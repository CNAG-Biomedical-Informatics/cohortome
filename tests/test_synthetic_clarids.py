import csv
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
    identity = query_store.patient_clarid_inventory('fixture')['PRIV001']
    assert identity['condition'] == 'G35'
    assert 'condition_name' not in identity
    assert query_store.resolve_patient_identifier('fixture', identity['human_id'])['clarid'] == identity
