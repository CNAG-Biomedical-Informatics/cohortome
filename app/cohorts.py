from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4

from app.config import BASE_DIR, DEFAULT_LOCAL_USER_ID
from app.user_state import normalize_user_id


LEGACY_SAVED_COHORTS_PATH = BASE_DIR / ".cache" / "saved-cohorts.json"
USER_STATE_ROOT = BASE_DIR / "state" / "users"


def _cohort_store_path(user_id: str = DEFAULT_LOCAL_USER_ID) -> Path:
    path = USER_STATE_ROOT / normalize_user_id(user_id) / "saved-cohorts.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _read_saved_cohorts(user_id: str = DEFAULT_LOCAL_USER_ID) -> List[Dict[str, Any]]:
    path = _cohort_store_path(user_id)
    if not path.exists() and LEGACY_SAVED_COHORTS_PATH.exists():
        path = LEGACY_SAVED_COHORTS_PATH
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return payload if isinstance(payload, list) else []


def _write_saved_cohorts(items: List[Dict[str, Any]], user_id: str = DEFAULT_LOCAL_USER_ID) -> None:
    path = _cohort_store_path(user_id)
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def list_saved_cohorts(data_dir: str | None = None, user_id: str = DEFAULT_LOCAL_USER_ID) -> List[Dict[str, Any]]:
    items = _read_saved_cohorts(user_id)
    if data_dir:
        filtered = [item for item in items if str(item.get("data_dir") or "") == data_dir]
    else:
        filtered = items
    return sorted(filtered, key=lambda item: str(item.get("created_at") or ""), reverse=True)


def get_saved_cohorts_by_ids(
    cohort_ids: List[str],
    data_dir: str | None = None,
    user_id: str = DEFAULT_LOCAL_USER_ID,
) -> List[Dict[str, Any]]:
    wanted = {str(item or "").strip() for item in cohort_ids if str(item or "").strip()}
    if not wanted:
        return []
    items = _read_saved_cohorts(user_id)
    matched = [
        item
        for item in items
        if str(item.get("id") or "") in wanted and (data_dir is None or str(item.get("data_dir") or "") == data_dir)
    ]
    matched.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return matched


def _dedupe_cohort_name(name: str, data_dir: str, items: List[Dict[str, Any]]) -> str:
    existing = {
        str(item.get("name") or "").strip()
        for item in items
        if str(item.get("data_dir") or "") == data_dir
    }
    if name not in existing:
        return name
    suffix = 2
    while True:
        candidate = f"{name} ({suffix})"
        if candidate not in existing:
            return candidate
        suffix += 1


def save_cohort(
    *,
    name: str,
    data_dir: str,
    ids: List[str],
    id_type: str,
    source_kind: str,
    source_prompt: str = "",
    user_id: str = DEFAULT_LOCAL_USER_ID,
) -> Dict[str, Any]:
    normalized_ids = []
    seen = set()
    for item in ids:
        value = str(item or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized_ids.append(value)
    if not normalized_ids:
        raise ValueError("A saved cohort requires at least one ID.")

    requested_name = (name or "").strip() or f"Cohort {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    now = datetime.now(timezone.utc).isoformat()
    items = _read_saved_cohorts(user_id)
    normalized_name = _dedupe_cohort_name(requested_name, data_dir, items)
    item = {
        "id": f"cohort_{uuid4().hex[:12]}",
        "name": normalized_name,
        "data_dir": data_dir,
        "id_type": id_type if id_type in {"patient", "original_record"} else "patient",
        "patient_ids": normalized_ids,
        "source": {
            "kind": source_kind or "manual",
            "prompt": source_prompt.strip(),
        },
        "created_at": now,
        "updated_at": now,
    }
    items.append(item)
    _write_saved_cohorts(items, user_id)
    return item


def delete_saved_cohort(cohort_id: str, user_id: str = DEFAULT_LOCAL_USER_ID) -> bool:
    items = _read_saved_cohorts(user_id)
    filtered = [item for item in items if str(item.get("id") or "") != cohort_id]
    if len(filtered) == len(items):
        return False
    _write_saved_cohorts(filtered, user_id)
    return True
