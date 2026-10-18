"""Pheno-Ranker conversations; generated artifacts remain owned by run history."""
import json
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from app import query_sessions as store
from app.auth import require_authenticated
from app.user_state import request_user_id
from app.datasets import resolve_dataset_ids, resolve_dataset_dir, dataset_scope_id
from app.routes import (_require_detailed_assay_access, _analysis_session_workspace_status,
                        workspace_fingerprint_for_data_dir)

router = APIRouter(prefix='/pheno-sessions', tags=['pheno-ranker'])


class PhenoChat(BaseModel):
    id: str = Field(min_length=1, max_length=100, pattern=r'^[A-Za-z0-9_-]+$')
    revision: int = Field(default=0, ge=0)
    title: str = Field(default='New chat', max_length=200)
    title_custom: bool = False
    dataset_id: str = Field(min_length=1, max_length=2000)
    setup: dict = Field(default_factory=dict)
    turns: list[dict] = Field(default_factory=list, max_length=200)


def access(request, item):
    _require_detailed_assay_access(request, item['dataset_id'], '')


@router.get('')
def listing(request: Request):
    require_authenticated(request)
    items = []
    for item in store.list_sessions(request_user_id(request), 'pheno'):
        try:
            access(request, item)
        except HTTPException:
            continue
        items.append({key: item.get(key) for key in ('id', 'title', 'dataset_id', 'updated_at')})
    return {'sessions': items}


@router.get('/{session_id}')
def get(session_id: str, request: Request):
    require_authenticated(request)
    item = store.get_session(request_user_id(request), session_id, 'pheno')
    if not item:
        raise HTTPException(404, 'Pheno-Ranker chat not found.')
    access(request, item)
    return dict(item, workspace_status=_analysis_session_workspace_status(item, request))


@router.post('')
def save(payload: PhenoChat, request: Request):
    require_authenticated(request)
    item = payload.model_dump()
    if len(json.dumps(item).encode()) > 2_000_000:
        raise HTTPException(413, 'Chat is too large. Start a new chat.')
    access(request, item)
    user = request_user_id(request)
    old = store.get_session(user, payload.id, 'pheno')
    if old:
        access(request, old)
        if old['dataset_id'] != payload.dataset_id:
            raise HTTPException(409, 'A chat cannot change its original workspace.')
        item['workspace_fingerprint'] = old.get('workspace_fingerprint', {})
    else:
        ids = resolve_dataset_ids(request, payload.dataset_id)
        item['dataset_id'] = dataset_scope_id(ids)
        item['workspace_fingerprint'] = workspace_fingerprint_for_data_dir(
            resolve_dataset_dir(request, payload.dataset_id), dataset_id=item['dataset_id'], dataset_ids=ids)
    try:
        return store.save_session(user, item, 'pheno')
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.delete('/{session_id}')
def delete(session_id: str, request: Request):
    require_authenticated(request)
    if not store.delete_session(request_user_id(request), session_id, 'pheno'):
        raise HTTPException(404, 'Pheno-Ranker chat not found.')
    return {'deleted': True}
