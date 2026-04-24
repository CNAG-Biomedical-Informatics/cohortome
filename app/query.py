import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib import error

from app.bff import (
    build_patient_navigator,
    dashboard_summary,
    ensure_data_dir,
    extract_event_date,
    extract_treatment_labels,
    group_patients,
    list_patient_summaries,
    medication_cohort,
    medication_counts,
    normalize_value,
    read_bff_records,
)
from app.entity_terms import entity_identifier_prefixes, inventory_count_prompt_matches, inventory_prompt_matches
from app.entity_terms import normalize_entity_synonym_mentions
from app.lm import (
    http_json as _http_json,
    lm_studio_base_url as _lm_studio_base_url,
    lm_studio_enabled as _lm_studio_enabled,
    sanitize_lm_text as _sanitize_lm_text,
)
from app.query_policy import (
    ai_provider_context_granularity as _ai_provider_context_granularity,
    ai_provider_granularity_mode as _ai_provider_granularity_mode,
    finalize_query_response as _finalize_query_response,
    normalize_ai_provider_access as _normalize_ai_provider_access,
    normalize_query_granularity_ceiling as _normalize_query_granularity_ceiling,
    normalize_query_granularity_mode as _normalize_query_granularity_mode,
)
from app.query_scope import (
    QueryScopeContext,
    apply_patient_scope_to_cohort as _apply_patient_scope_to_cohort,
    apply_patient_scope_to_rows as _apply_patient_scope_to_rows,
    build_query_scope_context as _build_query_scope_context_from_rows,
    patient_inventory_from_records as _patient_inventory_from_records,
    sample_inventory_from_records as _sample_inventory_from_records,
)
from app.query_store import (
    QueryStoreNotReadyError,
    cohort_over_time_summary as store_cohort_over_time_summary,
    disease_cohort as store_disease_cohort,
    disease_counts as store_disease_counts,
    duckdb_available,
    medication_cohort as store_medication_cohort,
    medication_counts as store_medication_counts,
    patient_medication_count_cohort as store_patient_medication_count_cohort,
    patient_query_index as store_patient_query_index,
    patient_visit_count_cohort as store_patient_visit_count_cohort,
)

def _contains_label(values: List[str], query: str) -> bool:
    lowered = query.lower()
    return any(lowered in value.lower() for value in values)


def _extract_disease_labels(record: Dict[str, Any]) -> List[str]:
    diseases = record.get("diseases")
    labels: List[str] = []
    if not isinstance(diseases, list):
        return labels
    for item in diseases:
        if not isinstance(item, dict):
            continue
        code = item.get("diseaseCode")
        if isinstance(code, dict):
            label = normalize_value(code.get("label")) or normalize_value(code.get("id"))
            if label is not None:
                text = str(label)
                if text not in labels:
                    labels.append(text)
    return labels


def disease_cohort(data_dir: str, disease_query: str) -> Dict[str, Any]:
    resolved_dir = ensure_data_dir(data_dir)
    bundles = group_patients(resolved_dir)
    query = disease_query.strip().lower()
    matches: List[Dict[str, Any]] = []

    for patient_id, bundle in sorted(bundles.items()):
        matched_visits: List[Dict[str, Any]] = []
        matched_labels: List[str] = []
        medication_labels: List[str] = []
        original_record_ids: List[str] = []
        for visit in bundle.context.visits:
            labels = _extract_disease_labels(visit.provenance.raw_bff)
            visit_matches = [label for label in labels if query in label.lower()]
            if not visit_matches:
                continue
            original_id = normalize_value(visit.provenance.raw_bff.get("id"))
            if isinstance(original_id, str) and original_id not in original_record_ids:
                original_record_ids.append(original_id)
            for medication_label in extract_treatment_labels(visit.provenance.raw_bff):
                if medication_label not in medication_labels:
                    medication_labels.append(medication_label)
            for label in visit_matches:
                if label not in matched_labels:
                    matched_labels.append(label)
            matched_visits.append(
                {
                    "visit_id": visit.visit_id,
                    "original_id": str(original_id) if isinstance(original_id, str) else None,
                    "event_type": visit.event_type,
                    "event_date": visit.event_date,
                    "matched_diseases": visit_matches,
                    "source_file": visit.provenance.source_file,
                    "record_index": visit.provenance.record_index,
                }
            )

        if matched_visits:
            matches.append(
                {
                    "patient_id": patient_id,
                    "sex": bundle.context.sex,
                    "visit_count": len(matched_visits),
                    "medications": medication_labels,
                    "medication_count": len(medication_labels),
                    "matched_diseases": matched_labels,
                    "original_record_ids": original_record_ids,
                    "visits": matched_visits,
                }
            )

    return {
        "query": disease_query,
        "match_type": "case-insensitive substring",
        "patient_count": len(matches),
        "patients": matches,
    }


def disease_counts(data_dir: str) -> List[Dict[str, Any]]:
    resolved_dir = ensure_data_dir(data_dir)
    bundles = group_patients(resolved_dir)
    counts: Dict[str, Dict[str, Any]] = {}

    for patient_id, bundle in bundles.items():
        seen_for_patient = set()
        for visit in bundle.context.visits:
            for label in _extract_disease_labels(visit.provenance.raw_bff):
                entry = counts.setdefault(
                    label,
                    {"disease": label, "patient_count": 0, "patients": []},
                )
                if label in seen_for_patient:
                    continue
                seen_for_patient.add(label)
                entry["patient_count"] += 1
                entry["patients"].append(patient_id)

    return sorted(counts.values(), key=lambda item: (-item["patient_count"], item["disease"]))


def _patient_inventory_from_records(data_dir: str, scoped_patient_ids: Optional[List[str]] = None) -> List[str]:
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


def _patient_inventory(data_dir: str, scoped_patient_ids: Optional[List[str]] = None) -> List[str]:
    return _patient_inventory_from_records(data_dir, scoped_patient_ids=scoped_patient_ids)


def _sample_inventory(data_dir: str, scoped_patient_ids: Optional[List[str]] = None) -> List[str]:
    return _build_query_scope_context(data_dir, scoped_patient_ids=scoped_patient_ids).sample_ids


def _medication_counts(data_dir: str, scoped_patient_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    if duckdb_available() and not scoped_patient_ids:
        try:
            return store_medication_counts(data_dir)
        except QueryStoreNotReadyError:
            raise
        except Exception:
            pass
    if not scoped_patient_ids:
        return medication_counts(data_dir)
    return _build_query_scope_context(data_dir, scoped_patient_ids=scoped_patient_ids).medication_counts


def _disease_counts(data_dir: str, scoped_patient_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    if duckdb_available() and not scoped_patient_ids:
        try:
            return store_disease_counts(data_dir)
        except QueryStoreNotReadyError:
            raise
        except Exception:
            pass
    if not scoped_patient_ids:
        return disease_counts(data_dir)
    return _build_query_scope_context(data_dir, scoped_patient_ids=scoped_patient_ids).disease_counts


def _medication_cohort(data_dir: str, medication_query: str, scoped_patient_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    if duckdb_available() and not scoped_patient_ids:
        try:
            return store_medication_cohort(data_dir, medication_query)
        except QueryStoreNotReadyError:
            raise
        except Exception:
            pass
    return _apply_patient_scope_to_cohort(medication_cohort(data_dir, medication_query), scoped_patient_ids)


def _disease_cohort(data_dir: str, disease_query: str, scoped_patient_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    if duckdb_available() and not scoped_patient_ids:
        try:
            return store_disease_cohort(data_dir, disease_query)
        except QueryStoreNotReadyError:
            raise
        except Exception:
            pass
    return _apply_patient_scope_to_cohort(disease_cohort(data_dir, disease_query), scoped_patient_ids)


def _extract_patient_id(text: str) -> Optional[str]:
    for prefix in entity_identifier_prefixes("patient"):
        match = re.search(rf"\b{re.escape(prefix)}\s+([A-Za-z0-9:_-]+)\b", text, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def _extract_patient_ids_from_text(text: str, known_ids: List[str]) -> List[str]:
    found: List[str] = []
    lowered = str(text or "").lower()
    for patient_id in known_ids:
        token = patient_id.lower()
        pattern = rf"(?<![A-Za-z0-9_]){re.escape(token)}(?![A-Za-z0-9_])"
        if re.search(pattern, lowered) and patient_id not in found:
            found.append(patient_id)
    return found


def _extract_patient_like_tokens_from_text(text: str) -> List[str]:
    candidates: List[str] = []
    seen = set()
    for match in re.finditer(r"\b(?:beacon|syn)[_: -]?\d+(?::[A-Za-z0-9._-]+)?\b", str(text or ""), flags=re.IGNORECASE):
        token = match.group(0).strip().replace(" ", "_").replace("-", "_")
        normalized = token.upper()
        if normalized not in seen:
            seen.add(normalized)
            candidates.append(normalized)
    return candidates


def _explicit_patient_cohort_ids(text: str, known_ids: List[str]) -> Optional[Dict[str, List[str]]]:
    normalized = normalize_entity_synonym_mentions(text, "patient", "patient", "patients").strip()
    if not normalized:
        return None
    matched_ids = _extract_patient_ids_from_text(normalized, known_ids)
    if len(matched_ids) < 2:
        return None

    lowered = normalized.lower()
    if re.match(
        r"^(?:which|what|list|show|select|find)\s+patients?\s+(?:are|is)\b",
        lowered,
    ) or re.match(
        r"^(?:create|make|build|save)\s+(?:a\s+)?cohort\b",
        lowered,
    ) or re.match(
        r"^(?:patients?|patient ids?|ids?)\s*[:=]",
        lowered,
    ):
        candidate_tokens = _extract_patient_like_tokens_from_text(normalized)
        invalid_ids = [token for token in candidate_tokens if token not in set(matched_ids)]
        return {
            "patient_ids": matched_ids,
            "invalid_ids": invalid_ids,
        }

    residue = normalized
    for patient_id in matched_ids:
        residue = re.sub(
            rf"(?<![A-Za-z0-9_]){re.escape(patient_id)}(?![A-Za-z0-9_])",
            " ",
            residue,
            flags=re.IGNORECASE,
        )
    residue = re.sub(r"[,:;(){}\[\]]+", " ", residue)
    residue = re.sub(
        r"\b(?:and|or|vs|versus|patients?|subjects?|individuals?|participants?|ids?)\b",
        " ",
        residue,
        flags=re.IGNORECASE,
    )
    residue = re.sub(r"\s+", " ", residue).strip()
    if residue:
        return None
    candidate_tokens = _extract_patient_like_tokens_from_text(normalized)
    invalid_ids = [token for token in candidate_tokens if token not in set(matched_ids)]
    return {
        "patient_ids": matched_ids,
        "invalid_ids": invalid_ids,
    }


def _patient_query_index(data_dir: str) -> List[Dict[str, Any]]:
    if duckdb_available():
        try:
            return store_patient_query_index(data_dir)
        except QueryStoreNotReadyError:
            raise
        except Exception:
            pass
    resolved_dir = ensure_data_dir(data_dir)
    bundles = group_patients(resolved_dir)
    rows: List[Dict[str, Any]] = []

    for patient_id, bundle in sorted(bundles.items()):
        medication_labels: List[str] = []
        disease_labels: List[str] = []
        original_record_ids: List[str] = []

        for visit in bundle.context.visits:
            original_id = normalize_value(visit.provenance.raw_bff.get("id"))
            if isinstance(original_id, str) and original_id not in original_record_ids:
                original_record_ids.append(original_id)
            for label in extract_treatment_labels(visit.provenance.raw_bff):
                if label not in medication_labels:
                    medication_labels.append(label)
            for label in _extract_disease_labels(visit.provenance.raw_bff):
                if label not in disease_labels:
                    disease_labels.append(label)

        rows.append(
            {
                "patient_id": patient_id,
                "sex": bundle.context.sex,
                "visit_count": len(bundle.context.visits),
                "medications": medication_labels,
                "medication_count": len(medication_labels),
                "diseases": disease_labels,
                "disease_count": len(disease_labels),
                "original_record_ids": original_record_ids,
            }
        )

    return rows


def _build_query_scope_context(data_dir: str, scoped_patient_ids: Optional[List[str]] = None) -> QueryScopeContext:
    return _build_query_scope_context_from_rows(
        data_dir,
        _patient_query_index(data_dir),
        scoped_patient_ids=scoped_patient_ids,
    )


def _should_apply_scoped_context(
    query: str,
    history: Optional[List[Dict[str, str]]] = None,
    scoped_patient_ids: Optional[List[str]] = None,
) -> bool:
    if not history or not scoped_patient_ids:
        return False
    lowered = query.lower()
    if any(phrase in lowered for phrase in ("full workspace", "entire workspace", "whole workspace", "all patients in the workspace")):
        return False
    if re.search(r"\bshow patient\s+[A-Za-z0-9:_-]+\b", lowered):
        return False
    return True


def _sex_constraint(query: str) -> Optional[str]:
    lowered = query.lower()
    if re.search(r"\bmale\b|\bmales\b|\bman\b|\bmen\b", lowered):
        return "male"
    if re.search(r"\bfemale\b|\bfemales\b|\bwoman\b|\bwomen\b", lowered):
        return "female"
    return None


def _medication_count_constraint(query: str) -> Optional[Dict[str, Any]]:
    lowered = query.lower()
    if not any(keyword in lowered for keyword in ("medication", "medications", "drug", "drugs", "treatment", "treatments")):
        return None

    patterns = [
        (r"\bmore than\s+(\d+)\s+(?:medications?|drugs?|treatments?)\b", "gt"),
        (r"\bat least\s+(\d+)\s+(?:medications?|drugs?|treatments?)\b", "gte"),
        (r"\bless than\s+(\d+)\s+(?:medications?|drugs?|treatments?)\b", "lt"),
        (r"\bat most\s+(\d+)\s+(?:medications?|drugs?|treatments?)\b", "lte"),
        (r"\bexactly\s+(\d+)\s+(?:medications?|drugs?|treatments?)\b", "eq"),
    ]
    for pattern, operator in patterns:
        match = re.search(pattern, lowered)
        if match:
            return {"operator": operator, "value": int(match.group(1))}

    if re.search(r"\bno\s+(?:medications?|drugs?|treatments?)\b", lowered):
        return {"operator": "eq", "value": 0}
    if re.search(r"\bmore than one\s+(?:medications?|drugs?|treatments?)\b", lowered):
        return {"operator": "gt", "value": 1}
    if re.search(r"\bmore than 1\s+(?:medications?|drugs?|treatments?)\b", lowered):
        return {"operator": "gt", "value": 1}
    if re.search(r"\bone medication\b", lowered) and "more than" not in lowered and "less than" not in lowered:
        return {"operator": "eq", "value": 1}
    return None


def _visit_count_constraint(query: str) -> Optional[Dict[str, Any]]:
    lowered = query.lower()
    if not any(keyword in lowered for keyword in ("visit", "visits", "timepoint", "timepoints")):
        return None

    patterns = [
        (r"\bmore than\s+(\d+)\s+(?:visits?|timepoints?)\b", "gt"),
        (r"\bat least\s+(\d+)\s+(?:visits?|timepoints?)\b", "gte"),
        (r"\bless than\s+(\d+)\s+(?:visits?|timepoints?)\b", "lt"),
        (r"\bat most\s+(\d+)\s+(?:visits?|timepoints?)\b", "lte"),
        (r"\bexactly\s+(\d+)\s+(?:visits?|timepoints?)\b", "eq"),
    ]
    for pattern, operator in patterns:
        match = re.search(pattern, lowered)
        if match:
            return {"operator": operator, "value": int(match.group(1))}

    if re.search(r"\bno\s+(?:visits?|timepoints?)\b", lowered):
        return {"operator": "eq", "value": 0}
    if re.search(r"\bmore than one\s+(?:visits?|timepoints?)\b", lowered):
        return {"operator": "gt", "value": 1}
    if re.search(r"\bmore than 1\s+(?:visits?|timepoints?)\b", lowered):
        return {"operator": "gt", "value": 1}
    if re.search(r"\bone visit\b|\bone timepoint\b", lowered) and "more than" not in lowered and "less than" not in lowered:
        return {"operator": "eq", "value": 1}
    return None


def _matches_numeric_constraint(value: int, operator: str, target: int) -> bool:
    if operator == "gt":
        return value > target
    if operator == "gte":
        return value >= target
    if operator == "lt":
        return value < target
    if operator == "lte":
        return value <= target
    return value == target


def patient_medication_count_cohort(
    data_dir: str,
    operator: str,
    target: int,
    scoped_patient_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    if duckdb_available():
        try:
            return store_patient_medication_count_cohort(data_dir, operator, target)
        except QueryStoreNotReadyError:
            raise
        except Exception:
            pass
    patients = []
    for row in _apply_patient_scope_to_rows(_patient_query_index(data_dir), scoped_patient_ids):
        if _matches_numeric_constraint(row["medication_count"], operator, target):
            patients.append(row)

    return {
        "operator": operator,
        "target": target,
        "patient_count": len(patients),
        "patients": patients,
    }


def _format_medication_count_constraint(operator: str, target: int) -> str:
    noun = "medication" if target == 1 else "medications"
    if operator == "gt":
        return f"more than {target} {noun}"
    if operator == "gte":
        return f"at least {target} {noun}"
    if operator == "lt":
        return f"less than {target} {noun}"
    if operator == "lte":
        return f"at most {target} {noun}"
    if target == 0:
        return "no medications"
    if target == 1:
        return "exactly 1 medication"
    return f"exactly {target} medications"


def _format_visit_count_constraint(operator: str, target: int) -> str:
    noun = "timepoint" if target == 1 else "timepoints"
    if operator == "gt":
        return f"more than {target} {noun}"
    if operator == "gte":
        return f"at least {target} {noun}"
    if operator == "lt":
        return f"less than {target} {noun}"
    if operator == "lte":
        return f"at most {target} {noun}"
    if target == 0:
        return "no timepoints"
    if target == 1:
        return "exactly 1 timepoint"
    return f"exactly {target} timepoints"


def patient_visit_count_cohort(
    data_dir: str,
    operator: str,
    target: int,
    scoped_patient_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    if duckdb_available():
        try:
            return store_patient_visit_count_cohort(data_dir, operator, target)
        except QueryStoreNotReadyError:
            raise
        except Exception:
            pass
    patients = []
    for row in _apply_patient_scope_to_rows(_patient_query_index(data_dir), scoped_patient_ids):
        if _matches_numeric_constraint(row["visit_count"], operator, target):
            patients.append(row)
    return {
        "operator": operator,
        "target": target,
        "patient_count": len(patients),
        "patients": patients,
    }


def _cohort_over_time_summary(data_dir: str, scoped_patient_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    if duckdb_available():
        try:
            return store_cohort_over_time_summary(data_dir)
        except QueryStoreNotReadyError:
            raise
        except Exception:
            pass
    patient_rows = _apply_patient_scope_to_rows(_patient_query_index(data_dir), scoped_patient_ids)
    allowed = {str(item).strip() for item in scoped_patient_ids or [] if str(item).strip()}
    dated = []
    undated = 0
    period_counts: Dict[str, Dict[str, Any]] = {}
    for _, _, record in read_bff_records(ensure_data_dir(data_dir)):
        raw_patient_id = normalize_value(record.get("patient_id")) or normalize_value(record.get("id"))
        patient_id = str(raw_patient_id).split(":")[0] if isinstance(raw_patient_id, str) and raw_patient_id else ""
        if allowed and patient_id not in allowed:
            continue
        date = normalize_value(extract_event_date(record))
        if isinstance(date, str) and date.strip():
            date = date.strip()
            dated.append(date)
            period = date[:7] if len(date) >= 7 else date
            entry = period_counts.setdefault(period, {"period": period, "timepoint_count": 0, "patients": set()})
            entry["timepoint_count"] += 1
            if patient_id:
                entry["patients"].add(patient_id)
        else:
            undated += 1
    periods = [
        {
            "period": period,
            "timepoint_count": values["timepoint_count"],
            "patient_count": len(values["patients"]),
        }
        for period, values in sorted(period_counts.items())
    ]
    return {
        "timepoint_count": len(dated) + undated,
        "patient_count": len(patient_rows),
        "dated_timepoint_count": len(dated),
        "undated_timepoint_count": undated,
        "first_event_date": min(dated) if dated else None,
        "last_event_date": max(dated) if dated else None,
        "periods": periods,
    }


def _term_timepoint_summary(
    data_dir: str,
    term: str,
    scoped_patient_ids: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    medication = _apply_patient_scope_to_cohort(_medication_cohort(data_dir, term), scoped_patient_ids)
    disease = _apply_patient_scope_to_cohort(_disease_cohort(data_dir, term), scoped_patient_ids)
    if medication["patient_count"] == 0 and disease["patient_count"] == 0:
        return None
    selected = medication if medication["patient_count"] >= disease["patient_count"] else disease
    intent = "medication_timepoint_cohort" if selected is medication else "disease_timepoint_cohort"
    matched_timepoint_count = sum(len(item.get("visits", [])) for item in selected["patients"])
    return {
        "intent": intent,
        "term": term,
        "patient_count": selected["patient_count"],
        "timepoint_count": matched_timepoint_count,
        "patients": selected["patients"],
    }


def _term_from_timepoint_query(text: str) -> str:
    patterns = (
        r"(?:timepoints?|visits?)\s+(?:mentioning|mention|with)\s+(.+)",
        r"(?:with|for)\s+(.+?)\s*(?:over time)?$",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip(" ?.")
    return ""


def _negative_patient_term_query(text: str) -> Optional[Dict[str, str]]:
    patterns = (
        r"^how many patients do not have\s+(.+)$",
        r"^how many patients don't have\s+(.+)$",
        r"^which patients do not have\s+(.+)$",
        r"^which patients don't have\s+(.+)$",
        r"^list patients who do not have\s+(.+)$",
        r"^list patients who don't have\s+(.+)$",
        r"^which patients are not on\s+(.+)$",
        r"^how many patients are not on\s+(.+)$",
    )
    stripped = text.strip().rstrip("?.")
    lowered = stripped.lower()
    for pattern in patterns:
        match = re.match(pattern, lowered, flags=re.IGNORECASE)
        if match:
            term = stripped[match.start(1):].strip()
            intent = "count" if lowered.startswith("how many") else "list"
            return {"term": term, "intent": intent}
    return None


def _resolve_patient_filter_kind(
    data_dir: str,
    term: str,
    preferred_kind: Optional[str] = None,
    scoped_patient_ids: Optional[List[str]] = None,
) -> Tuple[Optional[str], Dict[str, Any]]:
    if preferred_kind == "disease":
        cohort = _apply_patient_scope_to_cohort(_disease_cohort(data_dir, term), scoped_patient_ids)
        return "disease", cohort
    if preferred_kind == "medication":
        cohort = _apply_patient_scope_to_cohort(_medication_cohort(data_dir, term), scoped_patient_ids)
        return "medication", cohort

    disease = _apply_patient_scope_to_cohort(_disease_cohort(data_dir, term), scoped_patient_ids)
    medication = _apply_patient_scope_to_cohort(_medication_cohort(data_dir, term), scoped_patient_ids)
    if disease["patient_count"] == 0 and medication["patient_count"] == 0:
        return None, {"patient_count": 0, "patients": []}
    if disease["patient_count"] >= medication["patient_count"]:
        return "disease", disease
    return "medication", medication


def _looks_like_treatment_category_candidate(term: str) -> bool:
    normalized = normalize_value(term).strip().lower()
    if not normalized:
        return False
    if not re.fullmatch(r"[a-z][a-z\s-]{2,}", normalized):
        return False
    if normalized in {"disease", "diseases", "treatment", "treatments", "medication", "medications"}:
        return False
    return normalized.endswith("s")


def _parse_patient_filter_clause(clause: str) -> Optional[Dict[str, str]]:
    cleaned = clause.strip().strip("?.")
    if not cleaned:
        return None

    timepoint_constraint = _visit_count_constraint(cleaned)
    if timepoint_constraint is not None and any(keyword in cleaned.lower() for keyword in ("with", "mention")):
        term = _term_from_timepoint_query(cleaned)
        if term:
            return {
                "mode": "include",
                "preferred_kind": "",
                "term": term,
                "scope": "timepoint",
                "operator": timepoint_constraint["operator"],
                "value": str(timepoint_constraint["value"]),
            }

    if re.search(r"\bno\s+(?:timepoints?|visits?)\s+(?:with|mentioning|mention)\s+", cleaned, flags=re.IGNORECASE):
        term = _term_from_timepoint_query(cleaned)
        if term:
            return {
                "mode": "exclude",
                "preferred_kind": "",
                "term": term,
                "scope": "timepoint",
                "operator": "gt",
                "value": "0",
            }

    patterns = [
        (r"^(?:do not|don't)\s+have\s+(.+)$", "exclude", "disease"),
        (r"^(?:do not|don't)\s+take\s+(.+)$", "exclude", "medication"),
        (r"^(?:are not on|not on)\s+(.+)$", "exclude", "medication"),
        (r"^without\s+(.+)$", "exclude", None),
        (r"^(?:have|has)\s+(.+)$", "include", "disease"),
        (r"^(?:take|takes|taking)\s+(.+)$", "include", "medication"),
        (r"^(?:are on|on|using|use|uses|treated with|receive|receives)\s+(.+)$", "include", "medication"),
        (r"^with\s+(.+)$", "include", None),
    ]
    for pattern, mode, preferred_kind in patterns:
        match = re.match(pattern, cleaned, flags=re.IGNORECASE)
        if match:
            term = match.group(1).strip().strip("?.")
            if term:
                return {
                    "mode": mode,
                    "preferred_kind": preferred_kind or "",
                    "term": term,
                    "scope": "patient",
                    "operator": "",
                    "value": "",
                }
    return None


def _patient_filter_query(text: str) -> Optional[Dict[str, Any]]:
    stripped = text.strip().rstrip("?.")
    lowered = stripped.lower()
    prefixes = (
        "how many patients ",
        "which patients ",
        "list patients ",
    )
    prefix = next((item for item in prefixes if lowered.startswith(item)), None)
    if prefix is None:
        return None

    body = stripped[len(prefix):].strip()
    if not body:
        return None

    raw_clauses = re.split(r"\s+(?:but|and)\s+", body, flags=re.IGNORECASE)
    if len(raw_clauses) < 2:
        return None

    conditions: List[Dict[str, str]] = []
    for raw_clause in raw_clauses:
        parsed = _parse_patient_filter_clause(raw_clause)
        if parsed is None:
            return None
        conditions.append(parsed)

    intent = "count" if lowered.startswith("how many") else "list"
    return {"intent": intent, "conditions": conditions}


def _resolve_timepoint_filter_condition(
    data_dir: str,
    term: str,
    operator: str,
    target: int,
    scoped_patient_ids: Optional[List[str]] = None,
) -> Tuple[Optional[str], List[Dict[str, Any]], int]:
    result = _term_timepoint_summary(data_dir, term, scoped_patient_ids=scoped_patient_ids)
    if result is None:
        return None, [], 0
    kind = "medication" if result["intent"] == "medication_timepoint_cohort" else "disease"
    filtered = [
        item
        for item in result["patients"]
        if _matches_numeric_constraint(len(item.get("visits", [])), operator, target)
    ]
    return kind, filtered, result["patient_count"]


def _temporal_order_query(text: str) -> Optional[Dict[str, str]]:
    stripped = text.strip().rstrip("?.")
    lowered = stripped.lower()
    prefixes = (
        "which patients had ",
        "how many patients had ",
        "list patients who had ",
    )
    prefix = next((item for item in prefixes if lowered.startswith(item)), None)
    if prefix is None:
        return None

    body = stripped[len(prefix):].strip()
    for relation in (" before ", " after "):
        if relation in body.lower():
            parts = re.split(relation, body, maxsplit=1, flags=re.IGNORECASE)
            if len(parts) != 2:
                return None
            earlier = parts[0].strip()
            later = parts[1].strip()
            if not earlier or not later:
                return None
            return {
                "intent": "count" if lowered.startswith("how many") else "list",
                "first_term": earlier,
                "second_term": later,
                "relation": relation.strip(),
            }
    return None


def _transition_query(text: str) -> Optional[Dict[str, str]]:
    stripped = text.strip().rstrip("?.")
    lowered = stripped.lower()
    prefixes = (
        "which patients changed from ",
        "how many patients changed from ",
        "list patients who changed from ",
    )
    prefix = next((item for item in prefixes if lowered.startswith(item)), None)
    if prefix is None:
        return None

    body = stripped[len(prefix):].strip()
    parts = re.split(r"\s+to\s+", body, maxsplit=1, flags=re.IGNORECASE)
    if len(parts) != 2:
        return None
    first_term = parts[0].strip()
    second_term = parts[1].strip()
    if not first_term or not second_term:
        return None
    return {
        "intent": "count" if lowered.startswith("how many") else "list",
        "first_term": first_term,
        "second_term": second_term,
    }


def _start_after_query(text: str) -> Optional[Dict[str, str]]:
    stripped = text.strip().rstrip("?.")
    lowered = stripped.lower()
    prefixes = (
        "which patients started ",
        "how many patients started ",
        "list patients who started ",
    )
    prefix = next((item for item in prefixes if lowered.startswith(item)), None)
    if prefix is None:
        return None

    body = stripped[len(prefix):].strip()
    parts = re.split(r"\s+after\s+", body, maxsplit=1, flags=re.IGNORECASE)
    if len(parts) != 2:
        return None
    started_term = parts[0].strip()
    after_term = parts[1].strip()
    if not started_term or not after_term:
        return None
    return {
        "intent": "count" if lowered.startswith("how many") else "list",
        "started_term": started_term,
        "after_term": after_term,
    }


def _dated_patient_term_events(
    data_dir: str,
    term: str,
    scoped_patient_ids: Optional[List[str]] = None,
) -> Tuple[Optional[str], Dict[str, List[str]]]:
    kind, cohort = _resolve_patient_filter_kind(data_dir, term, scoped_patient_ids=scoped_patient_ids)
    if kind is None:
        return None, {}

    events: Dict[str, List[str]] = {}
    for item in cohort["patients"]:
        patient_id = item["patient_id"]
        for visit in item.get("visits", []):
            event_date = visit.get("event_date")
            if isinstance(event_date, str) and event_date.strip():
                events.setdefault(patient_id, []).append(event_date.strip())
    for patient_id in list(events.keys()):
        events[patient_id] = sorted(set(events[patient_id]))
    return kind, events


def _patient_temporal_order_cohort(
    data_dir: str,
    first_term: str,
    second_term: str,
    relation: str,
    scoped_patient_ids: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    first_kind, first_events = _dated_patient_term_events(data_dir, first_term, scoped_patient_ids=scoped_patient_ids)
    second_kind, second_events = _dated_patient_term_events(data_dir, second_term, scoped_patient_ids=scoped_patient_ids)
    if first_kind is None or second_kind is None:
        return None

    inventory = _apply_patient_scope_to_rows(_patient_query_index(data_dir), scoped_patient_ids)
    rows_by_id = {row["patient_id"]: row for row in inventory}
    matched_rows: List[Dict[str, Any]] = []

    candidate_ids = set(first_events) & set(second_events)
    for patient_id in sorted(candidate_ids):
        first_dates = first_events.get(patient_id, [])
        second_dates = second_events.get(patient_id, [])
        if not first_dates or not second_dates:
            continue
        condition_met = min(first_dates) < max(second_dates) if relation == "before" else max(first_dates) > min(second_dates)
        if not condition_met:
            continue
        row = dict(rows_by_id.get(patient_id, {"patient_id": patient_id}))
        row["first_term_dates"] = first_dates
        row["second_term_dates"] = second_dates
        matched_rows.append(row)

    return {
        "first_term": first_term,
        "second_term": second_term,
        "relation": relation,
        "first_kind": first_kind,
        "second_kind": second_kind,
        "patient_count": len(matched_rows),
        "patient_ids": [row["patient_id"] for row in matched_rows],
        "patients": matched_rows,
    }


def _patient_transition_cohort(
    data_dir: str,
    first_term: str,
    second_term: str,
    scoped_patient_ids: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    first_kind, first_events = _dated_patient_term_events(data_dir, first_term, scoped_patient_ids=scoped_patient_ids)
    second_kind, second_events = _dated_patient_term_events(data_dir, second_term, scoped_patient_ids=scoped_patient_ids)
    if first_kind is None or second_kind is None:
        return None

    inventory = _apply_patient_scope_to_rows(_patient_query_index(data_dir), scoped_patient_ids)
    rows_by_id = {row["patient_id"]: row for row in inventory}
    matched_rows: List[Dict[str, Any]] = []

    candidate_ids = set(first_events) & set(second_events)
    for patient_id in sorted(candidate_ids):
        first_dates = first_events.get(patient_id, [])
        second_dates = second_events.get(patient_id, [])
        if not first_dates or not second_dates:
            continue
        if min(first_dates) >= max(second_dates):
            continue
        row = dict(rows_by_id.get(patient_id, {"patient_id": patient_id}))
        row["from_term_dates"] = first_dates
        row["to_term_dates"] = second_dates
        matched_rows.append(row)

    return {
        "first_term": first_term,
        "second_term": second_term,
        "first_kind": first_kind,
        "second_kind": second_kind,
        "patient_count": len(matched_rows),
        "patient_ids": [row["patient_id"] for row in matched_rows],
        "patients": matched_rows,
    }


def _patient_started_after_cohort(
    data_dir: str,
    started_term: str,
    after_term: str,
    scoped_patient_ids: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    started_kind, started_events = _dated_patient_term_events(data_dir, started_term, scoped_patient_ids=scoped_patient_ids)
    after_kind, after_events = _dated_patient_term_events(data_dir, after_term, scoped_patient_ids=scoped_patient_ids)
    if started_kind is None or after_kind is None:
        return None

    inventory = _apply_patient_scope_to_rows(_patient_query_index(data_dir), scoped_patient_ids)
    rows_by_id = {row["patient_id"]: row for row in inventory}
    matched_rows: List[Dict[str, Any]] = []

    candidate_ids = set(started_events) & set(after_events)
    for patient_id in sorted(candidate_ids):
        started_dates = started_events.get(patient_id, [])
        after_dates = after_events.get(patient_id, [])
        if not started_dates or not after_dates:
            continue
        if min(started_dates) <= min(after_dates):
            continue
        row = dict(rows_by_id.get(patient_id, {"patient_id": patient_id}))
        row["started_term_dates"] = started_dates
        row["after_term_dates"] = after_dates
        matched_rows.append(row)

    return {
        "started_term": started_term,
        "after_term": after_term,
        "started_kind": started_kind,
        "after_kind": after_kind,
        "patient_count": len(matched_rows),
        "patient_ids": [row["patient_id"] for row in matched_rows],
        "patients": matched_rows,
    }


def _is_patient_list_query(text: str) -> bool:
    return inventory_prompt_matches(text, "patient")


def _is_sample_list_query(text: str) -> bool:
    return inventory_prompt_matches(text, "sample")


def _is_patient_count_query(text: str) -> bool:
    return inventory_count_prompt_matches(text, "patient")


def _render_patient_summary(navigator: Dict[str, Any]) -> str:
    summary = navigator["summary"]
    context = navigator["patient_context"]
    return (
        "Patient {patient_id} has {visit_count} visits. Sex: {sex}. "
        "DOB: {date_of_birth}. Vital status: {vital_status}."
    ).format(
        patient_id=summary["patient_id"],
        visit_count=summary["visit_count"],
        sex=context.get("sex") or "n/a",
        date_of_birth=context.get("date_of_birth") or "n/a",
        vital_status=context.get("vital_status") or "n/a",
    )


def _render_visit_list(navigator: Dict[str, Any]) -> str:
    visits = navigator["visits"]
    if not visits:
        return "No visits found for that patient."
    parts = []
    for visit in visits:
        parts.append("%s (%s)" % (visit["visit_id"], visit.get("diagnosis") or visit.get("event_type") or "event"))
    return "Visits: " + ", ".join(parts)


def _render_patient_timeline(navigator: Dict[str, Any]) -> str:
    visits = navigator["visits"]
    if not visits:
        return "No timepoints found for that patient."
    lines = [f"Timeline for patient {navigator['patient_id']}:"]
    for visit in visits:
        diseases = visit.get("evidence", {}).get("diseases", {}).get("examples", [])
        treatments = visit.get("evidence", {}).get("treatments", {}).get("examples", [])
        lines.append(
            "- {visit_id} | date: {event_date} | diagnosis: {diagnosis} | diseases: {diseases} | treatments: {treatments}".format(
                visit_id=visit.get("visit_id") or "n/a",
                event_date=visit.get("event_date") or "n/a",
                diagnosis=visit.get("diagnosis") or visit.get("event_type") or "n/a",
                diseases=", ".join(diseases) if diseases else "none",
                treatments=", ".join(treatments) if treatments else "none",
            )
        )
    return "\n".join(lines)


def _lm_studio_max_patient_summaries() -> int:
    raw = os.getenv("LM_STUDIO_MAX_PATIENT_SUMMARIES", "8").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 8


def _lm_studio_max_history_turns() -> int:
    raw = os.getenv("LM_STUDIO_MAX_HISTORY_TURNS", "4").strip()
    try:
        return max(0, int(raw))
    except ValueError:
        return 4


def _lm_studio_include_patient_navigator() -> bool:
    value = os.getenv("LM_STUDIO_INCLUDE_PATIENT_NAVIGATOR", "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _follow_up_suggestions(query: str) -> List[str]:
    text = query.strip().rstrip("?.")
    if not text:
        return [
            "How many patients are in this workspace?",
            "What diseases appear most often?",
            "Show patient 107",
        ]

    normalized_subject = re.sub(
        r"^(?:how many patients (?:have|take|takes|are taking|receive|received|are on|use|used)|which patients (?:have|take|takes|are taking|receive|received|are on|use|used))\s+",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()
    normalized_subject = re.sub(r"^(?:what treatments are associated with|show the visits mentioning)\s+", "", normalized_subject, flags=re.IGNORECASE).strip()
    normalized_subject = normalized_subject.rstrip("?.").strip()
    subject = normalized_subject or text
    lowered = text.lower()
    if _extract_patient_id(text) or re.search(r"\bpatient\s+[A-Za-z0-9:_-]+\b", text, flags=re.IGNORECASE):
        return [
            f"List visits for {text}",
            f"What treatments are recorded for {text}?",
            f"Summarize the key evidence for {text}.",
        ]
    if any(keyword in lowered for keyword in ("disease", "diagnosis", "crohn", "colitis")):
        return [
            f"How many patients have {subject}?",
            f"Which patients have {subject}?",
            f"What treatments are associated with {subject}?",
        ]
    if any(keyword in lowered for keyword in ("medication", "drug", "treatment", "prednisolone", "infliximab", "take ", "takes ", "taking ", "receive ", "received ", "use ", "used ", " on ")):
        return [
            f"How many patients have {subject}?",
            f"Which patients have {subject}?",
            f"Show the visits mentioning {subject}.",
        ]
    return [
        f"{text} by patient",
        f"{text} over time",
        f"What evidence supports {text}?",
    ]


def _needs_clarification(query: str) -> bool:
    lowered = query.strip().lower()
    if not lowered:
        return False
    vague_prompts = {
        "help",
        "what about this",
        "tell me more",
        "continue",
        "go on",
        "why",
        "and",
        "what next",
        "more",
    }
    if lowered in vague_prompts:
        return True
    tokens = re.findall(r"[a-z0-9:_-]+", lowered)
    return len(tokens) < 3


def _lm_scoped_overview(data_dir: str, scoped_patient_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    rows = _apply_patient_scope_to_rows(_patient_query_index(data_dir), scoped_patient_ids)
    medication_counts: Dict[str, int] = {}
    disease_counts: Dict[str, int] = {}
    for row in rows:
        for label in row.get("medications", []) if isinstance(row, dict) else []:
            medication_counts[str(label)] = medication_counts.get(str(label), 0) + 1
        for label in row.get("diseases", []) if isinstance(row, dict) else []:
            disease_counts[str(label)] = disease_counts.get(str(label), 0) + 1
    top_medications = [item[0] for item in sorted(medication_counts.items(), key=lambda item: (-item[1], item[0]))[:10]]
    top_diseases = [item[0] for item in sorted(disease_counts.items(), key=lambda item: (-item[1], item[0]))[:10]]
    return {
        "dataset_overview": {
            "patients": len(rows),
            "visits": sum(int(row.get("visit_count", 0)) for row in rows),
        },
        "top_medications": top_medications,
        "top_diseases": top_diseases,
    }


def _lm_history_context(
    history: Optional[List[Dict[str, str]]],
    granularity_mode: str,
) -> List[Dict[str, str]]:
    if not history or granularity_mode == "summary":
        return []
    max_history_turns = _lm_studio_max_history_turns()
    return history[-max_history_turns:] if max_history_turns else []


def _lm_studio_context(
    data_dir: str,
    query: str,
    history: Optional[List[Dict[str, str]]] = None,
    scoped_patient_ids: Optional[List[str]] = None,
    scope_context: Optional[QueryScopeContext] = None,
    granularity_mode: str = "detailed",
    ai_provider_access: str = "detailed_allowed",
) -> Dict[str, Any]:
    normalized_ai_provider_access = _normalize_ai_provider_access(ai_provider_access)
    if normalized_ai_provider_access == "safe_summary":
        return _restricted_ai_provider_context(query)
    summaries = list_patient_summaries(data_dir)
    allowed = {str(item).strip() for item in scoped_patient_ids or [] if str(item).strip()}
    if allowed:
        summaries = [summary for summary in summaries if str(summary.patient_id).strip() in allowed]
        scoped_overview = {
            "dataset_overview": {
                "patients": len(scope_context.patient_rows) if scope_context else len(summaries),
                "visits": sum(int(row.get("visit_count", 0)) for row in (scope_context.patient_rows if scope_context else [])),
            },
            "top_medications": scope_context.medication_counts[:10] if scope_context else _lm_scoped_overview(data_dir, scoped_patient_ids)["top_medications"],
            "top_diseases": scope_context.disease_counts[:10] if scope_context else _lm_scoped_overview(data_dir, scoped_patient_ids)["top_diseases"],
        }
        if scope_context:
            scoped_overview["top_medications"] = [item["medication"] for item in scope_context.medication_counts[:10]]
            scoped_overview["top_diseases"] = [item["disease"] for item in scope_context.disease_counts[:10]]
    else:
        scoped_overview = {
            "dataset_overview": dashboard_summary(data_dir)["totals"],
            "top_medications": [item["medication"] for item in _medication_counts(data_dir)[:10]],
            "top_diseases": [item["disease"] for item in _disease_counts(data_dir)[:10]],
        }
    patient_id = _extract_patient_id(query)
    context: Dict[str, Any] = {
        "question": query,
        "dataset_overview": scoped_overview["dataset_overview"],
        "top_medications": scoped_overview["top_medications"],
        "top_diseases": scoped_overview["top_diseases"],
        "patient_summaries": [
            (
                {
                    "visit_count": summary.visit_count,
                    "sex": summary.sex,
                    "first_event_date": summary.first_event_date,
                    "last_event_date": summary.last_event_date,
                    "disease_count": summary.evidence.diseases.count,
                    "treatment_count": summary.evidence.treatments.count,
                }
                if granularity_mode == "summary"
                else {
                    "patient_id": summary.patient_id,
                    "visit_count": summary.visit_count,
                    "sex": summary.sex,
                    "first_event_date": summary.first_event_date,
                    "last_event_date": summary.last_event_date,
                    "disease_count": summary.evidence.diseases.count,
                    "treatment_count": summary.evidence.treatments.count,
                }
            )
            for summary in summaries[: _lm_studio_max_patient_summaries()]
        ],
    }
    history_context = _lm_history_context(history, granularity_mode)
    if history_context:
        context["conversation_history"] = history_context
    if granularity_mode != "summary" and patient_id is not None and _lm_studio_include_patient_navigator():
        navigator = build_patient_navigator(data_dir, patient_id)
        if navigator is not None:
            context["patient_navigator"] = {
                "summary": navigator.summary.model_dump(),
                "patient_context": navigator.patient_context.model_dump(),
                "visits": [
                    {
                        "visit_id": visit.visit_id,
                        "event_date": visit.event_date,
                        "event_type": visit.event_type,
                        "diagnosis": visit.diagnosis,
                    }
                    for visit in navigator.visits[:6]
                ],
                "key_fragments": [fragment.model_dump() for fragment in navigator.key_fragments[:12]],
            }
    return context


def _extract_lm_response_text(response: Dict[str, Any]) -> Optional[str]:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        return None

    message = choices[0].get("message", {})
    content = message.get("content")
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str):
                parts.append(item["text"])
        content = "\n".join(parts).strip()

    if not isinstance(content, str) or not content.strip():
        return None
    return _sanitize_lm_text(content)


def _resolve_lm_studio_model() -> Optional[str]:
    configured = os.getenv("LM_STUDIO_MODEL", "").strip()
    if configured:
        return configured
    try:
        payload = _http_json(f"{_lm_studio_base_url()}/models", log_kind="query_models")
    except (error.URLError, TimeoutError, json.JSONDecodeError):
        return None
    data = payload.get("data")
    if not isinstance(data, list) or not data:
        return None
    first = data[0]
    if not isinstance(first, dict):
        return None
    model_id = first.get("id")
    return model_id if isinstance(model_id, str) and model_id.strip() else None


def _semantic_query_catalog(
    data_dir: str,
    scoped_patient_ids: Optional[List[str]] = None,
    scope_context: Optional[QueryScopeContext] = None,
    ai_provider_access: str = "detailed_allowed",
) -> Dict[str, Any]:
    if _normalize_ai_provider_access(ai_provider_access) == "safe_summary":
        return {
            "supported_domains": ["patient_id", "disease", "treatment", "medication_count", "visit_count"],
            "supported_outputs": ["count", "patient_list"],
            "supported_logic": ["and", "or"],
            "supported_string_operators": ["contains", "eq"],
            "supported_numeric_operators": ["eq", "gt", "gte", "lt", "lte"],
            "catalog_policy": "Safe-summary AI-provider mode does not expose patient-derived clinical catalog values.",
        }
    context = scope_context or _build_query_scope_context(data_dir, scoped_patient_ids=scoped_patient_ids)
    return {
        "patient_count": len(context.patient_ids),
        "supported_domains": ["patient_id", "disease", "treatment", "medication_count", "visit_count"],
        "supported_outputs": ["count", "patient_list"],
        "supported_logic": ["and", "or"],
        "supported_string_operators": ["contains", "eq"],
        "supported_numeric_operators": ["eq", "gt", "gte", "lt", "lte"],
        "known_diseases": [item["disease"] for item in context.disease_counts[:50]],
        "known_treatments": [item["medication"] for item in context.medication_counts[:50]],
    }


def _extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _validate_semantic_query_plan(plan: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if plan.get("intent") != "cohort_query":
        return None

    output = plan.get("output")
    logic = str(plan.get("logic", "and")).lower()
    filters = plan.get("filters")
    if output not in {"count", "patient_list"} or logic not in {"and", "or"} or not isinstance(filters, list) or not filters:
        return None

    validated_filters: List[Dict[str, Any]] = []
    for item in filters[:6]:
        if not isinstance(item, dict):
            return None
        domain = str(item.get("domain", "")).strip().lower()
        operator = str(item.get("operator", "")).strip().lower()
        negate = bool(item.get("negate", False))
        if domain in {"patient_id", "disease", "treatment"}:
            if operator not in {"contains", "eq"}:
                return None
            value = normalize_value(item.get("value"))
            if not isinstance(value, str) or not value.strip():
                return None
            validated_filters.append(
                {"domain": domain, "operator": operator, "value": value.strip(), "negate": negate}
            )
            continue
        if domain in {"medication_count", "visit_count"}:
            if operator not in {"eq", "gt", "gte", "lt", "lte"}:
                return None
            value = item.get("value")
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                return None
            validated_filters.append(
                {"domain": domain, "operator": operator, "value": int(value), "negate": negate}
            )
            continue
        return None

    if not validated_filters:
        return None

    return {"intent": "cohort_query", "output": output, "logic": logic, "filters": validated_filters}


def _semantic_filter_matches(row: Dict[str, Any], condition: Dict[str, Any]) -> bool:
    domain = condition["domain"]
    operator = condition["operator"]
    value = condition["value"]

    if domain == "patient_id":
        patient_id = str(row.get("patient_id", ""))
        matched = value.lower() == patient_id.lower() if operator == "eq" else value.lower() in patient_id.lower()
    elif domain == "disease":
        labels = [str(item) for item in row.get("diseases", [])]
        matched = any(
            value.lower() == label.lower() if operator == "eq" else value.lower() in label.lower()
            for label in labels
        )
    elif domain == "treatment":
        labels = [str(item) for item in row.get("medications", [])]
        matched = any(
            value.lower() == label.lower() if operator == "eq" else value.lower() in label.lower()
            for label in labels
        )
    elif domain == "medication_count":
        matched = _matches_numeric_constraint(int(row.get("medication_count", 0)), operator, int(value))
    else:
        matched = _matches_numeric_constraint(int(row.get("visit_count", 0)), operator, int(value))

    return not matched if condition.get("negate") else matched


def _semantic_condition_label(condition: Dict[str, Any]) -> str:
    domain = condition["domain"]
    operator = condition["operator"]
    value = condition["value"]
    negate = condition.get("negate", False)

    if domain == "patient_id":
        return ("patient ID does not match '%s'" if negate else "patient ID matches '%s'") % value
    if domain == "disease":
        return ("does not have disease '%s'" if negate else "has disease '%s'") % value
    if domain == "treatment":
        return ("does not take '%s'" if negate else "takes '%s'") % value
    if domain == "medication_count":
        prefix = "does not have " if negate else "has "
        return prefix + _format_medication_count_constraint(operator, int(value))
    prefix = "does not have " if negate else "has "
    return prefix + _format_visit_count_constraint(operator, int(value))


def _semantic_query_follow_ups(plan: Dict[str, Any], filtered_rows: List[Dict[str, Any]]) -> List[str]:
    first = plan["filters"][0]
    if first["domain"] in {"patient_id", "disease", "treatment"}:
        return _follow_up_suggestions(str(first["value"]))
    if first["domain"] == "medication_count":
        label = _format_medication_count_constraint(first["operator"], int(first["value"]))
    else:
        label = _format_visit_count_constraint(first["operator"], int(first["value"]))
    return [
        "How many patients have %s?" % label,
        "Which patients have %s?" % label,
        "Show patient %s" % (filtered_rows[0]["patient_id"] if filtered_rows else "107"),
    ]


def _requested_query_output(query: str) -> Optional[str]:
    lowered = query.strip().lower()
    if lowered.startswith("how many patients"):
        return "count"
    if lowered.startswith("which patients") or lowered.startswith("list patients"):
        return "patient_list"
    return None


def _execute_semantic_query_plan(
    data_dir: str,
    query: str,
    plan: Dict[str, Any],
    model: str,
    scoped_patient_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    inventory = _apply_patient_scope_to_rows(_patient_query_index(data_dir), scoped_patient_ids)
    conditions = plan["filters"]
    if plan["logic"] == "or":
        filtered_rows = [row for row in inventory if any(_semantic_filter_matches(row, item) for item in conditions)]
    else:
        filtered_rows = [row for row in inventory if all(_semantic_filter_matches(row, item) for item in conditions)]

    patient_ids = [row["patient_id"] for row in filtered_rows]
    labels = [_semantic_condition_label(condition) for condition in conditions]
    label_text = (" %s " % plan["logic"]).join(labels)
    effective_output = _requested_query_output(query) or plan["output"]
    effective_plan = {**plan, "output": effective_output}

    if effective_output == "count":
        noun = "patient" if len(filtered_rows) == 1 else "patients"
        reply = "%s %s match: %s." % (len(filtered_rows), noun, label_text)
    else:
        reply = "Patients matching %s are shown below." % label_text if patient_ids else "No patients match: %s." % label_text

    return {
        "query": query,
        "intent": "semantic_cohort_query",
        "reply": reply,
        "data": {
            "patient_count": len(filtered_rows),
            "patient_ids": patient_ids,
            "patients": filtered_rows,
            "scoped_follow_up": bool(scoped_patient_ids),
            "semantic_plan": effective_plan,
            "execution": "deterministic",
            "planner": {
                "provider": "lm_studio",
                "model": model,
                "base_url": _lm_studio_base_url(),
            },
            "follow_up_suggestions": _semantic_query_follow_ups(plan, filtered_rows),
        },
    }


def _semantic_query_plan(
    data_dir: str,
    query: str,
    history: Optional[List[Dict[str, str]]] = None,
    scoped_patient_ids: Optional[List[str]] = None,
    scope_context: Optional[QueryScopeContext] = None,
    granularity_mode: str = "detailed",
    ai_provider_access: str = "detailed_allowed",
) -> Optional[Dict[str, Any]]:
    if _normalize_ai_provider_access(ai_provider_access) == "safe_summary":
        return None
    if not _lm_studio_enabled():
        return None

    model = _resolve_lm_studio_model()
    if model is None:
        return None

    history_context = _lm_history_context(history, granularity_mode)
    payload = {
        "model": model,
        "temperature": 0,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You translate clinician cohort questions into a constrained JSON plan. "
                    "Return JSON only. Do not answer the question. "
                    "If unsupported, return {\"intent\":\"unsupported\",\"reason\":\"...\"}. "
                    "Supported schema: "
                    "{\"intent\":\"cohort_query\",\"output\":\"count|patient_list\",\"logic\":\"and|or\","
                    "\"filters\":[{\"domain\":\"patient_id|disease|treatment|medication_count|visit_count\","
                    "\"operator\":\"contains|eq|gt|gte|lt|lte\",\"value\":\"string or number\",\"negate\":false}]}. "
                    "Use string operators only for patient_id/disease/treatment and numeric operators only for medication_count/visit_count. "
                    "If the question uses a category term such as biologics, expand it into explicit treatment filters using the known treatments in the catalog."
                ),
            },
            {
                "role": "user",
                "content": "Catalog JSON:\n%s\n\nQuestion: %s%s" % (
                    json.dumps(
                        _semantic_query_catalog(
                            data_dir,
                            scoped_patient_ids=scoped_patient_ids,
                            scope_context=scope_context,
                            ai_provider_access=ai_provider_access,
                        ),
                        ensure_ascii=True,
                        separators=(",", ":"),
                    ),
                    query,
                    (
                        "\n\nRecent conversation history JSON:\n%s"
                        % json.dumps(history_context, ensure_ascii=True, separators=(",", ":"))
                    )
                    if history_context
                    else "",
                ),
            },
        ],
    }
    try:
        response = _http_json(
            f"{_lm_studio_base_url()}/chat/completions",
            payload,
            log_kind="query_semantic_plan",
        )
    except (error.HTTPError, error.URLError, TimeoutError, json.JSONDecodeError):
        return None

    content = _extract_lm_response_text(response)
    if content is None:
        return None
    parsed = _extract_json_object(content)
    if not isinstance(parsed, dict):
        return None
    validated = _validate_semantic_query_plan(parsed)
    if validated is None:
        return None
    return _execute_semantic_query_plan(data_dir, query, validated, model, scoped_patient_ids=scoped_patient_ids)


def _lm_studio_reply(
    data_dir: str,
    query: str,
    history: Optional[List[Dict[str, str]]] = None,
    scoped_patient_ids: Optional[List[str]] = None,
    scope_context: Optional[QueryScopeContext] = None,
    granularity_mode: str = "detailed",
    ai_provider_access: str = "detailed_allowed",
) -> Optional[Dict[str, Any]]:
    if not _lm_studio_enabled():
        return None

    model = _resolve_lm_studio_model()
    if model is None:
        return {
            "query": query,
            "intent": "llm_unavailable",
            "reply": (
                "LM Studio fallback is enabled, but no loaded model was found. "
                "Load a model in LM Studio or set LM_STUDIO_MODEL."
            ),
            "data": {"provider": "lm_studio", "base_url": _lm_studio_base_url()},
        }

    context = _lm_studio_context(
        data_dir,
        query,
        history=history,
        scoped_patient_ids=scoped_patient_ids,
        scope_context=scope_context,
        granularity_mode=granularity_mode,
        ai_provider_access=ai_provider_access,
    )
    normalized_ai_provider_access = _normalize_ai_provider_access(ai_provider_access)
    payload = {
        "model": model,
        "temperature": 0.1,
        "messages": [
            {
                "role": "system",
                "content": (
                    (
                        "You answer questions about a patient navigation dataset. "
                        "Use only the supplied JSON context. "
                        "If the answer is not supported by the context, say that clearly. "
                        "Prefer short answers. "
                        "Be concise and factual."
                    )
                    if normalized_ai_provider_access != "safe_summary"
                    else (
                        "You answer questions using only provider-safe, non-clinical structural summary context. "
                        "Do not infer or reveal patient counts, visit counts, diseases, treatments, phenotypes, timelines, "
                        "or any other patient-derived clinical facts. "
                        "If the question requires clinical context, say that you do not have enough permitted context to answer safely. "
                        "Prefer short answers. "
                        "Be concise and factual."
                    )
                ),
            },
            {
                "role": "user",
                "content": "Context JSON:\n%s\n\nQuestion: %s" % (
                    json.dumps(context, ensure_ascii=True, separators=(",", ":")),
                    query,
                ),
            },
        ],
    }
    try:
        response = _http_json(f"{_lm_studio_base_url()}/chat/completions", payload, log_kind="query_fallback")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        reply = "LM Studio returned an HTTP error while answering this query."
        if exc.code == 400 and "context length" in detail.lower():
            reply = (
                "LM Studio rejected the prompt because the context is still too large for the loaded model. "
                "Load the model with a larger context window or lower the LM Studio context env limits."
            )
        return {
            "query": query,
            "intent": "llm_error",
            "reply": reply,
            "data": {
                "provider": "lm_studio",
                "base_url": _lm_studio_base_url(),
                "status_code": exc.code,
                "detail": detail,
            },
        }
    except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {
            "query": query,
            "intent": "llm_error",
            "reply": "LM Studio is enabled but could not be reached from this app.",
            "data": {
                "provider": "lm_studio",
                "base_url": _lm_studio_base_url(),
                "detail": str(exc),
            },
        }

    explicit_error = response.get("error")
    if isinstance(explicit_error, str) and explicit_error.strip():
        return {
            "query": query,
            "intent": "llm_error",
            "reply": f"LM Studio error: {explicit_error.strip()}",
            "data": {
                "provider": "lm_studio",
                "base_url": _lm_studio_base_url(),
                "response": response,
            },
        }

    cleaned_content = _extract_lm_response_text(response)
    if cleaned_content is None:
        return {
            "query": query,
            "intent": "llm_error",
            "reply": "LM Studio returned an unexpected or empty answer.",
            "data": {
                "provider": "lm_studio",
                "base_url": _lm_studio_base_url(),
                "response": response,
            },
        }

    return {
        "query": query,
        "intent": "llm_fallback",
        "reply": cleaned_content,
        "data": {
            "provider": "lm_studio",
            "model": model,
            "base_url": _lm_studio_base_url(),
            "context": context,
            "follow_up_suggestions": _follow_up_suggestions(query),
        },
    }


def _ai_provider_blocked_response(query: str, history: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
    return {
        "query": query,
        "intent": "unsupported",
        "reply": (
            "AI provider access is blocked for this dataset. "
            "Use a deterministic query or update Data Administration."
        ),
        "data": {
            "follow_up_suggestions": _follow_up_suggestions(query),
            "conversation_history": history[-8:] if history else [],
        },
    }


def _restricted_ai_provider_context(query: str) -> Dict[str, Any]:
    return {
        "question": query,
        "permitted_context": "restricted_non_clinical",
        "workspace_capabilities": {
            "query_support": [
                "deterministic patient, disease, medication, and timeline queries inside the app",
                "deterministic cohort counts and lists inside the app",
                "llm assistance only when permitted context is available",
            ],
            "policy": "No patient-derived clinical facts, counts, diseases, medications, timelines, or scoped cohort details are available to the AI provider for this dataset.",
        },
    }


def _answer_query_impl(
    data_dir: str,
    query: str,
    query_mode: str = "auto",
    history: Optional[List[Dict[str, str]]] = None,
    scoped_patient_ids: Optional[List[str]] = None,
    granularity_mode: str = "detailed",
    ai_provider_access: str = "detailed_allowed",
) -> Dict[str, Any]:
    text = normalize_entity_synonym_mentions(query.strip(), "patient", "patient", "patients")
    lowered = text.lower()
    mode = str(query_mode or "auto").strip().lower()
    normalized_ai_provider_access = _normalize_ai_provider_access(ai_provider_access)
    provider_granularity_mode = _ai_provider_granularity_mode(granularity_mode, normalized_ai_provider_access)
    active_scoped_patient_ids = scoped_patient_ids if _should_apply_scoped_context(text, history=history, scoped_patient_ids=scoped_patient_ids) else []

    if not text:
        return {
            "query": query,
            "intent": "empty",
            "reply": "Ask a question about medications, diseases, or a patient timeline.",
            "data": {},
        }

    if _needs_clarification(text):
        return {
            "query": query,
            "intent": "needs_clarification",
            "reply": (
                "That prompt is too short to answer reliably. Try naming a patient, disease, medication, "
                "or the cohort question you want to answer."
            ),
            "data": {
                "follow_up_suggestions": _follow_up_suggestions(text),
                "conversation_history": history[-8:] if history else [],
            },
        }

    scope_context = _build_query_scope_context(data_dir, scoped_patient_ids=active_scoped_patient_ids)

    if mode in {"planner_only", "llm_only"}:
        if normalized_ai_provider_access == "blocked":
            return _ai_provider_blocked_response(query, history=history)
        if mode == "planner_only":
            semantic_fallback = _semantic_query_plan(
                data_dir,
                query,
                history=history,
                scoped_patient_ids=active_scoped_patient_ids,
                scope_context=scope_context,
                granularity_mode=provider_granularity_mode,
                ai_provider_access=normalized_ai_provider_access,
            )
            if semantic_fallback is not None:
                return semantic_fallback
        fallback = _lm_studio_reply(
            data_dir,
            query,
            history=history,
            scoped_patient_ids=active_scoped_patient_ids,
            scope_context=scope_context,
            granularity_mode=provider_granularity_mode,
            ai_provider_access=normalized_ai_provider_access,
        )
        if fallback is not None:
            return fallback
        return {
            "query": query,
            "intent": "unsupported",
            "reply": (
                "I could not answer that query with the current semantic planner or LM fallback. "
                "Try rephrasing the filter more explicitly."
            ),
            "data": {
                "follow_up_suggestions": _follow_up_suggestions(text),
                "conversation_history": history[-8:] if history else [],
            },
        }

    medication_count_constraint = _medication_count_constraint(text)
    visit_count_constraint = _visit_count_constraint(text)
    if medication_count_constraint is not None and (
        lowered.startswith("which patients")
        or lowered.startswith("how many patients")
        or lowered.startswith("list patients")
    ):
        operator = medication_count_constraint["operator"]
        target = medication_count_constraint["value"]
        cohort = patient_medication_count_cohort(data_dir, operator, target, scoped_patient_ids=active_scoped_patient_ids)
        label = _format_medication_count_constraint(operator, target)
        if lowered.startswith("how many"):
            verb = "has" if cohort["patient_count"] == 1 else "have"
            noun = "patient" if cohort["patient_count"] == 1 else "patients"
            reply = "%s %s %s %s." % (cohort["patient_count"], noun, verb, label)
        else:
            patient_ids = [item["patient_id"] for item in cohort["patients"]]
            reply = "Patients with %s: %s." % (
                label,
                ", ".join(patient_ids) if patient_ids else "none",
            )
        return {
            "query": query,
            "intent": "patient_medication_count_cohort",
            "reply": reply,
            "data": {
                **cohort,
                "constraint_label": label,
                "scoped_follow_up": bool(active_scoped_patient_ids),
                "follow_up_suggestions": [
                    "How many patients have %s?" % label,
                    "Which patients have no medications?",
                    "Which patients have exactly 1 medication?",
                ],
            },
        }

    sex_constraint = _sex_constraint(text)
    if sex_constraint is not None and (
        lowered.startswith("how many patients")
        or re.match(r"^how many\s+(?:male|males|female|females)\s+patients?\b", lowered) is not None
        or lowered.startswith("how many are")
        or lowered.startswith("which patients")
        or re.match(r"^(which|list|show)\s+(?:male|males|female|females)\s+patients?\b", lowered) is not None
        or lowered.startswith("which are")
        or lowered.startswith("which ")
        or lowered.startswith("list patients")
        or lowered.startswith("show patients")
    ):
        inventory = _apply_patient_scope_to_rows(_patient_query_index(data_dir), active_scoped_patient_ids)
        filtered_rows = [
            row for row in inventory
            if str(row.get("sex") or "").strip().lower() == sex_constraint
        ]
        if lowered.startswith("how many"):
            reply = "%s %s are %s." % (
                len(filtered_rows),
                "patient" if len(filtered_rows) == 1 else "patients",
                sex_constraint,
            )
        else:
            reply = "Patients who are %s: %s." % (
                sex_constraint,
                ", ".join(row["patient_id"] for row in filtered_rows) if filtered_rows else "none",
            )
        return {
            "query": query,
            "intent": "patient_sex_cohort",
            "reply": reply,
            "data": {
                "sex": sex_constraint,
                "patient_count": len(filtered_rows),
                "patient_ids": [row["patient_id"] for row in filtered_rows],
                "patients": filtered_rows,
                "scoped_follow_up": bool(active_scoped_patient_ids),
                "follow_up_suggestions": [
                    "Which patients are %s?" % sex_constraint,
                    "How many patients have Crohn Disease?",
                    "Show patient %s" % (filtered_rows[0]["patient_id"] if filtered_rows else "107"),
                ],
            },
        }

    if (
        "what happened to this cohort over time" in lowered
        or "what happened to this workspace over time" in lowered
        or "cohort over time" in lowered
        or "workspace over time" in lowered
        or "timeline of this cohort" in lowered
        or "timeline of this workspace" in lowered
    ):
        summary = _cohort_over_time_summary(data_dir, scoped_patient_ids=active_scoped_patient_ids)
        periods = summary["periods"]
        period_text = ", ".join(
            "%s: %s timepoints across %s patients" % (item["period"], item["timepoint_count"], item["patient_count"])
            for item in periods[:6]
        )
        if not period_text:
            period_text = "No dated timepoints were available."
        reply = (
            "This workspace has %(timepoint_count)s timepoints across %(patient_count)s patients. "
            "Dated range: %(first)s to %(last)s. %(period_text)s."
        ) % {
            "timepoint_count": summary["timepoint_count"],
            "patient_count": summary["patient_count"],
            "first": summary["first_event_date"] or "n/a",
            "last": summary["last_event_date"] or "n/a",
            "period_text": period_text,
        }
        return {
            "query": query,
            "intent": "cohort_over_time",
            "reply": reply,
            "data": {
                **summary,
                "follow_up_suggestions": [
                    "How many timepoints are in this workspace?",
                    "Which patients have more than 1 timepoint?",
                    "Show patient 107",
                ],
            },
        }

    if re.search(r"\bhow many\s+(?:timepoints?|visits?)\b", lowered):
        if any(keyword in lowered for keyword in ("mention", "with ", " for ")):
            term = _term_from_timepoint_query(text)
            if term:
                result = _term_timepoint_summary(data_dir, term, scoped_patient_ids=active_scoped_patient_ids)
                if result is not None:
                    return {
                        "query": query,
                        "intent": result["intent"],
                        "reply": "%s timepoints match '%s' across %s patients." % (
                            result["timepoint_count"],
                            term,
                            result["patient_count"],
                        ),
                        "data": {
                            **result,
                            "follow_up_suggestions": _follow_up_suggestions(term),
                        },
                    }
        summary = _cohort_over_time_summary(data_dir, scoped_patient_ids=active_scoped_patient_ids)
        return {
            "query": query,
            "intent": "timepoint_inventory",
            "reply": "This workspace contains %s timepoints across %s patients." % (
                summary["timepoint_count"],
                summary["patient_count"],
            ),
            "data": {
                **summary,
                "follow_up_suggestions": [
                    "What happened to this workspace over time?",
                    "Which patients have more than 1 timepoint?",
                    "List all patients in the workspace",
                ],
            },
        }

    if _is_sample_list_query(text):
        sample_ids = scope_context.sample_ids
        reply_lines = ["Samples in the workspace (%s):" % len(sample_ids)]
        reply_lines.extend("- %s" % sample_id for sample_id in sample_ids)
        return {
            "query": query,
            "intent": "sample_inventory",
            "reply": "\n".join(reply_lines),
            "data": {
                "sample_count": len(sample_ids),
                "sample_ids": sample_ids,
                "follow_up_suggestions": [
                    "How many timepoints are in this workspace?",
                    "Tell me the list of patients in the workspace",
                    "What happened to this workspace over time?",
                ],
            },
        }

    explicit_patient_cohort = _explicit_patient_cohort_ids(text, _patient_inventory(data_dir))
    if explicit_patient_cohort is not None:
        inventory = _patient_query_index(data_dir)
        rows_by_id = {str(row.get("patient_id") or "").strip(): row for row in inventory}
        patient_ids = [
            patient_id
            for patient_id in explicit_patient_cohort["patient_ids"]
            if patient_id in rows_by_id
        ]
        matched_rows = [rows_by_id[patient_id] for patient_id in patient_ids]
        original_record_ids: List[str] = []
        for row in matched_rows:
            for record_id in row.get("original_record_ids", []) if isinstance(row, dict) else []:
                normalized = str(record_id or "").strip()
                if normalized and normalized not in original_record_ids:
                    original_record_ids.append(normalized)
        reply = "Selected patients: %s." % ", ".join(patient_ids)
        invalid_ids = explicit_patient_cohort.get("invalid_ids", [])
        if invalid_ids:
            reply += " Ignored unknown IDs: %s." % ", ".join(invalid_ids)
        return {
            "query": query,
            "intent": "explicit_patient_id_cohort",
            "reply": reply,
            "data": {
                "patient_count": len(patient_ids),
                "patient_ids": patient_ids,
                "patients": matched_rows,
                "sample_count": len(original_record_ids),
                "sample_ids": original_record_ids,
                "invalid_patient_ids": invalid_ids,
                "scoped_follow_up": False,
                "follow_up_suggestions": [
                    "Show patient %s" % patient_ids[0],
                    "Open this selected cohort in Analysis",
                    "Save this selected cohort",
                ],
            },
        }

    if _is_patient_count_query(text):
        patient_ids = scope_context.patient_ids
        sample_ids = scope_context.sample_ids
        return {
            "query": query,
            "intent": "patient_inventory",
            "reply": "This workspace contains %s %s." % (
                len(patient_ids),
                "patient" if len(patient_ids) == 1 else "patients",
            ),
            "data": {
                "patient_count": len(patient_ids),
                "patient_ids": patient_ids,
                "sample_count": len(sample_ids),
                "sample_ids": sample_ids,
                "scoped_follow_up": bool(active_scoped_patient_ids),
                "follow_up_suggestions": [
                    "List all patients in the workspace",
                    "How many timepoints are in this workspace?",
                    "Which patients have more than 1 medication?",
                ],
            },
        }

    if _is_patient_list_query(text):
        patient_ids = scope_context.patient_ids
        sample_ids = scope_context.sample_ids
        reply_lines = ["Patients in the workspace (%s):" % len(patient_ids)]
        reply_lines.extend("- %s" % patient_id for patient_id in patient_ids)
        return {
            "query": query,
            "intent": "patient_inventory",
            "reply": "\n".join(reply_lines),
            "data": {
                "patient_count": len(patient_ids),
                "patient_ids": patient_ids,
                "sample_count": len(sample_ids),
                "sample_ids": sample_ids,
                "scoped_follow_up": bool(active_scoped_patient_ids),
                "follow_up_suggestions": [
                    "How many patients are in this workspace?",
                    "Show patient %s" % (patient_ids[0] if patient_ids else "107"),
                    "Which patients have more than 1 medication?",
                ],
            },
        }

    transition_query = _transition_query(text)
    if transition_query is not None:
        result = _patient_transition_cohort(
            data_dir,
            transition_query["first_term"],
            transition_query["second_term"],
            scoped_patient_ids=active_scoped_patient_ids,
        )
        if result is not None:
            first_term = transition_query["first_term"]
            second_term = transition_query["second_term"]
            if transition_query["intent"] == "count":
                noun = "patient" if result["patient_count"] == 1 else "patients"
                reply = "%s %s changed from '%s' to '%s'." % (
                    result["patient_count"],
                    noun,
                    first_term,
                    second_term,
                )
            else:
                reply = "Patients who changed from '%s' to '%s': %s." % (
                    first_term,
                    second_term,
                    ", ".join(result["patient_ids"]) if result["patient_ids"] else "none",
                )
            return {
                "query": query,
                "intent": "patient_transition_cohort",
                "reply": reply,
                "data": {
                    **result,
                    "follow_up_suggestions": [
                        "Show the timeline for patient %s" % (result["patient_ids"][0] if result["patient_ids"] else "107"),
                        "How many patients have %s?" % first_term,
                        "How many patients have %s?" % second_term,
                    ],
                },
            }

    start_after_query = _start_after_query(text)
    if start_after_query is not None:
        result = _patient_started_after_cohort(
            data_dir,
            start_after_query["started_term"],
            start_after_query["after_term"],
            scoped_patient_ids=active_scoped_patient_ids,
        )
        if result is not None:
            started_term = start_after_query["started_term"]
            after_term = start_after_query["after_term"]
            if start_after_query["intent"] == "count":
                noun = "patient" if result["patient_count"] == 1 else "patients"
                reply = "%s %s started '%s' after '%s'." % (
                    result["patient_count"],
                    noun,
                    started_term,
                    after_term,
                )
            else:
                reply = "Patients who started '%s' after '%s': %s." % (
                    started_term,
                    after_term,
                    ", ".join(result["patient_ids"]) if result["patient_ids"] else "none",
                )
            return {
                "query": query,
                "intent": "patient_started_after_cohort",
                "reply": reply,
                "data": {
                    **result,
                    "follow_up_suggestions": [
                        "Show the timeline for patient %s" % (result["patient_ids"][0] if result["patient_ids"] else "107"),
                        "How many patients have %s?" % started_term,
                        "Which patients had %s after %s?" % (started_term, after_term),
                    ],
                },
            }

    temporal_order_query = _temporal_order_query(text)
    if temporal_order_query is not None:
        result = _patient_temporal_order_cohort(
            data_dir,
            temporal_order_query["first_term"],
            temporal_order_query["second_term"],
            temporal_order_query["relation"],
            scoped_patient_ids=active_scoped_patient_ids,
        )
        if result is not None:
            relation = temporal_order_query["relation"]
            first_term = temporal_order_query["first_term"]
            second_term = temporal_order_query["second_term"]
            if temporal_order_query["intent"] == "count":
                noun = "patient" if result["patient_count"] == 1 else "patients"
                reply = "%s %s had '%s' %s '%s'." % (
                    result["patient_count"],
                    noun,
                    first_term,
                    relation,
                    second_term,
                )
            else:
                reply = "Patients who had '%s' %s '%s': %s." % (
                    first_term,
                    relation,
                    second_term,
                    ", ".join(result["patient_ids"]) if result["patient_ids"] else "none",
                )
            return {
                "query": query,
                "intent": "patient_temporal_order_cohort",
                "reply": reply,
                "data": {
                    **result,
                    "follow_up_suggestions": [
                        "Show the timeline for patient %s" % (result["patient_ids"][0] if result["patient_ids"] else "107"),
                        "How many timepoints mention %s?" % first_term,
                        "How many patients have %s?" % second_term,
                    ],
                },
            }

    patient_filter_query = _patient_filter_query(text)
    if patient_filter_query is not None:
        inventory = _apply_patient_scope_to_rows(_patient_query_index(data_dir), active_scoped_patient_ids)
        rows_by_id = {row["patient_id"]: row for row in inventory}
        remaining_ids = {row["patient_id"] for row in inventory}
        resolved_conditions: List[Dict[str, Any]] = []

        for condition in patient_filter_query["conditions"]:
            if condition["scope"] == "timepoint":
                operator = condition["operator"]
                target = int(condition["value"])
                kind, matched_rows, matched_patient_count = _resolve_timepoint_filter_condition(
                    data_dir,
                    condition["term"],
                    operator,
                    target,
                    scoped_patient_ids=active_scoped_patient_ids,
                )
                if kind is None:
                    return {
                        "query": query,
                        "intent": "patient_filter_cohort",
                        "reply": "I could not resolve '%s' as a known disease or medication." % condition["term"],
                        "data": {
                            "conditions": patient_filter_query["conditions"],
                            "patient_count": 0,
                            "patients": [],
                            "patient_ids": [],
                            "follow_up_suggestions": _follow_up_suggestions(condition["term"]),
                        },
                    }
                matched_ids = {item["patient_id"] for item in matched_rows}
                if condition["mode"] == "include":
                    remaining_ids &= matched_ids
                else:
                    remaining_ids -= matched_ids
                resolved_conditions.append(
                    {
                        "mode": condition["mode"],
                        "kind": kind,
                        "scope": "timepoint",
                        "term": condition["term"],
                        "operator": operator,
                        "target": target,
                        "matched_patient_count": len(matched_rows),
                        "raw_term_patient_count": matched_patient_count,
                    }
                )
                continue

            preferred_kind = condition["preferred_kind"] or None
            kind, cohort = _resolve_patient_filter_kind(
                data_dir,
                condition["term"],
                preferred_kind=preferred_kind,
                scoped_patient_ids=active_scoped_patient_ids,
            )
            if kind is None:
                return {
                    "query": query,
                    "intent": "patient_filter_cohort",
                    "reply": "I could not resolve '%s' as a known disease or medication." % condition["term"],
                    "data": {
                        "conditions": patient_filter_query["conditions"],
                        "patient_count": 0,
                        "patients": [],
                        "patient_ids": [],
                        "follow_up_suggestions": _follow_up_suggestions(condition["term"]),
                    },
                }
            matched_ids = {item["patient_id"] for item in cohort["patients"]}
            if condition["mode"] == "include":
                remaining_ids &= matched_ids
            else:
                remaining_ids -= matched_ids
            resolved_conditions.append(
                {
                    "mode": condition["mode"],
                    "kind": kind,
                    "scope": "patient",
                    "term": condition["term"],
                    "matched_patient_count": cohort["patient_count"],
                }
            )

        filtered_rows = [row for row in inventory if row["patient_id"] in remaining_ids]
        condition_labels = []
        for condition in resolved_conditions:
            if condition["scope"] == "timepoint":
                timepoint_label = _format_visit_count_constraint(condition["operator"], condition["target"])
                if condition["mode"] == "exclude":
                    condition_labels.append("does not have %s with '%s'" % (timepoint_label, condition["term"]))
                else:
                    condition_labels.append("has %s with '%s'" % (timepoint_label, condition["term"]))
                continue

            verb = "has" if condition["kind"] == "disease" else "takes"
            if condition["mode"] == "exclude":
                verb = "does not have" if condition["kind"] == "disease" else "does not take"
            condition_labels.append("%s '%s'" % (verb, condition["term"]))
        label_text = " and ".join(condition_labels)

        if patient_filter_query["intent"] == "count":
            noun = "patient" if len(filtered_rows) == 1 else "patients"
            reply = "%s %s match: %s." % (len(filtered_rows), noun, label_text)
        else:
            reply = "Patients matching %s: %s." % (
                label_text,
                ", ".join(row["patient_id"] for row in filtered_rows) if filtered_rows else "none",
            )

        return {
            "query": query,
            "intent": "patient_filter_cohort",
            "reply": reply,
            "data": {
                "patient_count": len(filtered_rows),
                "patient_ids": [row["patient_id"] for row in filtered_rows],
                "patients": filtered_rows,
                "conditions": resolved_conditions,
                "scoped_follow_up": bool(active_scoped_patient_ids),
                "follow_up_suggestions": [
                    "How many patients have %s?" % resolved_conditions[0]["term"],
                    "Which patients have %s?" % resolved_conditions[0]["term"],
                    "Show patient %s" % (filtered_rows[0]["patient_id"] if filtered_rows else "107"),
                ],
            },
        }

    negative_term_query = _negative_patient_term_query(text)
    if negative_term_query is not None:
        term = negative_term_query["term"]
        inventory = _apply_patient_scope_to_rows(_patient_query_index(data_dir), active_scoped_patient_ids)
        all_patient_ids = [row["patient_id"] for row in inventory]

        medication = _apply_patient_scope_to_cohort(_medication_cohort(data_dir, term), active_scoped_patient_ids)
        disease = _apply_patient_scope_to_cohort(_disease_cohort(data_dir, term), active_scoped_patient_ids)

        selected_intent = "negative_medication_cohort"
        selected_matches = medication["patients"]
        selected_count = medication["patient_count"]
        if disease["patient_count"] > medication["patient_count"]:
            selected_intent = "negative_disease_cohort"
            selected_matches = disease["patients"]
            selected_count = disease["patient_count"]

        matched_ids = {item["patient_id"] for item in selected_matches}
        complement_ids = [patient_id for patient_id in all_patient_ids if patient_id not in matched_ids]
        complement_rows = [row for row in inventory if row["patient_id"] in set(complement_ids)]

        if negative_term_query["intent"] == "count":
            reply = "%s patients do not have '%s'." % (len(complement_ids), term)
        else:
            reply = "Patients without '%s': %s." % (
                term,
                ", ".join(complement_ids) if complement_ids else "none",
            )
        return {
            "query": query,
            "intent": selected_intent,
            "reply": reply,
            "data": {
                "term": term,
                "matched_patient_count": selected_count,
                "patient_count": len(complement_ids),
                "patient_ids": complement_ids,
                "patients": complement_rows,
                "scoped_follow_up": bool(active_scoped_patient_ids),
                "follow_up_suggestions": [
                    "How many patients have %s?" % term,
                    "Which patients have %s?" % term,
                    "Show patient %s" % (complement_ids[0] if complement_ids else "107"),
                ],
            },
        }

    explicit_medication_match = re.match(
        r"^(how many|which)\s+patients?\s+(?:take|takes|are taking|receive|receives|received|are on|on|use|uses|using|treated with)\s+(.+)$",
        text,
        flags=re.IGNORECASE,
    )
    if explicit_medication_match:
        term = explicit_medication_match.group(2).strip(" ?.")
        if not _looks_like_treatment_category_candidate(term):
            medication = _apply_patient_scope_to_cohort(_medication_cohort(data_dir, term), active_scoped_patient_ids)
            if lowered.startswith("how many"):
                reply = "%s patients match medication query '%s'." % (medication["patient_count"], term)
            else:
                reply = (
                    "Patients matching medication query '%s' are shown below." % term
                    if medication["patient_count"] > 0
                    else "No patients match medication query '%s'." % term
                )
            return {
                "query": query,
                "intent": "medication_cohort",
                "reply": reply,
                "data": {
                    **medication,
                    "scoped_follow_up": bool(active_scoped_patient_ids),
                    "follow_up_suggestions": _follow_up_suggestions(term),
                },
            }

    if (
        visit_count_constraint is None
        and "in the name" not in lowered
        and (lowered.startswith("how many patients have ") or lowered.startswith("which patients have "))
    ):
        term = re.sub(r"^(how many patients have|which patients have)\s+", "", text, flags=re.IGNORECASE).strip(" ?.")
        kind, cohort = _resolve_patient_filter_kind(data_dir, term, scoped_patient_ids=active_scoped_patient_ids)
        if kind is not None:
            if lowered.startswith("how many"):
                reply = "%s patients match %s query '%s'." % (cohort["patient_count"], kind, term)
            else:
                reply = (
                    "Patients matching %s query '%s' are shown below." % (kind, term)
                    if cohort["patient_count"] > 0
                    else "No patients match %s query '%s'." % (kind, term)
                )
            return {
                "query": query,
                "intent": f"{kind}_cohort",
                "reply": reply,
                "data": {
                    **cohort,
                    "scoped_follow_up": bool(active_scoped_patient_ids),
                    "follow_up_suggestions": _follow_up_suggestions(term),
                },
            }
        if not _looks_like_treatment_category_candidate(term):
            if lowered.startswith("how many"):
                reply = "0 patients match '%s' in this workspace." % term
            else:
                reply = "No patients match '%s' in this workspace." % term
            return {
                "query": query,
                "intent": "term_cohort",
                "reply": reply,
                "data": {
                    "patient_count": 0,
                    "patient_ids": [],
                    "patients": [],
                    "scoped_follow_up": bool(active_scoped_patient_ids),
                    "follow_up_suggestions": _follow_up_suggestions(term),
                },
            }

    select_take_match = re.search(
        r"^(?:select|find|show|list)\s+patients?\s+(?:that|who)\s+(?:take|takes|are taking|receive|received|are on|on|use|used)\s+(.+)$",
        text,
        flags=re.IGNORECASE,
    )
    if select_take_match:
        medication = select_take_match.group(1).strip(" ?.")
        cohort = _medication_cohort(data_dir, medication, scoped_patient_ids=active_scoped_patient_ids)
        patient_ids = [item["patient_id"] for item in cohort["patients"]]
        return {
            "query": query,
            "intent": "medication_cohort",
            "reply": "Patients matching medication query '%s': %s." % (
                medication,
                ", ".join(patient_ids) if patient_ids else "none",
            ),
            "data": {
                **cohort,
                "follow_up_suggestions": _follow_up_suggestions(medication),
            },
        }

    medication_match = re.search(
        r"(?:medication|drug|treatment)\s+(.+)",
        lowered,
    )
    if medication_match:
        medication = text[medication_match.start(1):].strip(" ?.")
        cohort = _medication_cohort(data_dir, medication, scoped_patient_ids=active_scoped_patient_ids)
        patient_ids = [item["patient_id"] for item in cohort["patients"]]
        return {
            "query": query,
            "intent": "medication_cohort",
            "reply": "Patients matching medication query '%s': %s." % (
                medication,
                ", ".join(patient_ids) if patient_ids else "none",
            ),
            "data": {
                **cohort,
                "follow_up_suggestions": _follow_up_suggestions(medication),
            },
        }

    if "what medications" in lowered or "list medications" in lowered:
        counts = scope_context.medication_counts
        meds = [item["medication"] for item in counts[:20]]
        return {
            "query": query,
            "intent": "medication_inventory",
            "reply": "Known medications: %s." % (", ".join(meds) if meds else "none"),
            "data": {
                "medications": counts,
                "follow_up_suggestions": [
                    "How many patients have Infliximab?",
                    "Which patients have Prednisolone?",
                    "Show the visits mentioning Azathioprine.",
                ],
            },
        }

    if "what diseases" in lowered or "list diseases" in lowered:
        counts = scope_context.disease_counts
        labels = [item["disease"] for item in counts[:20]]
        return {
            "query": query,
            "intent": "disease_inventory",
            "reply": "Known diseases: %s." % (", ".join(labels) if labels else "none"),
            "data": {
                "diseases": counts,
                "follow_up_suggestions": [
                    "How many patients have Crohn Disease?",
                    "Which patients have Ulcerative Colitis?",
                    "Show patient 107",
                ],
            },
        }

    patient_id = _extract_patient_id(text)
    if patient_id is not None:
        navigator = build_patient_navigator(data_dir, patient_id)
        if navigator is None:
            return {
                "query": query,
                "intent": "patient_lookup",
                "reply": "Patient not found: %s." % patient_id,
                "data": {
                    "patient_id": patient_id,
                    "follow_up_suggestions": [
                        "List patients",
                        "Show patient 107",
                        "How many patients are in this workspace?",
                    ],
                },
            }
        payload = navigator.model_dump()
        if "timeline" in lowered or "over time" in lowered:
            reply = _render_patient_timeline(payload)
            intent = "patient_timeline"
        elif "visit" in lowered:
            reply = _render_visit_list(payload)
            intent = "patient_visits"
        else:
            reply = _render_patient_summary(payload)
            intent = "patient_summary"
        return {
            "query": query,
            "intent": intent,
            "reply": reply,
            "data": {
                **payload,
                "follow_up_suggestions": [
                    "Show the timeline for patient %s" % patient_id,
                    "List visits for patient %s" % patient_id,
                    "What treatments are recorded for patient %s?" % patient_id,
                    "What diseases are recorded for patient %s?" % patient_id,
                ],
            },
        }

    if visit_count_constraint is not None and any(keyword in lowered for keyword in ("with", "mention")):
        term = _term_from_timepoint_query(text)
        if term:
            result = _term_timepoint_summary(data_dir, term, scoped_patient_ids=active_scoped_patient_ids)
            if result is not None:
                operator = visit_count_constraint["operator"]
                target = visit_count_constraint["value"]
                filtered = [
                    item for item in result["patients"]
                    if _matches_numeric_constraint(len(item.get("visits", [])), operator, target)
                ]
                label = _format_visit_count_constraint(operator, target)
                if lowered.startswith("how many"):
                    reply = "%s patients have %s matching '%s'." % (len(filtered), label, term)
                else:
                    reply = "Patients with %s matching '%s': %s." % (
                        label,
                        term,
                        ", ".join(item["patient_id"] for item in filtered) if filtered else "none",
                    )
                return {
                    "query": query,
                    "intent": "term_patient_visit_count_cohort",
                    "reply": reply,
                    "data": {
                        "term": term,
                        "constraint_label": label,
                        "patient_count": len(filtered),
                        "patients": filtered,
                        "follow_up_suggestions": _follow_up_suggestions(term),
                    },
                }

    if visit_count_constraint is not None and (
        lowered.startswith("which patients")
        or lowered.startswith("how many patients")
        or lowered.startswith("list patients")
    ):
        operator = visit_count_constraint["operator"]
        target = visit_count_constraint["value"]
        cohort = patient_visit_count_cohort(data_dir, operator, target, scoped_patient_ids=active_scoped_patient_ids)
        label = _format_visit_count_constraint(operator, target)
        if lowered.startswith("how many"):
            verb = "has" if cohort["patient_count"] == 1 else "have"
            noun = "patient" if cohort["patient_count"] == 1 else "patients"
            reply = "%s %s %s %s." % (cohort["patient_count"], noun, verb, label)
        else:
            patient_ids = [item["patient_id"] for item in cohort["patients"]]
            reply = "Patients with %s: %s." % (
                label,
                ", ".join(patient_ids) if patient_ids else "none",
            )
        return {
            "query": query,
            "intent": "patient_visit_count_cohort",
            "reply": reply,
            "data": {
                **cohort,
                "constraint_label": label,
                "follow_up_suggestions": [
                    "How many timepoints are in this workspace?",
                    "What happened to this workspace over time?",
                    "Show patient %s" % (cohort["patients"][0]["patient_id"] if cohort["patients"] else "107"),
                ],
            },
        }

    if normalized_ai_provider_access != "blocked":
        semantic_fallback = _semantic_query_plan(
            data_dir,
            query,
            history=history,
            scoped_patient_ids=active_scoped_patient_ids,
            scope_context=scope_context,
            granularity_mode=provider_granularity_mode,
            ai_provider_access=normalized_ai_provider_access,
        )
        if semantic_fallback is not None:
            return semantic_fallback

        fallback = _lm_studio_reply(
            data_dir,
            query,
            history=history,
            scoped_patient_ids=active_scoped_patient_ids,
            scope_context=scope_context,
            granularity_mode=provider_granularity_mode,
            ai_provider_access=normalized_ai_provider_access,
        )
        if fallback is not None:
            return fallback

    return {
        "query": query,
        "intent": "unsupported",
        "reply": (
            "I can answer common questions about medications, diseases, patient summaries, "
            "and visit timelines. LM Studio fallback is currently unavailable. "
            "Examples: 'How many patients have Prednisolone?', "
            "'Which patients have Crohn Disease?', 'Show patient 107', 'List visits for patient 107'."
        ),
        "data": {
            "follow_up_suggestions": _follow_up_suggestions(text),
            "conversation_history": history[-8:] if history else [],
        },
    }


def answer_query(
    data_dir: str,
    query: str,
    query_mode: str = "auto",
    history: Optional[List[Dict[str, str]]] = None,
    scoped_patient_ids: Optional[List[str]] = None,
    granularity_mode: str = "detailed",
    granularity_ceiling: str = "detailed",
    ai_provider_access: str = "detailed_allowed",
) -> Dict[str, Any]:
    normalized_mode = _normalize_query_granularity_mode(granularity_mode)
    normalized_ceiling = _normalize_query_granularity_ceiling(granularity_ceiling)
    normalized_ai_provider_access = _normalize_ai_provider_access(ai_provider_access)
    applied_mode = "summary" if normalized_mode == "summary" or normalized_ceiling == "summary" else "detailed"
    payload = _answer_query_impl(
        data_dir,
        query,
        query_mode=query_mode,
        history=history,
        scoped_patient_ids=scoped_patient_ids,
        granularity_mode=applied_mode,
        ai_provider_access=normalized_ai_provider_access,
    )
    return _finalize_query_response(payload, normalized_mode, applied_mode, normalized_ai_provider_access)
