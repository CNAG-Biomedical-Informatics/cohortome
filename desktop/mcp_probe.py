"""Exercise a bundled connector over stdio, with no Python/MCP on its PATH."""
import json
from pathlib import Path
from queue import Queue
import subprocess
import threading


def verify_connector(connector, executable):
    # macOS temporary directories can be spelled /var or /private/var.
    # Compare the actual destination, not its symlink spelling.
    assert connector['args'] == []
    assert Path(connector['command']).resolve(strict=True) == Path(executable).resolve(strict=True)


def probe(client, executable, environment, cwd):
    shared = client.post('/local-agent/share', json={'workspace': 'default', 'acknowledge': True})
    assert shared.status_code == 200, 'Could not share the synthetic test scope'
    grant = shared.json()
    if grant.get('connector'):
        verify_connector(grant['connector'], executable)
        executable = Path(grant['connector']['command'])
    process = subprocess.Popen([str(executable)], cwd=cwd,
        env={**environment, 'COHORTOME_MCP_URL': grant['url'], 'COHORTOME_MCP_TOKEN': grant['token']},
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    messages = Queue()

    def read():
        for line in process.stdout:
            messages.put(line)
        messages.put('')

    threading.Thread(target=read, daemon=True).start()

    def send(message):
        process.stdin.write(json.dumps({'jsonrpc': '2.0', **message}) + '\n')
        process.stdin.flush()

    def call(identifier, method, params):
        send({'id': identifier, 'method': method, 'params': params})
        # Ignore bounded protocol notifications; never log returned records/tokens.
        for _ in range(20):
            line = messages.get(timeout=30)
            assert line, 'Bundled connector exited before replying'
            reply = json.loads(line)
            if reply.get('id') == identifier:
                assert 'error' not in reply, 'MCP protocol request failed'
                return reply['result']
        raise AssertionError('Too many notifications from the connector')

    try:
        initialized = call(1, 'initialize', {'protocolVersion': '2025-06-18', 'capabilities': {},
            'clientInfo': {'name': 'cohortome-package-test', 'version': '1'}})
        assert initialized['serverInfo']['name'] == 'cohortome'
        send({'method': 'notifications/initialized'})
        listed = call(2, 'tools/list', {})
        assert {t['name'] for t in listed['tools']} == {
            'describe_scope', 'list_filter_fields', 'find_patients', 'summarize_selection'}
        result = call(3, 'tools/call', {'name': 'describe_scope', 'arguments': {}})
        assert not result.get('isError')
        assert result['structuredContent']['patient_count'] == grant['patient_count']
        assert client.delete('/local-agent/share').status_code == 200
        denied = call(4, 'tools/call', {'name': 'describe_scope', 'arguments': {}})
        assert denied.get('isError'), 'Turning off MCP did not revoke the running connector'
        process.stdin.close()
        assert process.wait(timeout=15) == 0
        assert not process.stderr.read(), 'Bundled connector emitted unexpected diagnostics'
    finally:
        client.delete('/local-agent/share')
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        for stream in (process.stdin, process.stdout, process.stderr):
            stream.close()
    print('PASS: bundled MCP initialization, tools, scope and revocation with empty PATH')
