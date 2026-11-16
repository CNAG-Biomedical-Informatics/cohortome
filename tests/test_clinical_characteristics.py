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
        assert sum(bin['count'] for bin in age['distribution']) == 2
        assert age['distribution'][0]['low'] == 25
        assert age['distribution'][-1]['high'] == 40
        assert age['field_id']
        ethnicity = next(row for row in dataset['rows'] if row['label'] == 'Ethnicity')
        assert ethnicity['categories'] == [{'label':'A','count':1}, {'label':'B','count':1}]
    selected = characteristics(sources, [{'dataset_id':'a','patient_id':'P1'}])
    assert [dataset['patients'] for dataset in selected] == [1, 0]
    assert [dataset['chart_summary']['totals']['patients'] for dataset in result] == [3, 3]
    assert [dataset['chart_summary']['totals']['patients'] for dataset in selected] == [1, 0]
    assert selected[0]['chart_summary']['visit_distribution'] == {'2-4': 1}
    assert selected[1]['chart_summary']['sex_counts'] == {}
    selected_age = next(row for row in selected[0]['rows'] if row['kind'] == 'number')
    assert selected_age['distribution'] == [dict(low=25, high=25, count=1)]
    empty_age = next(row for row in selected[1]['rows'] if row['kind'] == 'number')
    assert empty_age['distribution'] == []
    assert all('patients' not in dataset['chart_summary'] for dataset in result)
    fields = _catalogue(sources)
    assert all(field['label'] == 'Age at recorded visit' for field in fields.values() if field.get('is_recorded_age'))


def test_histogram_boundaries_and_bounded_output():
    from app.clinical_characteristics import _distribution
    assert _distribution([]) == []
    assert _distribution([0, 0]) == [dict(low=0, high=0, count=2)]
    bins = _distribution([-2, -1, 0, 1, 2])
    assert sum(b['count'] for b in bins) == 5
    assert bins[0]['low'] == -2 and bins[-1]['high'] == 2
    bins = _distribution(list(range(1000)))
    assert len(bins) == 20 and sum(b['count'] for b in bins) == 1000
    assert _distribution([-1e308, 1e308]) == []
