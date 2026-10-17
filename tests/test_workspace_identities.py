"""Execution identity regression tests using deliberately colliding synthetic IDs."""
import json

from app import bff, query_store
from app.identities import identity_key, decode_identity


def test_merged_sql_and_bff_use_the_same_keys(tmp_path, monkeypatch):
    paths = {}
    merged = tmp_path / 'merged'
    (merged / 'clinical').mkdir(parents=True)
    manifest = {'dataset_ids': ['a', 'a__b'], 'clinical_files': []}
    for dataset in manifest['dataset_ids']:
        root = tmp_path / dataset
        (root / 'clinical').mkdir(parents=True)
        payload = json.dumps([{'id': 'P001:V1', 'patient_id': 'P001', 'sex': 'female'}])
        (root / 'clinical' / 'records.json').write_text(payload)
        db = root / 'store.duckdb'
        meta = root / 'store.json'
        query_store._build_query_store(str(root), db, meta, {})
        paths[dataset] = (db, meta, root)
        target = dataset + '__records.json'
        (merged / 'clinical' / target).write_text(payload)
        manifest['clinical_files'].append({'dataset_id': dataset, 'target': target})
    (merged / 'manifest.json').write_text(json.dumps(manifest))
    monkeypatch.setattr(query_store, '_dataset_store_paths', paths.__getitem__)
    monkeypatch.setattr(query_store, '_store_ready_or_raise', lambda _: None)
    connection = query_store._connect_workspace(manifest['dataset_ids'])
    try:
        patients = {row[0] for row in connection.execute('SELECT patient_id FROM patients').fetchall()}
        samples = set(connection.execute('SELECT patient_id, original_id FROM timepoints').fetchall())
        assert patients == {identity_key(d, 'patient', 'P001') for d in paths}
        assert samples == {(identity_key(d, 'patient', 'P001'), identity_key(d, 'sample', 'P001:V1')) for d in paths}
    finally:
        connection.close()
    records = [record for _, _, record in bff.read_bff_records(merged / 'clinical')]
    assert {bff.extract_patient_id(r) for r in records} == patients
    assert {(bff.extract_patient_id(r), r['id']) for r in records} == samples
    for record in records:
        assert record['_cohortome_source']['patient_id'] == 'P001'
        assert decode_identity(record['id'])[2] == 'P001:V1'
    from app.analysis import derive_scope_patient_ids, record_matches_scope
    selected = identity_key('a', 'sample', 'P001:V1')
    assert derive_scope_patient_ids([selected], str(merged)) == [identity_key('a', 'patient', 'P001')]
    assert sum(record_matches_scope(r, {selected}) for r in records) == 1
    from app.pheno import expand_scope_ids_to_record_ids
    expanded = expand_scope_ids_to_record_ids(records, [identity_key('a', 'patient', 'P001')])
    assert expanded['record_ids'] == [selected]
    # Preparing a workspace must not rewrite the source records or source stores.
    for _, _, root in paths.values():
        assert json.loads((root / 'clinical' / 'records.json').read_text())[0]['id'] == 'P001:V1'


def test_identity_decode_rejects_malformed_and_preserves_unicode():
    assert decode_identity(identity_key('étude', 'patient', '雪:01')) == ('étude', 'patient', '雪:01')
    for value in ['', 'P001', 'cohortome-v1-!', 'cohortome-v1-W10', None]:
        assert decode_identity(value) is None


def test_external_assay_header_qualifies_links_without_rewriting_matrix(tmp_path, monkeypatch):
    matrix = tmp_path / 'matrix.tsv'
    matrix.write_text('feature\tS1\nmarker\t12\n')
    monkeypatch.setattr(query_store, '_external_assay_matrix_path', lambda *args: matrix)
    monkeypatch.setattr(query_store, '_manifest_item_root', lambda *args: tmp_path)
    monkeypatch.setattr(query_store, '_manifest_assay_sample_patient_links', lambda *args: {'links': {'S1': 'P1'}})
    _, _, samples, links = query_store._external_assay_header(str(tmp_path), {'_source_dataset_id': 'a'})
    key = identity_key('a', 'sample', 'S1')
    assert samples == [key]
    assert links == {key: identity_key('a', 'patient', 'P1')}
    assert matrix.read_text() == 'feature\tS1\nmarker\t12\n'


def test_mds_patient_linkage_is_explicit(tmp_path):
    from app.pheno import generate_mds_points
    import csv
    sample = identity_key('a', 'sample', 'unrelated-sample-name')
    patient = identity_key('a', 'patient', 'P001')
    label = 'C1_' + sample
    matrix = tmp_path / 'matrix.txt'
    matrix.write_text(f'id\t{label}\n{label}\t0\n')
    result = generate_mds_points(matrix, record_patients={sample: patient})
    assert result['returncode'] == '0'
    with (tmp_path / 'mds_points.tsv').open() as handle:
        row = next(csv.DictReader(handle, delimiter='\t'))
    assert row['record_id'] == label
    assert row['patient_id'] == patient


def test_rsem_export_selects_source_columns_with_qualified_keys(tmp_path, monkeypatch):
    from app.analysis_external import _export_manifest_count_like_matrix
    matrix = tmp_path / 'matrix.tsv'
    matrix.write_text('gene\tS1\tS2\nG1\t1.5\t2.5\nG2\t3.5\t4.5\n')
    item = {'file': 'matrix.tsv', '_source_dataset_id': 'a'}
    monkeypatch.setattr(query_store, '_manifest_assay_item', lambda *args: item)
    monkeypatch.setattr(query_store, '_manifest_item_root', lambda *args: tmp_path)
    monkeypatch.setattr(query_store, '_manifest_assay_sample_patient_links', lambda *args: {'links': {'S1': 'P1', 'S2': 'P2'}})
    output = tmp_path / 'export.tsv'
    result = _export_manifest_count_like_matrix(str(tmp_path), dataset_name='a__rna',
        cohort_a_scope={'patient_ids': [identity_key('a', 'patient', 'P1')], 'sample_ids': []},
        cohort_b_scope={'patient_ids': [identity_key('a', 'patient', 'P2')], 'sample_ids': []}, output_path=output)
    assert result['sample_ids'] == [identity_key('a', 'sample', sid) for sid in ['S1', 'S2']]
    assert result['sample_table_rows'][0]['patient_id'] == identity_key('a', 'patient', 'P1')
    assert output.read_text().splitlines()[1:] == ['G1\t1.5\t2.5', 'G2\t3.5\t4.5']
