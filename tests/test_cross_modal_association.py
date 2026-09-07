import json

import duckdb
import pytest

from app import query_store
from app.multimodal import cross_modal_association, _spearman
from scripts.generate_synthetic_autoimmune_demo import build


@pytest.fixture
def demo(tmp_path, monkeypatch):
    root = tmp_path / 'demo'
    build(root)
    db = tmp_path / 'demo.duckdb'
    query_store._build_query_store(str(root), db, tmp_path / 'meta.json', {})
    monkeypatch.setattr(query_store, 'ensure_query_store', lambda _: None)
    monkeypatch.setattr(query_store, '_connect', lambda _: duckdb.connect(str(db), read_only=True))
    return root


def parameters():
    return dict(assay_x='synthetic_autoimmune_flow_cytometry', feature_x='CD4_T_cells_fraction',
                assay_y='synthetic_autoimmune_serology', feature_y='CRP_mg_L')


def test_feature_discovery_names_descriptions_and_units(demo):
    assay = 'synthetic_autoimmune_serology'
    assert query_store.assay_feature_inventory(str(demo), assay, 'C-reactive') == ['CRP_mg_L']
    assert 'CRP_mg_L' in query_store.assay_feature_inventory(str(demo), assay, 'demonstration')
    assert query_store.assay_feature_inventory(str(demo), assay, 'mg/L') == ['CRP_mg_L']
    annotation = query_store.assay_feature_annotations(['CRP_mg_L'], str(demo), assay)['CRP_mg_L']
    assert annotation['unit'] == 'mg/L'
    assert annotation['label'] == 'C-reactive protein (CRP)'
    assert query_store.assay_feature_annotations(['CRP_mg_L'], str(demo), 'synthetic_autoimmune_methylation') == {}
    assert query_store.assay_feature_annotations(['SYNCPG0001'], str(demo), 'synthetic_autoimmune_methylation') == {}


def test_real_demo_association(demo):
    result = cross_modal_association(str(demo), parameters())
    assert 3 <= result['counts']['matched_patients'] <= 81
    assert sum(group['n'] for group in result['groups']) == len(result['points'])
    assert -1 <= result['spearman_rho'] <= 1
    assert all(len(item['sha256']) == 64 for item in result['provenance'])
    assert result['counts']['shared_samples'] == (result['counts']['matched_patients'] + result['counts']['missing_pairs'])
    json.dumps(result, allow_nan=False)
    scope = ','.join(point['patient_id'] for point in result['points'][:5])
    assert cross_modal_association(str(demo), parameters(), scope)['counts']['matched_patients'] == 5


def test_association_rejects_invalid_inputs(demo):
    params = parameters()
    params['feature_x'] = 'not-present'
    with pytest.raises(ValueError, match='not found'):
        cross_modal_association(str(demo), params)
    with pytest.raises(ValueError, match='at least 3'):
        cross_modal_association(str(demo), parameters(), 'missing-person')


def test_spearman_ties_and_constant():
    assert _spearman([dict(x=v, y=v) for v in [1, 1, 3, 4]]) == pytest.approx(1)
    assert _spearman([dict(x=v, y=-v) for v in [1, 1, 3, 4]]) == pytest.approx(-1)
    assert _spearman([dict(x=1, y=v) for v in [1, 2, 3]]) is None


def test_summary_access_rejected_before_reading(monkeypatch):
    from app.analysis import analysis_llm_reply
    with pytest.raises(RuntimeError, match='Detailed'):
        analysis_llm_reply('Compare measurements: ' + json.dumps(parameters()), 'unused', granularity_ceiling='summary')


def test_dataset_imaging_trait(demo):
    from app.datasets import dataset_content_metadata
    assert dataset_content_metadata(str(demo))['has_imaging'] is False
    imaging = demo / 'assays/imaging'
    imaging.mkdir()
    (imaging / 'dicom_studies.json').write_text('{"studies": []}')
    assert dataset_content_metadata(str(demo))['has_imaging'] is False
    (imaging / 'dicom_studies.json').write_text('{"studies": [{"study_id": "synthetic"}]}')
    assert dataset_content_metadata(str(demo))['has_imaging'] is True


def test_matching_drops_repeats_bad_links_and_missing(monkeypatch):
    from app import multimodal
    ids = ['a', 'b', 'c', 'd', 'bad', 'missing']
    links = dict(zip(ids, ['p1', 'p1', 'p2', 'p3', 'p4', 'p5']))
    def feature(_, assay, __):
        values = dict(zip(ids, [1, 2, 3, 4, 5, None]))
        current = dict(links)
        if assay == 'y':
            current['bad'] = 'wrong'
        return {'modality': assay}, values, current, 'f' * 64
    monkeypatch.setattr(multimodal, '_association_feature', feature)
    monkeypatch.setattr(multimodal, '_workspace_dataset_ids', lambda _: [])
    monkeypatch.setattr(multimodal, 'clinical_workspace_inventory', lambda _: {'samples': [
        dict(sample_id=sid, patient_id=links[sid], event_date=f'2025-01-0{i+1}') for i, sid in enumerate(ids)]})
    monkeypatch.setattr(query_store, 'patient_query_index', lambda _: [])
    result = multimodal.cross_modal_association('fixture', dict(assay_x='x', assay_y='y', feature_x='x', feature_y='y'))
    assert result['counts']['invalid_linkage'] == 1
    assert result['counts']['missing_pairs'] == 1
    assert result['counts']['repeated_observations'] == 1
    assert [point['sample_id'] for point in result['points']] == ['a', 'c', 'd']
