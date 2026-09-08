"""Runs only inside the disposable container. All emitted content is untrusted."""
import base64
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

out = Path('/work/output')
out.mkdir()
language = sys.argv[1] if len(sys.argv) > 1 else 'python'
commands = {'python': ['python', '-I', '/input/analysis.py'], 'r': ['Rscript', '--vanilla', '/input/analysis.R']}
if language not in commands:
    raise SystemExit('Unsupported language')
with open('/work/stdout.txt', 'wb') as stdout, open('/work/stderr.txt', 'wb') as stderr:
    try:
        result = subprocess.run(commands[language], cwd='/work',
                                stdout=stdout, stderr=stderr, timeout=90)
        exit_code = result.returncode
    except subprocess.TimeoutExpired:
        exit_code = 124

artifacts = []
total = 0
for path in sorted(out.iterdir())[:8]:
    # Nonblocking + no-follow: script-produced FIFOs/symlinks are not outputs.
    if path.suffix.lower() not in {'.csv', '.txt', '.png'}:
        continue
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > 4 * 1024 * 1024 - total:
                continue
            data = handle.read(4 * 1024 * 1024 - total + 1)
        total += len(data)
        if total > 4 * 1024 * 1024:
            break
        artifacts.append({'name': path.name, 'data': base64.b64encode(data).decode('ascii')})
    except OSError:
        continue

def log(name):
    try:
        fd = os.open('/work/' + name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                return ''
            return handle.read(65536).decode('utf-8', errors='replace')
    except OSError:
        return ''

print(json.dumps({'exit_code': exit_code, 'stdout': log('stdout.txt'),
                  'stderr': log('stderr.txt'), 'artifacts': artifacts}))
