import json

from app import patient_overview as overview
from app import bff


def test_workspace_timeline_preserves_duplicate_ids_and_assay_only_patients(monkeypatch):
    monkeypatch.setattr(overview, 'sources', lambda *_: [('alpha', 'alpha', 'Alpha'), ('beta', 'beta', 'Beta')])
    monkeypatch.setattr(overview, 'ensure_query_store', lambda _: None)
    monkeypatch.setattr(bff, 'dashboard_summary', lambda root: dict(timelines=[
        dict(patient_id='P1', events=[dict(visit_id=root)], visit_count=1)]))
    monkeypatch.setattr(overview, 'sample_inventory', lambda root, **_: ([
        dict(patient_id='P1', sample_id='S1', modality='proteomics', collection_date=''),
        dict(patient_id='ONLY_ASSAY', sample_id='S2', modality='proteomics', collection_date='')
    ], []))
    payload = overview.timeline(None, 'scope--alpha--beta')
    assert [json.loads(row['patient_id']) for row in payload['timelines']] == [
        ['alpha', 'P1'], ['alpha', 'ONLY_ASSAY'], ['beta', 'P1'], ['beta', 'ONLY_ASSAY']]
    assert payload['timelines'][0]['samples'][0]['collection_date'] == ''
    assert payload['timelines'][1]['events'] == []
    assert payload['timelines'][2]['events'][0]['visit_id'] == 'beta'


def test_inventory_reads_all_links_without_matrix_values(tmp_path):
    assays = tmp_path / 'assays'
    assays.mkdir()
    (assays / 'matrix.csv').write_text('feature_id;S1;S2;ORPHAN\nnot matrix values\n')
    (assays / 'metadata.tsv').write_text('sample_id\tpatient_id\tcollection_date\nS1\tP1\t2025-01-01\nS2\tP2\t\n')
    manifest = dict(assay_id='protein', modality='proteomics', file='assays/matrix.csv',
                    sample_metadata_file='assays/metadata.tsv')
    (assays / 'manifest.json').write_text(json.dumps({'assays':[manifest]}))
    rows, warnings = overview.sample_inventory(tmp_path, include_imaging=True)
    assert [r['patient_id'] for r in rows] == ['P1', 'P2']
    assert [r['collection_date'] for r in rows] == ['2025-01-01', '']
    assert len(warnings) == 1
    # An undeclared naming convention must not invent patient links.
    manifest.pop('sample_metadata_file')
    (assays / 'manifest.json').write_text(json.dumps({'assays':[manifest]}))
    assert overview.sample_inventory(tmp_path, include_imaging=True)[0] == []
