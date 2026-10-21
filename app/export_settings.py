"""Deployment-wide export size limits, editable by the administrator."""
import json

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.auth import require_admin
from app.config import STATE_ROOT_DIR
from app.state_io import advisory_file_lock, atomic_write_json

router = APIRouter(prefix="/export-settings", tags=["exports"])
SETTINGS_PATH = STATE_ROOT_DIR / "export-settings.json"
MIB = 1024 * 1024


class ExportLimits(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_mib: int = Field(default=512, ge=1, le=2048, strict=True)
    total_source_mib: int = Field(default=1024, ge=1, le=4096, strict=True)
    output_mib: int = Field(default=256, ge=1, le=1024, strict=True)

    @model_validator(mode="after")
    def ordered(self):
        if self.total_source_mib < self.source_mib:
            raise ValueError("Combined source limit must be at least the per-file limit.")
        return self


def stored_limits():
    if not SETTINGS_PATH.exists():
        return {}
    try:
        return ExportLimits.model_validate(json.loads(SETTINGS_PATH.read_text())).model_dump()
    except (OSError, ValueError):
        raise HTTPException(503, "Export settings are unreadable. Ask an administrator to save them again.") from None


def byte_limit(key, default):
    return stored_limits().get(key, default // MIB) * MIB if SETTINGS_PATH.exists() else default


@router.get("")
def get_limits(request: Request):
    require_admin(request)
    return ExportLimits(**stored_limits()).model_dump()


@router.put("")
def save_limits(payload: ExportLimits, request: Request):
    require_admin(request)
    with advisory_file_lock(SETTINGS_PATH.with_suffix(".lock")):
        atomic_write_json(SETTINGS_PATH, payload.model_dump())
    return payload.model_dump()
