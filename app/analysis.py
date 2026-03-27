from __future__ import annotations

import json
import re
from datetime import date
from typing import Any, Dict, List

from app.bff import ensure_data_dir, extract_event_date, extract_patient_id, extract_treatment_labels, normalize_value, read_bff_records
from app.lm import (
    http_json,
    lm_studio_base_url,
    lm_studio_enabled,
    resolve_lm_studio_model,
    sanitize_lm_text,
)
from app.query_store import (
    cohort_over_time_summary as store_cohort_over_time_summary,
    disease_counts as store_disease_counts,
    duckdb_available,
    medication_counts as store_medication_counts,
    molecular_dataset_gene_means as store_molecular_dataset_gene_means,
    molecular_dataset_pairwise_gene_differences as store_molecular_dataset_pairwise_gene_differences,
    molecular_dataset_inventory as store_molecular_dataset_inventory,
    molecular_expression_summary as store_molecular_expression_summary,
    patient_query_index as store_patient_query_index,
)


def _extract_lm_response_text(response: Dict[str, Any]) -> str | None:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    message = choices[0].get("message", {})
    content = message.get("content")
    if isinstance(content, list):
        text_parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str):
                text_parts.append(item["text"])
        content = "\n".join(text_parts).strip()
    if not isinstance(content, str) or not content.strip():
        return None
    return sanitize_lm_text(content)


def _parse_iso_date(value: Any) -> date | None:
    normalized = normalize_value(value)
    if not isinstance(normalized, str) or not normalized.strip():
        return None
    text = normalized.strip()
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _measure_label(item: Dict[str, Any]) -> str | None:
    assay = item.get("assayCode")
    if isinstance(assay, dict):
        label = normalize_value(assay.get("label")) or normalize_value(assay.get("id"))
        if isinstance(label, str) and label.strip():
            return label.strip()
    notes = normalize_value(item.get("notes"))
    if isinstance(notes, str) and notes.strip():
        return notes.strip()
    return None


def _measure_numeric_value(item: Dict[str, Any]) -> float | None:
    candidates = [
        item.get("value"),
        (item.get("measurementValue") or {}).get("value") if isinstance(item.get("measurementValue"), dict) else None,
    ]
    measurement_value = item.get("measurementValue")
    if isinstance(measurement_value, dict):
        quantity = measurement_value.get("quantity")
        if isinstance(quantity, dict):
            candidates.append(quantity.get("value"))
    for candidate in candidates:
        normalized = normalize_value(candidate)
        if isinstance(normalized, (int, float)):
            return float(normalized)
        if isinstance(normalized, str):
            try:
                return float(normalized)
            except ValueError:
                continue
    return None


def _measure_unit_label(item: Dict[str, Any]) -> str | None:
    measurement_value = item.get("measurementValue")
    if not isinstance(measurement_value, dict):
        return None
    quantity = measurement_value.get("quantity")
    if not isinstance(quantity, dict):
        return None
    unit = quantity.get("unit")
    if isinstance(unit, dict):
        label = normalize_value(unit.get("label")) or normalize_value(unit.get("id"))
        if isinstance(label, str) and label.strip():
            return label.strip()
    return None


def _matches_operator(value: float, operator: str, threshold: float) -> bool:
    if operator == ">":
        return value > threshold
    if operator == ">=":
        return value >= threshold
    if operator == "<":
        return value < threshold
    if operator == "<=":
        return value <= threshold
    return False


def _parse_survival_request(prompt: str) -> Dict[str, Any] | None:
    lowered = prompt.lower()
    if not any(token in lowered for token in ("kaplan", "survival")):
        return None
    pattern = re.search(
        r"(?:kaplan[\s-]*meier|survival)(?:\s+curve)?(?:\s+for)?(?:\s+time\s+to)?\s+(.+?)\s*(>=|<=|>|<)\s*(-?\d+(?:\.\d+)?)",
        prompt,
        flags=re.IGNORECASE,
    )
    if not pattern:
        return None
    raw_label = re.sub(r"^(?:time\s+to)\s+", "", pattern.group(1).strip(), flags=re.IGNORECASE)
    raw_label = re.sub(r"^(?:first\s+)", "", raw_label, flags=re.IGNORECASE).strip(" .:")
    if not raw_label:
        return None
    return {
        "measure_query": raw_label,
        "operator": pattern.group(2),
        "threshold": float(pattern.group(3)),
    }


def _resolve_measure_name(query: str, labels: List[str]) -> str | None:
    normalized_query = query.strip().lower()
    if not normalized_query:
        return None
    for label in labels:
        if label.lower() == normalized_query:
            return label
    for label in labels:
        if normalized_query in label.lower():
            return label
    return None


def _resolve_treatment_name(query: str, labels: List[str]) -> str | None:
    normalized_query = query.strip().lower()
    if not normalized_query:
        return None
    for label in labels:
        if label.lower() == normalized_query:
            return label
    for label in labels:
        if normalized_query in label.lower():
            return label
    return None


def _parse_trajectory_request(prompt: str) -> Dict[str, Any] | None:
    lowered = prompt.lower()
    if "kaplan" in lowered or "survival" in lowered:
        return None
    if "response to" in lowered and "using" in lowered:
        match = re.search(r"response to\s+(.+?)\s+using\s+(.+)", prompt, flags=re.IGNORECASE)
        if match:
            treatment_query = match.group(1).strip(" .:")
            measure_query = re.sub(r"\s+over\s+time.*$", "", match.group(2).strip(" .:"), flags=re.IGNORECASE)
            measure_query = re.sub(r"^cohort\s+a\s+and\s+cohort\s+b\s+(?:by|for)\s+", "", measure_query, flags=re.IGNORECASE)
            measure_query = re.sub(r"^(?:compare|show|plot)\s+", "", measure_query, flags=re.IGNORECASE)
            if treatment_query and measure_query:
                return {"mode": "treatment_response", "treatment_query": treatment_query, "measure_query": measure_query}
    if "trajectory" in lowered or "trajectories" in lowered:
        for pattern in (
            r"trajectory(?:\s+of)?\s+(.+?)(?:\s+over\s+time)?$",
            r"(.+?)\s+trajectories(?:\s+over\s+time)?$",
        ):
            match = re.search(pattern, prompt.strip(), flags=re.IGNORECASE)
            if not match:
                continue
            measure_query = re.sub(r"^(?:show|compare|plot)\s+", "", match.group(1).strip(" .:"), flags=re.IGNORECASE)
            measure_query = re.sub(r"^cohort\s+a\s+and\s+cohort\s+b\s+(?:by|for)\s+", "", measure_query, flags=re.IGNORECASE)
            measure_query = re.sub(r"^(?:the\s+)?", "", measure_query, flags=re.IGNORECASE).strip()
            if measure_query:
                return {"mode": "trajectory", "measure_query": measure_query}
    return None


def _parse_molecular_expression_request(prompt: str) -> Dict[str, Any] | None:
    lowered = prompt.lower()
    if "expression" not in lowered:
        return None
    compare = any(token in lowered for token in ("compare expression", "expression between cohort a and cohort b"))
    match = re.search(r"(?:show|compare)\s+expression\s+of\s+([A-Za-z0-9._-]+)", prompt, flags=re.IGNORECASE)
    if not match:
        match = re.search(r"expression\s+of\s+([A-Za-z0-9._-]+)", prompt, flags=re.IGNORECASE)
    if not match:
        return None
    gene_id = match.group(1).strip(" .:")
    if not gene_id:
        return None
    return {"gene_id": gene_id, "compare": compare}


def _parse_molecular_medication_request(prompt: str) -> bool:
    lowered = prompt.lower()
    if "gene expression" not in lowered and "expression" not in lowered:
        return False
    return any(token in lowered for token in ("medication", "treatment", "drug", "biologic", "biologics"))


def molecular_expression_by_medication_context(data_dir: str) -> Dict[str, Any]:
    datasets = store_molecular_dataset_inventory(data_dir)
    if len(datasets) < 2:
        return {
            "mode": "molecular_medication_compare",
            "error": "At least two molecular datasets are required to compare gene expression by medication.",
            "comparisons": [],
        }
    medication_items = store_medication_counts(data_dir)
    medication_labels = [str(item.get("medication") or "") for item in medication_items if str(item.get("medication") or "").strip()]
    normalized_to_label = {label.lower().replace(" ", ""): label for label in medication_labels}
    matched: List[Dict[str, Any]] = []
    for item in datasets:
        dataset_name = str(item.get("dataset_name") or "")
        normalized_name = dataset_name.lower().replace(" ", "").replace("_", "")
        matched_label = None
        for normalized_label, label in normalized_to_label.items():
            if normalized_label and normalized_label in normalized_name:
                matched_label = label
                break
        if matched_label:
            matched.append({"medication": matched_label, "dataset": item})
    if len(matched) < 2:
        return {
            "mode": "molecular_medication_compare",
            "error": "No medication-aligned molecular datasets were found for deterministic comparison.",
            "comparisons": [],
        }
    comparisons: List[Dict[str, Any]] = []
    for left, right in zip(matched, matched[1:]):
        left_dataset = left["dataset"]["dataset_name"]
        right_dataset = right["dataset"]["dataset_name"]
        top_differences = store_molecular_dataset_pairwise_gene_differences(data_dir, left_dataset, right_dataset, limit=8)
        comparisons.append(
            {
                "medication_a": left["medication"],
                "medication_b": right["medication"],
                "dataset_a": left_dataset,
                "dataset_b": right_dataset,
                "top_genes_a": store_molecular_dataset_gene_means(data_dir, left_dataset, limit=5),
                "top_genes_b": store_molecular_dataset_gene_means(data_dir, right_dataset, limit=5),
                "top_differences": top_differences,
            }
        )
    return {
        "mode": "molecular_medication_compare",
        "comparisons": comparisons,
        "matched_datasets": matched,
    }


def molecular_expression_context(
    data_dir: str,
    gene_id: str,
    selected_patient_ids: str = "",
    compare_selected_patient_ids: str = "",
) -> Dict[str, Any]:
    datasets = store_molecular_dataset_inventory(data_dir)
    if not datasets:
        return {
            "mode": "molecular_expression",
            "gene_id": gene_id,
            "datasets": [],
            "error": "No molecular datasets are currently available.",
        }
    summaries = [
        store_molecular_expression_summary(
            data_dir,
            item["dataset_name"],
            gene_id,
            selected_patient_ids=selected_patient_ids,
            compare_selected_patient_ids=compare_selected_patient_ids,
        )
        for item in datasets
    ]
    return {
        "mode": "molecular_expression",
        "gene_id": gene_id,
        "datasets": summaries,
        "compare_mode": bool(compare_selected_patient_ids.strip()),
    }


def _median(values: List[float]) -> float | None:
    if not values:
        return None
    sorted_values = sorted(values)
    mid = len(sorted_values) // 2
    if len(sorted_values) % 2 == 1:
        return float(sorted_values[mid])
    return (sorted_values[mid - 1] + sorted_values[mid]) / 2.0


def _build_trajectory_context(
    data_dir: str,
    measure_query: str,
    selected_patient_ids: str = "",
    treatment_query: str = "",
) -> Dict[str, Any]:
    resolved_dir = ensure_data_dir(data_dir)
    scope_ids = set(parse_scope_ids(selected_patient_ids))
    patient_measure_events: Dict[str, List[Dict[str, Any]]] = {}
    patient_treatment_dates: Dict[str, Dict[str, List[date]]] = {}
    known_measures: List[str] = []
    known_treatments: List[str] = []

    for _, _, record in read_bff_records(resolved_dir):
        if not record_matches_scope(record, scope_ids):
            continue
        patient_id = extract_record_patient_id(record)
        if not patient_id:
            continue
        event_date = _parse_iso_date(extract_event_date(record))
        if event_date is None:
            continue
        for treatment in extract_treatment_labels(record):
            if treatment not in known_treatments:
                known_treatments.append(treatment)
            patient_treatment_dates.setdefault(patient_id, {}).setdefault(treatment, []).append(event_date)
        measures = record.get("measures")
        if not isinstance(measures, list):
            continue
        for item in measures:
            if not isinstance(item, dict):
                continue
            label = _measure_label(item)
            if not label:
                continue
            if label not in known_measures:
                known_measures.append(label)
            value = _measure_numeric_value(item)
            if value is None:
                continue
            patient_measure_events.setdefault(patient_id, []).append(
                {
                    "date": event_date,
                    "label": label,
                    "value": value,
                    "unit": _measure_unit_label(item),
                }
            )

    resolved_measure = _resolve_measure_name(measure_query, known_measures)
    if not resolved_measure:
        return {
            "mode": "trajectory_response" if treatment_query else "trajectory",
            "source": "deterministic_trajectory",
            "scope_ids": sorted(scope_ids),
            "error": f"Measure not found for trajectory analysis: {measure_query}",
            "available_measures": sorted(known_measures)[:40],
            "available_treatments": sorted(known_treatments)[:40],
        }

    resolved_treatment = ""
    if treatment_query:
        resolved_treatment = _resolve_treatment_name(treatment_query, known_treatments) or ""
        if not resolved_treatment:
            return {
                "mode": "trajectory_response",
                "source": "deterministic_trajectory",
                "scope_ids": sorted(scope_ids),
                "measure": resolved_measure,
                "measure_query": measure_query,
                "error": f"Treatment not found for trajectory analysis: {treatment_query}",
                "available_measures": sorted(known_measures)[:40],
                "available_treatments": sorted(known_treatments)[:40],
            }

    patient_series: List[Dict[str, Any]] = []
    summary_buckets: Dict[str, List[float]] = {}
    unit_label = None
    for patient_id, events in sorted(patient_measure_events.items()):
        matching = [item for item in events if item["label"] == resolved_measure]
        if not matching:
            continue
        matching.sort(key=lambda item: item["date"])
        if resolved_treatment:
            treatment_dates = (patient_treatment_dates.get(patient_id) or {}).get(resolved_treatment, [])
            if not treatment_dates:
                continue
            baseline_date = min(treatment_dates)
            aligned_points = []
            for item in matching:
                if item["date"] < baseline_date:
                    continue
                day = (item["date"] - baseline_date).days
                aligned_points.append({"x": day, "x_label": str(day), "date": item["date"].isoformat(), "value": item["value"]})
                summary_buckets.setdefault(str(day), []).append(float(item["value"]))
            if not aligned_points:
                continue
            unit_label = unit_label or matching[0].get("unit")
            patient_series.append(
                {
                    "patient_id": patient_id,
                    "points": aligned_points,
                    "baseline_date": baseline_date.isoformat(),
                }
            )
        else:
            points = []
            for item in matching:
                key = item["date"].isoformat()
                points.append({"x": key, "x_label": key, "date": key, "value": item["value"]})
                summary_buckets.setdefault(key, []).append(float(item["value"]))
            if not points:
                continue
            unit_label = unit_label or matching[0].get("unit")
            patient_series.append({"patient_id": patient_id, "points": points})

    if len(patient_series) < 2:
        analysis_mode = "trajectory_response" if resolved_treatment else "trajectory"
        return {
            "mode": analysis_mode,
            "source": "deterministic_trajectory",
            "scope_ids": sorted(scope_ids),
            "measure": resolved_measure,
            "measure_query": measure_query,
            "treatment": resolved_treatment or None,
            "unit": unit_label,
            "error": (
                f"Trajectory analysis is unavailable for {resolved_measure}"
                + (f" after {resolved_treatment}" if resolved_treatment else "")
                + " because this scope contains fewer than 2 patients with dated numeric observations."
            ),
            "available_measures": sorted(known_measures)[:40],
            "available_treatments": sorted(known_treatments)[:40],
            "patient_count": len(patient_series),
        }

    summary_points = []
    for key in sorted(summary_buckets, key=lambda item: int(item) if item.isdigit() or (item.startswith("-") and item[1:].isdigit()) else item):
        median_value = _median(summary_buckets[key])
        if median_value is None:
            continue
        if resolved_treatment:
            summary_points.append({"x": int(key), "x_label": key, "value": round(median_value, 4)})
        else:
            summary_points.append({"x": key, "x_label": key, "value": round(median_value, 4)})

    analysis_mode = "trajectory_response" if resolved_treatment else "trajectory"
    return {
        "mode": analysis_mode,
        "source": "deterministic_trajectory",
        "scope_ids": sorted(scope_ids),
        "measure": resolved_measure,
        "measure_query": measure_query,
        "treatment": resolved_treatment or None,
        "unit": unit_label,
        "patient_count": len(patient_series),
        "summary_points": summary_points,
        "patient_series": patient_series[:24],
        "available_measures": sorted(known_measures)[:40],
        "available_treatments": sorted(known_treatments)[:40],
    }


def compare_trajectory_context(data_dir: str, measure_query: str, selected_patient_ids_a: str, selected_patient_ids_b: str, treatment_query: str = "") -> Dict[str, Any]:
    context_a = _build_trajectory_context(data_dir, measure_query, selected_patient_ids=selected_patient_ids_a, treatment_query=treatment_query)
    context_b = _build_trajectory_context(data_dir, measure_query, selected_patient_ids=selected_patient_ids_b, treatment_query=treatment_query)
    return {
        "mode": "trajectory_compare_response" if treatment_query else "trajectory_compare",
        "source": "deterministic_trajectory_compare",
        "measure": context_a.get("measure") or context_b.get("measure") or measure_query,
        "measure_query": measure_query,
        "treatment": context_a.get("treatment") or context_b.get("treatment") or None,
        "unit": context_a.get("unit") or context_b.get("unit"),
        "cohort_a": context_a,
        "cohort_b": context_b,
    }


def _kaplan_meier_points(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    at_risk = len(rows)
    if at_risk <= 0:
        return [{"time_days": 0, "survival_probability": 1.0, "at_risk": 0, "events": 0, "censored": 0}]
    points = [{"time_days": 0, "survival_probability": 1.0, "at_risk": at_risk, "events": 0, "censored": 0}]
    survival = 1.0
    event_times = sorted({int(row["time_to_event_days"]) for row in rows if row.get("event_observed")})
    for event_time in event_times:
        events = sum(1 for row in rows if row.get("event_observed") and int(row["time_to_event_days"]) == event_time)
        censored = sum(1 for row in rows if not row.get("event_observed") and int(row["time_to_event_days"]) == event_time)
        if at_risk > 0:
            survival *= (at_risk - events) / at_risk
        points.append(
            {
                "time_days": event_time,
                "survival_probability": round(survival, 6),
                "at_risk": at_risk,
                "events": events,
                "censored": censored,
            }
        )
        at_risk -= events + censored
    return points


def _median_survival_days(points: List[Dict[str, Any]]) -> int | None:
    for point in points:
        probability = point.get("survival_probability")
        if isinstance(probability, (int, float)) and float(probability) <= 0.5:
            time_days = point.get("time_days")
            return int(time_days) if isinstance(time_days, (int, float)) else None
    return None


def survival_analysis_context(data_dir: str, measure_query: str, operator: str, threshold: float, selected_patient_ids: str = "") -> Dict[str, Any]:
    resolved_dir = ensure_data_dir(data_dir)
    scope_ids = set(parse_scope_ids(selected_patient_ids))
    patient_events: Dict[str, List[Dict[str, Any]]] = {}
    known_labels: List[str] = []

    for _, _, record in read_bff_records(resolved_dir):
        if not record_matches_scope(record, scope_ids):
            continue
        patient_id = extract_record_patient_id(record)
        if not patient_id:
            continue
        event_date = _parse_iso_date(extract_event_date(record))
        if event_date is None:
            continue
        measures = record.get("measures")
        if not isinstance(measures, list):
            continue
        for item in measures:
            if not isinstance(item, dict):
                continue
            label = _measure_label(item)
            if not label:
                continue
            if label not in known_labels:
                known_labels.append(label)
            value = _measure_numeric_value(item)
            if value is None:
                continue
            patient_events.setdefault(patient_id, []).append(
                {
                    "date": event_date,
                    "label": label,
                    "value": value,
                    "unit": _measure_unit_label(item),
                }
            )

    resolved_measure = _resolve_measure_name(measure_query, known_labels)
    if not resolved_measure:
        return {
            "mode": "survival",
            "source": "deterministic_survival",
            "scope_ids": sorted(scope_ids),
            "error": f"Measure not found for Kaplan-Meier analysis: {measure_query}",
            "available_measures": sorted(known_labels)[:40],
        }

    patient_rows: List[Dict[str, Any]] = []
    unit_label = None
    for patient_id, items in sorted(patient_events.items()):
        matching = [item for item in items if item["label"] == resolved_measure]
        if not matching:
            continue
        matching.sort(key=lambda item: item["date"])
        baseline = matching[0]["date"]
        unit_label = unit_label or matching[0].get("unit")
        event_item = next((item for item in matching if _matches_operator(float(item["value"]), operator, threshold)), None)
        last_date = matching[-1]["date"]
        observed = event_item is not None
        target_date = event_item["date"] if event_item is not None else last_date
        patient_rows.append(
            {
                "patient_id": patient_id,
                "time_to_event_days": max((target_date - baseline).days, 0),
                "event_observed": observed,
                "baseline_date": baseline.isoformat(),
                "target_date": target_date.isoformat(),
                "baseline_value": matching[0]["value"],
                "target_value": event_item["value"] if event_item is not None else matching[-1]["value"],
            }
        )

    if len(patient_rows) < 2:
        return {
            "mode": "survival",
            "source": "deterministic_survival",
            "scope_ids": sorted(scope_ids),
            "measure": resolved_measure,
            "measure_query": measure_query,
            "operator": operator,
            "threshold": threshold,
            "unit": unit_label,
            "error": (
                f"Kaplan-Meier is unavailable for {resolved_measure} because this scope contains fewer than 2 patients "
                "with dated numeric observations for that measure."
            ),
            "patient_count": len(patient_rows),
            "available_measures": sorted(known_labels)[:40],
        }

    points = _kaplan_meier_points(patient_rows)
    event_count = sum(1 for row in patient_rows if row["event_observed"])
    censored_count = sum(1 for row in patient_rows if not row["event_observed"])
    median_days = _median_survival_days(points)
    return {
        "mode": "survival",
        "source": "deterministic_survival",
        "scope_ids": sorted(scope_ids),
        "measure": resolved_measure,
        "measure_query": measure_query,
        "operator": operator,
        "threshold": threshold,
        "unit": unit_label,
        "patient_count": len(patient_rows),
        "event_count": event_count,
        "censored_count": censored_count,
        "median_survival_days": median_days,
        "curve_points": points,
        "patient_rows": patient_rows[:200],
        "available_measures": sorted(known_labels)[:40],
    }


def _top_item_name(items: List[Dict[str, Any]], key: str) -> str:
    if items and isinstance(items[0], dict):
        value = items[0].get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "n/a"


def _counts_map(items: List[Dict[str, Any]], label_key: str) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        label = item.get(label_key)
        count = item.get("patient_count")
        if isinstance(label, str) and label.strip() and isinstance(count, int):
            counts[label.strip()] = count
    return counts


def _top_deltas(items_a: List[Dict[str, Any]], items_b: List[Dict[str, Any]], label_key: str, *, limit: int = 8) -> List[Dict[str, Any]]:
    counts_a = _counts_map(items_a, label_key)
    counts_b = _counts_map(items_b, label_key)
    labels = sorted(set(counts_a) | set(counts_b))
    deltas: List[Dict[str, Any]] = []
    for label in labels:
        count_a = counts_a.get(label, 0)
        count_b = counts_b.get(label, 0)
        delta = count_a - count_b
        deltas.append(
            {
                "label": label,
                "cohort_a": count_a,
                "cohort_b": count_b,
                "delta": delta,
                "dominant": "A" if delta > 0 else ("B" if delta < 0 else "equal"),
            }
        )
    deltas.sort(key=lambda item: (-abs(int(item["delta"])), item["label"]))
    return deltas[:limit]


def extract_record_patient_id(record: Dict[str, Any]) -> str | None:
    resolved = extract_patient_id(record)
    if isinstance(resolved, str) and resolved.strip():
        return resolved.strip()
    return None


def extract_record_disease_labels(record: Dict[str, Any]) -> List[str]:
    diseases = record.get("diseases")
    if not isinstance(diseases, list):
        return []
    labels: List[str] = []
    for item in diseases:
        if not isinstance(item, dict):
            continue
        code = item.get("diseaseCode")
        if not isinstance(code, dict):
            continue
        label = code.get("label") or code.get("id")
        if isinstance(label, str) and label.strip() and label not in labels:
            labels.append(label.strip())
    return labels


def parse_scope_ids(value: str) -> List[str]:
    if not value.strip():
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def record_matches_scope(record: Dict[str, Any], scope_ids: set[str]) -> bool:
    if not scope_ids:
        return True
    raw_id = normalize_value(record.get("id"))
    patient_id = extract_record_patient_id(record)
    if isinstance(raw_id, str) and raw_id in scope_ids:
        return True
    if isinstance(patient_id, str) and patient_id in scope_ids:
        return True
    return False


def _analysis_catalog(data_dir: str, selected_patient_ids: str = "", compare_mode: bool = False) -> Dict[str, Any]:
    resolved_dir = ensure_data_dir(data_dir)
    scope_ids = set(parse_scope_ids(selected_patient_ids))
    measures: List[str] = []
    treatments: List[str] = []
    for _, _, record in read_bff_records(resolved_dir):
        if not record_matches_scope(record, scope_ids):
            continue
        for label in extract_treatment_labels(record):
            if label not in treatments:
                treatments.append(label)
        record_measures = record.get("measures")
        if not isinstance(record_measures, list):
            continue
        for item in record_measures:
            if not isinstance(item, dict):
                continue
            label = _measure_label(item)
            if label and label not in measures:
                measures.append(label)
    return {
        "compare_mode": bool(compare_mode),
        "supported_analysis_types": ["summary", "compare_summary", "trajectory", "survival"],
        "supported_survival_operators": [">", ">=", "<", "<="],
        "available_measures": sorted(measures)[:60],
        "available_treatments": sorted(treatments)[:60],
    }


def _validate_analysis_plan(plan: Dict[str, Any], compare_mode: bool = False) -> Dict[str, Any] | None:
    if plan.get("intent") != "analysis_plan":
        return None
    analysis_type = str(plan.get("analysis_type", "")).strip().lower()
    if analysis_type not in {"summary", "compare_summary", "trajectory", "survival"}:
        return None
    if analysis_type == "compare_summary" and not compare_mode:
        return None

    validated: Dict[str, Any] = {"intent": "analysis_plan", "analysis_type": analysis_type}
    if analysis_type == "trajectory":
        measure_query = normalize_value(plan.get("measure_query"))
        if not isinstance(measure_query, str) or not measure_query.strip():
            return None
        validated["measure_query"] = measure_query.strip()
        treatment_query = normalize_value(plan.get("treatment_query"))
        if isinstance(treatment_query, str) and treatment_query.strip():
            validated["treatment_query"] = treatment_query.strip()
        return validated

    if analysis_type == "survival":
        measure_query = normalize_value(plan.get("measure_query"))
        operator = normalize_value(plan.get("operator"))
        threshold = plan.get("threshold")
        if not isinstance(measure_query, str) or not measure_query.strip():
            return None
        if operator not in {">", ">=", "<", "<="}:
            return None
        if not isinstance(threshold, (int, float)) or isinstance(threshold, bool):
            return None
        validated["measure_query"] = measure_query.strip()
        validated["operator"] = operator
        validated["threshold"] = float(threshold)
        return validated

    return validated


def _execute_analysis_plan(
    plan: Dict[str, Any],
    prompt: str,
    data_dir: str,
    selected_patient_ids: str = "",
    compare_mode: bool = False,
    compare_selected_patient_ids: str = "",
    planner_model: str = "",
) -> Dict[str, Any]:
    analysis_type = plan["analysis_type"]
    if analysis_type == "survival":
        if compare_mode:
            context = compare_survival_analysis_context(
                data_dir,
                plan["measure_query"],
                plan["operator"],
                plan["threshold"],
                selected_patient_ids,
                compare_selected_patient_ids,
            )
            intent = "analysis_survival_compare"
        else:
            context = survival_analysis_context(
                data_dir,
                plan["measure_query"],
                plan["operator"],
                plan["threshold"],
                selected_patient_ids=selected_patient_ids,
            )
            intent = "analysis_survival"
    elif analysis_type == "trajectory":
        if compare_mode:
            context = compare_trajectory_context(
                data_dir,
                plan["measure_query"],
                selected_patient_ids,
                compare_selected_patient_ids,
                treatment_query=plan.get("treatment_query", ""),
            )
            intent = "analysis_trajectory_compare"
        else:
            context = _build_trajectory_context(
                data_dir,
                plan["measure_query"],
                selected_patient_ids=selected_patient_ids,
                treatment_query=plan.get("treatment_query", ""),
            )
            intent = "analysis_trajectory"
    elif analysis_type == "compare_summary":
        context = compare_analysis_context(data_dir, selected_patient_ids, compare_selected_patient_ids)
        intent = "analysis_compare"
    else:
        context = analysis_context(data_dir, selected_patient_ids=selected_patient_ids)
        intent = "analysis_deterministic"

    return {
        "intent": intent,
        "reply": deterministic_analysis_reply(prompt, context),
        "data": {
            "source": "deterministic",
            "context": context,
            "model": None,
            "base_url": lm_studio_base_url(),
            "planner": {
                "provider": "lm_studio",
                "model": planner_model,
                "plan": plan,
            },
            "execution": "deterministic",
        },
    }


def _analysis_semantic_plan(
    prompt: str,
    data_dir: str,
    selected_patient_ids: str = "",
    compare_mode: bool = False,
    compare_selected_patient_ids: str = "",
    history: List[Dict[str, str]] | None = None,
) -> Dict[str, Any] | None:
    if not lm_studio_enabled():
        return None
    model = resolve_lm_studio_model(log_kind="analysis_planner_models")
    if not model:
        return None
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You translate clinical analysis requests into a constrained JSON plan. "
                    "Return JSON only. Do not write an analysis answer. "
                    "If unsupported, return {\"intent\":\"unsupported\",\"reason\":\"...\"}. "
                    "Supported schema: "
                    "{\"intent\":\"analysis_plan\",\"analysis_type\":\"summary|compare_summary|trajectory|survival\","
                    "\"measure_query\":\"string optional\",\"treatment_query\":\"string optional\","
                    "\"operator\":\">|>=|<|<= optional\",\"threshold\":0 optional}. "
                    "Use compare_summary only when compare_mode is true. "
                    "Use trajectory only when a specific measure is implied. "
                    "Use survival only when you can infer a specific measure, threshold, and operator from the request."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "analysis_request": prompt,
                        "compare_mode": compare_mode,
                        "selected_patient_ids": parse_scope_ids(selected_patient_ids)[:20],
                        "compare_selected_patient_ids": parse_scope_ids(compare_selected_patient_ids)[:20],
                        "conversation_history": history[-4:] if history else [],
                        "analysis_catalog": _analysis_catalog(data_dir, selected_patient_ids=selected_patient_ids, compare_mode=compare_mode),
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        "temperature": 0,
    }
    try:
        response = http_json(f"{lm_studio_base_url()}/chat/completions", payload, log_kind="analysis_planner")
    except Exception:
        return None
    content = _extract_lm_response_text(response)
    if content is None:
        return None
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, flags=re.DOTALL)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    if not isinstance(parsed, dict):
        return None
    validated = _validate_analysis_plan(parsed, compare_mode=compare_mode)
    if validated is None:
        return None
    return _execute_analysis_plan(
        validated,
        prompt,
        data_dir,
        selected_patient_ids=selected_patient_ids,
        compare_mode=compare_mode,
        compare_selected_patient_ids=compare_selected_patient_ids,
        planner_model=model,
    )


def analysis_context(data_dir: str, selected_patient_ids: str = "") -> Dict[str, Any]:
    resolved_dir = ensure_data_dir(data_dir)
    scope_ids = set(parse_scope_ids(selected_patient_ids))
    if duckdb_available() and not scope_ids:
        patient_rows = store_patient_query_index(str(resolved_dir))
        top_diseases = store_disease_counts(str(resolved_dir))[:8]
        top_medications = store_medication_counts(str(resolved_dir))[:8]
        over_time = store_cohort_over_time_summary(str(resolved_dir))
        source = "duckdb"
    else:
        source = "scoped_records" if scope_ids else "dashboard_fallback"
        patient_stats: Dict[str, Dict[str, Any]] = {}
        disease_patient_sets: Dict[str, set[str]] = {}
        medication_patient_sets: Dict[str, set[str]] = {}
        period_counts: Dict[str, Dict[str, Any]] = {}
        dated_values: List[str] = []
        undated_timepoint_count = 0

        for _, _, record in read_bff_records(resolved_dir):
            if not record_matches_scope(record, scope_ids):
                continue
            patient_id = extract_record_patient_id(record)
            if not patient_id:
                continue
            stat = patient_stats.setdefault(
                patient_id,
                {
                    "visit_count": 0,
                    "medications": set(),
                    "diseases": set(),
                    "original_record_ids": set(),
                },
            )
            stat["visit_count"] += 1
            raw_id = normalize_value(record.get("id"))
            if isinstance(raw_id, str) and raw_id:
                stat["original_record_ids"].add(raw_id)
            for label in extract_record_disease_labels(record):
                stat["diseases"].add(label)
                disease_patient_sets.setdefault(label, set()).add(patient_id)
            for label in extract_treatment_labels(record):
                stat["medications"].add(label)
                medication_patient_sets.setdefault(label, set()).add(patient_id)

            event_date = normalize_value(extract_event_date(record))
            if isinstance(event_date, str) and event_date.strip():
                event_date = event_date.strip()
                dated_values.append(event_date)
                period = event_date[:7] if len(event_date) >= 7 else event_date
                entry = period_counts.setdefault(period, {"period": period, "timepoint_count": 0, "patients": set()})
                entry["timepoint_count"] += 1
                entry["patients"].add(patient_id)
            else:
                undated_timepoint_count += 1

        patient_rows = [
            {
                "patient_id": patient_id,
                "visit_count": stat["visit_count"],
                "medication_count": len(stat["medications"]),
                "disease_count": len(stat["diseases"]),
                "original_record_ids": sorted(stat["original_record_ids"]),
                "medications": sorted(stat["medications"]),
                "diseases": sorted(stat["diseases"]),
            }
            for patient_id, stat in sorted(patient_stats.items())
        ]
        top_diseases = [
            {"disease": label, "patient_count": len(patients), "patients": sorted(patients)}
            for label, patients in sorted(disease_patient_sets.items(), key=lambda item: (-len(item[1]), item[0]))[:8]
        ]
        top_medications = [
            {"medication": label, "patient_count": len(patients), "patients": sorted(patients)}
            for label, patients in sorted(medication_patient_sets.items(), key=lambda item: (-len(item[1]), item[0]))[:8]
        ]
        over_time = {
            "timepoint_count": sum(stat["visit_count"] for stat in patient_stats.values()),
            "patient_count": len(patient_stats),
            "dated_timepoint_count": len(dated_values),
            "undated_timepoint_count": undated_timepoint_count,
            "first_event_date": min(dated_values) if dated_values else None,
            "last_event_date": max(dated_values) if dated_values else None,
            "periods": [
                {
                    "period": period,
                    "timepoint_count": values["timepoint_count"],
                    "patient_count": len(values["patients"]),
                }
                for period, values in sorted(period_counts.items())
            ],
        }

    visit_distribution: Dict[str, int] = {}
    multi_timepoint_patients = 0
    poly_medication_patients = 0
    for row in patient_rows:
        visit_count = int(row.get("visit_count") or 0)
        visit_distribution[str(visit_count)] = visit_distribution.get(str(visit_count), 0) + 1
        if visit_count > 1:
            multi_timepoint_patients += 1
        if int(row.get("medication_count") or 0) > 1:
            poly_medication_patients += 1

    patient_count = over_time.get("patient_count") or len(patient_rows)
    timepoint_count = over_time.get("timepoint_count") or sum(int(row.get("visit_count") or 0) for row in patient_rows)
    notable = []
    if top_diseases:
        notable.append("Most common disease: %s (%s patients)" % (top_diseases[0]["disease"], top_diseases[0]["patient_count"]))
    if top_medications:
        notable.append("Most common medication: %s (%s patients)" % (top_medications[0]["medication"], top_medications[0]["patient_count"]))
    if patient_count:
        notable.append("%s/%s patients have more than one timepoint" % (multi_timepoint_patients, patient_count))
        notable.append("%s/%s patients have more than one medication" % (poly_medication_patients, patient_count))

    return {
        "source": source,
        "scope_ids": sorted(scope_ids),
        "overview": {
            "patient_count": patient_count,
            "timepoint_count": timepoint_count,
            "first_event_date": over_time.get("first_event_date"),
            "last_event_date": over_time.get("last_event_date"),
            "dated_timepoint_count": over_time.get("dated_timepoint_count", 0),
            "undated_timepoint_count": over_time.get("undated_timepoint_count", 0),
            "multi_timepoint_patients": multi_timepoint_patients,
            "poly_medication_patients": poly_medication_patients,
        },
        "top_diseases": top_diseases,
        "top_medications": top_medications,
        "timepoints_by_period": over_time.get("periods", [])[:12],
        "visit_distribution": [{"label": key, "value": value} for key, value in sorted(visit_distribution.items(), key=lambda item: int(item[0]))],
        "notable_findings": notable,
    }


def deterministic_analysis_reply(prompt: str, context: Dict[str, Any]) -> str:
    if context.get("mode") == "molecular_medication_compare":
        if context.get("error"):
            return str(context["error"])
        comparisons = [item for item in (context.get("comparisons") or []) if isinstance(item, dict)]
        if not comparisons:
            return "No deterministic medication-based molecular comparison is available."
        lines: List[str] = []
        for item in comparisons:
            top_difference = (item.get("top_differences") or [{}])[0]
            top_gene_a = (item.get("top_genes_a") or [{}])[0]
            top_gene_b = (item.get("top_genes_b") or [{}])[0]
            if top_difference and top_difference.get("gene_id"):
                lead_a = ""
                if top_gene_a and top_gene_a.get("gene_id"):
                    lead_a = f" {item.get('medication_a')} is led by {top_gene_a['gene_id']} (mean {top_gene_a.get('mean_raw_count', 0):.1f})."
                lead_b = ""
                if top_gene_b and top_gene_b.get("gene_id"):
                    lead_b = f" {item.get('medication_b')} is led by {top_gene_b['gene_id']} (mean {top_gene_b.get('mean_raw_count', 0):.1f})."
                lines.append(
                    (
                        f"Comparing {item.get('medication_a')} vs {item.get('medication_b')}, "
                        f"the largest expression difference is {top_difference['gene_id']} "
                        f"({item.get('medication_a')} mean {float(top_difference.get('mean_a', 0)):.1f}, "
                        f"{item.get('medication_b')} mean {float(top_difference.get('mean_b', 0)):.1f})."
                        f"{lead_a}{lead_b}"
                    )
                )
            else:
                lines.append(
                    f"Comparing {item.get('medication_a')} vs {item.get('medication_b')}, no gene-level difference summary is available."
                )
        return " ".join(lines)
    if context.get("mode") == "molecular_expression":
        if context.get("error"):
            return str(context["error"])
        datasets = [item for item in (context.get("datasets") or []) if isinstance(item, dict)]
        if not datasets:
            return f"No molecular expression summaries are available for {context.get('gene_id', 'the requested gene')}."
        gene_id = context.get("gene_id", "the requested gene")
        lines: List[str] = [f"{gene_id} was found in {len(datasets)} molecular dataset{'s' if len(datasets) != 1 else ''}."]
        for item in datasets:
            dataset_name = item.get("dataset_name", "dataset")
            scope_a = item.get("scope_a", {}) if isinstance(item.get("scope_a"), dict) else {}
            scope_b = item.get("scope_b", {}) if isinstance(item.get("scope_b"), dict) else {}
            if context.get("compare_mode"):
                lines.append(
                    (
                        f"In {dataset_name}, Cohort A has {scope_a.get('sample_count', 0)} samples "
                        f"(mean {scope_a.get('mean', 'n/a')}, median {scope_a.get('median', 'n/a')}, "
                        f"range {scope_a.get('min', 'n/a')} to {scope_a.get('max', 'n/a')}); "
                        f"Cohort B has {scope_b.get('sample_count', 0)} samples "
                        f"(mean {scope_b.get('mean', 'n/a')}, median {scope_b.get('median', 'n/a')}, "
                        f"range {scope_b.get('min', 'n/a')} to {scope_b.get('max', 'n/a')})."
                    )
                )
            else:
                lines.append(
                    (
                        f"In {dataset_name}, {scope_a.get('sample_count', 0)} samples matched the current scope "
                        f"(mean {scope_a.get('mean', 'n/a')}, median {scope_a.get('median', 'n/a')}, "
                        f"range {scope_a.get('min', 'n/a')} to {scope_a.get('max', 'n/a')})."
                    )
                )
        return " ".join(lines)
    if context.get("mode") in {"trajectory", "trajectory_response"}:
        if context.get("error"):
            available = context.get("available_measures") or []
            suffix = f" Known measures include: {', '.join(available[:6])}." if available else ""
            return f"{context['error']}.{suffix}"
        treatment = context.get("treatment")
        treatment_text = f" after first exposure to {treatment}" if isinstance(treatment, str) and treatment.strip() else ""
        unit = f" {context['unit']}" if context.get("unit") else ""
        return (
            f"Trajectory analysis for {context.get('measure', 'measure')}{treatment_text} includes "
            f"{context.get('patient_count', 0)} patients with dated numeric observations. "
            f"The plot shows patient-level trajectories and the cohort median trajectory{unit}."
        )
    if context.get("mode") in {"trajectory_compare", "trajectory_compare_response"}:
        cohort_a = context.get("cohort_a", {})
        cohort_b = context.get("cohort_b", {})
        if cohort_a.get("error") or cohort_b.get("error"):
            problems = [item for item in [cohort_a.get("error"), cohort_b.get("error")] if isinstance(item, str) and item.strip()]
            return " ".join(problems) if problems else "Trajectory comparison is unavailable for the current cohorts."
        treatment = context.get("treatment")
        treatment_text = f" after first exposure to {treatment}" if isinstance(treatment, str) and treatment.strip() else ""
        return (
            f"Trajectory comparison for {context.get('measure', 'measure')}{treatment_text} shows "
            f"Cohort A with {cohort_a.get('patient_count', 0)} patients and Cohort B with {cohort_b.get('patient_count', 0)} patients."
        )
    if context.get("mode") == "survival":
        if context.get("error"):
            available = context.get("available_measures") or []
            suffix = f" Known measures include: {', '.join(available[:6])}." if available else ""
            return f"{context['error']}.{suffix}"
        measure = context.get("measure", "measure")
        operator = context.get("operator", "")
        threshold = context.get("threshold", "")
        unit = f" {context['unit']}" if context.get("unit") else ""
        median = context.get("median_survival_days")
        median_text = f" Median time to event is {median} days." if isinstance(median, int) else " Median time to event is not estimable from the observed follow-up."
        return (
            f"Kaplan-Meier analysis for time to {measure} {operator} {threshold}{unit} includes "
            f"{context.get('patient_count', 0)} patients, with {context.get('event_count', 0)} observed events and "
            f"{context.get('censored_count', 0)} censored patients.{median_text}"
        )
    if context.get("mode") == "survival_compare":
        cohort_a = context.get("cohort_a", {})
        cohort_b = context.get("cohort_b", {})
        if cohort_a.get("error") or cohort_b.get("error"):
            problems = [item for item in [cohort_a.get("error"), cohort_b.get("error")] if isinstance(item, str) and item.strip()]
            return " ".join(problems) if problems else "Kaplan-Meier comparison is unavailable for the current cohorts."
        cohort_a = context.get("cohort_a", {})
        cohort_b = context.get("cohort_b", {})
        measure = context.get("measure", "measure")
        operator = context.get("operator", "")
        threshold = context.get("threshold", "")
        return (
            f"Kaplan-Meier comparison for time to {measure} {operator} {threshold} shows "
            f"Cohort A with {cohort_a.get('patient_count', 0)} patients and {cohort_a.get('event_count', 0)} events, "
            f"and Cohort B with {cohort_b.get('patient_count', 0)} patients and {cohort_b.get('event_count', 0)} events."
        )
    if context.get("mode") == "compare":
        cohort_a = context.get("cohort_a", {})
        cohort_b = context.get("cohort_b", {})
        overview_a = cohort_a.get("overview", {})
        overview_b = cohort_b.get("overview", {})
        disease_delta = (context.get("disease_deltas") or [{}])[0]
        medication_delta = (context.get("medication_deltas") or [{}])[0]
        lines = [
            "Cohort A has %s patients and %s timepoints; Cohort B has %s patients and %s timepoints."
            % (
                overview_a.get("patient_count", 0),
                overview_a.get("timepoint_count", 0),
                overview_b.get("patient_count", 0),
                overview_b.get("timepoint_count", 0),
            ),
            "Top disease in Cohort A: %s. Top disease in Cohort B: %s."
            % (_top_item_name(cohort_a.get("top_diseases", []), "disease"), _top_item_name(cohort_b.get("top_diseases", []), "disease")),
            "Top medication in Cohort A: %s. Top medication in Cohort B: %s."
            % (_top_item_name(cohort_a.get("top_medications", []), "medication"), _top_item_name(cohort_b.get("top_medications", []), "medication")),
        ]
        if disease_delta and disease_delta.get("label"):
            lines.append(
                "Largest disease difference: %s (%s in A vs %s in B)."
                % (disease_delta["label"], disease_delta.get("cohort_a", 0), disease_delta.get("cohort_b", 0))
            )
        if medication_delta and medication_delta.get("label"):
            lines.append(
                "Largest medication difference: %s (%s in A vs %s in B)."
                % (medication_delta["label"], medication_delta.get("cohort_a", 0), medication_delta.get("cohort_b", 0))
            )
        lines.append("LLM analysis is unavailable, so this is a deterministic comparison summary for: %s" % prompt.strip())
        return " ".join(lines)

    overview = context["overview"]
    notable = context.get("notable_findings", [])
    top_disease = context["top_diseases"][0]["disease"] if context["top_diseases"] else "n/a"
    top_medication = context["top_medications"][0]["medication"] if context["top_medications"] else "n/a"
    lines = [
        "This cohort has %s patients and %s timepoints." % (overview["patient_count"], overview["timepoint_count"]),
        "Date range: %s to %s." % (overview.get("first_event_date") or "n/a", overview.get("last_event_date") or "n/a"),
        "Most common disease: %s." % top_disease,
        "Most common medication: %s." % top_medication,
    ]
    if notable:
        lines.append("Notable findings: %s." % "; ".join(notable[:3]))
    lines.append("LLM analysis is unavailable, so this is a deterministic cohort summary for: %s" % prompt.strip())
    return " ".join(lines)


def compare_analysis_context(data_dir: str, selected_patient_ids_a: str, selected_patient_ids_b: str) -> Dict[str, Any]:
    context_a = analysis_context(data_dir, selected_patient_ids=selected_patient_ids_a)
    context_b = analysis_context(data_dir, selected_patient_ids=selected_patient_ids_b)
    return {
        "mode": "compare",
        "source": "comparison",
        "cohort_a": context_a,
        "cohort_b": context_b,
        "disease_deltas": _top_deltas(context_a.get("top_diseases", []), context_b.get("top_diseases", []), "disease"),
        "medication_deltas": _top_deltas(context_a.get("top_medications", []), context_b.get("top_medications", []), "medication"),
    }


def compare_survival_analysis_context(
    data_dir: str,
    measure_query: str,
    operator: str,
    threshold: float,
    selected_patient_ids_a: str,
    selected_patient_ids_b: str,
) -> Dict[str, Any]:
    context_a = survival_analysis_context(data_dir, measure_query, operator, threshold, selected_patient_ids=selected_patient_ids_a)
    context_b = survival_analysis_context(data_dir, measure_query, operator, threshold, selected_patient_ids=selected_patient_ids_b)
    return {
        "mode": "survival_compare",
        "source": "deterministic_survival_compare",
        "measure": context_a.get("measure") or context_b.get("measure") or measure_query,
        "measure_query": measure_query,
        "operator": operator,
        "threshold": threshold,
        "unit": context_a.get("unit") or context_b.get("unit"),
        "cohort_a": context_a,
        "cohort_b": context_b,
    }


def compact_analysis_context_for_llm(context: Dict[str, Any]) -> Dict[str, Any]:
    if context.get("mode") == "molecular_medication_compare":
        return {
            "mode": "molecular_medication_compare",
            "comparisons": [
                {
                    "medication_a": item.get("medication_a"),
                    "medication_b": item.get("medication_b"),
                    "dataset_a": item.get("dataset_a"),
                    "dataset_b": item.get("dataset_b"),
                    "top_differences": [
                        {
                            "gene_id": gene.get("gene_id"),
                            "mean_a": gene.get("mean_a"),
                            "mean_b": gene.get("mean_b"),
                            "abs_delta": gene.get("abs_delta"),
                            "dominant_dataset": gene.get("dominant_dataset"),
                        }
                        for gene in (item.get("top_differences") or [])[:8]
                        if isinstance(gene, dict)
                    ],
                }
                for item in (context.get("comparisons") or [])[:4]
                if isinstance(item, dict)
            ],
        }
    if context.get("mode") == "molecular_expression":
        return {
            "mode": "molecular_expression",
            "gene_id": context.get("gene_id"),
            "compare_mode": context.get("compare_mode"),
            "datasets": [
                {
                    "dataset_name": item.get("dataset_name"),
                    "scope_a": {
                        "sample_count": item.get("scope_a", {}).get("sample_count"),
                        "patient_count": item.get("scope_a", {}).get("patient_count"),
                        "min": item.get("scope_a", {}).get("min"),
                        "median": item.get("scope_a", {}).get("median"),
                        "mean": item.get("scope_a", {}).get("mean"),
                        "max": item.get("scope_a", {}).get("max"),
                    },
                    "scope_b": {
                        "sample_count": item.get("scope_b", {}).get("sample_count"),
                        "patient_count": item.get("scope_b", {}).get("patient_count"),
                        "min": item.get("scope_b", {}).get("min"),
                        "median": item.get("scope_b", {}).get("median"),
                        "mean": item.get("scope_b", {}).get("mean"),
                        "max": item.get("scope_b", {}).get("max"),
                    } if isinstance(item.get("scope_b"), dict) else None,
                }
                for item in (context.get("datasets") or [])[:8]
                if isinstance(item, dict)
            ],
        }
    if context.get("mode") in {"trajectory_compare", "trajectory_compare_response"}:
        return {
            "mode": context.get("mode"),
            "source": context.get("source"),
            "measure": context.get("measure"),
            "treatment": context.get("treatment"),
            "unit": context.get("unit"),
            "cohort_a": {
                "patient_count": context.get("cohort_a", {}).get("patient_count"),
                "summary_points": (context.get("cohort_a", {}).get("summary_points") or [])[:40],
            },
            "cohort_b": {
                "patient_count": context.get("cohort_b", {}).get("patient_count"),
                "summary_points": (context.get("cohort_b", {}).get("summary_points") or [])[:40],
            },
        }
    if context.get("mode") in {"trajectory", "trajectory_response"}:
        return {
            "mode": context.get("mode"),
            "source": context.get("source"),
            "measure": context.get("measure"),
            "treatment": context.get("treatment"),
            "unit": context.get("unit"),
            "patient_count": context.get("patient_count"),
            "summary_points": (context.get("summary_points") or [])[:40],
        }
    if context.get("mode") == "compare":
        return {
            "mode": "compare",
            "source": context.get("source"),
            "cohort_a": compact_analysis_context_for_llm(context.get("cohort_a", {})),
            "cohort_b": compact_analysis_context_for_llm(context.get("cohort_b", {})),
            "disease_deltas": [
                {
                    "label": item.get("label"),
                    "cohort_a": item.get("cohort_a"),
                    "cohort_b": item.get("cohort_b"),
                    "delta": item.get("delta"),
                    "dominant": item.get("dominant"),
                }
                for item in (context.get("disease_deltas") or [])[:8]
                if isinstance(item, dict)
            ],
            "medication_deltas": [
                {
                    "label": item.get("label"),
                    "cohort_a": item.get("cohort_a"),
                    "cohort_b": item.get("cohort_b"),
                    "delta": item.get("delta"),
                    "dominant": item.get("dominant"),
                }
                for item in (context.get("medication_deltas") or [])[:8]
                if isinstance(item, dict)
            ],
        }
    if context.get("mode") == "survival_compare":
        return {
            "mode": "survival_compare",
            "source": context.get("source"),
            "measure": context.get("measure"),
            "operator": context.get("operator"),
            "threshold": context.get("threshold"),
            "unit": context.get("unit"),
            "cohort_a": {
                "patient_count": context.get("cohort_a", {}).get("patient_count"),
                "event_count": context.get("cohort_a", {}).get("event_count"),
                "censored_count": context.get("cohort_a", {}).get("censored_count"),
                "median_survival_days": context.get("cohort_a", {}).get("median_survival_days"),
                "curve_points": (context.get("cohort_a", {}).get("curve_points") or [])[:60],
            },
            "cohort_b": {
                "patient_count": context.get("cohort_b", {}).get("patient_count"),
                "event_count": context.get("cohort_b", {}).get("event_count"),
                "censored_count": context.get("cohort_b", {}).get("censored_count"),
                "median_survival_days": context.get("cohort_b", {}).get("median_survival_days"),
                "curve_points": (context.get("cohort_b", {}).get("curve_points") or [])[:60],
            },
        }
    if context.get("mode") == "survival":
        return {
            "mode": "survival",
            "source": context.get("source"),
            "measure": context.get("measure"),
            "operator": context.get("operator"),
            "threshold": context.get("threshold"),
            "unit": context.get("unit"),
            "patient_count": context.get("patient_count"),
            "event_count": context.get("event_count"),
            "censored_count": context.get("censored_count"),
            "median_survival_days": context.get("median_survival_days"),
            "curve_points": (context.get("curve_points") or [])[:60],
        }

    return {
        "mode": context.get("mode", "single"),
        "source": context.get("source"),
        "scope_ids": (context.get("scope_ids") or [])[:20],
        "overview": context.get("overview", {}),
        "top_diseases": [
            {
                "disease": item.get("disease"),
                "patient_count": item.get("patient_count"),
            }
            for item in (context.get("top_diseases") or [])[:8]
            if isinstance(item, dict)
        ],
        "top_medications": [
            {
                "medication": item.get("medication"),
                "patient_count": item.get("patient_count"),
            }
            for item in (context.get("top_medications") or [])[:8]
            if isinstance(item, dict)
        ],
        "timepoints_by_period": [
            {
                "period": item.get("period"),
                "timepoint_count": item.get("timepoint_count"),
                "patient_count": item.get("patient_count"),
            }
            for item in (context.get("timepoints_by_period") or [])[:12]
            if isinstance(item, dict)
        ],
        "visit_distribution": [
            {
                "label": item.get("label"),
                "value": item.get("value"),
            }
            for item in (context.get("visit_distribution") or [])[:12]
            if isinstance(item, dict)
        ],
        "notable_findings": (context.get("notable_findings") or [])[:6],
    }


def analysis_llm_reply(
    prompt: str,
    data_dir: str,
    selected_patient_ids: str = "",
    compare_mode: bool = False,
    compare_selected_patient_ids: str = "",
    llm_only: bool = False,
    history: List[Dict[str, str]] | None = None,
) -> Dict[str, Any]:
    if _parse_molecular_medication_request(prompt):
        context = molecular_expression_by_medication_context(data_dir)
        return {
            "intent": "analysis_molecular_medication_compare",
            "reply": deterministic_analysis_reply(prompt, context),
            "data": {
                "source": "deterministic",
                "context": context,
                "model": None,
                "base_url": lm_studio_base_url(),
            },
        }
    molecular_request = _parse_molecular_expression_request(prompt)
    if molecular_request is not None:
        context = molecular_expression_context(
            data_dir,
            molecular_request["gene_id"],
            selected_patient_ids=selected_patient_ids,
            compare_selected_patient_ids=compare_selected_patient_ids if compare_mode else "",
        )
        return {
            "intent": "analysis_molecular_expression",
            "reply": deterministic_analysis_reply(prompt, context),
            "data": {
                "source": "deterministic",
                "context": context,
                "model": None,
                "base_url": lm_studio_base_url(),
            },
        }
    survival_request = _parse_survival_request(prompt)
    if survival_request is not None:
        if compare_mode:
            context = compare_survival_analysis_context(
                data_dir,
                survival_request["measure_query"],
                survival_request["operator"],
                survival_request["threshold"],
                selected_patient_ids,
                compare_selected_patient_ids,
            )
            intent = "analysis_survival_compare"
        else:
            context = survival_analysis_context(
                data_dir,
                survival_request["measure_query"],
                survival_request["operator"],
                survival_request["threshold"],
                selected_patient_ids=selected_patient_ids,
            )
            intent = "analysis_survival"
        return {
            "intent": intent,
            "reply": deterministic_analysis_reply(prompt, context),
            "data": {
                "source": "deterministic",
                "context": context,
                "model": None,
                "base_url": lm_studio_base_url(),
            },
        }
    trajectory_request = _parse_trajectory_request(prompt)
    if trajectory_request is not None:
        if compare_mode:
            context = compare_trajectory_context(
                data_dir,
                trajectory_request["measure_query"],
                selected_patient_ids,
                compare_selected_patient_ids,
                treatment_query=trajectory_request.get("treatment_query", ""),
            )
            intent = "analysis_trajectory_compare"
        else:
            context = _build_trajectory_context(
                data_dir,
                trajectory_request["measure_query"],
                selected_patient_ids=selected_patient_ids,
                treatment_query=trajectory_request.get("treatment_query", ""),
            )
            intent = "analysis_trajectory"
        return {
            "intent": intent,
            "reply": deterministic_analysis_reply(prompt, context),
            "data": {
                "source": "deterministic",
                "context": context,
                "model": None,
                "base_url": lm_studio_base_url(),
            },
        }
    if compare_mode:
        context = compare_analysis_context(data_dir, selected_patient_ids, compare_selected_patient_ids)
        intent = "analysis_compare"
    else:
        context = analysis_context(data_dir, selected_patient_ids=selected_patient_ids)
        intent = "analysis_deterministic"

    if not llm_only:
        semantic_plan = _analysis_semantic_plan(
            prompt,
            data_dir,
            selected_patient_ids=selected_patient_ids,
            compare_mode=compare_mode,
            compare_selected_patient_ids=compare_selected_patient_ids,
            history=history,
        )
        if semantic_plan is not None:
            return semantic_plan

    model = resolve_lm_studio_model(log_kind="pheno_models") if lm_studio_enabled() else None
    if not lm_studio_enabled() or not model:
        return {
            "intent": intent,
            "reply": deterministic_analysis_reply(prompt, context),
            "data": {
                "source": "deterministic",
                "context": context,
                "model": model,
                "base_url": lm_studio_base_url(),
            },
        }

    trimmed_history = history[-4:] if history else []
    compact_context = compact_analysis_context_for_llm(context)
    prompt_payload = {
        "analysis_request": prompt,
        "conversation_history": trimmed_history,
        "cohort_analysis_context": compact_context,
        "instructions": [
            "Act as a clinical/bioinformatics analysis assistant.",
            "Use only the provided cohort analysis context.",
            "Summarize important patterns, call out uncertainty, and suggest next analyses.",
            "Do not invent patient-level facts that are not present in the context.",
            "Keep the answer concise but analytical.",
        ],
    }
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "You analyze private clinical cohort summaries. Be precise, restrained, and evidence-based.",
            },
            {
                "role": "user",
                "content": json.dumps(prompt_payload, ensure_ascii=False),
            },
        ],
        "temperature": 0.2,
    }
    try:
        response = http_json(f"{lm_studio_base_url()}/chat/completions", payload, log_kind="analysis_llm")
    except Exception as exc:
        return {
            "intent": intent,
            "reply": deterministic_analysis_reply(prompt, context),
            "data": {
                "source": "deterministic",
                "context": context,
                "model": model,
                "base_url": lm_studio_base_url(),
                "llm_error": str(exc),
            },
        }
    if isinstance(response.get("error"), str):
        return {
            "intent": intent,
            "reply": deterministic_analysis_reply(prompt, context),
            "data": {
                "source": "deterministic",
                "context": context,
                "model": model,
                "base_url": lm_studio_base_url(),
                "llm_error": response["error"],
            },
        }
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        return {
            "intent": intent,
            "reply": deterministic_analysis_reply(prompt, context),
            "data": {
                "source": "deterministic",
                "context": context,
                "model": model,
                "base_url": lm_studio_base_url(),
                "llm_error": "LM Studio returned an unexpected response format.",
            },
        }
    message = choices[0].get("message", {})
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        return {
            "intent": intent,
            "reply": deterministic_analysis_reply(prompt, context),
            "data": {
                "source": "deterministic",
                "context": context,
                "model": model,
                "base_url": lm_studio_base_url(),
                "llm_error": "LM Studio returned an empty analysis reply.",
            },
        }
    return {
        "intent": "analysis_compare_llm" if compare_mode else "analysis_llm",
        "reply": sanitize_lm_text(content),
        "data": {
            "source": "llm",
            "context": context,
            "model": model,
            "base_url": lm_studio_base_url(),
        },
    }
