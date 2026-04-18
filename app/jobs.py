from __future__ import annotations

import json
import os
import shutil
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4

from fastapi import HTTPException

from app.user_state import normalize_user_id, user_state_dir


JOB_RECORD_FILENAME = "job.json"
JOB_RESULT_FILENAME = "result.json"
JOB_LOG_FILENAMES = {
    "stdout": "stdout.txt",
    "stderr": "stderr.txt",
    "command": "command.txt",
    "error": "error.txt",
}
JOB_STATUS_PRECEDENCE = {"queued": 0, "running": 1, "completed": 2, "failed": 3, "cancelled": 4}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def jobs_enabled() -> bool:
    try:
        import redis  # noqa: F401
        import rq  # noqa: F401
    except Exception:
        return False
    return True


def jobs_queue_name() -> str:
    return str(os.getenv("PN_JOBS_QUEUE_NAME", "analysis")).strip() or "analysis"


def jobs_redis_url() -> str:
    return str(os.getenv("PN_JOBS_REDIS_URL", "redis://127.0.0.1:6379/0")).strip() or "redis://127.0.0.1:6379/0"


def jobs_default_timeout_seconds() -> int:
    raw = str(os.getenv("PN_JOBS_DEFAULT_TIMEOUT_SECONDS", "1800")).strip()
    try:
        return max(30, int(raw))
    except ValueError:
        return 1800


def user_jobs_root(user_id: str) -> Path:
    path = user_state_dir(user_id) / "jobs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def job_dir(job_id: str, user_id: str, *, create: bool = False) -> Path:
    safe_user = normalize_user_id(user_id)
    safe_job = Path(str(job_id or "")).name
    path = (user_jobs_root(safe_user) / safe_job).resolve()
    root = user_jobs_root(safe_user).resolve()
    if path != root and root not in path.parents:
        raise HTTPException(status_code=404, detail="Job not found.")
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def job_record_path(job_id: str, user_id: str, *, create: bool = False) -> Path:
    return job_dir(job_id, user_id, create=create) / JOB_RECORD_FILENAME


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _artifact_inventory(path: Path) -> List[Dict[str, Any]]:
    artifacts: List[Dict[str, Any]] = []
    if not path.exists() or not path.is_dir():
        return artifacts
    for item in sorted(path.iterdir()):
        if not item.is_file():
            continue
        if item.name == JOB_RECORD_FILENAME:
            continue
        artifacts.append(
            {
                "name": item.name,
                "size": item.stat().st_size,
                "content_type": "application/json" if item.suffix == ".json" else "text/plain",
            }
        )
    return artifacts


def create_job_record(
    *,
    job_type: str,
    user_id: str,
    data: Dict[str, Any],
) -> Dict[str, Any]:
    job_id = uuid4().hex
    now = _now_iso()
    record = {
        "job_id": job_id,
        "job_type": str(job_type or "").strip() or "analysis",
        "submitted_by": normalize_user_id(user_id),
        "status": "queued",
        "submitted_at": now,
        "started_at": "",
        "completed_at": "",
        "updated_at": now,
        "error": "",
        "reply_preview": "",
        "result_available": False,
        "artifacts": [],
        **dict(data or {}),
    }
    _write_json(job_record_path(job_id, user_id, create=True), record)
    return record


def load_job_record(job_id: str, user_id: str) -> Dict[str, Any]:
    record = _read_json(job_record_path(job_id, user_id))
    if not record:
        raise HTTPException(status_code=404, detail="Job not found.")
    return record


def save_job_record(job_id: str, user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    record = dict(payload or {})
    record["job_id"] = str(record.get("job_id") or job_id).strip() or str(job_id)
    record["submitted_by"] = normalize_user_id(str(record.get("submitted_by") or user_id))
    record["updated_at"] = _now_iso()
    record["artifacts"] = _artifact_inventory(job_dir(job_id, user_id, create=True))
    _write_json(job_record_path(job_id, user_id, create=True), record)
    return record


def update_job_record(job_id: str, user_id: str, **updates: Any) -> Dict[str, Any]:
    record = load_job_record(job_id, user_id)
    record.update(updates)
    return save_job_record(job_id, user_id, record)


def list_job_records(user_id: str) -> List[Dict[str, Any]]:
    root = user_jobs_root(user_id)
    items: List[Dict[str, Any]] = []
    for path in sorted(root.iterdir(), reverse=True):
        if not path.is_dir():
            continue
        record = _read_json(path / JOB_RECORD_FILENAME)
        if not record:
            continue
        record["artifacts"] = _artifact_inventory(path)
        items.append(record)
    items.sort(
        key=lambda item: (
            str(item.get("updated_at") or ""),
            JOB_STATUS_PRECEDENCE.get(str(item.get("status") or ""), -1),
        ),
        reverse=True,
    )
    return items


def list_jobs_for_analysis_session(session_id: str, user_id: str) -> List[Dict[str, Any]]:
    wanted = str(session_id or "").strip()
    if not wanted:
        return []
    return [
        item
        for item in list_job_records(user_id)
        if str(item.get("analysis_session_id") or "").strip() == wanted
    ]


def delete_job(job_id: str, user_id: str) -> bool:
    record = load_job_record(job_id, user_id)
    status = str(record.get("status") or "").strip().lower()
    if status not in {"completed", "failed", "cancelled"}:
        raise HTTPException(status_code=409, detail="Only terminal jobs can be deleted.")
    path = job_dir(job_id, user_id)
    if not path.exists():
        return False
    shutil.rmtree(path)
    return True


def job_result_path(job_id: str, user_id: str) -> Path:
    return job_dir(job_id, user_id) / JOB_RESULT_FILENAME


def load_job_result(job_id: str, user_id: str) -> Dict[str, Any] | None:
    payload = _read_json(job_result_path(job_id, user_id))
    return payload or None


def save_job_result(job_id: str, user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    _write_json(job_result_path(job_id, user_id), payload)
    return payload


def resolve_job_artifact_path(job_id: str, user_id: str, filename: str) -> Path:
    root = job_dir(job_id, user_id)
    safe_name = Path(str(filename or "")).name
    path = (root / safe_name).resolve()
    if root not in path.parents:
        raise HTTPException(status_code=404, detail="Job artifact not found.")
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Job artifact not found.")
    return path


def public_job_payload(record: Dict[str, Any], *, include_result: bool = False, user_id: str = "") -> Dict[str, Any]:
    payload = {
        "job_id": str(record.get("job_id") or "").strip(),
        "job_type": str(record.get("job_type") or "").strip(),
        "feature": str(record.get("feature") or "").strip(),
        "status": str(record.get("status") or "").strip(),
        "submitted_at": str(record.get("submitted_at") or "").strip(),
        "started_at": str(record.get("started_at") or "").strip(),
        "completed_at": str(record.get("completed_at") or "").strip(),
        "updated_at": str(record.get("updated_at") or "").strip(),
        "name": str(record.get("name") or "").strip(),
        "prompt": str(record.get("prompt") or "").strip(),
        "dataset_id": str(record.get("dataset_id") or "").strip(),
        "analysis_session_id": str(record.get("analysis_session_id") or "").strip(),
        "catalog_item_id": str(record.get("catalog_item_id") or "").strip(),
        "catalog_item_name": str(record.get("catalog_item_name") or "").strip(),
        "runner_type": str(record.get("runner_type") or "").strip(),
        "runner_ref": str(record.get("runner_ref") or "").strip(),
        "execution_backend": str(record.get("execution_backend") or "").strip(),
        "reply_preview": str(record.get("reply_preview") or "").strip(),
        "error": str(record.get("error") or "").strip(),
        "result_available": bool(record.get("result_available")),
        "artifacts": [],
    }
    for artifact in list(record.get("artifacts") or []):
        item = dict(artifact or {})
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        payload["artifacts"].append(
            {
                **item,
                "url": f"/jobs/{payload['job_id']}/artifacts/{name}",
            }
        )
    if include_result and payload["result_available"] and user_id:
        payload["result_payload"] = load_job_result(payload["job_id"], user_id)
    return payload


def _rq_connection():
    from redis import Redis

    return Redis.from_url(jobs_redis_url())


def _rq_queue():
    from rq import Queue

    return Queue(jobs_queue_name(), connection=_rq_connection())


def enqueue_analysis_job(job_id: str, user_id: str, timeout_seconds: int) -> str:
    queue = _rq_queue()
    rq_job = queue.enqueue(
        run_analysis_job,
        job_id,
        user_id,
        job_timeout=timeout_seconds,
        result_ttl=86400,
        failure_ttl=604800,
    )
    return str(rq_job.id)


def submit_analysis_job(
    *,
    user_id: str,
    analysis_session_id: str,
    prompt: str,
    data_dir: str,
    dataset_id: str,
    catalog_item: Dict[str, Any],
    selected_patient_ids: str = "",
    compare_selected_patient_ids: str = "",
    compare_mode: bool = False,
) -> Dict[str, Any]:
    if not jobs_enabled():
        raise RuntimeError("Background jobs require RQ and Redis to be installed and configured.")
    timeout_seconds = int(catalog_item.get("job_timeout_seconds") or jobs_default_timeout_seconds())
    record = create_job_record(
        job_type="analysis",
        user_id=user_id,
        data={
            "feature": "analysis",
            "name": str(catalog_item.get("name") or "").strip() or "Analysis job",
            "prompt": str(prompt or "").strip(),
            "dataset_id": str(dataset_id or "").strip(),
            "data_dir": str(data_dir or "").strip(),
            "analysis_session_id": str(analysis_session_id or "").strip(),
            "catalog_item_id": str(catalog_item.get("id") or "").strip(),
            "catalog_item_name": str(catalog_item.get("name") or "").strip(),
            "runner_type": str(catalog_item.get("runner_type") or "").strip(),
            "runner_ref": str(catalog_item.get("runner_ref") or "").strip(),
            "execution_backend": str(catalog_item.get("execution_backend") or "job").strip(),
            "expected_runtime": str(catalog_item.get("expected_runtime") or "").strip(),
            "job_timeout_seconds": timeout_seconds,
            "job_priority": str(catalog_item.get("job_priority") or "").strip() or "normal",
            "selected_patient_ids": str(selected_patient_ids or "").strip(),
            "compare_selected_patient_ids": str(compare_selected_patient_ids or "").strip(),
            "compare_mode": bool(compare_mode),
        },
    )
    try:
        rq_job_id = enqueue_analysis_job(record["job_id"], user_id, timeout_seconds)
    except Exception as exc:
        update_job_record(record["job_id"], user_id, status="failed", error=str(exc))
        raise RuntimeError(f"Unable to submit background job. {exc}") from exc
    record = update_job_record(record["job_id"], user_id, rq_job_id=rq_job_id)
    return public_job_payload(record, user_id=user_id)


def run_analysis_job(job_id: str, user_id: str) -> Dict[str, Any]:
    record = load_job_record(job_id, user_id)
    update_job_record(job_id, user_id, status="running", started_at=_now_iso(), error="")
    try:
        from app.analysis_catalog import get_analysis_catalog_item
        from app.analysis_external import run_rscript_analysis

        catalog_item_id = str(record.get("catalog_item_id") or "").strip()
        item = get_analysis_catalog_item(catalog_item_id)
        if not item:
            raise RuntimeError(f"Unknown analysis catalog item '{catalog_item_id}'.")
        runner_type = str(item.get("runner_type") or "").strip().lower()
        if runner_type != "rscript":
            raise RuntimeError(f"Queued execution is not supported for runner type '{runner_type}'.")
        payload = run_rscript_analysis(
            str(item.get("runner_ref") or "").strip(),
            prompt=str(record.get("prompt") or ""),
            data_dir=str(record.get("data_dir") or ""),
            selected_patient_ids=str(record.get("selected_patient_ids") or ""),
            compare_selected_patient_ids=str(record.get("compare_selected_patient_ids") or ""),
            job_dir=job_dir(job_id, user_id, create=True),
            timeout_seconds=int(record.get("job_timeout_seconds") or jobs_default_timeout_seconds()),
        )
        payload.setdefault("data", {})
        payload["data"]["catalog_item_id"] = catalog_item_id
        payload["data"]["catalog_item_name"] = str(item.get("name") or "").strip()
        payload["data"]["job_id"] = job_id
        payload["data"]["job_status"] = "completed"
        save_job_result(job_id, user_id, payload)
        record = update_job_record(
            job_id,
            user_id,
            status="completed",
            completed_at=_now_iso(),
            result_available=True,
            reply_preview=str(payload.get("reply") or "")[:280],
            error="",
        )
        return public_job_payload(record, include_result=True, user_id=user_id)
    except Exception as exc:
        error_text = str(exc).strip() or "Background analysis job failed."
        path = job_dir(job_id, user_id, create=True) / JOB_LOG_FILENAMES["error"]
        path.write_text(error_text + "\n\n" + traceback.format_exc(), encoding="utf-8")
        record = update_job_record(
            job_id,
            user_id,
            status="failed",
            completed_at=_now_iso(),
            error=error_text,
        )
        return public_job_payload(record, user_id=user_id)
