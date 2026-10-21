"""Reviewed resource downloads and bounded, admin-only dataset installation."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
import threading
from urllib.parse import urlparse
from uuid import uuid4
import zipfile

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.auth import require_admin
from app.config import CONFIG_DIR, STATE_ROOT_DIR
from app.dataset_validation import validate_package
from app import datasets, query_store
from app.state_io import advisory_file_lock
from app.resource_storage import import_root
from app.geo_source import SourcePreparationError

router = APIRouter(prefix="/resources", tags=["datasets"])
REPOSITORY = "CNAG-Biomedical-Informatics/cohortome-store"
ROOT = STATE_ROOT_DIR / "resources"
MAX_ARCHIVE = 1024 * 1024 * 1024
MAX_EXPANDED = 4 * MAX_ARCHIVE
MAX_FILES = 25000
BUNDLED = {"default", "synthetic-cross-sectional-demo"}
CHUNK = 1024 * 1024
_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="resource-install")
_lock = threading.Lock()
_jobs = {}
TERMINAL = {"ready", "failed", "cancelled"}


class InstallError(ValueError):
    pass


class Cancelled(Exception):
    pass


class DownloadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dataset_id: str
    github_token: SecretStr = Field(default=SecretStr(""))
    source_terms_acknowledged: bool = False


class RemoveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmation: str
    remove_files: bool = False


@router.post("/datasets/{dataset_id}/remove")
def remove_dataset(dataset_id: str, payload: RemoveRequest, request: Request):
    require_admin(request)
    if dataset_id in BUNDLED:
        raise HTTPException(409, "Bundled datasets cannot be removed.")
    if payload.confirmation != dataset_id:
        raise HTTPException(400, "Confirm the exact dataset ID.")
    store_paths = query_store._dataset_store_paths(dataset_id)
    store_status = store_paths[2]
    store_lock = store_status.with_name(f".{store_status.name}.lock")
    with advisory_file_lock(ROOT / ".install.lock"):
        # Store preparation takes these locks in the same order.
        with advisory_file_lock(store_lock), advisory_file_lock(datasets._registry_lock_path()):
            items = datasets._read_registry_unlocked()
            record = next((item for item in items if item["dataset_id"] == dataset_id), None)
            if not record:
                raise HTTPException(404, "Dataset not found.")
            # Disable first so new requests cannot resolve this dataset.
            was_enabled = record.get("enabled", True)
            record["enabled"] = False
            datasets._write_registry_unlocked(items)
            moved = None
            try:
                # Conservative across users and datasets, including direct P-R runs.
                for path in (STATE_ROOT_DIR / "users").glob("*/jobs/*/job.json"):
                    job = json.loads(path.read_text())
                    if job.get("status") in {"queued", "running"}:
                        raise HTTPException(409, "Finish or cancel active jobs before removing a dataset.")
                with _lock:
                    if any(job["stage"] not in TERMINAL for job in _jobs.values()):
                        raise HTTPException(409, "Wait for the dataset installation to finish.")
                root = Path(record["root_path"])
                if payload.remove_files:
                    receipt_path = root / ".resource-install.json"
                    if (root.is_symlink() or root.resolve() != root.absolute()
                            or root.parent.name != "installed"
                            or not re.fullmatch(r"[a-f0-9]{32}", root.name)
                            or receipt_path.is_symlink() or not receipt_path.is_file()):
                        raise HTTPException(409, "Only installer-managed dataset files can be removed. Uncheck file removal.")
                    receipt = json.loads(receipt_path.read_text())
                    if not receipt.get("complete") or receipt.get("dataset_id") in BUNDLED:
                        raise HTTPException(409, "This package cannot be removed.")
                    if any(item is not record and Path(item["root_path"]).resolve().is_relative_to(root.resolve())
                           for item in items):
                        raise HTTPException(409, "Another dataset uses this directory.")
                    # Recoverable removal, never recursive deletion of a source folder.
                    removed_root = root.parent.parent / "removed"
                    if removed_root.is_symlink():
                        raise HTTPException(409, "Unsafe recovery directory.")
                    removed_root.mkdir(exist_ok=True)
                    moved = removed_root / uuid4().hex
                    root.rename(moved)
                for path in store_paths:
                    path.unlink(missing_ok=True)
                datasets._write_registry_unlocked([item for item in items if item is not record])
                with _lock:
                    for key in list(_jobs):
                        if _jobs[key].get("dataset_id") == dataset_id:
                            del _jobs[key]
            except Exception:
                if moved is not None:
                    moved.rename(root)
                record["enabled"] = was_enabled
                datasets._write_registry_unlocked(items)
                raise
    return {"removed": True, "files_removed": payload.remove_files,
            "message": ("Dataset removed. Package files moved to the storage folder's removed directory for recovery."
                        if payload.remove_files else "Dataset removed. Original package files retained.")}


def catalogue():
    return json.loads((CONFIG_DIR / "resources.json").read_text(encoding="utf-8"))


def snapshot(job):
    with _lock:
        return {key: value for key, value in job.items() if not key.startswith("_")}


def progress(job, stage, **values):
    with _lock:
        job.update(stage=stage, **values)


def check_cancel(job):
    if job["_cancel"].is_set():
        raise Cancelled()


def new_job(name):
    root = import_root(ROOT)
    with _lock:
        if any(job["stage"] not in TERMINAL for job in _jobs.values()):
            raise HTTPException(409, "A dataset installation is already in progress.")
        # Keep only the latest result; imported provenance lives with the package.
        _jobs.clear()
        job = dict(id=uuid4().hex, name=name, stage="queued", bytes=0,
                   total=0, cancellable=True, message="", _cancel=threading.Event(), _root=str(root))
        _jobs[job["id"]] = job
        return job


def extract_package(archive, destination, job):
    """Reject traversal, symlinks, ambiguous Windows paths and oversized ZIPs."""
    with zipfile.ZipFile(archive) as bundle:
        entries = bundle.infolist()
        if not entries or len(entries) > MAX_FILES or sum(x.file_size for x in entries) > MAX_EXPANDED:
            raise InstallError("Package exceeds the extraction limits.")
        destination.mkdir(parents=True, exist_ok=True)
        if shutil.disk_usage(destination).free < sum(x.file_size for x in entries) + 64 * CHUNK:
            raise InstallError("Not enough free space to extract this package. Change the storage folder in Settings.")
        seen, roots = set(), set()
        for info in entries:
            path = PurePosixPath(info.filename)
            parts = path.parts
            if (not parts or path.is_absolute() or "\\" in info.filename
                    or any(p in {".", ".."} or ":" in p or p.endswith((" ", ".")) for p in parts)
                    or any(re.fullmatch(r"(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?", p) for p in parts)):
                raise InstallError("Package contains an unsafe path.")
            key = path.as_posix().casefold()
            mode = info.external_attr >> 16
            if key in seen or (stat.S_IFMT(mode) not in {0, stat.S_IFREG, stat.S_IFDIR}):
                raise InstallError("Package contains duplicate paths or special files.")
            if info.flag_bits & 1:
                raise InstallError("Encrypted packages are not supported.")
            seen.add(key)
            roots.add(parts[0])
            if len(parts) < 2 and not info.is_dir():
                raise InstallError("ZIP must contain one dataset folder.")
        if len(roots) != 1:
            raise InstallError("ZIP must contain one dataset folder.")
        written = 0
        for info in entries:
            check_cancel(job)
            target = destination.joinpath(*PurePosixPath(info.filename).parts)
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(info) as source, target.open("xb") as output:
                while data := source.read(CHUNK):
                    check_cancel(job)
                    written += len(data)
                    if written > MAX_EXPANDED:
                        raise InstallError("Package exceeds the extraction limits.")
                    output.write(data)
    return destination / next(iter(roots))


def download(entry, token, target, job):
    """Use credentials only with api.github.com, never with asset redirects."""
    tag = f'{entry["dataset_id"]}-{entry["version"]}'
    filename = tag + ".zip"
    if shutil.disk_usage(target.parent).free < entry["archive_bytes"] + 64 * CHUNK:
        raise InstallError("Not enough free space for this download. Change the storage folder in Settings.")
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with httpx.Client(timeout=30, follow_redirects=False) as client:
        response = client.get(f"https://api.github.com/repos/{REPOSITORY}/releases/tags/{tag}", headers=headers)
        if response.status_code in {401, 403, 404}:
            raise InstallError("GitHub access failed. Check repository access and the token, or import a downloaded ZIP.")
        response.raise_for_status()
        asset = next((a for a in response.json().get("assets", []) if a.get("name") == filename), None)
        if not asset or not isinstance(asset.get("id"), int):
            raise InstallError("The reviewed release asset is unavailable.")
        url = f'https://api.github.com/repos/{REPOSITORY}/releases/assets/{asset["id"]}'
        headers["Accept"] = "application/octet-stream"
        progress(job, "downloading", total=entry["archive_bytes"])
        for _ in range(5):
            check_cancel(job)
            with client.stream("GET", url, headers=headers) as response:
                if response.is_redirect:
                    url = response.headers.get("location", "")
                    parsed = urlparse(url)
                    if (parsed.scheme != "https" or parsed.username or parsed.password
                            or not (parsed.hostname or "").endswith(".githubusercontent.com")
                            or parsed.port not in {None, 443}):
                        raise InstallError("Unexpected download redirect.")
                    headers = {}  # Never forward the token to asset storage.
                    continue
                response.raise_for_status()
                digest, size = hashlib.sha256(), 0
                with target.open("xb") as output:
                    for data in response.iter_bytes(CHUNK):
                        check_cancel(job)
                        size += len(data)
                        if size > entry["archive_bytes"] or size > MAX_ARCHIVE:
                            raise InstallError("Download exceeds its declared size.")
                        output.write(data)
                        digest.update(data)
                        progress(job, "downloading", bytes=size)
                if size != entry["archive_bytes"] or digest.hexdigest() != entry["archive_sha256"]:
                    raise InstallError("Downloaded archive does not match the catalogue checksum.")
                return digest.hexdigest()
        raise InstallError("Too many download redirects.")


def rollback(dataset_id, target):
    """Remove only this installer's still-disabled registration and owned files."""
    if dataset_id:
        with advisory_file_lock(datasets._registry_lock_path()):
            items = datasets._read_registry_unlocked()
            record = next((x for x in items if x["dataset_id"] == dataset_id), None)
            if record and (record["enabled"] or record["root_path"] != str(target)):
                return  # Another administrator took ownership; never delete their data.
            datasets._write_registry_unlocked([x for x in items if x["dataset_id"] != dataset_id])
        query_store.remove_dataset_query_store(dataset_id)
    if target and target.is_dir():
        shutil.rmtree(target)


def install(job, user, entry=None, token="", uploaded=None):
    target = None
    dataset_id = None
    try:
        ROOT.mkdir(parents=True, exist_ok=True)
        destination = Path(job["_root"]) if "_root" in job else import_root(ROOT)
        destination.mkdir(parents=True, exist_ok=True)
        # Serializes installations across multiple server processes too.
        with advisory_file_lock(ROOT / ".install.lock"), tempfile.TemporaryDirectory(dir=destination, prefix=".staging-") as staging:
            check_cancel(job)
            staging = Path(staging)
            archive = uploaded or staging / "download.zip"
            if entry and entry.get("install_mode") == "source":
                from app.geo_source import fetch_source
                from app.geo_gse85034 import build_package
                # Recipe selection is fixed in shipped code, never received from a client.
                progress(job, "downloading", message="Downloading the reviewed source files…")
                if entry["dataset_id"] == "gse85034":
                    source = staging / "GSE85034_series_matrix.txt.gz"
                    fetch_source(source, check_cancel=lambda: check_cancel(job),
                                 report=lambda **kw: progress(job, "downloading", **kw))
                    progress(job, "building", message="Preparing locally…")
                    build_package(source, archive, check_cancel=lambda: check_cancel(job),
                                  report=lambda **kw: progress(job, "building", **kw))
                else:
                    from app.source_builders import fetch, build
                    source = staging / "sources"
                    fetch(entry["dataset_id"], source, lambda: check_cancel(job),
                          lambda **kw: progress(job, "downloading", **kw))
                    progress(job, "building", message="Preparing locally…")
                    build(entry["dataset_id"], source, archive, lambda: check_cancel(job),
                          lambda **kw: progress(job, "building", **kw))
                with archive.open("rb") as handle:
                    digest = hashlib.file_digest(handle, "sha256").hexdigest()
            elif entry:
                digest = download(entry, token, archive, job)
            else:
                with archive.open("rb") as source:
                    digest = hashlib.file_digest(source, "sha256").hexdigest()
            token = ""  # Never persist credentials or include them in job metadata.
            # Same archive is never registered twice, even under a different filename.
            for record in datasets.list_registered_datasets():
                root = Path(record["root_path"])
                receipt = root / ".resource-install.json"
                if receipt.is_file() and json.loads(receipt.read_text()).get("sha256") == digest:
                    if record["enabled"]:
                        progress(job, "ready", dataset_id=record["dataset_id"], cancellable=False,
                                 already_installed=True,
                                 message="Already installed — no changes made. Select the existing dataset to add it to your workspace.")
                        return
                    if json.loads(receipt.read_text()).get("complete"):
                        raise InstallError("This package is installed but disabled. Enable it in Admin > Data.")
                    # Recover this installer's disabled entry after an interrupted process.
                    rollback(record["dataset_id"], root)
            progress(job, "validating", message="Validating package…")
            package = extract_package(archive, staging / "unpacked", job)
            resource = json.loads((package / "resource.json").read_text())
            if resource.get("manifest_version") != 1 or resource.get("schema_version") != 1:
                raise InstallError("Unsupported resource or dataset schema version.")
            if resource.get("dataset_id") in BUNDLED:
                raise InstallError("This dataset is already included with COHORTome. Select the bundled dataset instead.")
            if entry and any(resource.get(k) != entry[k] for k in ("dataset_id", "version")):
                raise InstallError("Package identity does not match the catalogue.")
            if not all(isinstance(resource.get(k), str) and resource[k].strip() for k in ("dataset_id", "version")):
                raise InstallError("Package must declare a dataset ID and resource version.")
            for record in datasets.list_registered_datasets():
                receipt = Path(record["root_path"]) / ".resource-install.json"
                if receipt.is_file():
                    previous = json.loads(receipt.read_text())
                    if all(previous.get(k) == resource[k] for k in ("dataset_id", "version")):
                        raise InstallError("This resource version is already registered with different archive bytes. Use a new version for changed content.")
            validation = validate_package(package)
            check_cancel(job)
            # Once database preparation starts, finish or roll back; do not kill DuckDB mid-write.
            with _lock:
                check_cancel(job)
                job.update(stage="preparing", cancellable=False,
                           message="Preparing database… You can continue using the app.")
            target = destination / "installed" / job["id"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(package), target)
            from app.state_io import atomic_write_json
            atomic_write_json(target / ".resource-install.json", {
                "sha256": digest, "dataset_id": resource.get("dataset_id"),
                "version": resource.get("version"), "validation": validation,
                **({"source_review": job["_source_review"]} if job.get("_source_review") else {}),
            })
            name = entry["name"] if entry else str(resource.get("dataset_id") or "Imported dataset")[:120]
            record = datasets.register_dataset(
                name=name, root_path=str(target), description=f'Imported resource {resource.get("version", "")}',
                visibility="admin_only", data_classification="private",
                query_granularity_ceiling="detailed", ai_provider_access="blocked",
                enabled=False, created_by=user,
            )
            dataset_id = record["dataset_id"]
            query_store.prepare_dataset_query_store(dataset_id)
            receipt = target / ".resource-install.json"
            atomic_write_json(receipt, {**json.loads(receipt.read_text()), "complete": True})
            datasets.update_dataset(dataset_id, enabled=True)
            progress(job, "ready", dataset_id=dataset_id, cancellable=False,
                     message="Ready. Select it in Datasets to add it to your workspace.")
    except Cancelled:
        rollback(dataset_id, target)
        progress(job, "cancelled", cancellable=False, message="Installation cancelled.")
    except Exception as exc:
        try:
            rollback(dataset_id, target)
        except Exception:
            progress(job, "failed", cancellable=False,
                     message="Installation failed and cleanup could not finish. Check storage access before retrying.")
            return
        # Do not leak source paths, credentials, response bodies or clinical validation values.
        progress(job, "failed", cancellable=False,
                 message=str(exc) if isinstance(exc, (InstallError, SourcePreparationError)) else
                 "Source download or local preparation failed. Check network access, storage and the preparation tools, then retry."
                 if entry and entry.get("install_mode") == "source" else
                 "Installation failed. Check that the ZIP is a valid COHORTome resource package and that storage is available. You can retry.")
    finally:
        if uploaded:
            uploaded.unlink(missing_ok=True)


@router.get("")
def list_resources(request: Request):
    require_admin(request)
    return {"resources": [{**entry, "included": entry["dataset_id"] in BUNDLED} for entry in catalogue()],
            "repository": REPOSITORY}


@router.get("/jobs")
def list_jobs(request: Request):
    require_admin(request)
    with _lock:
        jobs = list(_jobs.values())
    return {"jobs": [snapshot(job) for job in jobs]}


@router.post("/download", status_code=202)
def start_download(payload: DownloadRequest, request: Request):
    user = require_admin(request)
    token = payload.github_token.get_secret_value()
    if len(token) > 512 or any(c.isspace() for c in token):
        raise HTTPException(400, "Invalid GitHub token format.")
    entry = next((x for x in catalogue() if x["dataset_id"] == payload.dataset_id), None)
    if not entry:
        raise HTTPException(404, "Resource is not in the reviewed catalogue.")
    if entry["dataset_id"] in BUNDLED:
        raise HTTPException(409, "This dataset is already included with COHORTome. Select the bundled dataset instead.")
    if entry.get("install_mode") == "source":
        if not payload.source_terms_acknowledged:
            raise HTTPException(400, "Review the source terms before downloading data.")
        from app.geo_gse85034 import preflight
        try:
            preflight()
        except SourcePreparationError as exc:
            raise HTTPException(400, str(exc)) from None
        token = ""
    job = new_job(entry["name"])
    if entry.get("install_mode") == "source":
        job["_source_review"] = {
            "acknowledged_at": datetime.now(timezone.utc).isoformat(),
            "acknowledged_by": user["username"],
            "dataset_id": entry["dataset_id"], "version": entry["version"],
            "recipe_version": entry["recipe_version"],
            "statement": entry["review_statement"], "source_page": entry["source_page"],
            "source_policy_url": entry["source_policy_url"], "notice": entry["terms"],
            "additional_source_links": entry.get("additional_source_links", []),
        }
    _pool.submit(install, job, user["username"], entry, token)
    return snapshot(job)


@router.post("/upload", status_code=202)
async def upload(request: Request):
    user = require_admin(request)
    if request.headers.get("content-type") != "application/zip":
        raise HTTPException(415, "Upload a ZIP with Content-Type application/zip.")
    job = new_job("Local package")
    destination = Path(job["_root"])
    path = destination / f".upload-{job['id']}.zip"
    size = 0
    try:
        destination.mkdir(parents=True, exist_ok=True)
        progress(job, "uploading")
        with path.open("xb") as output:
            async for data in request.stream():
                check_cancel(job)
                size += len(data)
                if size > MAX_ARCHIVE:
                    raise HTTPException(413, "ZIP exceeds the 1 GiB upload limit.")
                output.write(data)
                progress(job, "uploading", bytes=size)
        _pool.submit(install, job, user["username"], uploaded=path)
        return snapshot(job)
    except BaseException:
        path.unlink(missing_ok=True)
        progress(job, "cancelled", cancellable=False, message="Upload stopped. You can retry.")
        raise


@router.post("/jobs/{job_id}/cancel")
def cancel(job_id: str, request: Request):
    require_admin(request)
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            raise HTTPException(404, "Installation not found.")
        if not job["cancellable"]:
            raise HTTPException(409, "Database preparation has started; wait for it to finish.")
        job["_cancel"].set()
    return snapshot(job)
