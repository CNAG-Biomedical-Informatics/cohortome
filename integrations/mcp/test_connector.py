"""Protocol/transport checks, using only a disposable synthetic loopback server."""
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.shared.exceptions import McpError

SCRIPT = Path(__file__).with_name('cohortome_mcp.py')
spec = importlib.util.spec_from_file_location('cohortome_mcp', SCRIPT)
connector = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = connector
spec.loader.exec_module(connector)
TOKEN = 'test_only_not_a_real_connection_0123456789'
URL = 'http://127.0.0.1:43210/local-agent/call'


@pytest.mark.parametrize('url', [
    'https://127.0.0.1:43210/local-agent/call', 'http://localhost:43210/local-agent/call',
    'http://[::1]:43210/local-agent/call', 'http://10.0.0.1:43210/local-agent/call',
    'http://127.0.0.1:0/local-agent/call', 'http://127.0.0.1:65536/local-agent/call',
    'http://user@127.0.0.1:43210/local-agent/call', URL + '?token=secret', URL + '#fragment',
    URL + '/', URL + '\n', 'http://127.0.0.1:43210/admin',
])
def test_reject_noncanonical_endpoint(url):
    with pytest.raises(connector.ConnectorError, match='exact loopback URL'):
        connector.Connection(url, TOKEN)


def test_token_not_in_representation():
    assert TOKEN not in repr(connector.Connection(URL, TOKEN))
    with pytest.raises(connector.ConnectorError):
        connector.Connection(URL, 'bad\nsecret')


def mock_http(monkeypatch, handler):
    real = httpx.AsyncClient
    options = []

    def make_client(**kwargs):
        options.append(kwargs)
        return real(**kwargs, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(connector.httpx, 'AsyncClient', make_client)
    return options


@pytest.mark.parametrize('status', [302, 401, 403, 409, 422, 429, 500])
def test_errors_are_sanitized_and_redirects_not_followed(monkeypatch, status):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, json={'detail':f'private path /secret/{TOKEN}'},
                              headers={'Location':'https://example.invalid/steal'})

    options = mock_http(monkeypatch, handler)
    with pytest.raises(connector.ConnectorError) as error:
        asyncio.run(connector.Connection(URL, TOKEN).request({'operation':'list_tools'}))
    assert TOKEN not in str(error.value) and '/secret' not in str(error.value)
    assert len(calls) == 1 and calls[0].url == URL
    assert calls[0].headers['Authorization'] == f'Bearer {TOKEN}'
    assert 'origin' not in calls[0].headers
    assert options[0]['trust_env'] is False and options[0]['follow_redirects'] is False


def test_bounded_response_and_invalid_json(monkeypatch):
    mock_http(monkeypatch, lambda _: httpx.Response(200, content=b'x' * (connector.MAX_RESPONSE_BYTES + 1)))
    with pytest.raises(connector.ConnectorError, match='response is too large'):
        asyncio.run(connector.Connection(URL, TOKEN).request({'operation':'list_tools'}))


@pytest.mark.parametrize('content', [b'not json', b'[]', b'\xff'])
def test_invalid_response(monkeypatch, content):
    mock_http(monkeypatch, lambda _: httpx.Response(200, content=content))
    with pytest.raises(connector.ConnectorError, match='invalid response'):
        asyncio.run(connector.Connection(URL, TOKEN).request({'operation':'list_tools'}))


def test_request_limits_precede_network(monkeypatch):
    def forbidden(**_):
        pytest.fail('Invalid request must not open a connection')
    monkeypatch.setattr(connector.httpx, 'AsyncClient', forbidden)
    with pytest.raises(connector.ConnectorError, match='too large'):
        asyncio.run(connector.Connection(URL, TOKEN).request({'data':'x' * connector.MAX_REQUEST_BYTES}))
    with pytest.raises(connector.ConnectorError, match='valid JSON'):
        asyncio.run(connector.Connection(URL, TOKEN).request({'data':float('nan')}))


def test_main_invalid_configuration_does_not_print_values():
    env = {**os.environ, 'COHORTOME_MCP_URL':f'https://invalid.example/{TOKEN}',
           'COHORTOME_MCP_TOKEN':TOKEN}
    result = subprocess.run([sys.executable, str(SCRIPT)], env=env, capture_output=True, timeout=15)
    assert result.returncode == 2
    assert not result.stdout
    assert TOKEN.encode() not in result.stderr and b'Traceback' not in result.stderr


def test_real_stdio_initialization_discovery_call_and_revocation(tmp_path):
    requests = []
    revoked = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            assert self.path == '/local-agent/call'
            assert self.headers['Authorization'] == f'Bearer {TOKEN}'
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            requests.append(body)
            if revoked.is_set():
                status, result = 401, {'detail':'token invalid'}
            elif body['operation'] == 'list_tools':
                status, result = 200, {'tools':[{
                    'name':'describe_scope', 'description':'Describe the shared synthetic selection.',
                    'inputSchema':{'type':'object', 'properties':{}, 'additionalProperties':False},
                }, {
                    'name':'prepare_analysis_run', 'description':'Request approval.',
                    'inputSchema':{'type':'object', 'properties':{}, 'additionalProperties':False},
                }]}
            else:
                assert body == {'operation':'call_tool', 'name':'describe_scope', 'arguments':{}}
                status, result = 200, {'result':{'patient_count':2, 'synthetic_only':True}}
            raw = json.dumps(result).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    async def exercise():
        parameters = StdioServerParameters(command=sys.executable, args=[str(SCRIPT)], env={
            'COHORTOME_MCP_URL':f'http://127.0.0.1:{server.server_port}/local-agent/call',
            'COHORTOME_MCP_TOKEN':TOKEN,
            'HTTP_PROXY':'http://127.0.0.1:1', 'ALL_PROXY':'http://127.0.0.1:1', 'NO_PROXY':'',
        })
        with (tmp_path / 'stderr.txt').open('w+') as log:
            async with stdio_client(parameters, errlog=log) as (read, write):
                async with ClientSession(read, write) as client:
                    initialized = await client.initialize()
                    assert initialized.serverInfo.name == 'cohortome'
                    listed = await client.list_tools()
                    assert [tool.name for tool in listed.tools] == ['describe_scope', 'prepare_analysis_run']
                    flags = listed.tools[0].annotations
                    assert flags.readOnlyHint and flags.idempotentHint
                    assert not flags.destructiveHint and not flags.openWorldHint
                    proposal_flags = listed.tools[1].annotations
                    assert not proposal_flags.readOnlyHint and not proposal_flags.idempotentHint
                    result = await client.call_tool('describe_scope', {})
                    assert not result.isError
                    assert result.structuredContent == {'patient_count':2, 'synthetic_only':True}
                    assert json.loads(result.content[0].text) == result.structuredContent
                    revoked.set()
                    failed = await client.call_tool('describe_scope', {})
                    assert failed.isError and 'revoked' in failed.content[0].text
                    with pytest.raises(McpError, match='revoked'):
                        await client.list_tools()
            log.seek(0)
            assert log.read() == ''

    try:
        asyncio.run(exercise())
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
    assert requests[0] == {'operation':'list_tools'}
    assert sum(r['operation'] == 'call_tool' for r in requests) == 2
