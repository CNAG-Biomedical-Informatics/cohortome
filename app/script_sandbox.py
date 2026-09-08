"""Synthetic-only container execution. Never falls back to host execution."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import shutil
import subprocess
import tempfile
import time
from uuid import uuid4

IMAGE = 'cohortome-script-sandbox:prototype-v1'
DOCKER_HOST = 'unix:///var/run/docker.sock'


def _docker():
    binary = shutil.which('docker')
    if not binary:
        raise RuntimeError('The isolated script runner needs Docker on the worker host.')
    return [binary, '--host', DOCKER_HOST]


def _control(arguments, timeout=15):
    result = subprocess.run(_docker() + arguments, capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError('The script sandbox is unavailable. Ask the administrator to build the sandbox image and check worker Docker access.')
    return result.stdout.decode('utf-8')


def sandbox_image():
    image_id = _control(['image', 'inspect', '--format', '{{.Id}}', IMAGE]).strip()
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', image_id):
        raise RuntimeError('Invalid script sandbox image identity.')
    return image_id


def sandbox_status():
    try:
        return {'available': True, 'image_id': sandbox_image()}
    except (RuntimeError, OSError, subprocess.TimeoutExpired):
        return {'available': False, 'message': 'Sandbox image or Docker access unavailable. Templates can still be prepared; execution needs administrator setup.'}


def _read_bounded(command):
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    data = bytearray()
    try:
        deadline = time.monotonic() + 110
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while True:
                if time.monotonic() >= deadline:
                    raise RuntimeError('Custom script exceeded its execution deadline.')
                if not selector.select(timeout=0.25):
                    continue
                chunk = os.read(process.stdout.fileno(), 65536)
                if not chunk:
                    break
                data.extend(chunk)
                if len(data) > 6 * 1024 * 1024:
                    raise RuntimeError('Custom script output exceeded the output limit.')
        if process.wait(timeout=5):
            raise RuntimeError('The sandbox stopped unsuccessfully, possibly because a resource limit was reached.')
        return json.loads(data)
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
        process.stdout.close()


def execute_script(files, script, job_root, expected_image, language='python'):
    if language not in {'python', 'r'}:
        raise RuntimeError('Choose Python or R.')
    image_id = sandbox_image()
    if image_id != expected_image:
        raise RuntimeError('The sandbox environment changed. Prepare the template again before running.')
    name = 'cohortome-script-' + uuid4().hex
    # No job/runtime/secret directory is mounted. Temporary inputs are synthetic.
    with tempfile.TemporaryDirectory(prefix='cohortome-script-') as temporary:
        inputs = Path(temporary)
        inputs.chmod(0o755)
        for filename, text in {**files, 'analysis.R' if language == 'r' else 'analysis.py': script}.items():
            path = inputs / filename
            path.write_text(text, encoding='utf-8')
            path.chmod(0o444)
        try:
            _control(['create', '--name', name, '--pull', 'never', '--network', 'none',
                      '--read-only', '--user', '65534:65534', '--cap-drop', 'ALL',
                      '--security-opt', 'no-new-privileges=true', '--pids-limit', '64',
                      '--cpus', '1', '--memory', '512m', '--memory-swap', '512m',
                      '--ulimit', 'nofile=1024:1024', '--ulimit', 'core=0:0',
                      '--log-driver', 'none', '--ipc', 'none',
                      '--tmpfs', '/work:rw,noexec,nosuid,nodev,size=64m,mode=1777',
                      '--tmpfs', '/tmp:rw,noexec,nosuid,nodev,size=16m,mode=1777',
                      '--mount', f'type=bind,source={inputs},target=/input,readonly', image_id, language])
            payload = _read_bounded(_docker() + ['start', '--attach', name])
        finally:
            # Stop the container, not just the attaching Docker client, on timeout.
            try:
                _control(['rm', '--force', name])
            except (RuntimeError, subprocess.TimeoutExpired):
                raise RuntimeError('Sandbox cleanup failed. Ask the administrator to inspect orphaned cohortome-script containers.') from None
    if not isinstance(payload, dict) or not isinstance(payload.get('exit_code'), int):
        raise RuntimeError('The sandbox returned an invalid result.')
    artifacts = payload.get('artifacts')
    if not isinstance(artifacts, list) or len(artifacts) > 8:
        raise RuntimeError('The sandbox returned too many artifacts.')
    validated, total = {}, 0
    for item in artifacts:
        if not isinstance(item, dict):
            raise RuntimeError('Invalid script artifact.')
        name = item.get('name', '')
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,95}\.(csv|txt|png)', name) or name in validated:
            raise RuntimeError('Script output names must be simple, unique CSV, TXT or PNG filenames.')
        try:
            raw = base64.b64decode(item['data'], validate=True)
        except (ValueError, TypeError, KeyError):
            raise RuntimeError('Invalid script artifact encoding.') from None
        total += len(raw)
        if total > 4 * 1024 * 1024:
            raise RuntimeError('Script artifacts exceed 4 MiB.')
        if name.endswith('.png') and not raw.startswith(b'\x89PNG\r\n\x1a\n'):
            raise RuntimeError('Invalid PNG artifact.')
        validated[name] = raw
    outputs = job_root / 'outputs'
    outputs.mkdir(exist_ok=True)
    for name, raw in validated.items():
        (outputs / name).write_bytes(raw)
    for stream in ('stdout', 'stderr'):
        value = payload.get(stream, '')
        if not isinstance(value, str) or len(value.encode()) > 200000:
            raise RuntimeError('Invalid script log.')
        (job_root / f'{stream}.txt').write_text(value, encoding='utf-8')
    return {'exit_code': payload['exit_code'], 'files': list(validated), 'image_id': image_id,
            'script_sha256': hashlib.sha256(script.encode()).hexdigest(),
            'stdout': payload['stdout'][:4000], 'stderr': payload['stderr'][:4000]}
