from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from app.config import DEFAULT_LOCAL_USER_ID, STATE_ROOT_DIR
from app.state_io import advisory_file_lock, atomic_write_json
from app.user_state import normalize_user_id


USER_STATE_ROOT = STATE_ROOT_DIR / "users"


def _store_path(user_id: str = DEFAULT_LOCAL_USER_ID) -> Path:
    path = USER_STATE_ROOT / normalize_user_id(user_id) / "analysis-sessions.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _read_sessions(user_id: str = DEFAULT_LOCAL_USER_ID) -> List[Dict[str, Any]]:
    path = _store_path(user_id)
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return payload if isinstance(payload, list) else []


def _write_sessions(items: List[Dict[str, Any]], user_id: str = DEFAULT_LOCAL_USER_ID) -> None:
    atomic_write_json(_store_path(user_id), items)


def _store_lock_path(user_id: str = DEFAULT_LOCAL_USER_ID) -> Path:
    path = _store_path(user_id)
    return path.with_name(f".{path.name}.lock")


def list_analysis_sessions(user_id: str = DEFAULT_LOCAL_USER_ID) -> List[Dict[str, Any]]:
    items = _read_sessions(user_id)
    return sorted(items, key=lambda item: str(item.get("updated_at") or ""), reverse=True)


def get_analysis_session(session_id: str, user_id: str = DEFAULT_LOCAL_USER_ID) -> Dict[str, Any] | None:
    wanted = str(session_id or "").strip()
    if not wanted:
        return None
    for item in _read_sessions(user_id):
        if str(item.get("id") or "").strip() == wanted:
            return dict(item)
    return None


def save_analysis_session(item: Dict[str, Any], user_id: str = DEFAULT_LOCAL_USER_ID) -> Dict[str, Any]:
    session_id = str(item.get("id") or "").strip()
    if not session_id:
        raise ValueError("Analysis session id is required.")
    now = datetime.now(timezone.utc).isoformat()
    normalized = {
        "id": session_id,
        "title": str(item.get("title") or "").strip(),
        "dataset_id": str(item.get("dataset_id") or "").strip(),
        "data_dir": str(item.get("data_dir") or "").strip(),
        "workspace_fingerprint": item.get("workspace_fingerprint") if isinstance(item.get("workspace_fingerprint"), dict) else {},
        "catalog_item_id": str(item.get("catalog_item_id") or "").strip(),
        "prompt_draft": str(item.get("prompt_draft") or "").strip(),
        "framing": item.get("framing") if isinstance(item.get("framing"), dict) else {},
        "context_mode": "general" if str(item.get("context_mode") or "").strip().lower() == "general" else "workspace",
        "scope": str(item.get("scope") or "").strip(),
        "scope_metadata": _normalize_scope_metadata(item.get("scope_metadata")),
        "saved_cohort_id_a": str(item.get("saved_cohort_id_a") or "").strip(),
        "compare_mode": bool(item.get("compare_mode")),
        "compare_scope": str(item.get("compare_scope") or "").strip(),
        "compare_scope_metadata": _normalize_scope_metadata(item.get("compare_scope_metadata")),
        "saved_cohort_id_b": str(item.get("saved_cohort_id_b") or "").strip(),
        "history": item.get("history") if isinstance(item.get("history"), list) else [],
        "turns": item.get("turns") if isinstance(item.get("turns"), list) else [],
        "updated_at": str(item.get("updated_at") or now),
        "created_at": str(item.get("created_at") or now),
    }
    with advisory_file_lock(_store_lock_path(user_id)):
        items = _read_sessions(user_id)
        replaced = False
        for index, existing in enumerate(items):
            if str(existing.get("id") or "") == session_id:
                normalized["created_at"] = str(existing.get("created_at") or normalized["created_at"])
                items[index] = normalized
                replaced = True
                break
        if not replaced:
            items.append(normalized)
        _write_sessions(items, user_id)
    return normalized


def _normalize_scope_metadata(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    sample_ids = _normalize_id_list(value.get("sample_ids"))
    patient_ids = _normalize_id_list(value.get("patient_ids"))
    query_result_handle = str(value.get("query_result_handle") or "").strip()
    if not sample_ids and not patient_ids and not query_result_handle:
        return {}
    if not patient_ids and sample_ids:
        patient_ids = sorted({item.split(":", 1)[0].strip() for item in sample_ids if item.split(":", 1)[0].strip()})
    if not sample_ids and patient_ids:
        sample_ids = list(patient_ids)
    source = value.get("source") if isinstance(value.get("source"), dict) else {}
    return {
        "id": str(value.get("id") or "").strip(),
        "name": str(value.get("name") or "").strip(),
        "dataset_id": str(value.get("dataset_id") or "").strip(),
        "dataset_ids": _normalize_id_list(value.get("dataset_ids")),
        "data_dir": str(value.get("data_dir") or "").strip(),
        "id_type": str(value.get("id_type") or ("sample" if sample_ids and any(":" in item for item in sample_ids) else "patient")).strip(),
        "query_result_handle": query_result_handle,
        "sample_ids": sample_ids,
        "patient_ids": patient_ids,
        "sample_count": len(sample_ids),
        "patient_count": len(patient_ids),
        "is_full_dataset": bool(value.get("is_full_dataset")),
        "source": {
            "kind": str(source.get("kind") or value.get("source_kind") or "").strip(),
            "prompt": str(source.get("prompt") or value.get("source_prompt") or "").strip(),
        },
    }


def _normalize_id_list(value: Any) -> List[str]:
    raw_items = value if isinstance(value, list) else str(value or "").split(",")
    normalized: List[str] = []
    seen = set()
    for item in raw_items:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return normalized


def rename_analysis_session(session_id: str, title: str, user_id: str = DEFAULT_LOCAL_USER_ID) -> Dict[str, Any] | None:
    with advisory_file_lock(_store_lock_path(user_id)):
        items = _read_sessions(user_id)
        for index, item in enumerate(items):
            if str(item.get("id") or "") != session_id:
                continue
            updated = dict(item)
            updated["title"] = title.strip()
            updated["updated_at"] = datetime.now(timezone.utc).isoformat()
            items[index] = updated
            _write_sessions(items, user_id)
            return updated
    return None


def delete_analysis_session(session_id: str, user_id: str = DEFAULT_LOCAL_USER_ID) -> bool:
    with advisory_file_lock(_store_lock_path(user_id)):
        items = _read_sessions(user_id)
        filtered = [item for item in items if str(item.get("id") or "") != session_id]
        if len(filtered) == len(items):
            return False
        _write_sessions(filtered, user_id)
        return True


def list_sessions_referencing_saved_cohort(cohort_id: str, user_id: str = DEFAULT_LOCAL_USER_ID) -> List[Dict[str, Any]]:
    wanted = str(cohort_id or "").strip()
    if not wanted:
        return []
    matches: List[Dict[str, Any]] = []
    for item in _read_sessions(user_id):
        saved_a = str(item.get("saved_cohort_id_a") or "").strip()
        saved_b = str(item.get("saved_cohort_id_b") or "").strip()
        if saved_a != wanted and saved_b != wanted:
            continue
        matches.append({
            "id": str(item.get("id") or "").strip(),
            "title": str(item.get("title") or "").strip(),
        })
    return matches
