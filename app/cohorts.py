from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4

from app.bff import ensure_data_dir, extract_patient_id, normalize_value, read_bff_records
from app.config import BASE_DIR, DEFAULT_LOCAL_USER_ID
from app.user_state import normalize_user_id


USER_STATE_ROOT = BASE_DIR / "state" / "users"


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
        sample_ids = [str(value).strip() for value in item.get("sample_ids", []) if str(value).strip()]
        patient_ids = [str(value).strip() for value in item.get("patient_ids", []) if str(value).strip()]
        dataset_ids = [str(value).strip() for value in item.get("dataset_ids", []) if str(value).strip()]
        if not sample_ids and patient_ids:
            sample_ids = list(patient_ids)
        if not patient_ids and sample_ids:
            patient_ids = sorted({value.split(":", 1)[0].strip() for value in sample_ids if value.split(":", 1)[0].strip()})
        if not dataset_ids:
            dataset_id = str(item.get("dataset_id") or "").strip()
            dataset_ids = [dataset_id] if dataset_id else []
        normalized_item = dict(item)
        normalized_item["dataset_id"] = str(item.get("dataset_id") or "").strip()
        normalized_item["dataset_ids"] = dataset_ids
        normalized_item["sample_ids"] = sample_ids
        normalized_item["patient_ids"] = patient_ids
        normalized_item["sample_count"] = len(sample_ids)
        normalized_item["patient_count"] = len(patient_ids)
        normalized_item["is_full_dataset"] = bool(item.get("is_full_dataset"))
        normalized.append(normalized_item)
    return normalized


def _write_saved_cohorts(items: List[Dict[str, Any]], user_id: str = DEFAULT_LOCAL_USER_ID) -> None:
    path = _cohort_store_path(user_id)
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def list_saved_cohorts(dataset_id: str | None = None, user_id: str = DEFAULT_LOCAL_USER_ID) -> List[Dict[str, Any]]:
    items = _read_saved_cohorts(user_id)
    if dataset_id:
        filtered = [item for item in items if str(item.get("dataset_id") or "") == dataset_id]
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
    items = _read_saved_cohorts(user_id)
    matched = [
        item
        for item in items
        if str(item.get("id") or "") in wanted and (dataset_id is None or str(item.get("dataset_id") or "") == dataset_id)
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


def _dataset_scope_metadata(data_dir: str) -> Dict[str, Any]:
    sample_ids: List[str] = []
    patient_ids: List[str] = []
    seen_sample_ids = set()
    seen_patient_ids = set()
    for _, _, record in read_bff_records(ensure_data_dir(data_dir)):
        raw_id = normalize_value(record.get("id"))
        if isinstance(raw_id, str) and raw_id.strip() and raw_id not in seen_sample_ids:
            seen_sample_ids.add(raw_id)
            sample_ids.append(raw_id)
        patient_id = extract_patient_id(record)
        if isinstance(patient_id, str) and patient_id.strip() and patient_id not in seen_patient_ids:
            seen_patient_ids.add(patient_id)
            patient_ids.append(patient_id)
    return {
        "sample_ids": sample_ids,
        "patient_ids": patient_ids,
        "sample_id_set": set(sample_ids),
        "patient_id_set": set(patient_ids),
    }


def _matches_full_dataset_scope(
    sample_ids: List[str],
    patient_ids: List[str],
    data_dir: str,
    dataset_scope: Dict[str, Any] | None = None,
) -> bool:
    if not data_dir:
        return False
    try:
        scope = dataset_scope or _dataset_scope_metadata(data_dir)
    except FileNotFoundError:
        return False
    sample_id_set = {str(item).strip() for item in sample_ids if str(item).strip()}
    patient_id_set = {str(item).strip() for item in patient_ids if str(item).strip()}
    return sample_id_set == scope["sample_id_set"] and patient_id_set == scope["patient_id_set"]


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
) -> Dict[str, Any]:
    raw_sample_ids = sample_ids if sample_ids is not None else []
    raw_patient_ids = patient_ids if patient_ids is not None else []
    if ids is not None:
        if id_type in {"sample", "original_record"} and not raw_sample_ids:
            raw_sample_ids = ids
        if id_type == "patient" and not raw_patient_ids:
            raw_patient_ids = ids

    normalized_sample_ids = []
    seen_sample_ids = set()
    for item in raw_sample_ids:
        value = str(item or "").strip()
        if not value or value in seen_sample_ids:
            continue
        seen_sample_ids.add(value)
        normalized_sample_ids.append(value)

    normalized_patient_ids = []
    seen = set()
    for item in raw_patient_ids:
        value = str(item or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized_patient_ids.append(value)

    if not normalized_sample_ids and normalized_patient_ids:
        normalized_sample_ids = list(normalized_patient_ids)
    if not normalized_patient_ids and normalized_sample_ids:
        normalized_patient_ids = sorted({value.split(":", 1)[0].strip() for value in normalized_sample_ids if value.split(":", 1)[0].strip()})

    if not normalized_sample_ids:
        raise ValueError("A saved cohort requires at least one ID.")

    is_full_dataset = False
    try:
        dataset_scope = _dataset_scope_metadata(data_dir)
        is_full_dataset = (
            set(normalized_sample_ids) == dataset_scope["sample_id_set"]
            and set(normalized_patient_ids) == dataset_scope["patient_id_set"]
        )
    except FileNotFoundError:
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
    _write_saved_cohorts(items, user_id)
    return item


def delete_saved_cohort(cohort_id: str, user_id: str = DEFAULT_LOCAL_USER_ID) -> bool:
    items = _read_saved_cohorts(user_id)
    filtered = [item for item in items if str(item.get("id") or "") != cohort_id]
    if len(filtered) == len(items):
        return False
    _write_saved_cohorts(filtered, user_id)
    return True
