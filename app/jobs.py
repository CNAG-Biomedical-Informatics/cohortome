from __future__ import annotations

import json
import os
import shutil
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List
from uuid import uuid4

from fastapi import HTTPException

from app.analysis_sessions import get_analysis_session
from app.user_state import normalize_user_id, user_state_dir
from app.env import app_env


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
    return str(app_env("BRN_JOBS_QUEUE_NAME", "analysis")).strip() or "analysis"


def jobs_redis_url() -> str:
    return str(app_env("BRN_JOBS_REDIS_URL", "redis://127.0.0.1:6379/0")).strip() or "redis://127.0.0.1:6379/0"


def jobs_default_timeout_seconds() -> int:
    raw = str(app_env("BRN_JOBS_DEFAULT_TIMEOUT_SECONDS", "1800")).strip()
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


def job_code(job_id: str) -> str:
    normalized = str(job_id or "").strip().replace("-", "")
    if not normalized:
        return ""
    return f"Job {normalized[:8].upper()}"


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
    for item in sorted(path.rglob("*")):
        if not item.is_file():
            continue
        relative_name = item.relative_to(path).as_posix()
        if relative_name == JOB_RECORD_FILENAME:
            continue
        artifacts.append(
            {
                "name": relative_name,
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


def _load_job_record_raw(job_id: str, user_id: str) -> Dict[str, Any]:
    record = _read_json(job_record_path(job_id, user_id))
    if not record:
        raise HTTPException(status_code=404, detail="Job not found.")
    return record


def _coerce_iso_datetime(value: Any) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc).isoformat()
        return value.astimezone(timezone.utc).isoformat()
    text = str(value or "").strip()
    return text


def _job_result_exists(job_id: str, user_id: str) -> bool:
    return job_result_path(job_id, user_id).exists()


def _job_reply_preview(job_id: str, user_id: str) -> str:
    payload = load_job_result(job_id, user_id) or {}
    return str(payload.get("reply") or "").strip()[:280]


def _feature_job_label(record: Dict[str, Any]) -> str:
    feature = str(record.get("feature") or "").strip().lower()
    if feature == "pheno":
        return "Pheno-Ranker"
    return "analysis"


def _rq_failure_message(record: Dict[str, Any], rq_status: str, exc_info: str = "") -> str:
    summary_lines = [line.strip() for line in str(exc_info or "").splitlines() if line.strip()]
    if summary_lines:
        last_line = summary_lines[-1]
        if len(last_line) <= 280:
            return last_line
    label = _feature_job_label(record)
    if rq_status in {"stopped", "canceled", "cancelled"}:
        return f"Background {label} job was cancelled before completion."
    if rq_status == "finished":
        return f"Background {label} job finished in RQ but did not persist a result payload."
    return f"Background {label} job failed before completion."


def _reconcile_active_job_record(record: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    status = str(record.get("status") or "").strip().lower()
    if status not in {"queued", "running"}:
        return record
    job_id = str(record.get("job_id") or "").strip()
    if not job_id:
        return record
    result_exists = _job_result_exists(job_id, user_id)
    rq_job_id = str(record.get("rq_job_id") or "").strip()

    def persist(**updates: Any) -> Dict[str, Any]:
        merged = dict(record)
        merged.update(updates)
        return save_job_record(job_id, user_id, merged)

    if result_exists and not rq_job_id:
        return persist(
            status="completed",
            completed_at=str(record.get("completed_at") or "").strip() or _now_iso(),
            result_available=True,
            reply_preview=_job_reply_preview(job_id, user_id),
            error="",
        )
    if not rq_job_id:
        return record

    if not jobs_enabled():
        return record

    try:
        from rq.exceptions import NoSuchJobError
        from rq.job import Job

        connection = _rq_connection()
        connection.ping()
        rq_job = Job.fetch(rq_job_id, connection=connection)
        rq_status_raw = rq_job.get_status(refresh=True)
        rq_status = str(getattr(rq_status_raw, "value", rq_status_raw) or "").strip().lower()
    except Exception as exc:
        no_such_job = False
        try:
            from rq.exceptions import NoSuchJobError

            no_such_job = isinstance(exc, NoSuchJobError)
        except Exception:
            no_such_job = False
        if result_exists:
            return persist(
                status="completed",
                completed_at=str(record.get("completed_at") or "").strip() or _now_iso(),
                result_available=True,
                reply_preview=_job_reply_preview(job_id, user_id),
                error="",
            )
        if no_such_job and status == "running":
            return persist(
                status="failed",
                completed_at=str(record.get("completed_at") or "").strip() or _now_iso(),
                error="Background worker exited before the job record was finalized.",
            )
        return record

    started_at = _coerce_iso_datetime(getattr(rq_job, "started_at", ""))
    ended_at = _coerce_iso_datetime(getattr(rq_job, "ended_at", "")) or _now_iso()

    if rq_status in {"started", "running"}:
        updates: Dict[str, Any] = {}
        if status != "running":
            updates["status"] = "running"
        if started_at and started_at != str(record.get("started_at") or "").strip():
            updates["started_at"] = started_at
        if updates:
            return persist(**updates)
        return record
    if rq_status in {"queued", "scheduled", "deferred"}:
        updates = {}
        if status != "queued":
            updates["status"] = "queued"
        if updates:
            return persist(**updates)
        return record
    if rq_status == "finished":
        if result_exists:
            return persist(
                status="completed",
                started_at=started_at or str(record.get("started_at") or "").strip(),
                completed_at=str(record.get("completed_at") or "").strip() or ended_at,
                result_available=True,
                reply_preview=_job_reply_preview(job_id, user_id),
                error="",
            )
        return persist(
            status="failed",
            started_at=started_at or str(record.get("started_at") or "").strip(),
            completed_at=str(record.get("completed_at") or "").strip() or ended_at,
            error=_rq_failure_message(record, rq_status),
        )
    if rq_status in {"failed", "stopped", "canceled", "cancelled"}:
        return persist(
            status="cancelled" if rq_status in {"stopped", "canceled", "cancelled"} else "failed",
            started_at=started_at or str(record.get("started_at") or "").strip(),
            completed_at=str(record.get("completed_at") or "").strip() or ended_at,
            error=_rq_failure_message(record, rq_status, getattr(rq_job, "exc_info", "")),
        )
    return record


def load_job_record(job_id: str, user_id: str) -> Dict[str, Any]:
    record = _load_job_record_raw(job_id, user_id)
    return _reconcile_active_job_record(record, user_id)


def save_job_record(job_id: str, user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    record = dict(payload or {})
    record["job_id"] = str(record.get("job_id") or job_id).strip() or str(job_id)
    record["submitted_by"] = normalize_user_id(str(record.get("submitted_by") or user_id))
    record["updated_at"] = _now_iso()
    record["artifacts"] = _artifact_inventory(job_dir(job_id, user_id, create=True))
    _write_json(job_record_path(job_id, user_id, create=True), record)
    return record


def update_job_record(job_id: str, user_id: str, **updates: Any) -> Dict[str, Any]:
    record = _load_job_record_raw(job_id, user_id)
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
        record = _reconcile_active_job_record(record, user_id)
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


def _job_retention_timestamp(record: Dict[str, Any]) -> datetime | None:
    for key in ("completed_at", "updated_at", "submitted_at"):
        text = str(record.get(key) or "").strip()
        if not text:
            continue
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            continue
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    return None


def delete_expired_terminal_jobs(user_id: str, retention_days: int) -> int:
    try:
        days = int(retention_days)
    except (TypeError, ValueError):
        return 0
    if days <= 0:
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    deleted_count = 0
    for item in list_job_records(user_id):
        if not terminal_job_status(item.get("status")):
            continue
        timestamp = _job_retention_timestamp(item)
        if timestamp is None or timestamp >= cutoff:
            continue
        job_id = str(item.get("job_id") or "").strip()
        if job_id and delete_job(job_id, user_id):
            deleted_count += 1
    return deleted_count


def list_jobs_for_analysis_session(session_id: str, user_id: str) -> List[Dict[str, Any]]:
    wanted = str(session_id or "").strip()
    if not wanted:
        return []
    return [
        item
        for item in list_job_records(user_id)
        if str(item.get("analysis_session_id") or "").strip() == wanted
    ]


def active_feature_job(user_id: str, feature: str) -> Dict[str, Any] | None:
    wanted = str(feature or "").strip()
    if not wanted:
        return None
    for item in list_job_records(user_id):
        if str(item.get("feature") or "").strip() != wanted:
            continue
        if str(item.get("status") or "").strip() not in {"queued", "running"}:
            continue
        return item
    return None


def next_run_number_for_analysis_session(session_id: str, user_id: str) -> int:
    existing = list_jobs_for_analysis_session(session_id, user_id)
    numeric_values: List[int] = []
    for item in existing:
        try:
            value = int(item.get("run_number") or 0)
        except (TypeError, ValueError):
            value = 0
        if value > 0:
            numeric_values.append(value)
    if numeric_values:
        return max(numeric_values) + 1
    return len(existing) + 1 if existing else 1


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


def terminal_job_status(value: Any) -> bool:
    return str(value or "").strip().lower() in {"completed", "failed", "cancelled"}


def active_job_status(value: Any) -> bool:
    return str(value or "").strip().lower() in {"queued", "running"}


def job_result_path(job_id: str, user_id: str) -> Path:
    return job_dir(job_id, user_id) / JOB_RESULT_FILENAME


def load_job_result(job_id: str, user_id: str) -> Dict[str, Any] | None:
    payload = _read_json(job_result_path(job_id, user_id))
    return payload or None


def save_job_result(job_id: str, user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    _write_json(job_result_path(job_id, user_id), payload)
    return payload


def resolve_job_artifact_path(job_id: str, user_id: str, filename: str) -> Path:
    root = job_dir(job_id, user_id).resolve()
    raw_name = str(filename or "").strip().lstrip("/")
    path = (root / raw_name).resolve()
    if path == root or root not in path.parents:
        raise HTTPException(status_code=404, detail="Job artifact not found.")
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Job artifact not found.")
    return path


def public_job_payload(record: Dict[str, Any], *, include_result: bool = False, user_id: str = "") -> Dict[str, Any]:
    normalized_job_id = str(record.get("job_id") or "").strip()
    payload = {
        "job_id": normalized_job_id,
        "job_code": job_code(normalized_job_id),
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
        "molecular_dataset_name": str(record.get("molecular_dataset_name") or "").strip(),
        "analysis_session_id": str(record.get("analysis_session_id") or "").strip(),
        "analysis_session_title": str(record.get("analysis_session_title") or "").strip(),
        "run_number": int(record.get("run_number") or 0) if str(record.get("run_number") or "").strip() else 0,
        "action": str(record.get("action") or "").strip(),
        "mode": str(record.get("mode") or "").strip(),
        "patient_id": str(record.get("patient_id") or "").strip(),
        "selected_patient_ids": str(record.get("selected_patient_ids") or "").strip(),
        "selected_saved_cohort_ids": list(record.get("selected_saved_cohort_ids") or []),
        "include_terms": list(record.get("include_terms") or []),
        "exclude_terms": list(record.get("exclude_terms") or []),
        "similarity_metric_cohort": str(record.get("similarity_metric_cohort") or "").strip(),
        "sort_by": str(record.get("sort_by") or "").strip(),
        "max_out": int(record.get("max_out") or 0) if str(record.get("max_out") or "").strip() else 0,
        "align": bool(record.get("align")),
        "render_heatmap": bool(record.get("render_heatmap")),
        "render_mds": bool(record.get("render_mds")),
        "render_graph": bool(record.get("render_graph")),
        "graph_min_weight": record.get("graph_min_weight"),
        "graph_max_weight": record.get("graph_max_weight"),
        "resolved_sample_count": int(record.get("resolved_sample_count") or 0) if str(record.get("resolved_sample_count") or "").strip() else 0,
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


def analysis_worker_available() -> bool:
    if not jobs_enabled():
        return False
    try:
        from rq import Worker

        connection = _rq_connection()
        connection.ping()
        wanted_queue = jobs_queue_name()
        for worker in Worker.all(connection=connection):
            queue_names: List[str] = []
            queue_names_method = getattr(worker, "queue_names", None)
            if callable(queue_names_method):
                try:
                    queue_names = [str(name or "").strip() for name in queue_names_method()]
                except Exception:
                    queue_names = []
            if not queue_names:
                queue_objects = getattr(worker, "queues", None) or []
                queue_names = [str(getattr(queue, "name", "") or "").strip() for queue in queue_objects]
            if wanted_queue in queue_names:
                return True
    except Exception:
        return False
    return False


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


def enqueue_pheno_job(job_id: str, user_id: str, timeout_seconds: int) -> str:
    queue = _rq_queue()
    rq_job = queue.enqueue(
        run_pheno_job,
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
    molecular_dataset_name: str,
    catalog_item: Dict[str, Any],
    selected_patient_ids: str = "",
    compare_selected_patient_ids: str = "",
    compare_mode: bool = False,
) -> Dict[str, Any]:
    if not jobs_enabled():
        raise RuntimeError("Background jobs require RQ and Redis to be installed and configured.")
    if not analysis_worker_available():
        raise RuntimeError("Background jobs are currently unavailable because no background worker is running.")
    timeout_seconds = int(catalog_item.get("job_timeout_seconds") or jobs_default_timeout_seconds())
    normalized_session_id = str(analysis_session_id or "").strip()
    session = get_analysis_session(normalized_session_id, user_id=user_id) if normalized_session_id else None
    session_title = str(session.get("title") or "").strip() if session else ""
    run_number = next_run_number_for_analysis_session(normalized_session_id, user_id) if normalized_session_id else 0
    record = create_job_record(
        job_type="analysis",
        user_id=user_id,
        data={
            "feature": "analysis",
            "name": str(catalog_item.get("name") or "").strip() or "Analysis job",
            "prompt": str(prompt or "").strip(),
            "dataset_id": str(dataset_id or "").strip(),
            "molecular_dataset_name": str(molecular_dataset_name or "").strip(),
            "data_dir": str(data_dir or "").strip(),
            "analysis_session_id": normalized_session_id,
            "analysis_session_title": session_title,
            "run_number": run_number,
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


def submit_pheno_job(
    *,
    user_id: str,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    if not jobs_enabled():
        raise RuntimeError("Background jobs require RQ and Redis to be installed and configured.")
    if not analysis_worker_available():
        raise RuntimeError("Background jobs are currently unavailable because no background worker is running.")
    active = active_feature_job(user_id, "pheno")
    if active:
        label = str(active.get("job_code") or job_code(str(active.get("job_id") or "")) or "").strip()
        if label:
            raise RuntimeError(f"A Pheno-Ranker background run is already in progress ({label}).")
        raise RuntimeError("A Pheno-Ranker background run is already in progress.")
    timeout_seconds = int(payload.get("job_timeout_seconds") or jobs_default_timeout_seconds())
    record = create_job_record(
        job_type="pheno",
        user_id=user_id,
        data={
            "feature": "pheno",
            "name": str(payload.get("name") or "").strip() or "Pheno-Ranker background run",
            "prompt": str(payload.get("prompt") or "").strip(),
            "dataset_id": str(payload.get("dataset_id") or "").strip(),
            "data_dir": str(payload.get("data_dir") or "").strip(),
            "action": str(payload.get("action") or "").strip(),
            "mode": str(payload.get("mode") or "").strip(),
            "patient_id": str(payload.get("patient_id") or "").strip(),
            "selected_patient_ids": str(payload.get("selected_patient_ids") or "").strip(),
            "selected_saved_cohort_ids": list(payload.get("selected_saved_cohort_ids") or []),
            "disease_filter": str(payload.get("disease_filter") or "").strip(),
            "include_terms": list(payload.get("include_terms") or []),
            "exclude_terms": list(payload.get("exclude_terms") or []),
            "similarity_metric_cohort": str(payload.get("similarity_metric_cohort") or "").strip(),
            "sort_by": str(payload.get("sort_by") or "").strip(),
            "max_out": int(payload.get("max_out") or 0),
            "align": bool(payload.get("align")),
            "render_heatmap": bool(payload.get("render_heatmap")),
            "render_mds": bool(payload.get("render_mds")),
            "render_graph": bool(payload.get("render_graph")),
            "graph_min_weight": payload.get("graph_min_weight"),
            "graph_max_weight": payload.get("graph_max_weight"),
            "granularity_ceiling": str(payload.get("granularity_ceiling") or "").strip(),
            "ai_provider_access": str(payload.get("ai_provider_access") or "").strip(),
            "resolved_sample_count": int(payload.get("resolved_sample_count") or 0),
            "execution_backend": "job",
            "job_timeout_seconds": timeout_seconds,
            "job_priority": str(payload.get("job_priority") or "").strip() or "normal",
        },
    )
    try:
        rq_job_id = enqueue_pheno_job(record["job_id"], user_id, timeout_seconds)
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
        from app.analysis_external import run_external_analysis

        catalog_item_id = str(record.get("catalog_item_id") or "").strip()
        item = get_analysis_catalog_item(catalog_item_id)
        if not item:
            raise RuntimeError(f"Unknown analysis catalog item '{catalog_item_id}'.")
        runner_type = str(item.get("runner_type") or "").strip().lower()
        if runner_type not in {"rscript", "snakemake", "nextflow", "workflow"}:
            raise RuntimeError(f"Queued execution is not supported for runner type '{runner_type}'.")
        payload = run_external_analysis(
            runner_type,
            str(item.get("runner_ref") or "").strip(),
            prompt=str(record.get("prompt") or ""),
            data_dir=str(record.get("data_dir") or ""),
            molecular_dataset_name=str(record.get("molecular_dataset_name") or ""),
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


def run_pheno_job(job_id: str, user_id: str) -> Dict[str, Any]:
    record = load_job_record(job_id, user_id)
    update_job_record(job_id, user_id, status="running", started_at=_now_iso(), error="")
    try:
        from app.pheno import run_pheno_ranker

        request = SimpleNamespace(
            prompt=str(record.get("prompt") or ""),
            action=str(record.get("action") or "compare"),
            mode=str(record.get("mode") or "cohort"),
            dataset_id=str(record.get("dataset_id") or ""),
            data_dir=str(record.get("data_dir") or ""),
            patient_id=str(record.get("patient_id") or ""),
            selected_patient_ids=str(record.get("selected_patient_ids") or ""),
            selected_saved_cohort_ids=list(record.get("selected_saved_cohort_ids") or []),
            disease_filter=str(record.get("disease_filter") or ""),
            include_terms=list(record.get("include_terms") or []),
            exclude_terms=list(record.get("exclude_terms") or []),
            similarity_metric_cohort=str(record.get("similarity_metric_cohort") or ""),
            sort_by=str(record.get("sort_by") or ""),
            max_out=int(record.get("max_out") or 0),
            align=bool(record.get("align")),
            render_heatmap=bool(record.get("render_heatmap")),
            render_mds=bool(record.get("render_mds")),
            render_graph=bool(record.get("render_graph")),
            graph_min_weight=record.get("graph_min_weight"),
            graph_max_weight=record.get("graph_max_weight"),
            granularity_ceiling=str(record.get("granularity_ceiling") or "detailed"),
            ai_provider_access=str(record.get("ai_provider_access") or "detailed_allowed"),
            job_dir_override=str(job_dir(job_id, user_id, create=True)),
        )
        payload = run_pheno_ranker(request)
        payload.setdefault("data", {})
        payload["data"]["job_id"] = job_id
        payload["data"]["job_status"] = "completed"
        save_job_result(job_id, user_id, payload)
        record = update_job_record(
            job_id,
            user_id,
            status="completed",
            completed_at=_now_iso(),
            result_available=True,
            reply_preview=str(payload.get("reply") or f"Completed {str(record.get('mode') or 'pheno')} Pheno-Ranker run.")[:280],
            error="",
        )
        return public_job_payload(record, include_result=True, user_id=user_id)
    except Exception as exc:
        error_text = str(exc).strip() or "Background Pheno-Ranker job failed."
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
