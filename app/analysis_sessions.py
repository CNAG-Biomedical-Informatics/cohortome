from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from app.config import BASE_DIR, DEFAULT_LOCAL_USER_ID
from app.user_state import normalize_user_id


LEGACY_ANALYSIS_SESSIONS_PATH = BASE_DIR / ".cache" / "analysis-sessions.json"
USER_STATE_ROOT = BASE_DIR / "state" / "users"


def _store_path(user_id: str = DEFAULT_LOCAL_USER_ID) -> Path:
    path = USER_STATE_ROOT / normalize_user_id(user_id) / "analysis-sessions.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _read_sessions(user_id: str = DEFAULT_LOCAL_USER_ID) -> List[Dict[str, Any]]:
    path = _store_path(user_id)
    if not path.exists() and LEGACY_ANALYSIS_SESSIONS_PATH.exists():
        path = LEGACY_ANALYSIS_SESSIONS_PATH
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return payload if isinstance(payload, list) else []


def _write_sessions(items: List[Dict[str, Any]], user_id: str = DEFAULT_LOCAL_USER_ID) -> None:
    path = _store_path(user_id)
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def list_analysis_sessions(user_id: str = DEFAULT_LOCAL_USER_ID) -> List[Dict[str, Any]]:
    items = _read_sessions(user_id)
    return sorted(items, key=lambda item: str(item.get("updated_at") or ""), reverse=True)


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
        "catalog_item_id": str(item.get("catalog_item_id") or "").strip(),
        "prompt_draft": str(item.get("prompt_draft") or "").strip(),
        "scope": str(item.get("scope") or "").strip(),
        "saved_cohort_id_a": str(item.get("saved_cohort_id_a") or "").strip(),
        "compare_mode": bool(item.get("compare_mode")),
        "compare_scope": str(item.get("compare_scope") or "").strip(),
        "saved_cohort_id_b": str(item.get("saved_cohort_id_b") or "").strip(),
        "history": item.get("history") if isinstance(item.get("history"), list) else [],
        "turns": item.get("turns") if isinstance(item.get("turns"), list) else [],
        "updated_at": str(item.get("updated_at") or now),
        "created_at": str(item.get("created_at") or now),
    }
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


def rename_analysis_session(session_id: str, title: str, user_id: str = DEFAULT_LOCAL_USER_ID) -> Dict[str, Any] | None:
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
