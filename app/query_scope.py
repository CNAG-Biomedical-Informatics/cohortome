from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.bff import ensure_data_dir, normalize_value, read_bff_records


@dataclass
class QueryScopeContext:
    patient_ids: List[str]
    patient_rows: List[Dict[str, Any]]
    sample_ids: List[str]
    disease_counts: List[Dict[str, Any]]
    medication_counts: List[Dict[str, Any]]


def patient_inventory_from_records(data_dir: str, scoped_patient_ids: Optional[List[str]] = None) -> List[str]:
    resolved_dir = ensure_data_dir(data_dir)
    allowed = {str(item).strip() for item in scoped_patient_ids or [] if str(item).strip()}
    ids: List[str] = []
    seen = set()
    for _, _, record in read_bff_records(resolved_dir):
        patient_id = normalize_value(record.get("patient_id"))
        if allowed and str(patient_id or "").strip() not in allowed:
            continue
        raw_id = normalize_value(record.get("id"))
        candidate = str(patient_id or raw_id or "").strip()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        ids.append(candidate)
    return sorted(ids)


def apply_patient_scope_to_rows(rows: List[Dict[str, Any]], scoped_patient_ids: Optional[List[str]]) -> List[Dict[str, Any]]:
    if not scoped_patient_ids:
        return rows
    allowed = {str(item).strip() for item in scoped_patient_ids if str(item).strip()}
    if not allowed:
        return rows
    return [row for row in rows if str(row.get("patient_id") or "").strip() in allowed]


def apply_patient_scope_to_cohort(cohort: Dict[str, Any], scoped_patient_ids: Optional[List[str]]) -> Dict[str, Any]:
    if not scoped_patient_ids:
        return cohort
    allowed = {str(item).strip() for item in scoped_patient_ids if str(item).strip()}
    if not allowed:
        return cohort
    patients = [
        item
        for item in cohort.get("patients", [])
        if str(item.get("patient_id") or "").strip() in allowed
    ]
    scoped = dict(cohort)
    scoped["patients"] = patients
    scoped["patient_count"] = len(patients)
    scoped["patient_ids"] = [item["patient_id"] for item in patients if isinstance(item, dict) and item.get("patient_id")]
    original_ids = []
    for item in patients:
        for record_id in item.get("original_record_ids", []) if isinstance(item, dict) else []:
            if record_id not in original_ids:
                original_ids.append(record_id)
    if original_ids:
        scoped["original_record_ids"] = original_ids
    return scoped


def sample_inventory_from_records(data_dir: str, scoped_patient_ids: Optional[List[str]] = None) -> List[str]:
    resolved_dir = ensure_data_dir(data_dir)
    allowed = {str(item).strip() for item in scoped_patient_ids or [] if str(item).strip()}
    ids: List[str] = []
    seen = set()
    for _, _, record in read_bff_records(resolved_dir):
        patient_id = normalize_value(record.get("patient_id"))
        if allowed and str(patient_id or "").strip() not in allowed:
            continue
        raw_id = normalize_value(record.get("id"))
        candidate = str(raw_id or "").strip()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        ids.append(candidate)
    return sorted(ids)


def bucket_counts_from_rows(rows: List[Dict[str, Any]], key: str, label_key: str) -> List[Dict[str, Any]]:
    counts: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        patient_id = str(row.get("patient_id") or "").strip()
        for label in row.get(key, []) if isinstance(row, dict) else []:
            normalized = str(label).strip()
            if not normalized:
                continue
            entry = counts.setdefault(
                normalized,
                {
                    label_key: normalized,
                    "patient_count": 0,
                    "patients": [],
                },
            )
            entry["patient_count"] += 1
            if patient_id:
                entry["patients"].append(patient_id)
    return sorted(counts.values(), key=lambda item: (-item["patient_count"], item[label_key]))


def build_query_scope_context(
    data_dir: str,
    patient_rows: List[Dict[str, Any]],
    scoped_patient_ids: Optional[List[str]] = None,
) -> QueryScopeContext:
    scoped_rows = apply_patient_scope_to_rows(patient_rows, scoped_patient_ids)
    patient_ids = [
        str(row.get("patient_id") or "").strip()
        for row in scoped_rows
        if str(row.get("patient_id") or "").strip()
    ]
    sample_ids: List[str] = []
    seen_sample_ids = set()
    for row in scoped_rows:
        for value in row.get("original_record_ids", []) if isinstance(row, dict) else []:
            sample_id = str(value or "").strip()
            if not sample_id or sample_id in seen_sample_ids:
                continue
            seen_sample_ids.add(sample_id)
            sample_ids.append(sample_id)
    return QueryScopeContext(
        patient_ids=patient_ids,
        patient_rows=scoped_rows,
        sample_ids=sorted(sample_ids),
        disease_counts=bucket_counts_from_rows(scoped_rows, "diseases", "disease"),
        medication_counts=bucket_counts_from_rows(scoped_rows, "medications", "medication"),
    )
