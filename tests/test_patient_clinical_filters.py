"""Patient filtering uses complete, dataset-qualified clinical matches."""
import json
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app import cohort_filters, patient_overview, query_store


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(query_store, 'QUERY_STORE_DIR', tmp_path / 'cache')
    monkeypatch.setattr(query_store, 'list_registered_datasets', lambda: [])
    available = []
    for dataset in ('a', 'b'):
        root = tmp_path / dataset
        (root / 'clinical').mkdir(parents=True)
        records = [{
            'id': f'P{i:03}:V1',
            'diseases': [{'diseaseCode': {'id': f'TEST:D{i % 2}',
                                        'label': 'Example' if i % 2 == 0 else 'Other'}}],
            'measures': [{'assayCode': {'id': 'TEST:M1', 'label': 'Marker'},
                          'measurementValue': {'quantity': {'value': i + (10 if dataset == 'b' else 0),
                                                            'unit': {'label': 'mg/L'}}}}],
        } for i in range(32)]
        (root / 'clinical/records.json').write_text(json.dumps(records))
        query_store.ensure_query_store(str(root))
        available.append((dataset, str(root), f'Dataset {dataset}'))
    monkeypatch.setattr(patient_overview, 'sources', lambda *args: available)
    monkeypatch.setattr(patient_overview, 'biosample_records', lambda *args, **kwargs: [
        {'id': f'S{i:03}', 'individualId': f'P{i:03}',
         'sampleOriginType': {'id': 'TEST:BLOOD', 'label': 'Blood'}}
        for i in range(0, 32, 3)])
    monkeypatch.setattr(cohort_filters, 'request_user_id', lambda _: 'test-user')
    app = FastAPI()
    app.include_router(patient_overview.router)
    app.include_router(cohort_filters.router)
    with TestClient(app) as client:
        catalogue = client.get('/cohort-builder/fields', params={'workspace': 'scope'}).json()
        marker = next(f for f in catalogue['fields'] if f['unit'] == 'mg/L')
        body = dict(workspace='scope', fingerprint=catalogue['fingerprint'], filters=[
            dict(field_id=marker['id'], operator='between', values=[5, 29])])
        yield client, body, available


def members(rows):
    return {(row['dataset_id'], row['patient_id']) for row in rows}


def expected_members():
    return {('a', f'P{i:03}') for i in range(5, 30)} | {('b', f'P{i:03}') for i in range(20)}


def test_filter_before_sorted_pagination_and_collect_complete_selection(workspace):
    client, body, _ = workspace
    found = []
    for offset in (0, 20, 40):
        response = client.post('/patient-overview/search', json=body, params={
            'workspace': 'scope', 'sort_by': 'patient_id', 'offset': offset})
        assert response.status_code == 200
        payload = response.json()
        assert payload['total'] == 45
        assert len(payload['matches']) == min(20, 45 - offset)
        assert payload['next'] == ({'offset': offset + 20} if offset < 40 else None)
        found.extend(payload['matches'])
    assert len(found) == len(members(found)) == 45
    assert members(found) == expected_members()
    selection = client.post('/patient-overview/selection', json=body, params={'workspace': 'scope'}).json()
    assert selection['patient_count'] == 45
    assert members(selection['members']) == expected_members()


def test_filter_before_cursor_pagination_preserves_repeated_ids(workspace):
    client, body, _ = workspace
    found = []
    params = {'workspace': 'scope'}
    for _ in range(3):
        response = client.post('/patient-overview/search', json=body, params=params)
        assert response.status_code == 200
        payload = response.json()
        found.extend(payload['matches'])
        params = {'workspace': 'scope', **(payload['next'] or {})}
    assert payload['next'] is None
    assert len(found) == 45
    assert members(found) == expected_members()


def test_clinical_filters_intersect_search_disease_and_origin(workspace):
    client, body, _ = workspace
    params = dict(workspace='scope', q='P01', disease='Example', sample_origin='TEST:BLOOD')
    selection = client.post('/patient-overview/selection', json=body, params=params).json()
    search = client.post('/patient-overview/search', json=body, params={**params, 'sort_by': 'patient_id'}).json()
    expected = {(dataset, pid) for dataset in ('a', 'b') for pid in ('P012', 'P018')}
    assert selection['patient_count'] == search['total'] == 4
    assert members(selection['members']) == members(search['matches']) == expected


def test_empty_filter_result_never_becomes_all_patients(workspace):
    client, body, _ = workspace
    body['filters'][0].update(operator='eq', values=[200])
    assert client.post('/patient-overview/search', json=body,
        params={'workspace': 'scope', 'sort_by': 'patient_id'}).json() == {
            'matches': [], 'total': 0, 'next': None}
    assert client.post('/patient-overview/selection', json=body,
        params={'workspace': 'scope'}).json() == {'members': [], 'patient_count': 0, 'id_type': 'patient'}
    assert client.get('/patient-overview/selection', params={'workspace': 'scope'}).json()['patient_count'] == 64


def test_no_matches_in_one_dataset_never_leaks_same_source_id(workspace):
    client, body, _ = workspace
    body['filters'][0].update(operator='eq', values=[1])
    for endpoint, key in [('search', 'matches'), ('selection', 'members')]:
        response = client.post(f'/patient-overview/{endpoint}', json=body, params={'workspace': 'scope'})
        assert response.status_code == 200
        assert members(response.json()[key]) == {('a', 'P001')}


def test_missing_values_keep_existing_patients_universe(workspace, monkeypatch):
    client, body, _ = workspace
    monkeypatch.setattr(patient_overview, 'sample_inventory',
                        lambda *args, **kwargs: ([{'patient_id': 'ASSAY_ONLY'}], []))
    body['filters'][0].update(operator='is_missing', values=[])
    # Coverage also includes assay-only patients. Patients currently describes
    # clinical patients; its table, total and complete selection must agree.
    search = client.post('/patient-overview/search', json=body,
                         params={'workspace': 'scope', 'sort_by': 'patient_id'}).json()
    selection = client.post('/patient-overview/selection', json=body,
                            params={'workspace': 'scope'}).json()
    assert search['matches'] == selection['members'] == []
    assert search['total'] == selection['patient_count'] == 0


@pytest.mark.parametrize('endpoint', ['search', 'selection'])
def test_patient_filters_reject_stale_sources(workspace, endpoint):
    client, body, available = workspace
    path = Path(available[0][1]) / 'clinical/records.json'
    path.write_text(path.read_text() + ' ')
    response = client.post(f'/patient-overview/{endpoint}', json=body, params={'workspace': 'scope'})
    assert response.status_code == 409
    assert 'changed' in response.json()['detail']


@pytest.mark.parametrize('endpoint', ['search', 'selection'])
def test_patient_filters_validate_workspace_and_body(workspace, endpoint):
    client, body, _ = workspace
    url = f'/patient-overview/{endpoint}'
    assert client.post(url, json=body, params={'workspace': 'different'}).status_code == 422
    assert client.post(url, json={**body, 'sql': 'select anything'}, params={'workspace': 'scope'}).status_code == 422
    assert client.post(url, params={'workspace': 'scope'}).status_code == 422
    body['filters'][0]['field_id'] = 'missing-field'
    assert client.post(url, json=body, params={'workspace': 'scope'}).status_code == 422


@pytest.mark.parametrize('status', [401, 403])
@pytest.mark.parametrize('endpoint', ['search', 'selection'])
def test_patient_filters_reauthorize_every_request(workspace, monkeypatch, endpoint, status):
    client, body, _ = workspace
    def deny(*args):
        raise HTTPException(status, 'Denied')
    monkeypatch.setattr(patient_overview, 'sources', deny)
    assert client.post(f'/patient-overview/{endpoint}', json=body,
                       params={'workspace': 'scope'}).status_code == status
