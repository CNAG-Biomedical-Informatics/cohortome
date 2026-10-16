import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app import query_sessions, routes
from app.schemas import QuerySessionRequest


@pytest.fixture
def setup(monkeypatch, tmp_path):
    monkeypatch.setattr(query_sessions, 'USER_STATE_ROOT', tmp_path)
    monkeypatch.setattr(routes, 'require_authenticated', lambda request: None)
    monkeypatch.setattr(routes, 'request_user_id', lambda request: request.scope['user_id'])
    monkeypatch.setattr(routes, 'resolve_dataset_ids', lambda request, key: [key])
    monkeypatch.setattr(routes, 'resolve_dataset_dir', lambda request, key: 'synthetic')
    monkeypatch.setattr(routes, 'dataset_scope_id', lambda ids: ','.join(ids))
    monkeypatch.setattr(routes, 'effective_query_granularity_ceiling', lambda ids: 'detailed')
    monkeypatch.setattr(routes, 'workspace_fingerprint_for_data_dir', lambda *args, **kwargs: {'token': 'original'})
    return Request({'type': 'http', 'user_id': 'alice'})


def test_user_ownership_roundtrip_and_conflict(setup):
    payload = QuerySessionRequest(id='chat1', dataset_id='default', title='My chat',
                                  turns=[{'role': 'user', 'prompt': 'List patients', 'contextMode': 'workspace'}])
    saved = routes.save_query_session(payload, setup)
    assert saved['revision'] == 1
    assert routes.get_query_session('chat1', setup)['turns'] == payload.turns
    bob = Request({'type': 'http', 'user_id': 'bob'})
    assert routes.get_query_sessions(bob)['sessions'] == []
    with pytest.raises(HTTPException) as error:
        routes.get_query_session('chat1', bob)
    assert error.value.status_code == 404
    with pytest.raises(HTTPException) as error:
        routes.save_query_session(payload, setup)
    assert error.value.status_code == 409
    renamed = routes.save_query_session(payload.model_copy(update={'revision': 1, 'title': 'Renamed'}), setup)
    assert renamed['title'] == 'Renamed'
    assert routes.remove_query_session('chat1', setup)['deleted']
    assert routes.get_query_sessions(setup)['sessions'] == []


def test_recheck_source_access_and_disclosure(setup, monkeypatch):
    routes.save_query_session(QuerySessionRequest(id='chat1', dataset_id='default', title='Sensitive title'), setup)
    monkeypatch.setattr(routes, 'effective_query_granularity_ceiling', lambda ids: 'summary')
    assert routes.get_query_sessions(setup)['sessions'] == []
    with pytest.raises(HTTPException) as error:
        routes.get_query_session('chat1', setup)
    assert error.value.status_code == 403
    def denied(*args):
        raise HTTPException(status_code=403, detail='Access revoked')
    monkeypatch.setattr(routes, 'resolve_dataset_ids', denied)
    assert routes.get_query_sessions(setup)['sessions'] == []
    with pytest.raises(HTTPException):
        routes.save_query_session(QuerySessionRequest(id='chat1', dataset_id='default', revision=1), setup)


def test_original_workspace_cannot_be_rebound(setup, monkeypatch):
    routes.save_query_session(QuerySessionRequest(id='chat1', dataset_id='default'), setup)
    monkeypatch.setattr(routes, 'workspace_fingerprint_for_data_dir', lambda *args, **kwargs: {'token': 'changed'})
    assert routes.get_query_session('chat1', setup)['workspace_status']['state'] == 'stale'
    saved = routes.save_query_session(QuerySessionRequest(id='chat1', dataset_id='default', revision=1), setup)
    assert saved['workspace_fingerprint']['token'] == 'original'
    with pytest.raises(HTTPException) as error:
        routes.save_query_session(QuerySessionRequest(id='chat1', dataset_id='other', revision=2), setup)
    assert error.value.status_code == 409


def test_general_only_chat_needs_no_dataset_but_cannot_add_unbound_workspace_turns(setup):
    payload = QuerySessionRequest(id='general', context_mode='general', turns=[{'role': 'user', 'contextMode': 'general', 'prompt': 'Hello'}])
    routes.save_query_session(payload, setup)
    assert routes.get_query_session('general', setup)['workspace_status']['state'] == 'current'
    with pytest.raises(HTTPException) as error:
        routes.save_query_session(payload.model_copy(update={'revision': 1, 'turns': [{'role': 'user', 'contextMode': 'workspace'}]}), setup)
    assert error.value.status_code == 400


def test_logout_without_auth_is_noop(monkeypatch):
    monkeypatch.setattr(routes, 'auth_enabled', lambda: False)
    monkeypatch.setattr(routes, 'get_auth_status', lambda request: {'authenticated': True})
    request = Request({'type': 'http', 'session': {'username': 'local'}})
    assert routes.logout_local(request)['authenticated'] is True
    assert request.session['username'] == 'local'
