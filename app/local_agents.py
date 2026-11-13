"""Explicit, temporary Desktop grants for the optional local MCP connector.

The connector never receives the Desktop cookie. Its token authorizes only the
bounded tool dispatcher below, not the ordinary application or approval routes.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
import secrets
import sys
import threading
import time

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from app import cohort_filters, datasets
from app.auth import require_admin
from app.cohort_members import resolve_members, source_inventory
from app.config import BASE_DIR
from app.dataset_sources import dataset_input_signature
from app.query_store import ensure_query_store
from app.user_state import request_user_id

router = APIRouter(prefix='/local-agent', tags=['agents'])
CALL_PATH = '/local-agent/call'
TTL_SECONDS = 8 * 60 * 60
MAX_BODY_BYTES = 256 * 1024
MAX_RESPONSE_BYTES = 1024 * 1024
APPROVAL_PATH = BASE_DIR / 'config/mcp/synthetic_inputs.json'
BUNDLED = {
    'default': ('synthetic-longitudinal-demo', 'Synthetic longitudinal demo'),
    'synthetic-cross-sectional-demo': ('synthetic-cross-sectional-demo', 'Synthetic cross-sectional demo'),
}
logger = logging.getLogger(__name__)
_lock = threading.RLock()
_work_lock = threading.Lock()
_origin = ''
_grant = None
_generation = 0


class Member(BaseModel):
    model_config = ConfigDict(extra='forbid')
    dataset_id: str = Field(min_length=1, max_length=200)
    patient_id: str = Field(min_length=1, max_length=1000)


class Share(BaseModel):
    model_config = ConfigDict(extra='forbid')
    workspace: str = Field(min_length=1, max_length=2000)
    members: list[Member] | None = Field(default=None, max_length=10_000)
    acknowledge: bool = Field(default=False, strict=True)


class ToolCall(BaseModel):
    model_config = ConfigDict(extra='forbid')
    operation: str = Field(max_length=30)
    name: str = Field(default='', max_length=80)
    arguments: dict = Field(default_factory=dict)


class RunDecision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    approve: bool = Field(strict=True)
    allow_results: bool = Field(default=False, strict=True)


@dataclass(frozen=True)
class Grant:
    token_hash: str
    workspace: str
    members: list[dict]
    sources: list[tuple]
    fingerprint: str
    user_id: str
    created: float
    expires: float
    deadline: float
    selection_signature: str = ''


def configure_desktop(origin):
    """Called only by the loopback Desktop launcher, never from HTTP or env."""
    global _origin
    _origin = origin
    _revoke()


def _revoke():
    global _grant, _generation
    with _lock:
        _grant = None
        _generation += 1


def _active():
    with _lock:
        if _grant and time.monotonic() >= _grant.deadline:
            _revoke()
        return _grant


def _owner(request):
    if not _origin or not request.scope.get('state', {}).get('desktop_ui'):
        raise HTTPException(404, 'Local agent sharing is available in Desktop only.')
    user = require_admin(request)
    if user['username'] != 'local':
        raise HTTPException(403, 'Only the Desktop owner can share this scope.')


def _iso(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat()


def _status(grant):
    if grant is None:
        return dict(enabled=False)
    return dict(enabled=True, patient_count=len(grant.members),
                datasets=[dict(dataset_id=key, name=label) for key, _, label in grant.sources],
                created_at=_iso(grant.created), expires_at=_iso(grant.expires),
                selection_signature=grant.selection_signature)


def _connector_command():
    """Installed executable only; never accept a command/path from the client."""
    if not getattr(sys, 'frozen', False):
        return None  # Source developers use the separate SDK environment.
    binary = Path(sys.executable).resolve().parent / 'mcp' / (
        'cohortome-mcp.exe' if sys.platform == 'win32' else 'cohortome-mcp')
    if not binary.is_file():
        raise HTTPException(503, 'The bundled MCP connector is missing. Reinstall COHORTome.')
    return {'command': str(binary), 'args': []}


def _verify_fixture(identifier, root):
    """A synthetic label alone is not proof: verify the bundled file set/content."""
    if identifier not in BUNDLED:
        raise HTTPException(403, 'This prototype shares only the two bundled synthetic demos.')
    expected = BASE_DIR / 'datasets' / BUNDLED[identifier][0]
    if Path(root).resolve() != expected.resolve() or expected.is_symlink():
        raise HTTPException(403, 'This prototype requires unchanged bundled synthetic data.')
    approved = json.loads(APPROVAL_PATH.read_text())[BUNDLED[identifier][0]]
    # Verify paths before reading manifests: a replaced symlink must not make
    # the discovery helper open files outside the approved fixture.
    for name, digest in approved.items():
        path = expected / name
        if (path.resolve() != expected.resolve() / name or not path.is_file()
                or path.stat().st_size > 10 * 1024 * 1024
                or hashlib.sha256(path.read_bytes()).hexdigest() != digest):
            raise HTTPException(403, 'The bundled demo changed. Agent sharing is blocked.')
    # Inspect inputs the application can actually consume, not unrelated files
    # under the source tree (e.g. a developer's ignored backup directory).
    consumed = {entry['name'] for entry in dataset_input_signature(expected)}
    imaging_manifest = 'assays/imaging/dicom_studies.json'
    if (expected / imaging_manifest).exists():
        consumed.add(imaging_manifest)
    if not consumed.issubset(approved):
        raise HTTPException(403, 'The bundled demo changed. Agent sharing is blocked.')


def _approved_sources(request, workspace):
    # Reject unapproved IDs before opening any source files, including when a
    # real dataset has been given a synthetic-looking name or description.
    ids = datasets.parse_scope_dataset_ids(workspace)
    if not ids or any(key not in BUNDLED for key in ids):
        raise HTTPException(403, 'Select only bundled synthetic demos before sharing.')
    sources = []
    for key in datasets.resolve_dataset_ids(request, workspace):
        item = datasets.get_dataset(key)
        if (not item or item.get('data_classification') != 'public'
                or item.get('query_granularity_ceiling') != 'detailed'
                or item.get('ai_provider_access') != 'detailed_allowed'):
            raise HTTPException(403, 'Dataset policy does not allow detailed agent access.')
        root = item['root_path']
        _verify_fixture(key, root)
        from app.dicom_files import index_path
        if index_path(root).exists():
            # A real DICOM folder linked to a demo overrides its bundled
            # studies at runtime. Do not read or share that external index.
            raise HTTPException(403, 'Unlink added imaging data before sharing this synthetic demo.')
        ensure_query_store(root)
        sources.append((key, root, BUNDLED[key][1]))
    _verify_scope_cache(sources)
    return sources


def _verify_scope_cache(sources):
    if len(sources) < 2:
        return
    root = Path(datasets.materialize_dataset_scope([key for key, _, _ in sources]))
    expected = {f'{key}__{path.name}': path.resolve() for key, source, _ in sources
                for pattern in ('*.json', '*.json.gz')
                for path in (Path(source) / 'clinical').glob(pattern)}
    actual = {path.name: path.resolve() for pattern in ('*.json', '*.json.gz')
              for path in (root / 'clinical').glob(pattern)}
    if actual != expected:
        raise HTTPException(409, 'The combined demo cache changed. Reload the workspace before sharing.')


@router.get('/status')
def status(request: Request):
    _owner(request)
    return JSONResponse(_status(_active()), headers={'Cache-Control': 'no-store'})


@router.delete('/share')
def revoke(request: Request):
    _owner(request)
    _revoke()
    logger.info('Local agent access revoked')
    return JSONResponse(dict(enabled=False), headers={'Cache-Control': 'no-store'})


@router.get('/plans')
def pending_plans(request: Request):
    _owner(request)
    from app.local_agent_runs import pending
    with _lock:
        return JSONResponse({'plans': pending(_active(), owner=True)}, headers={'Cache-Control':'no-store'})


@router.post('/plans/{plan_id}')
def decide_plan(plan_id: str, body: RunDecision, request: Request):
    _owner(request)
    from app.local_agent_runs import decide
    if not _work_lock.acquire(blocking=False):
        raise HTTPException(429, 'An agent request is running. Try again shortly.')
    try:
        with _lock:
            grant = _active()
            if grant is None:
                raise HTTPException(409, 'Agent access is off or expired.')
            result = decide(plan_id, grant, request, approve=body.approve, allow_results=body.allow_results)
        return JSONResponse(result, headers={'Cache-Control':'no-store'})
    finally:
        _work_lock.release()


@router.post('/share')
def share(body: Share, request: Request):
    return _share(body, request, update=False)


@router.put('/share')
def update_share(body: Share, request: Request):
    return _share(body, request, update=True)


def _share(body: Share, request: Request, *, update):
    global _grant
    _owner(request)
    if not body.acknowledge:
        raise HTTPException(422, 'Confirm that the agent may receive the selected synthetic data.')
    connector = _connector_command()
    if not _work_lock.acquire(blocking=False):
        raise HTTPException(429, 'An agent request is running. Try again shortly.')
    try:
        previous = _active() if update else None
        if update and previous is None:
            raise HTTPException(409, 'Access expired or was turned off. Enable sharing again.')
        # Scope updates are atomic: failures retain the previous snapshot. A
        # new connection explicitly rotates credentials and revokes the old one.
        if not update:
            _revoke()
        with _lock:
            generation = _generation
        sources = _approved_sources(request, body.workspace)
        workspace = datasets.dataset_scope_id([key for key, _, _ in sources])
        before = cohort_filters._fingerprint(sources, request_user_id(request))
        roots = {key: root for key, root, _ in sources}
        if body.members is None:
            members = [dict(dataset_id=key, patient_id=pid) for key, root in roots.items()
                       for pid in sorted(source_inventory(root)[0])]
        elif not body.members:
            members = []  # Empty never means the whole workspace.
        else:
            members = [dict(dataset_id=m['dataset_id'], patient_id=m['patient_id']) for m in
                       resolve_members(roots, members=[m.model_dump() for m in body.members])]
        if len(members) > 10_000:
            raise HTTPException(422, 'This prototype supports at most 10,000 shared patients.')
        if before != cohort_filters._fingerprint(sources, request_user_id(request)):
            raise HTTPException(409, 'The dataset changed. Apply the scope again before sharing.')
        token = None if update else secrets.token_urlsafe(32)
        now = time.time()
        selection = [body.workspace, None if body.members is None else
                     sorted({(m.dataset_id, m.patient_id) for m in body.members})]
        signature = hashlib.sha256(json.dumps(selection, ensure_ascii=False,
                                   separators=(',', ':')).encode()).hexdigest()
        grant = Grant(previous.token_hash if update else hashlib.sha256(token.encode()).hexdigest(),
                      workspace, members, sources, before, request_user_id(request),
                      previous.created if update else now,
                      previous.expires if update else now + TTL_SECONDS,
                      previous.deadline if update else time.monotonic() + TTL_SECONDS, signature)
        with _lock:
            if generation != _generation or (update and _active() is not previous):
                raise HTTPException(409, 'Sharing was cancelled. Try again when ready.')
            _grant = grant
        logger.info('Local agent scope shared: %d datasets, %d synthetic patients', len(sources), len(members))
        credentials = {} if update else {'url': _origin + CALL_PATH, 'token': token,
                                         'connector': connector}
        return JSONResponse({**_status(grant), **credentials},
                            headers={'Cache-Control': 'no-store', 'Pragma': 'no-cache'})
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(409, 'Unable to share this scope. Check that the bundled demo stores are ready.') from None
    finally:
        _work_lock.release()


def _authenticate(request):
    grant = _active()
    auth = request.headers.get('authorization', '')
    if not auth.startswith('Bearer ') or len(auth) > 256:
        raise HTTPException(401, 'Enable sharing in COHORTome and configure its connection token.')
    candidate = hashlib.sha256(auth[7:].encode()).hexdigest()
    if grant is None or not secrets.compare_digest(candidate, grant.token_hash):
        raise HTTPException(401, 'Agent access expired or was revoked. Share the scope again.')
    return grant


def _validate_grant(grant, request):
    if _active() is not grant:
        raise HTTPException(401, 'Agent access expired or was revoked.')
    sources = _approved_sources(request, grant.workspace)
    if (sources != grant.sources or request_user_id(request) != grant.user_id
            or cohort_filters._fingerprint(sources, grant.user_id) != grant.fingerprint):
        raise HTTPException(409, 'The shared dataset changed. Share the scope again.')


def _dispatch(body, grant, request):
    from app.local_agent_tools import TOOL_DEFINITIONS, execute_tool
    if not _work_lock.acquire(blocking=False):
        raise HTTPException(429, 'An agent request is running. Try again shortly.')
    started = time.monotonic()
    outcome = 'failed'
    try:
        _validate_grant(grant, request)
        if body.operation == 'list_tools' and not body.name and not body.arguments:
            result = dict(tools=TOOL_DEFINITIONS)
        elif body.operation == 'call_tool':
            result = dict(result=execute_tool(body.name, body.arguments, grant, request))
        else:
            raise HTTPException(422, 'Unknown agent operation.')
        _validate_grant(grant, request)  # Revoke/expiry/source changes also discard in-flight results.
        if len(json.dumps(result, allow_nan=False).encode()) > MAX_RESPONSE_BYTES:
            raise HTTPException(422, 'The result is too large. Narrow the filters or request a smaller page.')
        outcome = 'ok'
        return result
    finally:
        _work_lock.release()
        # No prompts, IDs, arguments, paths, tokens or returned values in logs.
        known = {entry['name'] for entry in TOOL_DEFINITIONS}
        name = body.name if body.name in known else 'list_tools' if body.operation == 'list_tools' else 'unknown'
        logger.info('Local agent tool=%s status=%s elapsed_ms=%d', name, outcome,
                    int((time.monotonic() - started) * 1000))


async def agent_endpoint(scope, receive, send):
    """Separate ASGI gate; deliberately never passes through LocalOwner/auth-none."""
    request = Request(scope, receive)
    try:
        if (not _origin or request.url.path != CALL_PATH or request.method != 'POST'
                or request.client is None or request.client.host != '127.0.0.1'
                or request.headers.get('host') != _origin.removeprefix('http://')
                or request.headers.get('origin') is not None or request.url.query):
            raise HTTPException(403, 'Only the local connector may use this endpoint.')
        grant = _authenticate(request)
        if request.headers.get('content-type', '').split(';', 1)[0] != 'application/json':
            raise HTTPException(415, 'Send application/json.')
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > MAX_BODY_BYTES:
                raise HTTPException(413, 'Agent request is too large.')
        body = ToolCall.model_validate_json(bytes(raw))
        # No caller-supplied cookies/user headers reach application helpers.
        # This internal identity is created only AFTER validating the grant.
        internal = Request({'type': 'http', 'method': 'POST', 'path': CALL_PATH,
                            'headers': [], 'query_string': b'',
                            'session': {'username': 'local', 'role': 'admin'}})
        result = await run_in_threadpool(_dispatch, body, grant, internal)
        response = JSONResponse(result)
    except HTTPException as error:
        # Only boundary-owned error text, never lower-level paths or data values.
        messages = {401: 'Agent access is disabled, expired or revoked. Share the scope in COHORTome.',
                    403: 'Agent access denied. Check the shared scope and dataset policy.',
                    409: 'The shared data are unavailable or changed. Share the scope again.',
                    413: 'Agent request is too large.', 415: 'Send application/json.',
                    422: 'Invalid tool request. Check the tool schema and use smaller pages.',
                    429: 'An agent request is running. Try again shortly.'}
        response = JSONResponse({'detail': messages.get(error.status_code, 'Agent request failed.')},
                                status_code=error.status_code)
    except (ValidationError, ValueError):
        response = JSONResponse({'detail': 'Invalid tool request. Check the tool schema.'}, status_code=422)
    except Exception:
        response = JSONResponse({'detail': 'Agent request failed. Check the shared demo stores.'}, status_code=409)
    response.headers['Cache-Control'] = 'no-store'
    await response(scope, receive, send)
