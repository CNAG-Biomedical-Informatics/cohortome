import csv
import json
from pathlib import Path

import pytest

from scripts.generate_synthetic_autoimmune_demo import build


def test_demo_reproducible_and_linked(tmp_path):
    first, second = tmp_path / 'first', tmp_path / 'second'
    build(first)
    build(second)
    for path in first.rglob('*'):
        if path.is_file():
            assert path.read_bytes() == (second / path.relative_to(first)).read_bytes()
    with pytest.raises(ValueError, match='already exists'):
        build(first)
    records = json.loads((first / 'clinical/fictional_participants.json').read_text())
    assert len(records) == 90
    patients = {r['patient_id'] for r in records}
    checked_in = Path(__file__).resolve().parents[1] / 'synthetic_autoimmune_demo/clinical/fictional_participants.json'
    assert patients == {r['patient_id'] for r in json.loads(checked_in.read_text())}
    assert len(patients) == 90
    assert all(r['info']['synthetic'] for r in records)
    manifest = json.loads((first / 'assays/manifest.json').read_text())
    expected = {'transcriptomics': (1000, 90), 'methylation': (128, 84),
                'flow_cytometry': (6, 81), 'serology': (6, 87)}
    for assay in manifest['assays']:
        with (first / assay['file']).open() as handle:
            rows = list(csv.reader(handle, delimiter=';'))
        features, samples = expected[assay['modality']]
        assert len(rows) == features + 1
        assert all(len(row) == samples + 1 for row in rows)
        with (first / assay['sample_metadata_file']).open() as handle:
            metadata = list(csv.DictReader(handle, delimiter='\t'))
        assert [p['sample_id'] for p in metadata] == rows[0][1:]
        assert {p['patient_id'] for p in metadata} <= patients
        assert all(sum(p['group'] == g for p in metadata) == samples // 3 for g in ['RA', 'SLE', 'HC'])


def test_demo_builds_real_query_store(tmp_path):
    from app.query_store import _build_query_store, _manifest_assay_inventory
    import duckdb
    root = tmp_path / 'demo'
    build(root)
    from app.datasets import validate_dataset_release_root
    assert validate_dataset_release_root(str(root)) == root
    db = tmp_path / 'demo.duckdb'
    _build_query_store(str(root), db, tmp_path / 'meta.json', {})
    with duckdb.connect(str(db), read_only=True) as con:
        assert con.execute('SELECT count(*) FROM patients').fetchone()[0] == 90
        assert con.execute('SELECT count(*) FROM patient_clarids').fetchone()[0] == 90
        assert con.execute("SELECT count(*) FROM patient_clarids WHERE condition_name <> ''").fetchone()[0] == 90
        patients = {r[0] for r in con.execute('SELECT patient_id FROM patients').fetchall()}
        assert con.execute('SELECT count(*) FROM transcript_counts').fetchone()[0] == 0
    inventory = _manifest_assay_inventory(str(root), set(), patients)
    assert len(inventory) == 4
    assert sum(a['sample_count'] for a in inventory) == 342
    assert all(a['clinical_overlap_patient_count'] == a['sample_count'] for a in inventory)
    assert all(a['unlinked_sample_count'] == 0 for a in inventory)
