"""Opt-in test of the real Desktop security gate and stdio connector together.

COHORTOME_TEST_APP_PYTHON selects the app's Python installation. Everything else
is temporary: Desktop state, prepared synthetic DuckDB, tokens and client logs.
No Tauri window is opened and no existing Desktop profile is accessed.
"""
import asyncio
import json
import os
from pathlib import Path
from queue import Empty, Queue
import subprocess
import sys
import threading
from urllib.parse import urlsplit

import httpx
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[2]
APP_PYTHON = os.environ.get('COHORTOME_TEST_APP_PYTHON')
pytestmark = pytest.mark.skipif(not APP_PYTHON, reason='Set COHORTOME_TEST_APP_PYTHON for the real Desktop test.')


@pytest.fixture
def desktop(tmp_path):
    env = {**os.environ, 'PYTHONPATH':os.pathsep.join((str(ROOT / '.deps'), str(ROOT))),
           'PYTHONDONTWRITEBYTECODE':'1'}
    runtime = tmp_path / 'desktop-runtime'
    with (tmp_path / 'desktop-stderr.txt').open('w+') as errors:
        process = subprocess.Popen([APP_PYTHON, str(ROOT / 'desktop/server.py'),
            '--runtime-dir', str(runtime)], cwd=ROOT, env=env,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors, text=True)
        lines = Queue(maxsize=1)
        threading.Thread(target=lambda: lines.put(process.stdout.readline()), daemon=True).start()
        try:
            try:
                line = lines.get(timeout=40)
            except Empty:
                pytest.fail('Temporary Desktop backend did not start within 40 seconds.')
            try:
                bootstrap = json.loads(line)['url']
                url = urlsplit(bootstrap)
                assert url.hostname == '127.0.0.1' and url.path == '/desktop/open'
                origin = f'{url.scheme}://{url.netloc}'
            except (ValueError, KeyError, AssertionError):
                pytest.fail('Temporary Desktop backend did not report a valid bootstrap URL.')
            with httpx.Client(base_url=origin, trust_env=False, timeout=120) as owner:
                assert owner.get('/').status_code == 403
                opened = owner.get(bootstrap, follow_redirects=True)
                assert opened.status_code == 200
                assert owner.get('/local-agent/status').json() == {'enabled':False}
                prepared = owner.post('/datasets/default/prepare-store')
                assert prepared.status_code == 200, 'Preparing the disposable synthetic store failed.'
                yield owner, origin, runtime
        finally:
            process.stdin.close()  # Normal desktop shutdown: parent pipe closes.
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()  # Only the backend process created by this fixture.
                process.wait(timeout=5)
            process.stdout.close()


def test_real_desktop_share_mcp_scope_and_revoke(desktop, tmp_path):
    owner, origin, runtime = desktop
    selected_before = owner.get('/datasets').json()['current_dataset_ids']

    def share(members=None):
        response = owner.post('/local-agent/share', json={
            'workspace':'default', 'members':members, 'acknowledge':True})
        assert response.status_code == 200, 'Sharing the disposable synthetic scope failed.'
        result = response.json()
        assert result['enabled'] and result['url'] == origin + '/local-agent/call'
        return result

    granted = share()
    assert granted['patient_count'] > 2
    header = {'Authorization':f"Bearer {granted['token']}"}
    with httpx.Client(base_url=origin, trust_env=False, timeout=120) as outsider:
        assert outsider.get('/datasets', headers=header).status_code == 403
        assert outsider.post('/local-agent/share', headers=header,
            json={'workspace':'default', 'acknowledge':True}).status_code == 403
        assert outsider.get('/local-agent/status', headers=header).status_code == 403
        assert outsider.post('/local-agent/call', headers={**header, 'Origin':origin},
            json={'operation':'list_tools'}).status_code == 403
        assert outsider.post('/local-agent/call', headers={**header, 'Host':'invalid.example'},
            json={'operation':'list_tools'}).status_code == 403
        assert outsider.post('/local-agent/call', json={'operation':'list_tools'}).status_code == 401

    async def inspect(grant, expected_count, *, revoke=False):
        parameters = StdioServerParameters(command=sys.executable,
            args=[str(ROOT / 'integrations/mcp/cohortome_mcp.py')],
            env={'COHORTOME_MCP_URL':grant['url'], 'COHORTOME_MCP_TOKEN':grant['token']})
        with (tmp_path / 'mcp-stderr.txt').open('w+') as errors:
            async with stdio_client(parameters, errlog=errors) as (read, write):
                async with ClientSession(read, write) as client:
                    await client.initialize()
                    tools = await client.list_tools()
                    assert {tool.name for tool in tools.tools} == {
                        'describe_scope', 'list_filter_fields', 'find_patients', 'summarize_selection'}
                    described = await client.call_tool('describe_scope', {})
                    assert not described.isError and described.structuredContent['patient_count'] == expected_count
                    found = await client.call_tool('find_patients', {'limit':2})
                    assert not found.isError, 'MCP patient search failed against the actual Desktop backend.'
                    patients = found.structuredContent
                    assert patients['patient_count'] == expected_count
                    assert len(patients['patients']) == min(expected_count, 2)
                    assert patients['next_offset'] == (2 if expected_count > 2 else None)
                    assert all(item['dataset_id'] == 'default' for item in patients['patients'])
                    fields = await client.call_tool('list_filter_fields', {'limit':2})
                    assert not fields.isError and len(fields.structuredContent['fields']) <= 2
                    summarized = await client.call_tool('summarize_selection', {})
                    assert not summarized.isError and summarized.structuredContent['patient_count'] == expected_count
                    no_matches = await client.call_tool('summarize_selection', {'q':'no-such-fictional-patient'})
                    assert not no_matches.isError and no_matches.structuredContent['patient_count'] == 0
                    unchanged = await client.call_tool('describe_scope', {})
                    assert unchanged.structuredContent['patient_count'] == expected_count
                    assert owner.get('/local-agent/status').json()['patient_count'] == expected_count
                    if revoke:
                        assert owner.delete('/local-agent/share').json() == {'enabled':False}
                        denied = await client.call_tool('describe_scope', {})
                        assert denied.isError and 'revoked' in denied.content[0].text
            errors.seek(0)
            assert errors.read() == ''
        return patients['patients']

    patients = asyncio.run(inspect(granted, granted['patient_count']))
    narrower = share(patients[:1])
    assert narrower['patient_count'] == 1
    with httpx.Client(trust_env=False) as client:
        assert client.post(granted['url'], headers=header,
            json={'operation':'list_tools'}).status_code == 401
    assert asyncio.run(inspect(narrower, 1)) == patients[:1]
    empty = share([])
    assert asyncio.run(inspect(empty, 0, revoke=True)) == []
    assert owner.get('/datasets').json()['current_dataset_ids'] == selected_before
    assert not list((runtime / 'runs').rglob('*.json')), 'Read-only tools must not launch analyses.'
