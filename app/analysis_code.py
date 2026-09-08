"""Deduplicated, content-addressed snapshots of public implementation code."""
import hashlib
import re
import os
import tempfile
from pathlib import Path

from fastapi import HTTPException
from app import user_state


def snapshot(source):
    digest = hashlib.sha256(source.encode()).hexdigest()
    directory = Path(user_state.STATE_ROOT_DIR) / 'analysis_code'
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = directory / (digest + '.py')
    if not path.exists():
        # Publish whole files atomically; a concurrent reader must not see partial code.
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=directory, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(source)
        try:
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
    return {'filename': 'analysis.py', 'sha256': digest, 'url': f'/analysis/code/{digest}',
            'note': 'Loaded COHORTome Analysis implementation, not a standalone script or full dependency archive. Resolved measurements and statistical parameters are in the result context; model provenance is recorded separately.'}


def code_path(digest):
    if not re.fullmatch(r'[0-9a-f]{64}', digest):
        raise HTTPException(status_code=404, detail='Implementation snapshot not found.')
    path = Path(user_state.STATE_ROOT_DIR) / 'analysis_code' / (digest + '.py')
    if not path.is_file() or path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise HTTPException(status_code=404, detail='Implementation snapshot not found.')
    return path
