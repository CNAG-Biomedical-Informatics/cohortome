from __future__ import annotations

import json
import re
from datetime import date
from typing import Any, Dict, List

from app.analysis_catalog import analysis_catalog_debug_enabled, get_analysis_catalog_item
from app.analysis_external import run_external_analysis
from app.jobs import submit_analysis_job
from app.bff import ensure_data_dir, extract_event_date, extract_patient_id, extract_treatment_labels, normalize_value, read_bff_records
from app.datasets import clinical_representation
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
    assay_dataset_feature_means_scoped as store_assay_dataset_feature_means_scoped,
    assay_dataset_pairwise_exploratory_volcano as store_assay_dataset_pairwise_exploratory_volcano,
    assay_dataset_pairwise_feature_differences as store_assay_dataset_pairwise_feature_differences,
    assay_dataset_inventory as store_assay_dataset_inventory,
    assay_expression_summary as store_assay_expression_summary,
    patient_query_index as store_patient_query_index,
)


def _normalize_analysis_granularity_ceiling(value: str) -> str:
    return "detailed" if str(value or "").strip().lower() == "detailed" else "summary"


def _normalize_analysis_ai_provider_access(value: str) -> str:
    normalized = str(value or "").strip().lower()
    aliases = {
        "use_thread_mode": "detailed_allowed",
        "detailed": "detailed_allowed",
        "summary_only": "safe_summary",
        "restricted": "safe_summary",
    }
    normalized = aliases.get(normalized, normalized)
    return normalized if normalized in {"detailed_allowed", "safe_summary", "blocked"} else "detailed_allowed"


def _analysis_ai_provider_context_granularity(granularity_applied: str, ai_provider_access: str) -> str:
    if ai_provider_access == "blocked":
        return "blocked"
    if ai_provider_access == "safe_summary":
        return "safe_summary"
    return granularity_applied


def _analysis_strip_scope_ids(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _analysis_strip_scope_ids(item)
            for key, item in value.items()
            if key != "scope_ids"
        }
    if isinstance(value, list):
        return [_analysis_strip_scope_ids(item) for item in value]
    return value


def _restricted_analysis_context_for_llm(context: Dict[str, Any]) -> Dict[str, Any]:
    mode = str(context.get("mode") or "single")
    return {
        "mode": mode,
        "source": context.get("source"),
        "compare_mode": mode in {"compare", "trajectory_compare", "trajectory_compare_response", "survival_compare", "measure_inventory_compare"},
        "context_sections": sorted(
            key for key in context.keys()
            if key not in {"top_diseases", "top_medications", "notable_findings", "scope_ids"}
        )[:12],
    }


def _analysis_provider_context_for_llm(
    context: Dict[str, Any],
    granularity_applied: str,
    ai_provider_access: str,
) -> Dict[str, Any]:
    if ai_provider_access == "safe_summary":
        return _restricted_analysis_context_for_llm(context)
    compact = compact_analysis_context_for_llm(context)
    if granularity_applied == "summary":
        return _analysis_strip_scope_ids(compact)
    return compact


def _analysis_finalize_response(
    payload: Dict[str, Any],
    granularity_applied: str,
    ai_provider_access: str,
) -> Dict[str, Any]:
    finalized = dict(payload)
    data = dict(finalized.get("data") or {})
    data["granularity_applied"] = granularity_applied
    data["ai_provider_access"] = ai_provider_access
    data["external_llm_allowed"] = ai_provider_access != "blocked"
    data["ai_provider_context_granularity"] = _analysis_ai_provider_context_granularity(
        granularity_applied,
        ai_provider_access,
    )
    finalized["data"] = data
    return finalized


def _analysis_ai_provider_blocked_response() -> Dict[str, Any]:
    return {
        "intent": "analysis_llm",
        "reply": (
            "AI provider access is blocked for this dataset or workspace. "
            "This Analysis prompt requires an AI provider, so no external interpretation was run."
        ),
        "data": {
            "source": "policy",
            "context": {"mode": "policy", "source": "analysis", "policy": "ai_provider_blocked"},
            "model": None,
            "base_url": lm_studio_base_url(),
        },
    }


def _analysis_ai_provider_unavailable_response(reason: str) -> Dict[str, Any]:
    return {
        "intent": "analysis_llm",
        "reply": (
            "This Analysis prompt requires an AI provider, but no provider reply was available. "
            f"{reason}"
        ).strip(),
        "data": {
            "source": "provider_unavailable",
            "context": {"mode": "provider_unavailable", "source": "analysis"},
            "model": None,
            "base_url": lm_studio_base_url(),
        },
    }


def _analysis_catalog_dispatch(
    prompt: str,
    *,
    catalog_item_id: str,
    data_dir: str,
    dataset_id: str = "",
    assay_id: str = "",
    analysis_session_id: str = "",
    user_id: str = "",
    selected_patient_ids: str = "",
    compare_selected_patient_ids: str = "",
    granularity_applied: str = "detailed",
) -> Dict[str, Any] | None:
    item = get_analysis_catalog_item(catalog_item_id)
    if not item:
        return None
    normalized_prompt = str(prompt or "").strip()
    if not normalized_prompt:
        raise RuntimeError("A prompt is required for the selected analysis.")
    # An explicit catalog id selects the reviewed runner. The prompt remains
    # editable context for that runner; server-side catalog, assay, scope, and
    # access checks remain authoritative.
    if item.get("debug_only") and not analysis_catalog_debug_enabled():
        raise RuntimeError("This analysis is not available in the current catalog.")
    if item.get("requires_detailed_access") and granularity_applied != "detailed":
        raise RuntimeError("This analysis requires Detailed in-app access for the current workspace.")
    required_representation = str(item.get("required_clinical_representation") or "").strip().lower()
    if required_representation and clinical_representation(data_dir) != required_representation:
        raise RuntimeError("This analysis requires longitudinal visit or timepoint records.")
    if item.get("requires_assays"):
        assay_inventory = store_assay_dataset_inventory(data_dir)
        required_modalities = {
            str(value or "").strip()
            for value in item.get("required_modalities", [])
            if str(value or "").strip()
        }
        required_data_types = {
            str(value or "").strip()
            for value in item.get("required_data_types", [])
            if str(value or "").strip()
        }
        compatible_assays = [
            assay
            for assay in assay_inventory
            if (
                not required_modalities
                or str(assay.get("modality") or "").strip() in required_modalities
            )
            and (
                not required_data_types
                or str(assay.get("data_type") or "").strip() in required_data_types
            )
        ]
        if not compatible_assays:
            raise RuntimeError("This analysis requires a compatible assay in the active workspace.")
        selected_assay = str(assay_id or "").strip()
        if selected_assay and not any(
            selected_assay
            in {
                str(assay.get("assay_id") or "").strip(),
                str(assay.get("dataset_name") or "").strip(),
            }
            for assay in compatible_assays
        ):
            raise RuntimeError("The selected assay is not compatible with this analysis.")
        selected_item = next(
            (
                assay
                for assay in compatible_assays
                if selected_assay
                in {
                    str(assay.get("assay_id") or "").strip(),
                    str(assay.get("dataset_name") or "").strip(),
                }
            ),
            compatible_assays[0] if not selected_assay and len(compatible_assays) == 1 else None,
        )
        minimum_samples = max(0, int(item.get("minimum_samples_per_cohort") or 0))
        if minimum_samples and item.get("default_compare_mode"):
            if selected_item is None:
                raise RuntimeError("This analysis requires one explicitly selected compatible assay.")
            assay_scope_ids = {
                str(value or "").strip()
                for key in ("sample_ids", "patient_ids")
                for value in selected_item.get(key, [])
                if str(value or "").strip()
            }
            cohort_a_ids = {
                value.strip()
                for value in str(selected_patient_ids or "").split(",")
                if value.strip()
            }
            cohort_b_ids = {
                value.strip()
                for value in str(compare_selected_patient_ids or "").split(",")
                if value.strip()
            }
            if (
                len(assay_scope_ids.intersection(cohort_a_ids)) < minimum_samples
                or len(assay_scope_ids.intersection(cohort_b_ids)) < minimum_samples
            ):
                raise RuntimeError(
                    f"This analysis requires at least {minimum_samples} assay-linked samples in each cohort."
                )
    runner_type = str(item.get("runner_type") or "builtin").strip().lower()
    execution_backend = str(item.get("execution_backend") or "sync").strip().lower()
    if runner_type == "builtin":
        return None
    if execution_backend == "job":
        payload = submit_analysis_job(
            user_id=user_id,
            analysis_session_id=analysis_session_id,
            prompt=prompt,
            data_dir=data_dir,
            dataset_id=dataset_id,
            assay_id=assay_id,
            catalog_item=item,
            selected_patient_ids=selected_patient_ids,
            compare_selected_patient_ids=compare_selected_patient_ids,
            compare_mode=bool(compare_selected_patient_ids),
        )
        job_code = str(payload.get("job_code") or "").strip()
        job_label = f" {job_code}." if job_code else ""
        return {
            "intent": "analysis_job",
            "reply": (
                f"Submitted {str(item.get('name') or 'analysis').strip() or 'analysis'} as a background job. "
                f"Open Jobs to monitor progress and view the result when it completes.{job_label}"
            ),
            "data": {
                "source": "job",
                "execution": "queued",
                "context": {
                    "mode": "queued_job",
                    "feature": "analysis",
                    "job_id": payload["job_id"],
                    "job_code": job_code,
                    "job_status": payload["status"],
                },
                "model": None,
                "base_url": "",
                "job_id": payload["job_id"],
                "job_code": job_code,
                "job_status": payload["status"],
                "analysis_session_title": str(payload.get("analysis_session_title") or "").strip(),
                "catalog_item_id": str(item.get("id") or "").strip(),
                "catalog_item_name": str(item.get("name") or "").strip(),
                "runner_type": runner_type,
                "runner_ref": str(item.get("runner_ref") or "").strip(),
                "analysis_session_id": analysis_session_id,
                "execution_backend": execution_backend,
            },
        }
    if runner_type in {"rscript", "snakemake", "nextflow", "workflow"}:
        payload = run_external_analysis(
            runner_type,
            str(item.get("runner_ref") or "").strip(),
            prompt=prompt,
            data_dir=data_dir,
            assay_id=assay_id,
            selected_patient_ids=selected_patient_ids,
            compare_selected_patient_ids=compare_selected_patient_ids,
        )
        payload["data"]["catalog_item_id"] = str(item.get("id") or "").strip()
        payload["data"]["catalog_item_name"] = str(item.get("name") or "").strip()
        return payload
    raise RuntimeError(f"Unsupported analysis runner type '{runner_type}'.")


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


def _parse_transcriptomics_expression_request(prompt: str) -> Dict[str, Any] | None:
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


def _parse_transcriptomics_medication_request(prompt: str) -> bool:
    lowered = prompt.lower()
    if "gene expression" not in lowered and "expression" not in lowered:
        return False
    return any(token in lowered for token in ("medication", "treatment", "drug", "biologic", "biologics"))


def _parse_measure_inventory_request(prompt: str) -> bool:
    lowered = prompt.lower()
    if not any(token in lowered for token in ("measure", "measures", "lab", "labs", "parameter", "parameters", "variable", "variables")):
        return False
    return any(
        token in lowered
        for token in (
            "what measures",
            "which measures",
            "available measures",
            "list measures",
            "what labs",
            "which labs",
            "available labs",
            "which numeric longitudinal measures",
            "what numeric longitudinal measures",
        )
    )


def measure_inventory_context(data_dir: str, selected_patient_ids: str = "") -> Dict[str, Any]:
    resolved_dir = ensure_data_dir(data_dir)
    scope_ids = set(parse_scope_ids(selected_patient_ids))
    counts: Dict[str, Dict[str, Any]] = {}
    for _, _, record in read_bff_records(resolved_dir):
        if not record_matches_scope(record, scope_ids):
            continue
        patient_id = extract_record_patient_id(record)
        measures = record.get("measures")
        if not patient_id or not isinstance(measures, list):
            continue
        for item in measures:
            if not isinstance(item, dict):
                continue
            label = _measure_label(item)
            value = _measure_numeric_value(item)
            if not label or value is None:
                continue
            entry = counts.setdefault(
                label,
                {
                    "measure": label,
                    "unit": _measure_unit_label(item),
                    "patient_ids": set(),
                    "observation_count": 0,
                },
            )
            entry["observation_count"] += 1
            entry["patient_ids"].add(patient_id)
            if not entry.get("unit"):
                entry["unit"] = _measure_unit_label(item)
    measures = sorted(
        [
            {
                "measure": label,
                "unit": values.get("unit"),
                "patient_count": len(values.get("patient_ids") or set()),
                "observation_count": int(values.get("observation_count") or 0),
            }
            for label, values in counts.items()
        ],
        key=lambda item: (-int(item["patient_count"]), item["measure"]),
    )
    return {
        "mode": "measure_inventory",
        "source": "deterministic_measure_inventory",
        "scope_ids": sorted(scope_ids),
        "measure_count": len(measures),
        "measures": measures,
    }


def compare_measure_inventory_context(data_dir: str, selected_patient_ids_a: str, selected_patient_ids_b: str) -> Dict[str, Any]:
    context_a = measure_inventory_context(data_dir, selected_patient_ids=selected_patient_ids_a)
    context_b = measure_inventory_context(data_dir, selected_patient_ids=selected_patient_ids_b)
    labels = sorted(
        {
            str(item.get("measure") or "")
            for item in (context_a.get("measures") or []) + (context_b.get("measures") or [])
            if str(item.get("measure") or "").strip()
        }
    )
    return {
        "mode": "measure_inventory_compare",
        "source": "deterministic_measure_inventory_compare",
        "cohort_a": context_a,
        "cohort_b": context_b,
        "measures": labels,
    }


def transcriptomics_expression_by_medication_context(
    data_dir: str,
    selected_patient_ids: str = "",
    compare_selected_patient_ids: str = "",
) -> Dict[str, Any]:
    datasets = store_assay_dataset_inventory(data_dir)
    scope_ids = parse_scope_ids(selected_patient_ids) + parse_scope_ids(compare_selected_patient_ids)
    scope_patient_ids = derive_scope_patient_ids(scope_ids)
    scope_patient_id_set = {item for item in scope_patient_ids if item}
    if len(datasets) < 2:
        return {
            "mode": "transcriptomics_medication_compare",
            "error": "At least two assays are required to compare gene expression by medication.",
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
            dataset_patient_ids = [str(value).strip() for value in (item.get("patient_ids") or []) if str(value).strip()]
            scoped_patient_ids = dataset_patient_ids
            if scope_patient_id_set:
                scoped_patient_ids = [patient_id for patient_id in dataset_patient_ids if patient_id in scope_patient_id_set]
                if not scoped_patient_ids:
                    continue
            matched.append({"medication": matched_label, "dataset": item, "scoped_patient_ids": scoped_patient_ids})
    if len(matched) < 2:
        if scope_patient_id_set:
            matched_summary = ", ".join(
                f"{item['medication']} ({len(item['scoped_patient_ids'])} scoped patient{'s' if len(item['scoped_patient_ids']) != 1 else ''})"
                for item in matched
            ) or "none"
            detail = (
                f" Current Analysis scope resolves to {len(scope_patient_id_set)} patient"
                f"{'s' if len(scope_patient_id_set) != 1 else ''} for assay comparison; medication-aligned assays found in scope: {matched_summary}."
            )
        else:
            detail = ""
        return {
            "mode": "transcriptomics_medication_compare",
            "error": (
                "At least two medication-aligned assays with patients in the current Analysis scope are required for deterministic comparison."
                + detail
            ),
            "comparisons": [],
            "matched_datasets": matched,
            "scope_patient_count": len(scope_patient_id_set),
        }
    comparisons: List[Dict[str, Any]] = []
    for left, right in zip(matched, matched[1:]):
        left_dataset = left["dataset"]["dataset_name"]
        right_dataset = right["dataset"]["dataset_name"]
        scoped_ids = sorted(set(left["scoped_patient_ids"]) | set(right["scoped_patient_ids"]))
        top_differences = store_assay_dataset_pairwise_feature_differences(
            data_dir,
            left_dataset,
            right_dataset,
            selected_patient_ids=scoped_ids,
            limit=8,
        )
        comparisons.append(
            {
                "medication_a": left["medication"],
                "medication_b": right["medication"],
                "dataset_a": left_dataset,
                "dataset_b": right_dataset,
                "scoped_patient_ids_a": left["scoped_patient_ids"],
                "scoped_patient_ids_b": right["scoped_patient_ids"],
                "top_genes_a": store_assay_dataset_feature_means_scoped(
                    data_dir,
                    left_dataset,
                    selected_patient_ids=left["scoped_patient_ids"],
                    limit=5,
                ),
                "top_genes_b": store_assay_dataset_feature_means_scoped(
                    data_dir,
                    right_dataset,
                    selected_patient_ids=right["scoped_patient_ids"],
                    limit=5,
                ),
                "top_differences": top_differences,
                "exploratory_volcano_points": store_assay_dataset_pairwise_exploratory_volcano(
                    data_dir,
                    left_dataset,
                    right_dataset,
                    selected_patient_ids=scoped_ids,
                    limit=1500,
                ),
            }
        )
    return {
        "mode": "transcriptomics_medication_compare",
        "comparisons": comparisons,
        "matched_datasets": matched,
        "scope_patient_count": len(scope_patient_id_set),
        "exploratory_note": (
            "Exploratory transcriptomics comparison based on log2(CPM+1) normalization and a simple "
            "per-gene normal-approximation test. This is preliminary and not DESeq2-grade differential expression."
        ),
    }


def transcriptomics_expression_context(
    data_dir: str,
    gene_id: str,
    selected_patient_ids: str = "",
    compare_selected_patient_ids: str = "",
) -> Dict[str, Any]:
    datasets = store_assay_dataset_inventory(data_dir)
    if not datasets:
        return {
            "mode": "transcriptomics_expression",
            "gene_id": gene_id,
            "datasets": [],
            "error": "No assays are currently available.",
        }
    summaries = [
        store_assay_expression_summary(
            data_dir,
            item["dataset_name"],
            gene_id,
            selected_patient_ids=selected_patient_ids,
            compare_selected_patient_ids=compare_selected_patient_ids,
        )
        for item in datasets
    ]
    return {
        "mode": "transcriptomics_expression",
        "gene_id": gene_id,
        "datasets": summaries,
        "compare_mode": bool(compare_selected_patient_ids.strip()),
    }


def _analysis_stat_cell(value: Any) -> str:
    normalized = normalize_value(value)
    if normalized is None or normalized == "":
        return "n/a"
    if isinstance(normalized, (int, float)):
        return f"{float(normalized):.3f}".rstrip("0").rstrip(".")
    return str(normalized)


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
    time_axis_label = "Days since treatment start" if resolved_treatment else "Days since first dated observation"
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
            baseline_date = matching[0]["date"]
            points = []
            for item in matching:
                day = (item["date"] - baseline_date).days
                key = str(day)
                points.append({"x": day, "x_label": key, "date": item["date"].isoformat(), "value": item["value"]})
                summary_buckets.setdefault(key, []).append(float(item["value"]))
            if not points:
                continue
            unit_label = unit_label or matching[0].get("unit")
            patient_series.append(
                {
                    "patient_id": patient_id,
                    "points": points,
                    "baseline_date": baseline_date.isoformat(),
                }
            )

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
        "time_axis_label": time_axis_label,
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
        "time_axis_label": context_a.get("time_axis_label") or context_b.get("time_axis_label") or "Days since first dated observation",
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


def derive_scope_patient_ids(scope_ids: List[str]) -> List[str]:
    derived: List[str] = []
    seen = set()
    for item in scope_ids:
        normalized = item.strip()
        if not normalized:
            continue
        patient_id = normalized.split(":", 1)[0].strip()
        if patient_id and patient_id not in seen:
            seen.add(patient_id)
            derived.append(patient_id)
    return derived


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
    granularity_applied: str = "detailed",
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
                        "selected_patient_ids": parse_scope_ids(selected_patient_ids)[:20] if granularity_applied == "detailed" else [],
                        "compare_selected_patient_ids": parse_scope_ids(compare_selected_patient_ids)[:20] if granularity_applied == "detailed" else [],
                        "conversation_history": history[-4:] if history and granularity_applied == "detailed" else [],
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
    if context.get("mode") == "measure_inventory":
        measures = [item for item in (context.get("measures") or []) if isinstance(item, dict)]
        if not measures:
            return "No numeric longitudinal measures are available in the current Analysis scope."
        parts = []
        for item in measures[:10]:
            label = str(item.get("measure") or "")
            unit = f" ({item['unit']})" if item.get("unit") else ""
            parts.append(
                f"{label}{unit}: {int(item.get('patient_count') or 0)} patients, {int(item.get('observation_count') or 0)} observations"
            )
        return "Available numeric longitudinal measures in the current Analysis scope: " + "; ".join(parts) + "."
    if context.get("mode") == "measure_inventory_compare":
        cohort_a = context.get("cohort_a", {})
        cohort_b = context.get("cohort_b", {})
        labels = [str(item) for item in (context.get("measures") or []) if str(item).strip()]
        if not labels:
            return "No shared numeric longitudinal measures are available across the selected Analysis cohorts."
        return (
            f"Cohort A has {int(cohort_a.get('measure_count') or 0)} numeric longitudinal measures and "
            f"Cohort B has {int(cohort_b.get('measure_count') or 0)}. "
            f"Available measures across these cohorts: {', '.join(labels[:12])}."
        )
    if context.get("mode") == "transcriptomics_medication_compare":
        if context.get("error"):
            return str(context["error"])
        comparisons = [item for item in (context.get("comparisons") or []) if isinstance(item, dict)]
        if not comparisons:
            return "No deterministic medication-based assay comparison is available."
        lines: List[str] = []
        if int(context.get("scope_patient_count") or 0) > 0:
            lines.append(
                f"The medication-based assay comparison is restricted to the current Analysis scope ({int(context.get('scope_patient_count') or 0)} patient{'s' if int(context.get('scope_patient_count') or 0) != 1 else ''})."
            )
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
        if context.get("exploratory_note"):
            lines.append(str(context["exploratory_note"]))
        return "\n".join(lines)
    if context.get("mode") == "transcriptomics_expression":
        if context.get("error"):
            return str(context["error"])
        datasets = [item for item in (context.get("datasets") or []) if isinstance(item, dict)]
        if not datasets:
            return f"No assay expression summaries are available for {context.get('gene_id', 'the requested gene')}."
        gene_id = context.get("gene_id", "the requested gene")
        lines: List[str] = [f"{gene_id} was found in {len(datasets)} assay{'s' if len(datasets) != 1 else ''}."]
        if context.get("compare_mode"):
            lines.extend(
                [
                    "",
                    "| Dataset | Scope | Samples | Patients | Mean | Median | Min | Max |",
                    "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
                ]
            )
            for item in datasets:
                dataset_name = item.get("dataset_name", "dataset")
                scope_a = item.get("scope_a", {}) if isinstance(item.get("scope_a"), dict) else {}
                scope_b = item.get("scope_b", {}) if isinstance(item.get("scope_b"), dict) else {}
                lines.append(
                    (
                        f"| {dataset_name} | Cohort A | {_analysis_stat_cell(scope_a.get('sample_count'))} "
                        f"| {_analysis_stat_cell(scope_a.get('patient_count'))} "
                        f"| {_analysis_stat_cell(scope_a.get('mean'))} "
                        f"| {_analysis_stat_cell(scope_a.get('median'))} "
                        f"| {_analysis_stat_cell(scope_a.get('min'))} "
                        f"| {_analysis_stat_cell(scope_a.get('max'))} |"
                    )
                )
                lines.append(
                    (
                        f"| {dataset_name} | Cohort B | {_analysis_stat_cell(scope_b.get('sample_count'))} "
                        f"| {_analysis_stat_cell(scope_b.get('patient_count'))} "
                        f"| {_analysis_stat_cell(scope_b.get('mean'))} "
                        f"| {_analysis_stat_cell(scope_b.get('median'))} "
                        f"| {_analysis_stat_cell(scope_b.get('min'))} "
                        f"| {_analysis_stat_cell(scope_b.get('max'))} |"
                    )
                )
        else:
            lines.extend(
                [
                    "",
                    "| Dataset | Samples | Patients | Mean | Median | Min | Max |",
                    "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
                ]
            )
            for item in datasets:
                dataset_name = item.get("dataset_name", "dataset")
                scope_a = item.get("scope_a", {}) if isinstance(item.get("scope_a"), dict) else {}
                lines.append(
                    (
                        f"| {dataset_name} | {_analysis_stat_cell(scope_a.get('sample_count'))} "
                        f"| {_analysis_stat_cell(scope_a.get('patient_count'))} "
                        f"| {_analysis_stat_cell(scope_a.get('mean'))} "
                        f"| {_analysis_stat_cell(scope_a.get('median'))} "
                        f"| {_analysis_stat_cell(scope_a.get('min'))} "
                        f"| {_analysis_stat_cell(scope_a.get('max'))} |"
                    )
                )
        return "\n".join(lines)
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
        formatted = [
            "### Deterministic Comparison Summary",
            "",
            "- **Cohort A:** %s patients, %s timepoints." % (
                overview_a.get("patient_count", 0),
                overview_a.get("timepoint_count", 0),
            ),
            "- **Cohort B:** %s patients, %s timepoints." % (
                overview_b.get("patient_count", 0),
                overview_b.get("timepoint_count", 0),
            ),
            "- **Date range:** %s to %s in Cohort A; %s to %s in Cohort B." % (
                overview_a.get("first_event_date") or "n/a",
                overview_a.get("last_event_date") or "n/a",
                overview_b.get("first_event_date") or "n/a",
                overview_b.get("last_event_date") or "n/a",
            ),
        ]
        if disease_delta and disease_delta.get("label"):
            formatted.append(
                "- **Largest disease difference:** %s (%s in A vs %s in B)." % (
                    disease_delta["label"],
                    disease_delta.get("cohort_a", 0),
                    disease_delta.get("cohort_b", 0),
                )
            )
        if medication_delta and medication_delta.get("label"):
            formatted.append(
                "- **Largest medication difference:** %s (%s in A vs %s in B)." % (
                    medication_delta["label"],
                    medication_delta.get("cohort_a", 0),
                    medication_delta.get("cohort_b", 0),
                )
            )
        return "\n".join(formatted)

    overview = context["overview"]
    notable = context.get("notable_findings", [])
    top_disease = context["top_diseases"][0]["disease"] if context["top_diseases"] else "n/a"
    top_medication = context["top_medications"][0]["medication"] if context["top_medications"] else "n/a"
    lines = [
        "### Deterministic Workspace Summary",
        "",
        "- **Patients:** %s" % overview["patient_count"],
        "- **Timepoints:** %s" % overview["timepoint_count"],
        "- **Date range:** %s to %s" % (
            overview.get("first_event_date") or "n/a",
            overview.get("last_event_date") or "n/a",
        ),
        "- **Most common disease:** %s" % top_disease,
        "- **Most common medication:** %s" % top_medication,
    ]
    if notable:
        lines.append("- **Notable findings:**")
        for item in notable[:3]:
            lines.append("  - %s" % item)
    return "\n".join(lines)


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
    if context.get("mode") == "transcriptomics_medication_compare":
        return {
            "mode": "transcriptomics_medication_compare",
            "exploratory_note": context.get("exploratory_note"),
            "comparisons": [
                {
                    "medication_a": item.get("medication_a"),
                    "medication_b": item.get("medication_b"),
                    "dataset_a": item.get("dataset_a"),
                    "dataset_b": item.get("dataset_b"),
                    "exploratory_volcano_points": [
                        {
                            "gene_id": gene.get("gene_id"),
                            "log2_fold_change": gene.get("log2_fold_change"),
                            "neg_log10_p": gene.get("neg_log10_p"),
                        }
                        for gene in (item.get("exploratory_volcano_points") or [])[:250]
                        if isinstance(gene, dict)
                    ],
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
    if context.get("mode") == "transcriptomics_expression":
        return {
            "mode": "transcriptomics_expression",
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


def _analysis_llm_reply_impl(
    prompt: str,
    data_dir: str,
    catalog_item_id: str = "",
    dataset_id: str = "",
    assay_id: str = "",
    analysis_session_id: str = "",
    user_id: str = "",
    selected_patient_ids: str = "",
    compare_mode: bool = False,
    compare_selected_patient_ids: str = "",
    llm_only: bool = False,
    deterministic_only: bool = False,
    history: List[Dict[str, str]] | None = None,
    granularity_applied: str = "detailed",
    ai_provider_access: str = "detailed_allowed",
) -> Dict[str, Any]:
    if not llm_only:
        catalog_payload = _analysis_catalog_dispatch(
            prompt,
            catalog_item_id=catalog_item_id,
            data_dir=data_dir,
            dataset_id=dataset_id,
            assay_id=assay_id,
            analysis_session_id=analysis_session_id,
            user_id=user_id,
            selected_patient_ids=selected_patient_ids,
            compare_selected_patient_ids=compare_selected_patient_ids if compare_mode else "",
            granularity_applied=granularity_applied,
        )
        if catalog_payload is not None:
            return catalog_payload
    if not llm_only and _parse_measure_inventory_request(prompt):
        if compare_mode:
            context = compare_measure_inventory_context(data_dir, selected_patient_ids, compare_selected_patient_ids)
            intent = "analysis_measure_inventory_compare"
        else:
            context = measure_inventory_context(data_dir, selected_patient_ids=selected_patient_ids)
            intent = "analysis_measure_inventory"
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
    if not llm_only and _parse_transcriptomics_medication_request(prompt):
        context = transcriptomics_expression_by_medication_context(
            data_dir,
            selected_patient_ids=selected_patient_ids,
            compare_selected_patient_ids=compare_selected_patient_ids if compare_mode else "",
        )
        return {
            "intent": "analysis_transcriptomics_medication_compare",
            "reply": deterministic_analysis_reply(prompt, context),
            "data": {
                "source": "deterministic",
                "context": context,
                "model": None,
                "base_url": lm_studio_base_url(),
            },
        }
    assay_request = _parse_transcriptomics_expression_request(prompt)
    if not llm_only and assay_request is not None:
        context = transcriptomics_expression_context(
            data_dir,
            assay_request["gene_id"],
            selected_patient_ids=selected_patient_ids,
            compare_selected_patient_ids=compare_selected_patient_ids if compare_mode else "",
        )
        return {
            "intent": "analysis_transcriptomics_expression",
            "reply": deterministic_analysis_reply(prompt, context),
            "data": {
                "source": "deterministic",
                "context": context,
                "model": None,
                "base_url": lm_studio_base_url(),
            },
        }
    survival_request = _parse_survival_request(prompt)
    if not llm_only and survival_request is not None:
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
    if not llm_only and trajectory_request is not None:
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

    if not llm_only and not deterministic_only and ai_provider_access == "detailed_allowed":
        semantic_plan = _analysis_semantic_plan(
            prompt,
            data_dir,
            selected_patient_ids=selected_patient_ids,
            compare_mode=compare_mode,
            compare_selected_patient_ids=compare_selected_patient_ids,
            history=history,
            granularity_applied=granularity_applied,
        )
        if semantic_plan is not None:
            return semantic_plan

    if ai_provider_access == "blocked":
        if llm_only:
            return _analysis_ai_provider_blocked_response()
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
    if deterministic_only:
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

    model = resolve_lm_studio_model(log_kind="pheno_models") if lm_studio_enabled() else None
    if not lm_studio_enabled() or not model:
        if llm_only:
            return _analysis_ai_provider_unavailable_response(
                "LM Studio is disabled or no model is currently loaded."
            )
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

    trimmed_history = history[-4:] if history and granularity_applied == "detailed" and ai_provider_access == "detailed_allowed" else []
    compact_context = _analysis_provider_context_for_llm(
        context,
        granularity_applied=granularity_applied,
        ai_provider_access=ai_provider_access,
    )
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
    if ai_provider_access == "safe_summary":
        prompt_payload["instructions"] = [
            "Act as a clinical/bioinformatics analysis assistant.",
            "Use only the provided provider-safe structural summary context.",
            "Do not infer private clinical facts, diseases, treatments, counts, or patient-level details.",
            "If the request needs clinical context, say that you do not have enough permitted context to answer safely.",
            "Keep the answer concise and explicit about the limitation.",
        ]
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You analyze private clinical cohort summaries. Be precise, restrained, and evidence-based."
                    if ai_provider_access != "safe_summary"
                    else "You may receive only provider-safe structural summary context. Do not infer private clinical details that are not explicitly permitted."
                ),
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
        if llm_only:
            return _analysis_ai_provider_unavailable_response(str(exc))
        return {
            "intent": intent,
            "reply": deterministic_analysis_reply(prompt, context),
            "data": {
                "source": "deterministic",
                "context": context,
                "model": None,
                "base_url": lm_studio_base_url(),
                "llm_error": str(exc),
            },
        }
    if isinstance(response.get("error"), str):
        if llm_only:
            return _analysis_ai_provider_unavailable_response(response["error"])
        return {
            "intent": intent,
            "reply": deterministic_analysis_reply(prompt, context),
            "data": {
                "source": "deterministic",
                "context": context,
                "model": None,
                "base_url": lm_studio_base_url(),
                "llm_error": response["error"],
            },
        }
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        if llm_only:
            return _analysis_ai_provider_unavailable_response(
                "The AI provider returned an unexpected response format."
            )
        return {
            "intent": intent,
            "reply": deterministic_analysis_reply(prompt, context),
            "data": {
                "source": "deterministic",
                "context": context,
                "model": None,
                "base_url": lm_studio_base_url(),
                "llm_error": "LM Studio returned an unexpected response format.",
            },
        }
    message = choices[0].get("message", {})
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        if llm_only:
            return _analysis_ai_provider_unavailable_response(
                "The AI provider returned an empty analysis reply."
            )
        return {
            "intent": intent,
            "reply": deterministic_analysis_reply(prompt, context),
            "data": {
                "source": "deterministic",
                "context": context,
                "model": None,
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


def analysis_llm_reply(
    prompt: str,
    data_dir: str,
    catalog_item_id: str = "",
    dataset_id: str = "",
    assay_id: str = "",
    analysis_session_id: str = "",
    user_id: str = "",
    selected_patient_ids: str = "",
    compare_mode: bool = False,
    compare_selected_patient_ids: str = "",
    llm_only: bool = False,
    deterministic_only: bool = False,
    history: List[Dict[str, str]] | None = None,
    granularity_ceiling: str = "detailed",
    ai_provider_access: str = "detailed_allowed",
) -> Dict[str, Any]:
    normalized_granularity = _normalize_analysis_granularity_ceiling(granularity_ceiling)
    normalized_ai_provider_access = _normalize_analysis_ai_provider_access(ai_provider_access)
    payload = _analysis_llm_reply_impl(
        prompt,
        data_dir,
        catalog_item_id=catalog_item_id,
        dataset_id=dataset_id,
        assay_id=assay_id,
        analysis_session_id=analysis_session_id,
        user_id=user_id,
        selected_patient_ids=selected_patient_ids,
        compare_mode=compare_mode,
        compare_selected_patient_ids=compare_selected_patient_ids,
        llm_only=llm_only,
        deterministic_only=deterministic_only,
        history=history,
        granularity_applied=normalized_granularity,
        ai_provider_access=normalized_ai_provider_access,
    )
    return _analysis_finalize_response(
        payload,
        granularity_applied=normalized_granularity,
        ai_provider_access=normalized_ai_provider_access,
    )
