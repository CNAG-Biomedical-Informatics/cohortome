"""Deployment storage destination for new dataset imports only."""
import json
from pathlib import Path
import shutil
import tempfile

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from app.auth import require_admin
from app.config import STATE_ROOT_DIR
from app.state_io import advisory_file_lock, atomic_write_json

router = APIRouter(prefix="/resource-storage", tags=["datasets"])
SETTINGS = STATE_ROOT_DIR / "resource-storage.json"
DEFAULT = STATE_ROOT_DIR / "resources"


class StorageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    directory: str = Field(min_length=1, max_length=4096)


def import_root(default=None):
    if not SETTINGS.exists():
        return Path(default or DEFAULT)
    try:
        path = Path(json.loads(SETTINGS.read_text())["directory"])
        if not path.is_absolute() or not path.is_dir():
            raise ValueError()
        return path
    except (OSError, ValueError, KeyError, TypeError):
        raise HTTPException(503, "Dataset storage is unavailable. Reconnect the disk or change the folder in Settings.") from None


def report(path):
    existing = path
    while not existing.exists():
        existing = existing.parent
    return {"directory": str(path), "free_bytes": shutil.disk_usage(existing).free}


@router.get("")
def get_storage(request: Request):
    require_admin(request)
    return report(import_root())


@router.put("")
def set_storage(payload: StorageRequest, request: Request):
    require_admin(request)
    path = Path(payload.directory)
    if not path.is_absolute():
        raise HTTPException(400, "Choose an absolute folder path on this computer or server.")
    try:
        path = path.resolve(strict=True)
        if not path.is_dir():
            raise ValueError()
        with tempfile.TemporaryFile(dir=path) as probe:
            probe.write(b"storage-check")
            probe.flush()
        result = report(path)
    except (OSError, ValueError):
        raise HTTPException(400, "Choose an existing folder writable by COHORTome.") from None
    with advisory_file_lock(SETTINGS.with_suffix(".lock")):
        atomic_write_json(SETTINGS, {"directory": str(path)})
    return result
