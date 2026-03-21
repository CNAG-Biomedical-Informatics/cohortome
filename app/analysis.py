from __future__ import annotations

import json
from typing import Any, Dict, List

from app.bff import ensure_data_dir, extract_treatment_labels, normalize_value, read_bff_records
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
    patient_query_index as store_patient_query_index,
)


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
    patient_id = record.get("patient_id")
    if isinstance(patient_id, str) and patient_id.strip():
        return patient_id.strip()
    record_id = record.get("id")
    if isinstance(record_id, str) and record_id.strip():
        return record_id.strip()
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

            event_date = normalize_value(record.get("event_date"))
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


def compact_analysis_context_for_llm(context: Dict[str, Any]) -> Dict[str, Any]:
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
    history: List[Dict[str, str]] | None = None,
) -> Dict[str, Any]:
    if compare_mode:
        context = compare_analysis_context(data_dir, selected_patient_ids, compare_selected_patient_ids)
        intent = "analysis_compare"
    else:
        context = analysis_context(data_dir, selected_patient_ids=selected_patient_ids)
        intent = "analysis_deterministic"
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
