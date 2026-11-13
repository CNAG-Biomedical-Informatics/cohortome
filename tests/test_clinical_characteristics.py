import json

from app import query_store
from app.clinical_characteristics import characteristics
from app.cohort_filters import _catalogue


def test_patient_weighting_missingness_and_dataset_selection(tmp_path, monkeypatch):
    monkeypatch.setattr(query_store, 'QUERY_STORE_DIR', tmp_path / 'cache')
    monkeypatch.setattr(query_store, 'list_registered_datasets', lambda: [])
    sources = []
    for dataset in ['a', 'b']:
        root = tmp_path / dataset
        (root / 'clinical').mkdir(parents=True)
        (root / 'clinical/data.json').write_text(json.dumps([
            {'id':'P1:V1', 'info':{'age':20}, 'ethnicity':{'label':'A'}},
            {'id':'P1:V2', 'info':{'age':30}, 'ethnicity':{'label':'A'}},
            {'id':'P2:V1', 'info':{'age':40}, 'ethnicity':{'label':'B'}},
            {'id':'P3:V1'},
        ]))
        query_store.ensure_query_store(str(root))
        sources.append((dataset, str(root), dataset))
    result = characteristics(sources)
    assert len(result) == 2
    for dataset in result:
        age = next(row for row in dataset['rows'] if row['kind'] == 'number')
        assert age['median'] == 32.5  # median of patient medians 25 and 40
        assert age['recorded'] == 2 and age['missing'] == 1
        ethnicity = next(row for row in dataset['rows'] if row['label'] == 'Ethnicity')
        assert ethnicity['categories'] == [{'label':'A','count':1}, {'label':'B','count':1}]
    selected = characteristics(sources, [{'dataset_id':'a','patient_id':'P1'}])
    assert [dataset['patients'] for dataset in selected] == [1, 0]
    fields = _catalogue(sources)
    assert all(field['label'] == 'Age at recorded visit' for field in fields.values() if field.get('is_recorded_age'))
