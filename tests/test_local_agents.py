"""The MCP connector cannot obtain normal Desktop authority or widen its grant."""
import hashlib
import json
from pathlib import Path

import pytest
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient

from app import local_agents as agents


def owner_request():
    return Request({'type': 'http', 'method': 'POST', 'path': '/local-agent/share',
                    'headers': [], 'state': {'desktop_ui': True},
                    'session': {'username': 'local', 'role': 'admin'}})


@pytest.fixture
def isolated(monkeypatch):
    agents.configure_desktop('http://127.0.0.1:45678')
    monkeypatch.setattr(agents, 'require_admin', lambda _: {'username': 'local'})
    monkeypatch.setattr(agents, '_approved_sources', lambda *_: [('default', '/fixture', 'Demo')])
    monkeypatch.setattr(agents.cohort_filters, '_fingerprint', lambda *_: 'a' * 64)
    monkeypatch.setattr(agents, 'source_inventory', lambda _: ({'P1', 'P2'}, {}))
    monkeypatch.setattr(agents, 'resolve_members', lambda _, members: members)
    yield owner_request()
    agents.configure_desktop('')


def share(request, members=None):
    response = agents.share(agents.Share(workspace='default', members=members, acknowledge=True), request)
    assert response.headers['cache-control'] == 'no-store'
    return json.loads(response.body)


@pytest.fixture
def connector():
    async def gate(scope, receive, send):
        if scope['type'] == 'http':
            scope['client'] = ('127.0.0.1', 43210)
        await agents.agent_endpoint(scope, receive, send)
    # No lifespan protocol: this is the launcher's narrow ASGI gate, not FastAPI.
    return TestClient(gate, base_url='http://127.0.0.1:45678')


def test_disabled_and_invalid_tokens(isolated, connector):
    assert json.loads(agents.status(isolated).body) == {'enabled': False}
    response = connector.post(agents.CALL_PATH, json={'operation': 'list_tools'})
    assert response.status_code == 401
    result = share(isolated)
    assert 'token' not in json.loads(agents.status(isolated).body)
    assert agents._grant.token_hash == hashlib.sha256(result['token'].encode()).hexdigest()
    assert connector.post(agents.CALL_PATH, json={'operation': 'list_tools'},
                          headers={'Authorization': 'Bearer wrong'}).status_code == 401


@pytest.mark.parametrize('platform,name', [('darwin', 'cohortome-mcp'), ('linux', 'cohortome-mcp'),
                                         ('win32', 'cohortome-mcp.exe')])
def test_bundled_connector_path_is_owned_by_installation(isolated, tmp_path, monkeypatch, platform, name):
    engine = tmp_path / 'installed app' / 'engine'
    binary = engine / 'mcp' / name
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b'fictional executable')
    monkeypatch.setattr(agents.sys, 'frozen', True, raising=False)
    monkeypatch.setattr(agents.sys, 'executable', str(engine / 'cohortome-backend'))
    monkeypatch.setattr(agents.sys, 'platform', platform)
    assert share(isolated)['connector'] == {'command': str(binary), 'args': []}
    binary.unlink()
    with pytest.raises(HTTPException) as error:
        share(isolated)
    assert error.value.status_code == 503


def test_source_connector_is_not_misrepresented_as_bundled(isolated, monkeypatch):
    monkeypatch.setattr(agents.sys, 'frozen', False, raising=False)
    assert share(isolated)['connector'] is None


def test_web_and_nonowner_cannot_create_grant(monkeypatch, isolated):
    request = Request({'type': 'http', 'headers': [], 'session': {'username': 'local'}})
    with pytest.raises(HTTPException) as error:
        agents.status(request)
    assert error.value.status_code == 404
    monkeypatch.setattr(agents, 'require_admin', lambda _: {'username': 'other'})
    with pytest.raises(HTTPException):
        share(isolated)


def test_consent_required_and_empty_stays_empty(isolated):
    with pytest.raises(HTTPException) as error:
        agents.share(agents.Share(workspace='default'), isolated)
    assert error.value.status_code == 422
    result = share(isolated, [])
    assert result['patient_count'] == 0
    assert agents._grant.members == []
    assert share(isolated)['patient_count'] == 2


def test_share_copies_members_and_rotates_token(isolated, connector):
    result = share(isolated, [{'dataset_id': 'default', 'patient_id': 'P1'}])
    assert agents._grant.members == [{'dataset_id': 'default', 'patient_id': 'P1'}]
    new = share(isolated)
    assert new['token'] != result['token']
    assert connector.post(agents.CALL_PATH, json={'operation': 'list_tools'},
                          headers={'Authorization': f"Bearer {result['token']}"}).status_code == 401


def test_update_keeps_token_and_expiry_and_changes_scope(isolated, connector):
    result = share(isolated)
    previous = agents._grant
    response = agents.update_share(agents.Share(workspace='default', members=[], acknowledge=True), isolated)
    updated = json.loads(response.body)
    assert 'token' not in updated and 'connector' not in updated
    assert updated['patient_count'] == 0
    assert updated['selection_signature'] != result['selection_signature']
    assert agents._grant.token_hash == previous.token_hash
    assert agents._grant.deadline == previous.deadline
    assert updated['expires_at'] == result['expires_at']
    reply = connector.post(agents.CALL_PATH, json={'operation':'call_tool', 'name':'describe_scope'},
                           headers={'Authorization': f"Bearer {result['token']}"})
    assert reply.status_code == 200 and reply.json()['result']['patient_count'] == 0


def test_failed_update_preserves_scope_and_revoke_cancels_update(isolated, monkeypatch):
    share(isolated)
    original = agents._grant
    def fail(*_):
        raise HTTPException(403, 'Not allowed')
    monkeypatch.setattr(agents, '_approved_sources', fail)
    with pytest.raises(HTTPException):
        agents.update_share(agents.Share(workspace='default', acknowledge=True), isolated)
    assert agents._grant is original
    def revoke_during_update(*_):
        agents._revoke()
        return [('default', '/fixture', 'Demo')]
    monkeypatch.setattr(agents, '_approved_sources', revoke_during_update)
    with pytest.raises(HTTPException):
        agents.update_share(agents.Share(workspace='default', acknowledge=True), isolated)
    assert agents._grant is None
    with pytest.raises(HTTPException):
        agents.update_share(agents.Share(workspace='default', acknowledge=True), isolated)


def test_revoked_expired_and_restarted_grants(isolated, connector, monkeypatch):
    for mode in ('revoke', 'expiry', 'restart'):
        result = share(isolated)
        headers = {'Authorization': f"Bearer {result['token']}"}
        if mode == 'revoke':
            agents.revoke(isolated)
        elif mode == 'expiry':
            monkeypatch.setattr(agents.time, 'monotonic', lambda: 10**20)
        else:
            agents.configure_desktop('http://127.0.0.1:45678')
        assert connector.post(agents.CALL_PATH, json={'operation': 'list_tools'}, headers=headers).status_code == 401


def test_valid_tools_and_scope_bounded_outputs(isolated, connector):
    result = share(isolated, [])
    headers = {'Authorization': f"Bearer {result['token']}"}
    tools = connector.post(agents.CALL_PATH, json={'operation': 'list_tools'}, headers=headers)
    assert tools.status_code == 200
    names = {tool['name'] for tool in tools.json()['tools']}
    from app.local_agent_tools import TOOL_DEFINITIONS
    assert names == {tool['name'] for tool in TOOL_DEFINITIONS}
    response = connector.post(agents.CALL_PATH, json={'operation': 'call_tool', 'name': 'describe_scope'}, headers=headers)
    assert response.json()['result']['patient_count'] == 0
    assert 'root_path' not in response.text and '/fixture' not in response.text


@pytest.mark.parametrize('extra', [{'origin': 'http://127.0.0.1:45678'},
                                  {'origin': 'https://hostile.example'}, {'host': 'hostile.example'}])
def test_browser_and_wrong_host_rejected(isolated, connector, extra):
    result = share(isolated)
    response = connector.post(agents.CALL_PATH, json={'operation': 'list_tools'},
                              headers={'Authorization': f"Bearer {result['token']}", **extra})
    assert response.status_code == 403


def test_no_cookie_user_header_query_or_alternate_path_access(isolated, connector):
    result = share(isolated)
    headers = {'Authorization': f"Bearer {result['token']}", 'X-User-Id': 'attacker',
               'Cookie': 'pn_user_id=attacker; cohortome_desktop=fake'}
    good = connector.post(agents.CALL_PATH, json={'operation': 'call_tool', 'name': 'describe_scope'}, headers=headers)
    assert good.status_code == 200  # Spoofed identity is ignored, not trusted.
    for path in ('/datasets', '/local-agent/share', agents.CALL_PATH + '?token=wrong'):
        assert connector.post(path, json={'operation': 'list_tools'}, headers=headers).status_code == 403
    assert connector.get(agents.CALL_PATH, headers=headers).status_code == 403


def test_stale_policy_and_fingerprint_are_checked_on_every_call(isolated, connector, monkeypatch):
    result = share(isolated)
    headers = {'Authorization': f"Bearer {result['token']}"}
    monkeypatch.setattr(agents.cohort_filters, '_fingerprint', lambda *_: 'b' * 64)
    response = connector.post(agents.CALL_PATH, json={'operation': 'list_tools'}, headers=headers)
    assert response.status_code == 409
    def denied(*_):
        raise HTTPException(403, 'Sensitive internal path must not be returned')
    monkeypatch.setattr(agents, '_approved_sources', denied)
    response = connector.post(agents.CALL_PATH, json={'operation': 'list_tools'}, headers=headers)
    assert response.status_code == 403
    assert 'Sensitive' not in response.text


def test_unknown_tool_bad_json_size_and_errors_are_sanitized(isolated, connector, monkeypatch):
    result = share(isolated)
    headers = {'Authorization': f"Bearer {result['token']}"}
    unknown = connector.post(agents.CALL_PATH, json={'operation': 'call_tool', 'name': 'execute_sql',
                             'arguments': {'secret': 'must-not-echo'}}, headers=headers)
    assert unknown.status_code == 422 and 'must-not-echo' not in unknown.text
    bad = connector.post(agents.CALL_PATH, content='not JSON', headers={**headers, 'Content-Type': 'application/json'})
    assert bad.status_code == 422
    big = connector.post(agents.CALL_PATH, content=b' ' * (agents.MAX_BODY_BYTES + 1),
                         headers={**headers, 'Content-Type': 'application/json'})
    assert big.status_code == 413
    def broken(*_):
        raise RuntimeError('Never expose /a/sensitive/path or TOKEN')
    monkeypatch.setattr(agents, '_approved_sources', broken)
    response = connector.post(agents.CALL_PATH, json={'operation': 'list_tools'}, headers=headers)
    assert response.status_code == 409 and 'TOKEN' not in response.text and '/a/' not in response.text


def test_revocation_during_call_discards_result(isolated, connector, monkeypatch):
    from app import local_agent_tools
    result = share(isolated)
    def revoked(*_):
        agents._revoke()
        return {'should_not_escape': True}
    monkeypatch.setattr(local_agent_tools, 'execute_tool', revoked)
    response = connector.post(agents.CALL_PATH, json={'operation': 'call_tool', 'name': 'describe_scope'},
                              headers={'Authorization': f"Bearer {result['token']}"})
    assert response.status_code == 401 and 'should_not_escape' not in response.text


def test_actual_bundled_fixture_hashes():
    for key, (directory, _) in agents.BUNDLED.items():
        agents._verify_fixture(key, str(agents.BASE_DIR / 'datasets' / directory))


def test_fixture_id_root_content_and_additional_clinical_inputs(tmp_path, monkeypatch):
    root = tmp_path / 'datasets/synthetic-longitudinal-demo'
    (root / 'clinical').mkdir(parents=True)
    files = {'manifest.json': '{}', 'assays/manifest.json': '{}', 'clinical/test.json': '[]'}
    for name, content in files.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    approval = tmp_path / 'approved.json'
    approval.write_text(json.dumps({'synthetic-longitudinal-demo': {
        name: hashlib.sha256(content.encode()).hexdigest() for name, content in files.items()}}))
    monkeypatch.setattr(agents, 'BASE_DIR', tmp_path)
    monkeypatch.setattr(agents, 'APPROVAL_PATH', approval)
    agents._verify_fixture('default', str(root))
    for identifier, path in [('real-study', root), ('default', tmp_path)]:
        with pytest.raises(HTTPException):
            agents._verify_fixture(identifier, str(path))
    (root / 'clinical/extra.json').write_text('[]')
    with pytest.raises(HTTPException):
        agents._verify_fixture('default', str(root))
    (root / 'clinical/extra.json').unlink()
    (root / 'clinical/test.json').write_text('[{}]')
    with pytest.raises(HTTPException):
        agents._verify_fixture('default', str(root))


def test_policy_checks_precede_data_reads(monkeypatch):
    request = owner_request()
    monkeypatch.setattr(agents.datasets, 'resolve_dataset_ids', lambda *_: ['default'])
    monkeypatch.setattr(agents, '_verify_fixture', lambda *_: pytest.fail('Do not read forbidden data'))
    with pytest.raises(HTTPException):
        agents._approved_sources(request, 'real-study')
    item = dict(root_path='/never-read', data_classification='public',
                query_granularity_ceiling='detailed', ai_provider_access='detailed_allowed')
    for key, value in [('data_classification', 'private'), ('query_granularity_ceiling', 'summary'),
                       ('ai_provider_access', 'blocked'), ('ai_provider_access', 'safe_summary')]:
        monkeypatch.setattr(agents.datasets, 'get_dataset', lambda _, data={**item, key:value}: data)
        with pytest.raises(HTTPException):
            agents._approved_sources(request, 'default')


def test_external_imaging_overlay_rejected_without_reading_it(tmp_path, monkeypatch):
    from app import dicom_files
    overlay = tmp_path / 'linked.json'
    overlay.write_text('Not even valid JSON; never read')
    monkeypatch.setattr(agents.datasets, 'resolve_dataset_ids', lambda *_: ['default'])
    monkeypatch.setattr(agents.datasets, 'get_dataset', lambda _: dict(root_path='/fixture',
        data_classification='public', query_granularity_ceiling='detailed', ai_provider_access='detailed_allowed'))
    monkeypatch.setattr(agents, '_verify_fixture', lambda *_: None)
    monkeypatch.setattr(dicom_files, 'index_path', lambda _: overlay)
    monkeypatch.setattr(agents, 'ensure_query_store', lambda _: pytest.fail('Do not open an overridden store'))
    with pytest.raises(HTTPException) as error:
        agents._approved_sources(owner_request(), 'default')
    assert error.value.status_code == 403


def test_combined_scope_rejects_unexpected_or_retargeted_cache(tmp_path, monkeypatch):
    sources = []
    for key in ('a', 'b'):
        root = tmp_path / key
        (root / 'clinical').mkdir(parents=True)
        (root / 'clinical/records.json').write_text('[]')
        sources.append((key, str(root), key))
    cache = tmp_path / 'combined'
    (cache / 'clinical').mkdir(parents=True)
    for key, source, _ in sources:
        (cache / f'clinical/{key}__records.json').symlink_to(Path(source) / 'clinical/records.json')
    monkeypatch.setattr(agents.datasets, 'materialize_dataset_scope', lambda _: str(cache))
    agents._verify_scope_cache(sources)
    (cache / 'clinical/unexpected.json').write_text('[]')
    with pytest.raises(HTTPException):
        agents._verify_scope_cache(sources)
    (cache / 'clinical/unexpected.json').unlink()
    (cache / 'clinical/a__records.json').unlink()
    (cache / 'clinical/a__records.json').symlink_to(tmp_path / 'b/clinical/records.json')
    with pytest.raises(HTTPException):
        agents._verify_scope_cache(sources)
