from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

from app.config import DEFAULT_LOCAL_USER_ID, private_artifact_runtime_is_safe
from app.state_io import advisory_file_lock, atomic_write_json
from app.user_state import normalize_user_id, user_state_dir


QUERY_RESULT_TTL_MINUTES = 60
QUERY_RESULT_DEFAULT_PAGE_SIZE = 50
QUERY_RESULT_MAX_PAGE_SIZE = 100
_HANDLE_PREFIX = "qr_"


class QueryResultNotFoundError(LookupError):
    pass


class QueryResultExpiredError(LookupError):
    pass


class QueryResultStaleError(RuntimeError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_time(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or ""))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _safe_handle(value: str) -> str:
    handle = str(value or "").strip()
    if not handle.startswith(_HANDLE_PREFIX) or len(handle) > 96:
        raise QueryResultNotFoundError("Query result not found.")
    token = handle[len(_HANDLE_PREFIX):]
    if not token or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for character in token):
        raise QueryResultNotFoundError("Query result not found.")
    return handle


def _owner_identity(value: str) -> str:
    return str(value or "").strip() or DEFAULT_LOCAL_USER_ID


def _result_dir(user_id: str) -> Path:
    path = user_state_dir(normalize_user_id(user_id)) / "query-results"
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)
    return path


def _result_path(user_id: str, handle: str) -> Path:
    return _result_dir(user_id) / f"{_safe_handle(handle)}.json"


def _existing_result_path(user_id: str, handle: str) -> Path:
    safe_user = normalize_user_id(user_id)
    path = user_state_dir(safe_user) / "query-results" / f"{_safe_handle(handle)}.json"
    try:
        path.relative_to(user_state_dir(safe_user))
    except ValueError as exc:
        raise QueryResultNotFoundError("Query result not found.") from exc
    return path


def _dedupe(values: Any) -> List[str]:
    found: List[str] = []
    seen = set()
    for item in values if isinstance(values, list) else []:
        value = str(item or "").strip()
        if value and value not in seen:
            seen.add(value)
            found.append(value)
    return found


def _canonical_dataset_ids(values: Any) -> List[str]:
    return sorted(_dedupe(values))


def purge_expired_query_results(user_id: str, *, now: datetime | None = None, max_files: int = 256) -> int:
    root = user_state_dir(normalize_user_id(user_id)) / "query-results"
    if not root.is_dir():
        return 0
    owner = _owner_identity(user_id)
    cutoff = now or _now()
    removed = 0
    for path in list(root.glob(f"{_HANDLE_PREFIX}*.json"))[:max(1, int(max_files or 1))]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        stored_owner = str(payload.get("owner_user_id") or "") if isinstance(payload, dict) else ""
        expires_at = _parse_time(payload.get("expires_at")) if isinstance(payload, dict) else None
        if not stored_owner or not hmac.compare_digest(stored_owner, owner) or (expires_at is not None and expires_at > cutoff):
            continue
        path.unlink(missing_ok=True)
        removed += 1
    return removed


def _result_items(patient_ids: List[str], sample_ids: List[str], rows: Any, id_type: str) -> List[Dict[str, Any]]:
    normalized_rows = [dict(item) for item in rows if isinstance(item, dict)] if isinstance(rows, list) else []
    if id_type == "sample":
        rows_by_sample = {
            str(item.get("sample_id") or item.get("record_id") or "").strip(): item
            for item in normalized_rows
            if str(item.get("sample_id") or item.get("record_id") or "").strip()
        }
        return [
            {"sample_id": sample_id, "row": rows_by_sample.get(sample_id, {"sample_id": sample_id})}
            for sample_id in sample_ids
        ]

    rows_by_patient = {
        str(item.get("patient_id") or "").strip(): {
            key: item.get(key)
            for key in ("patient_id", "sex", "visit_count", "medication_count", "disease_count")
            if item.get(key) is not None
        }
        for item in normalized_rows
        if str(item.get("patient_id") or "").strip()
    }
    return [
        {"patient_id": patient_id, "row": rows_by_patient.get(patient_id, {"patient_id": patient_id})}
        for patient_id in patient_ids
    ]


def create_query_result(
    *,
    user_id: str,
    dataset_id: str,
    dataset_ids: List[str],
    workspace_fingerprint: Dict[str, Any],
    policy_binding: Dict[str, Any] | None = None,
    patient_ids: List[str] | None = None,
    sample_ids: List[str] | None = None,
    rows: List[Dict[str, Any]] | None = None,
    id_type: str = "patient",
    private_scope: bool = False,
    ttl_minutes: int = QUERY_RESULT_TTL_MINUTES,
    query_text: str = "",
) -> Dict[str, Any]:
    if private_scope and not private_artifact_runtime_is_safe():
        raise RuntimeError(
            "Private query-result state requires COHORTOME_RUNTIME_ROOT to be an absolute path "
            "on protected storage outside the Git checkout."
        )
    purge_expired_query_results(user_id)
    normalized_patients = _dedupe(patient_ids or [])
    normalized_samples = _dedupe(sample_ids or [])
    primary_type = "sample" if id_type == "sample" and normalized_samples else "patient"
    items = _result_items(normalized_patients, normalized_samples, rows or [], primary_type)
    if not items:
        raise ValueError("A query result requires at least one patient or sample identifier.")

    created_at = _now()
    expires_at = created_at + timedelta(minutes=max(1, int(ttl_minutes or QUERY_RESULT_TTL_MINUTES)))
    handle = f"{_HANDLE_PREFIX}{secrets.token_urlsafe(32)}"
    record = {
        "schema_version": 1,
        "query_text": str(query_text or ""),
        "handle": handle,
        "owner_user_id": _owner_identity(user_id),
        "dataset_id": str(dataset_id or "").strip(),
        "dataset_ids": _canonical_dataset_ids(dataset_ids),
        "workspace_fingerprint": dict(workspace_fingerprint or {}),
        "policy_binding": dict(policy_binding or {}),
        "granularity_required": "detailed",
        "created_at": created_at.isoformat(),
        "expires_at": expires_at.isoformat(),
        "cursor_secret": secrets.token_urlsafe(32),
        "id_type": primary_type,
        "patient_ids": normalized_patients,
        "sample_ids": normalized_samples,
        "items": items,
    }
    path = _result_path(user_id, handle)
    lock_path = path.with_suffix(".lock")
    with advisory_file_lock(lock_path):
        lock_path.chmod(0o600)
        atomic_write_json(path, record, file_mode=0o600)
    return record


def load_query_result(user_id: str, handle: str, *, now: datetime | None = None) -> Dict[str, Any]:
    path = _existing_result_path(user_id, handle)
    if not path.is_file():
        raise QueryResultNotFoundError("Query result not found.")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise QueryResultNotFoundError("Query result not found.") from exc
    stored_owner = str(payload.get("owner_user_id") or "") if isinstance(payload, dict) else ""
    requested_owner = _owner_identity(user_id)
    if not isinstance(payload, dict) or not stored_owner or not hmac.compare_digest(stored_owner, requested_owner):
        raise QueryResultNotFoundError("Query result not found.")
    expires_at = _parse_time(payload.get("expires_at"))
    if expires_at is None or expires_at <= (now or _now()):
        path.unlink(missing_ok=True)
        raise QueryResultExpiredError("Query result has expired. Run the query again.")
    return payload


def delete_query_results(user_id: str) -> int:
    root = user_state_dir(normalize_user_id(user_id)) / "query-results"
    if not root.is_dir():
        return 0
    owner = _owner_identity(user_id)
    count = 0
    for path in root.glob(f"{_HANDLE_PREFIX}*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        stored_owner = str(payload.get("owner_user_id") or "") if isinstance(payload, dict) else ""
        if not stored_owner or not hmac.compare_digest(stored_owner, owner):
            continue
        path.unlink(missing_ok=True)
        path.with_suffix(".lock").unlink(missing_ok=True)
        count += 1
    try:
        root.rmdir()
    except OSError:
        pass
    return count


def require_query_result_binding(
    record: Dict[str, Any],
    *,
    dataset_id: str,
    dataset_ids: List[str],
    workspace_fingerprint: Dict[str, Any],
    policy_binding: Dict[str, Any] | None = None,
) -> None:
    if str(record.get("dataset_id") or "") != str(dataset_id or ""):
        raise QueryResultStaleError("Query result belongs to a different workspace.")
    if _canonical_dataset_ids(record.get("dataset_ids") or []) != _canonical_dataset_ids(dataset_ids):
        raise QueryResultStaleError("Query result belongs to a different workspace.")
    stored_token = str((record.get("workspace_fingerprint") or {}).get("token") or "")
    current_token = str((workspace_fingerprint or {}).get("token") or "")
    if not stored_token or not current_token or not hmac.compare_digest(stored_token, current_token):
        raise QueryResultStaleError("The workspace changed after this query ran. Run the query again.")
    if dict(record.get("policy_binding") or {}) != dict(policy_binding or {}):
        raise QueryResultStaleError("The workspace access policy changed after this query ran. Run the query again.")


def sort_query_result(record, rows, sort_by, direction="asc"):
    allowed = {"sample_id", "subject_clarid"} if record.get("id_type") == "sample" else {
        "patient_id", "subject_clarid", "dataset_names", "sex", "visit_count", "medication_count"}
    if sort_by not in allowed or direction not in {"asc", "desc"}:
        raise ValueError("Unsupported result sort column or direction.")
    primary = "sample_id" if record.get("id_type") == "sample" else "patient_id"
    numeric = sort_by in {"visit_count", "medication_count"}

    def value(row):
        raw = row.get(sort_by)
        if raw is None or raw == "":
            return None
        if numeric:
            try:
                number = float(raw)
                return number if math.isfinite(number) else None
            except (TypeError, ValueError):
                return None
        return str(raw).casefold()

    # Stable ID tie-breaking; unavailable values are last in either direction.
    pairs = [(row, value(row)) for row in sorted(rows, key=lambda row: str(row.get(primary, "")))]
    present = sorted((pair for pair in pairs if pair[1] is not None), key=lambda pair: pair[1], reverse=direction == "desc")
    ordered = present + [pair for pair in pairs if pair[1] is None]
    return {**record, "sort_by": sort_by, "sort_direction": direction,
            "items": [{primary: row[primary], "row": row} for row, _ in ordered]}


def _cursor_message(record, message):
    if record.get("sort_by"):
        return message + f":{record['sort_by']}:{record['sort_direction']}".encode("ascii")
    return message


def _cursor(record: Dict[str, Any], offset: int, page_size: int) -> str:
    message = f"{int(offset)}:{int(page_size)}".encode("ascii")
    signature = hmac.new(str(record.get("cursor_secret") or "").encode("utf-8"), _cursor_message(record, message), hashlib.sha256).digest()[:16]
    payload = base64.urlsafe_b64encode(message + b":" + signature).decode("ascii").rstrip("=")
    return payload


def _cursor_offset(record: Dict[str, Any], cursor: str, page_size: int) -> int:
    if not cursor:
        return 0
    try:
        padded = str(cursor) + "=" * (-len(str(cursor)) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
        offset_raw, size_raw, signature = decoded.split(b":", 2)
        offset = int(offset_raw)
        encoded_size = int(size_raw)
    except (ValueError, TypeError, UnicodeEncodeError) as exc:
        raise QueryResultStaleError("Invalid query-result cursor.") from exc
    if encoded_size != page_size or offset < 0:
        raise QueryResultStaleError("Invalid query-result cursor.")
    expected = hmac.new(
        str(record.get("cursor_secret") or "").encode("utf-8"),
        _cursor_message(record, f"{offset}:{page_size}".encode("ascii")),
        hashlib.sha256,
    ).digest()[:16]
    if not hmac.compare_digest(signature, expected):
        raise QueryResultStaleError("Invalid query-result cursor.")
    return offset


def query_result_page(record: Dict[str, Any], *, cursor: str = "", limit: int = QUERY_RESULT_DEFAULT_PAGE_SIZE) -> Dict[str, Any]:
    page_size = min(QUERY_RESULT_MAX_PAGE_SIZE, max(1, int(limit or QUERY_RESULT_DEFAULT_PAGE_SIZE)))
    items = [item for item in record.get("items", []) if isinstance(item, dict)]
    offset = _cursor_offset(record, cursor, page_size)
    if offset > len(items):
        raise QueryResultStaleError("Invalid query-result cursor.")
    page_items = items[offset:offset + page_size]
    primary_type = str(record.get("id_type") or "patient")
    rows = []
    for item in page_items:
        stored_row = dict(item.get("row") or {})
        if primary_type == "sample":
            rows.append({"sample_id": str(item.get("sample_id") or stored_row.get("sample_id") or "")})
            continue
        rows.append(
            {
                key: stored_row.get(key)
                for key in ("patient_id", "sex", "visit_count", "medication_count", "disease_count")
                if stored_row.get(key) is not None
            }
        )
    patient_ids = [str(item.get("patient_id") or "") for item in page_items if primary_type == "patient" and item.get("patient_id")]
    sample_ids = [str(item.get("sample_id") or "") for item in page_items if primary_type == "sample" and item.get("sample_id")]
    next_offset = offset + len(page_items)
    has_more = next_offset < len(items)
    return {
        "result_handle": str(record.get("handle") or ""),
        "id_type": primary_type,
        "total_count": len(items),
        "returned_count": len(page_items),
        "page_size": page_size,
        "has_more": has_more,
        "next_cursor": _cursor(record, next_offset, page_size) if has_more else "",
        "expires_at": str(record.get("expires_at") or ""),
        "patient_ids": patient_ids,
        "sample_ids": sample_ids,
        "rows": rows,
    }


def query_result_membership(record: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "result_handle": str(record.get("handle") or ""),
        "dataset_id": str(record.get("dataset_id") or ""),
        "dataset_ids": list(record.get("dataset_ids") or []),
        "id_type": str(record.get("id_type") or "patient"),
        "patient_ids": _dedupe(record.get("patient_ids") or []),
        "sample_ids": _dedupe(record.get("sample_ids") or []),
        "total_count": len([item for item in record.get("items", []) if isinstance(item, dict)]),
    }
