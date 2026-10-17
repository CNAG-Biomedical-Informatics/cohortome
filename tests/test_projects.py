"""Project resume references remain scoped to the owner and current datasets."""
import copy
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from app import projects


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(projects, 'STATE_ROOT_DIR', tmp_path)
    monkeypatch.setattr(projects, 'require_authenticated', lambda _: {'username':'tester'})
    monkeypatch.setattr(projects, 'request_user_id', lambda _: 'tester')
    monkeypatch.setattr(projects, 'current_dataset_ids', lambda _: ['synthetic'])
    monkeypatch.setattr(projects, 'authorized_datasets_for_user', lambda _: [{'dataset_id':'synthetic'}])
    monkeypatch.setattr(projects, 'effective_query_granularity_ceiling', lambda _: 'detailed')
    monkeypatch.setattr(projects, 'ensure_dataset_query_stores_ready', lambda _: None)
    monkeypatch.setattr(projects, 'fingerprint', lambda _: 'a'*64)
    monkeypatch.setattr(projects, 'list_saved_cohorts', lambda *a, **kw: [{'id':'cohort1'}])
    monkeypatch.setattr(projects, 'list_job_records', lambda _: [])
    monkeypatch.setattr(projects, 'get_analysis_session', lambda identifier, user_id: {'dataset_id':'synthetic'} if identifier == 'session1' else None)
    changes = []
    monkeypatch.setattr(projects, 'set_current_datasets', lambda owner, ids: changes.append((owner, ids)))
    app = FastAPI(); app.include_router(projects.router)
    with TestClient(app) as client:
        yield client, changes


def exported(client):
    response = client.post('/projects/export', json={'name':'Synthetic review', 'analysis_session_id':'session1',
        'conversation':[{'role':'user','text':'Which patients have lupus?'}]})
    assert response.status_code == 200, response.text
    return response.json()


def test_round_trip_is_read_only_until_open_and_contains_no_source_data(client):
    http, changes = client
    project = exported(http)
    assert project['cohort_ids'] == ['cohort1']
    assert 'data_dir' not in project and 'root_path' not in str(project)
    assert http.post('/projects/inspect', json=project).status_code == 200
    assert changes == []
    assert http.post('/projects/open', json=project).status_code == 200
    assert changes == [('tester', ['synthetic'])]


@pytest.mark.parametrize('field,value', [('owner','another-user'), ('installation','other-installation'),
    ('version',1), ('version',999), ('analysis_session_id','missing')])
def test_invalid_project_does_not_switch_workspace(client, field, value):
    http, changes = client
    project = exported(http); project[field] = value
    assert http.post('/projects/open', json=project).status_code in (409,422)
    assert not changes


def test_changed_revoked_and_summary_only_data_are_rejected(client, monkeypatch):
    http, changes = client
    project = exported(http)
    monkeypatch.setattr(projects, 'fingerprint', lambda _: 'b'*64)
    assert http.post('/projects/open', json=project).status_code == 409
    monkeypatch.setattr(projects, 'effective_query_granularity_ceiling', lambda _: 'summary')
    assert http.post('/projects/export', json={'name':'Denied'}).status_code == 403
    monkeypatch.setattr(projects, 'authorized_datasets_for_user', lambda _: [])
    assert http.post('/projects/open', json=project).status_code == 409
    assert not changes


def test_missing_optional_references_are_reported_and_unknown_fields_rejected(client):
    http, changes = client
    project = exported(http); project['run_ids'] = ['deleted-run']
    assert len(http.post('/projects/inspect', json=project).json()['warnings']) == 1
    project['path'] = '/arbitrary/input'
    assert http.post('/projects/open', json=project).status_code == 422
    assert not changes
