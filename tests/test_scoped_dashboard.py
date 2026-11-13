import json
from pathlib import Path

import pytest

from app.identities import decode_identity
from app.scoped_dashboard import scoped_assay_inventory
from bff_test_helpers import isolate_query_store


def test_scoped_inventory_keeps_source_identity_and_drops_global_statistics(tmp_path, monkeypatch):
    isolate_query_store(monkeypatch, tmp_path)
    roots = {}
    for dataset in ['one', 'two']:
        root = tmp_path / dataset
        roots[dataset] = root
        (root / 'clinical').mkdir(parents=True)
        (root / 'clinical/individuals.json').write_text(json.dumps([{'id':'P1'}, {'id':'P2'}]))
        (root / 'assays').mkdir()
        (root / 'assays/manifest.json').write_text(json.dumps({'assays':[{
            'assay_id':'panel', 'file':'assays/matrix.csv', 'modality':'proteomics',
            'data_type':'normalized_abundance', 'sample_metadata_file':'assays/samples.tsv',
            'feature_count':1}]}))
        (root / 'assays/matrix.csv').write_text('feature_id,S1,S2\nF1,1,2\n')
        (root / 'assays/samples.tsv').write_text('sample_id\tpatient_id\nS1\tP1\nS2\tP2\n')
    result = scoped_assay_inventory(roots, [{'dataset_id':'two', 'patient_id':'P1'}])
    assert len(result) == 1
    row = result[0]
    assert row['dataset_name'] == 'two::panel'
    assert row['sample_count'] == row['patient_count'] == row['clinical_overlap_patient_count'] == 1
    assert [decode_identity(value) for value in row['patient_ids']] == [('two', 'patient', 'P1')]
    assert [decode_identity(value) for value in row['sample_ids']] == [('two', 'sample', 'S1')]
    assert row['top_genes'] == [] and row['mean_total_counts_per_sample'] is None
    assert scoped_assay_inventory(roots, []) == []


def test_scoped_external_inventory_reads_only_header_without_declared_feature_count(tmp_path, monkeypatch):
    from app import query_store
    isolate_query_store(monkeypatch, tmp_path)
    (tmp_path / 'clinical').mkdir()
    (tmp_path / 'clinical/individuals.json').write_text('[{"id":"P1"},{"id":"P2"}]')
    (tmp_path / 'assays').mkdir()
    (tmp_path / 'assays/manifest.json').write_text(json.dumps({'assays':[{
        'assay_id':'rna', 'file':'assays/counts.csv', 'modality':'transcriptomics',
        'data_type':'rsem_expected_counts', 'sample_metadata_file':'assays/samples.tsv'}]}))
    matrix = tmp_path / 'assays/counts.csv'
    matrix.write_text('gene_id,S1,S2\nF1,10.5,20.7\nF2,12.3,43.1\n')
    (tmp_path / 'assays/samples.tsv').write_text('sample_id\tpatient_id\nS1\tP1\nS2\tP2\n')
    query_store.ensure_query_store(str(tmp_path))
    original_open = Path.open
    reads = []
    class HeaderOnly:
        def __init__(self, handle): self.handle = handle
        def __enter__(self): return self
        def __exit__(self, *args): self.handle.close()
        def readline(self, *args):
            if reads:
                pytest.fail('Scope apply must not read the matrix body')
            reads.append('header')
            return self.handle.readline(*args)
        def __iter__(self): pytest.fail('Scope apply must not iterate matrix values')
        def read(self, *args): pytest.fail('Scope apply must not read matrix values')
        def readlines(self, *args): pytest.fail('Scope apply must not read matrix values')
    def open_header_only(path, *args, **kwargs):
        handle = original_open(path, *args, **kwargs)
        return HeaderOnly(handle) if path == matrix else handle
    monkeypatch.setattr(Path, 'open', open_header_only)
    monkeypatch.setattr(query_store, '_expected_count_summary', lambda *args: pytest.fail('Do not compute discarded summaries'))
    result = scoped_assay_inventory({'one':str(tmp_path)}, [{'dataset_id':'one', 'patient_id':'P1'}])
    assert reads == ['header']
    assert result[0]['feature_count'] is None
    assert result[0]['sample_count'] == result[0]['patient_count'] == 1
    assert result[0]['mean_total_counts_per_sample'] is None
