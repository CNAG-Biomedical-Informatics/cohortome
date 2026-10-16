import pytest
from fastapi import HTTPException
from starlette.requests import Request
from app import pheno_sessions as chats, query_sessions as store


@pytest.fixture
def setup(monkeypatch, tmp_path):
    monkeypatch.setattr(store, 'USER_STATE_ROOT', tmp_path)
    monkeypatch.setattr(chats, 'require_authenticated', lambda _: None)
    monkeypatch.setattr(chats, 'request_user_id', lambda r: r.scope['user_id'])
    monkeypatch.setattr(chats, '_require_detailed_assay_access', lambda *a: ['default'])
    monkeypatch.setattr(chats, 'resolve_dataset_ids', lambda r,k: [k])
    monkeypatch.setattr(chats, 'resolve_dataset_dir', lambda *a: 'synthetic')
    monkeypatch.setattr(chats, 'workspace_fingerprint_for_data_dir', lambda *a, **k: {'token':'original'})
    monkeypatch.setattr(chats, '_analysis_session_workspace_status', lambda *a: {'state':'current'})
    return Request({'type':'http', 'user_id':'alice'})


def test_pheno_chat_roundtrip_namespace_conflict_and_ownership(setup):
    payload = chats.PhenoChat(id='same', dataset_id='default', setup={'mode':'cohort'},
                             turns=[{'kind':'result','payload':{'job_id':'synthetic-run'}}])
    saved = chats.save(payload, setup)
    assert saved['revision'] == 1
    assert chats.get('same', setup)['turns'] == payload.turns
    assert not store.list_sessions('alice')  # Query conversations stay independent.
    bob = Request({'type':'http','user_id':'bob'})
    assert chats.listing(bob) == {'sessions':[]}
    with pytest.raises(HTTPException) as e: chats.get('same', bob)
    assert e.value.status_code == 404
    with pytest.raises(HTTPException) as e: chats.save(payload, setup)
    assert e.value.status_code == 409
    assert chats.delete('same', setup)['deleted']


def test_permissions_rechecked_and_workspace_binding_preserved(setup, monkeypatch):
    payload=chats.PhenoChat(id='a',dataset_id='default')
    chats.save(payload,setup)
    with pytest.raises(HTTPException) as e:
        chats.save(payload.model_copy(update={'revision':1,'dataset_id':'other'}),setup)
    assert e.value.status_code == 409
    def denied(*a): raise HTTPException(403,'Access revoked')
    monkeypatch.setattr(chats,'_require_detailed_assay_access',denied)
    assert chats.listing(setup) == {'sessions':[]}
    with pytest.raises(HTTPException): chats.get('a',setup)
    with pytest.raises(HTTPException): chats.save(payload,setup)
