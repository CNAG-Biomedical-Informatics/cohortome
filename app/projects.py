"""Small, same-installation resume files; never import datasets or execute analyses."""
import hashlib
import json
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from app.auth import require_authenticated
from app.config import STATE_ROOT_DIR
from app.datasets import (authorized_datasets_for_user, current_dataset_ids,
                          dataset_scope_id, effective_query_granularity_ceiling,
                          set_current_datasets, workspace_fingerprint_for_data_dir)
from app.analysis_sessions import get_analysis_session
from app.cohorts import list_saved_cohorts
from app.jobs import list_job_records
from app.query_store import ensure_dataset_query_stores_ready, QueryStoreNotReadyError
from app.state_io import advisory_file_lock, atomic_write_json
from app.user_state import request_user_id
from pathlib import Path

router = APIRouter(prefix="/projects", tags=["ui"])


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Message(Strict):
    role: Literal["user", "assistant"]
    text: str = Field(max_length=16000)
    context: Literal["workspace", "general"] = "workspace"


class Draft(Strict):
    name: str = Field(min_length=1, max_length=100)
    view: Literal["dashboard", "datasets", "query", "analysis", "pheno"] = "dashboard"
    analysis_session_id: str = Field(default="", max_length=100)
    query_prompt: str = Field(default="", max_length=12000)
    query_context: Literal["workspace", "general"] = "workspace"
    conversation: list[Message] = Field(default_factory=list, max_length=16)


class DatasetRef(Strict):
    id: str = Field(min_length=1, max_length=150)
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")


class Project(Draft):
    format: Literal["cohortome-project"]
    version: Literal[1]
    installation: str = Field(max_length=100)
    owner: str = Field(max_length=150)
    saved_at: str = Field(max_length=100)
    datasets: list[DatasetRef] = Field(min_length=1, max_length=100)
    cohort_ids: list[str] = Field(default_factory=list, max_length=10000)
    run_ids: list[str] = Field(default_factory=list, max_length=10000)


def installation_id():
    path = STATE_ROOT_DIR / "project-installation.json"
    with advisory_file_lock(path.with_suffix(".lock")):
        if not path.exists():
            atomic_write_json(path, {"id": uuid4().hex}, file_mode=0o600)
        return json.loads(path.read_text())["id"]


def fingerprint(item):
    root = Path(item["root_path"])
    clinical = workspace_fingerprint_for_data_dir(str(root), dataset_id=item["dataset_id"])["token"]
    manifest = root / "assays/manifest.json"
    parts = [clinical]
    if manifest.exists():
        data = manifest.read_bytes()
        parts.append(hashlib.sha256(data).hexdigest())
        for assay in json.loads(data).get("assays", []):
            for key in ("file", "sample_metadata_file"):
                if assay.get(key):
                    path = root / assay[key]
                    stat = path.stat()
                    parts.append([key, str(path.resolve()), stat.st_size, stat.st_mtime_ns])
    return hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()


def authorized(request, ids):
    user = require_authenticated(request)
    available = {item["dataset_id"]: item for item in authorized_datasets_for_user(user)}
    if not ids or len(ids) != len(set(ids)) or any(identifier not in available for identifier in ids):
        raise HTTPException(409, "Project datasets are missing or unavailable to this user. The workspace was not changed.")
    if effective_query_granularity_ceiling(ids) != "detailed":
        raise HTTPException(403, "Projects currently require Detailed access to every selected dataset.")
    try:
        ensure_dataset_query_stores_ready(ids)
        return [DatasetRef(id=identifier, fingerprint=fingerprint(available[identifier])) for identifier in ids]
    except (OSError, ValueError, QueryStoreNotReadyError):
        raise HTTPException(409, "Project data or prepared stores are unavailable. Prepare the datasets before reopening.") from None


def check_session(identifier, owner, ids):
    if not identifier:
        return
    session = get_analysis_session(identifier, user_id=owner)
    if not session or session.get("dataset_id") != dataset_scope_id(ids):
        raise HTTPException(409, "The saved analysis conversation is missing or belongs to another workspace.")


@router.post("/export")
def export_project(draft: Draft, request: Request):
    require_authenticated(request)
    owner = request_user_id(request)
    ids = current_dataset_ids(owner)
    references = authorized(request, ids)
    check_session(draft.analysis_session_id, owner, ids)
    cohorts = list_saved_cohorts(dataset_scope_id(ids), user_id=owner)
    runs = [r for r in list_job_records(owner) if r.get("dataset_id") == dataset_scope_id(ids)]
    return Project(**draft.model_dump(), format="cohortome-project", version=1,
                   installation=installation_id(), owner=owner,
                   saved_at=datetime.now(timezone.utc).isoformat(), datasets=references,
                   cohort_ids=[c["id"] for c in cohorts], run_ids=[r["job_id"] for r in runs])


def validate_project(project, request):
    require_authenticated(request)
    owner = request_user_id(request)
    if project.installation != installation_id() or project.owner != owner:
        raise HTTPException(409, "This resume file belongs to another installation or user. Portable projects are not supported yet.")
    ids = [reference.id for reference in project.datasets]
    references = authorized(request, ids)
    if references != project.datasets:
        raise HTTPException(409, "Project data have changed since saving. The workspace was not changed; review the datasets before starting new analyses.")
    check_session(project.analysis_session_id, owner, ids)
    cohorts = {c["id"] for c in list_saved_cohorts(dataset_scope_id(ids), user_id=owner)}
    runs = {r["job_id"] for r in list_job_records(owner) if r.get("dataset_id") == dataset_scope_id(ids)}
    warnings = []
    if any(c not in cohorts for c in project.cohort_ids):
        warnings.append("Some referenced cohorts have been deleted; the project file does not contain copies.")
    if any(r not in runs for r in project.run_ids):
        warnings.append("Some referenced runs have been deleted; the project file does not contain results.")
    return owner, ids, warnings


@router.post("/inspect")
def inspect_project(project: Project, request: Request):
    _, ids, warnings = validate_project(project, request)
    return {"dataset_ids": ids, "warnings": warnings}


@router.post("/open")
def open_project(project: Project, request: Request):
    owner, ids, warnings = validate_project(project, request)
    set_current_datasets(owner, ids)
    return {"project": project, "dataset_ids": ids, "warnings": warnings}
