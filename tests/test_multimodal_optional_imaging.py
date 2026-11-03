import app.multimodal as multimodal


def test_imaging_categories_require_actual_inputs(monkeypatch):
    monkeypatch.setattr(multimodal, 'clinical_workspace_inventory', lambda _: {
        'patient_ids': ['P1'], 'sample_ids': ['S1']})
    assays, studies = [], []
    monkeypatch.setattr(multimodal, 'assay_dataset_inventory', lambda _: assays)
    monkeypatch.setattr(multimodal, 'dicom_studies', lambda _: studies)
    result = multimodal.multimodal_readiness('unused')
    assert [m['key'] for m in result['modalities']] == ['clinical']
    assert not result['pairwise_overlaps']
    assays.append({'modality': 'imaging', 'patient_ids': ['P1'], 'sample_ids': ['S1'], 'feature_count': 2})
    result = multimodal.multimodal_readiness('unused')
    assert {m['key'] for m in result['modalities']} == {'clinical', 'imaging'}
    studies.append({'patient_id': 'P1', 'sample_id': 'S1'})
    result = multimodal.multimodal_readiness('unused')
    assert {m['key'] for m in result['modalities']} == {'clinical', 'imaging', 'dicom'}
