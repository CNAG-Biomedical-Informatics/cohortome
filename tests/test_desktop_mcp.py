"""Opt-in frozen connector test against a disposable source Desktop backend."""
import importlib.util
import json
import os
from pathlib import Path
from queue import Queue
import shutil
import subprocess
import sys
import threading
from urllib.parse import urlsplit

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = os.environ.get('COHORTOME_TEST_MCP_BUNDLE')


def test_connector_validation_accepts_symlink_spelling_not_another_executable(tmp_path):
    spec = importlib.util.spec_from_file_location('mcp_probe', ROOT / 'desktop/mcp_probe.py')
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)
    actual = tmp_path / 'private' / 'engine'
    actual.mkdir(parents=True)
    binary = actual / 'cohortome-mcp'
    binary.write_bytes(b'fixture')
    alias = tmp_path / 'var'
    alias.symlink_to(actual, target_is_directory=True)
    probe.verify_connector({'command': str(binary), 'args': []}, alias / binary.name)
    other = actual / 'other'
    other.write_bytes(b'fixture')
    with pytest.raises(AssertionError):
        probe.verify_connector({'command': str(other), 'args': []}, binary)


@pytest.mark.skipif(not BUNDLE, reason='Set COHORTOME_TEST_MCP_BUNDLE to the frozen connector directory')
def test_relocated_frozen_connector_without_python(tmp_path):
    installed = tmp_path / 'installed app/mcp'
    shutil.copytree(BUNDLE, installed, symlinks=True)
    binary = installed / ('cohortome-mcp.exe' if os.name == 'nt' else 'cohortome-mcp')
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(('COHORTOME_', 'LM_STUDIO_', 'UVICORN_'))}
    env.update(PYTHONPATH=os.pathsep.join([str(ROOT / '.deps'), str(ROOT)]), PYTHONDONTWRITEBYTECODE='1')
    with (tmp_path / 'server.log').open('w+') as errors:
        child = subprocess.Popen([sys.executable, str(ROOT / 'desktop/server.py'),
            '--runtime-dir', str(tmp_path / 'runtime')], env=env, cwd=ROOT,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors, text=True)
        lines = Queue()
        threading.Thread(target=lambda: lines.put(child.stdout.readline()), daemon=True).start()
        try:
            bootstrap = json.loads(lines.get(timeout=40))['url']
            url = urlsplit(bootstrap)
            with httpx.Client(base_url=f'{url.scheme}://{url.netloc}', trust_env=False,
                              follow_redirects=True, timeout=120) as client:
                assert client.get(bootstrap).status_code == 200
                assert client.post('/datasets/default/prepare-store').status_code == 200
                spec = importlib.util.spec_from_file_location('mcp_probe', ROOT / 'desktop/mcp_probe.py')
                probe = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(probe)
                clean = {'PATH': '', 'HOME': str(tmp_path), 'LANG': 'C.UTF-8',
                         'PYTHONPATH': str(tmp_path / 'absent'), 'PYTHONNOUSERSITE': '1'}
                if os.name == 'nt':
                    clean.update({k: os.environ[k] for k in ('SystemRoot', 'WINDIR') if k in os.environ})
                probe.probe(client, binary, clean, tmp_path)
        finally:
            child.stdin.close()
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)
            child.stdout.close()
