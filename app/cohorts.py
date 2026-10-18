from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4

from app.config import DEFAULT_LOCAL_USER_ID, STATE_ROOT_DIR
from app.state_io import advisory_file_lock, atomic_write_json
from app.user_state import normalize_user_id
from app.identities import qualified_member


USER_STATE_ROOT = STATE_ROOT_DIR / "users"


def _cohort_store_path(user_id: str = DEFAULT_LOCAL_USER_ID) -> Path:
    path = USER_STATE_ROOT / normalize_user_id(user_id) / "saved-cohorts.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _read_saved_cohorts(user_id: str = DEFAULT_LOCAL_USER_ID) -> List[Dict[str, Any]]:
    path = _cohort_store_path(user_id)
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    items = payload if isinstance(payload, list) else []
    normalized: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        # Pre-identity cohorts cannot safely identify members; no legacy migration.
        if item.get('membership_version') != 2 or not item.get('members'):
            continue
        members = [qualified_member(m) for m in item['members']]
        normalized_item = dict(item, members=members,
            patient_ids=sorted({m['patient_key'] for m in members}),
            sample_ids=sorted({m['sample_key'] for m in members if m.get('sample_key')}))
        normalized_item['patient_count'] = len(normalized_item['patient_ids'])
        normalized_item['sample_count'] = len(normalized_item['sample_ids'])
        normalized.append(normalized_item)
    return normalized


def _write_saved_cohorts(items: List[Dict[str, Any]], user_id: str = DEFAULT_LOCAL_USER_ID) -> None:
    atomic_write_json(_cohort_store_path(user_id), items)


def _cohort_store_lock_path(user_id: str = DEFAULT_LOCAL_USER_ID) -> Path:
    path = _cohort_store_path(user_id)
    return path.with_name(f".{path.name}.lock")


def list_saved_cohorts(dataset_id: str | None = None, user_id: str = DEFAULT_LOCAL_USER_ID) -> List[Dict[str, Any]]:
    items = _read_saved_cohorts(user_id)
    if dataset_id:
        from app.datasets import parse_scope_dataset_ids
        active = set(parse_scope_dataset_ids(dataset_id))
        filtered = [item for item in items if str(item.get("dataset_id") or "") == dataset_id
                    or (item.get('members') and set(item.get('dataset_ids') or [])
                        and set(item['dataset_ids']).issubset(active))]
    else:
        filtered = items
    return sorted(filtered, key=lambda item: str(item.get("created_at") or ""), reverse=True)


def get_saved_cohorts_by_ids(
    cohort_ids: List[str],
    dataset_id: str | None = None,
    user_id: str = DEFAULT_LOCAL_USER_ID,
) -> List[Dict[str, Any]]:
    wanted = {str(item or "").strip() for item in cohort_ids if str(item or "").strip()}
    if not wanted:
        return []
    items = list_saved_cohorts(dataset_id, user_id=user_id)
    matched = [
        item
        for item in items
        if str(item.get("id") or "") in wanted
    ]
    matched.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return matched


def _dedupe_cohort_name(name: str, dataset_id: str, items: List[Dict[str, Any]]) -> str:
    existing = {
        str(item.get("name") or "").strip()
        for item in items
        if str(item.get("dataset_id") or "") == dataset_id
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
    dataset_id: str = "",
    dataset_ids: List[str] | None = None,
    data_dir: str,
    sample_ids: List[str] | None = None,
    patient_ids: List[str] | None = None,
    ids: List[str] | None = None,
    id_type: str,
    source_kind: str,
    source_prompt: str = "",
    user_id: str = DEFAULT_LOCAL_USER_ID,
    members: List[Dict[str, str]] | None = None,
) -> Dict[str, Any]:
    if members is None:
        raise ValueError('Saved cohorts require dataset-qualified members. Recreate this cohort.')
    members = [qualified_member(m) for m in members]
    if not members:
        raise ValueError('A saved cohort requires at least one member.')
    normalized_sample_ids = sorted({m['sample_key'] for m in members if m.get('sample_key')})
    normalized_patient_ids = sorted({m['patient_key'] for m in members})
    is_full_dataset = False

    normalized_dataset_id = str(dataset_id or data_dir).strip()
    normalized_dataset_ids = []
    seen_dataset_ids = set()
    for item in (dataset_ids or []):
        value = str(item or "").strip()
        if not value or value in seen_dataset_ids:
            continue
        seen_dataset_ids.add(value)
        normalized_dataset_ids.append(value)
    if not normalized_dataset_ids and normalized_dataset_id:
        normalized_dataset_ids = [normalized_dataset_id]
    requested_name = (name or "").strip() or f"Cohort {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    now = datetime.now(timezone.utc).isoformat()
    with advisory_file_lock(_cohort_store_lock_path(user_id)):
        items = _read_saved_cohorts(user_id)
        normalized_name = _dedupe_cohort_name(requested_name, normalized_dataset_id, items)
        item = {
            "id": f"cohort_{uuid4().hex[:12]}",
            "name": normalized_name,
            "dataset_id": normalized_dataset_id,
            "dataset_ids": normalized_dataset_ids,
            "data_dir": data_dir,
            "id_type": id_type if id_type in {"sample", "original_record", "patient"} else "sample",
            "sample_ids": normalized_sample_ids,
            "patient_ids": normalized_patient_ids,
            "sample_count": len(normalized_sample_ids),
            "patient_count": len(normalized_patient_ids),
            "is_full_dataset": is_full_dataset,
            "source": {
                "kind": source_kind or "manual",
                "prompt": source_prompt.strip(),
            },
            "created_at": now,
            "updated_at": now,
        }
        items.append(item)
        if members is not None:
            item['members'] = members
            item['membership_version'] = 2
            item['patient_count'] = len({(m['dataset_id'], m['patient_id']) for m in members})
            item['sample_count'] = len({(m['dataset_id'], m['sample_id']) for m in members if m.get('sample_id')})
            item['is_full_dataset'] = False
        _write_saved_cohorts(items, user_id)
    return item


def rename_saved_cohort(cohort_id: str, name: str, user_id: str = DEFAULT_LOCAL_USER_ID) -> Dict[str, Any]:
    name = name.strip()
    if not name or len(name) > 200:
        raise ValueError('Cohort name must contain 1–200 characters.')
    with advisory_file_lock(_cohort_store_lock_path(user_id)):
        items = _read_saved_cohorts(user_id)
        item = next((entry for entry in items if entry.get('id') == cohort_id), None)
        if item is None:
            raise KeyError(cohort_id)
        item['name'] = _dedupe_cohort_name(name, item['dataset_id'],
                                         [entry for entry in items if entry['id'] != cohort_id])
        item['updated_at'] = datetime.now(timezone.utc).isoformat()
        _write_saved_cohorts(items, user_id)
        return {key: item[key] for key in ('id', 'name', 'updated_at')}


def delete_saved_cohort(cohort_id: str, user_id: str = DEFAULT_LOCAL_USER_ID) -> bool:
    with advisory_file_lock(_cohort_store_lock_path(user_id)):
        items = _read_saved_cohorts(user_id)
        filtered = [item for item in items if str(item.get("id") or "") != cohort_id]
        if len(filtered) == len(items):
            return False
        _write_saved_cohorts(filtered, user_id)
        return True
