from __future__ import annotations

from typing import Any, Dict, List, Optional


def normalize_query_granularity_mode(value: str) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in {"summary", "detailed"}:
        return normalized
    return "detailed"


def normalize_query_granularity_ceiling(value: str) -> str:
    normalized = normalize_query_granularity_mode(value)
    if normalized == "summary":
        return "summary"
    return "detailed"


def normalize_ai_provider_access(value: str) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "use_thread_mode": "detailed_allowed",
        "detailed": "detailed_allowed",
        "summary_only": "safe_summary",
        "restricted": "safe_summary",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized in {"detailed_allowed", "safe_summary", "blocked"}:
        return normalized
    return "detailed_allowed"


def ai_provider_granularity_mode(granularity_mode: str, ai_provider_access: str) -> str:
    normalized_access = normalize_ai_provider_access(ai_provider_access)
    if normalized_access == "safe_summary":
        return "summary"
    return granularity_mode


def ai_provider_context_granularity(granularity_applied: str, ai_provider_access: str) -> str:
    normalized_access = normalize_ai_provider_access(ai_provider_access)
    if normalized_access == "blocked":
        return "blocked"
    if normalized_access == "safe_summary":
        return "safe_summary"
    return granularity_applied


def response_patient_ids(payload: Dict[str, Any]) -> List[str]:
    data = payload.get("data")
    if not isinstance(data, dict):
        return []
    patient_id = str(data.get("patient_id") or "").strip()
    if patient_id:
        return [patient_id]
    patient_ids = data.get("patient_ids")
    if isinstance(patient_ids, list):
        return [str(item).strip() for item in patient_ids if str(item).strip()]
    patients = data.get("patients")
    if isinstance(patients, list):
        found: List[str] = []
        for item in patients:
            if not isinstance(item, dict):
                continue
            patient_id = str(item.get("patient_id") or "").strip()
            if patient_id and patient_id not in found:
                found.append(patient_id)
        return found
    return []


def response_record_ids(payload: Dict[str, Any]) -> List[str]:
    data = payload.get("data")
    if not isinstance(data, dict):
        return []
    for key in ("sample_ids", "original_record_ids"):
        values = data.get(key)
        if isinstance(values, list):
            return [str(item).strip() for item in values if str(item).strip()]
    patients = data.get("patients")
    if isinstance(patients, list):
        found: List[str] = []
        for item in patients:
            if not isinstance(item, dict):
                continue
            values = item.get("original_record_ids")
            if not isinstance(values, list):
                continue
            for record_id in values:
                normalized = str(record_id or "").strip()
                if normalized and normalized not in found:
                    found.append(normalized)
        return found
    return []


def query_action_context(payload: Dict[str, Any]) -> Dict[str, Any]:
    patient_ids = response_patient_ids(payload)
    record_ids = response_record_ids(payload)
    return {
        "patient_ids": patient_ids,
        "record_ids": record_ids,
        "id_type": "sample" if record_ids else ("patient" if patient_ids else ""),
        "analysis_prompt": (
            "Interpret this selected workspace subset and summarize the main clinical and treatment patterns."
            if patient_ids or record_ids
            else ""
        ),
    }


def redact_action_context(action_context: Dict[str, Any], granularity_applied: str) -> Dict[str, Any]:
    if granularity_applied != "summary":
        return action_context
    return {
        "patient_ids": [],
        "record_ids": [],
        "id_type": "",
        "analysis_prompt": "",
    }


def query_available_actions(payload: Dict[str, Any], granularity_applied: str) -> Dict[str, bool]:
    if query_is_count_only(payload):
        return {
            "open_in_analysis": False,
            "save_cohort": False,
            "copy_patient_ids": False,
            "use_in_pheno_ranker": False,
        }
    action_context = query_action_context(payload)
    patient_ids = action_context["patient_ids"]
    record_ids = action_context["record_ids"]
    has_scope = bool(patient_ids or record_ids)
    return {
        "open_in_analysis": has_scope and granularity_applied == "detailed",
        "save_cohort": bool(patient_ids) and granularity_applied == "detailed",
        "copy_patient_ids": bool(patient_ids) and granularity_applied == "detailed",
        "use_in_pheno_ranker": bool(record_ids) and granularity_applied == "detailed",
    }


def query_is_count_only(payload: Dict[str, Any]) -> bool:
    data = payload.get("data")
    if isinstance(data, dict):
        semantic_plan = data.get("semantic_plan")
        if isinstance(semantic_plan, dict) and str(semantic_plan.get("output") or "").strip().lower() == "count":
            return True
        if data.get("count_only") is True:
            return True
    query = str(payload.get("query") or "").strip().lower()
    return bool(
        query.startswith("how many")
        or query.startswith("count ")
        or query.startswith("what is the number of")
        or query.startswith("what's the number of")
    )


def _strip_identifier_fields(value: Any) -> Any:
    identifier_keys = {
        "patient_id",
        "patient_ids",
        "sample_id",
        "sample_ids",
        "original_id",
        "original_record_ids",
        "record_id",
        "record_ids",
        "subject_id",
        "subject_ids",
        "clarid",
        "clar_id",
        "human_id",
        "stub_id",
        "patients",
        "visits",
        "timeline",
        "patient_context",
        "conversation_history",
    }
    if isinstance(value, dict):
        return {
            key: _strip_identifier_fields(item)
            for key, item in value.items()
            if key not in identifier_keys
        }
    if isinstance(value, list):
        return [_strip_identifier_fields(item) for item in value]
    return value


def shape_count_only_response(payload: Dict[str, Any]) -> Dict[str, Any]:
    shaped = dict(payload)
    data = shaped.get("data")
    shaped["data"] = _strip_identifier_fields(data) if isinstance(data, dict) else {}
    shaped["data"].pop("follow_up_suggestions", None)
    shaped["data"].pop("follow_up_suggestion_metadata", None)
    shaped["data"]["count_only"] = True
    shaped["reply"] = shape_summary_reply(
        str(shaped.get("intent") or ""),
        data if isinstance(data, dict) else {},
        "Count completed.",
    )
    return shaped


def patient_count_from_data(data: Dict[str, Any]) -> Optional[int]:
    value = data.get("patient_count")
    if isinstance(value, int):
        return value
    patient_ids = data.get("patient_ids")
    if isinstance(patient_ids, list):
        return len([item for item in patient_ids if str(item).strip()])
    patients = data.get("patients")
    if isinstance(patients, list):
        return len([item for item in patients if isinstance(item, dict)])
    return None


def sample_count_from_data(data: Dict[str, Any]) -> Optional[int]:
    value = data.get("sample_count")
    if isinstance(value, int):
        return value
    sample_ids = data.get("sample_ids")
    if isinstance(sample_ids, list):
        return len([item for item in sample_ids if str(item).strip()])
    return None


def shape_summary_reply(intent: str, data: Dict[str, Any], original_reply: str) -> str:
    if intent == "treatment_data_unavailable":
        return "No treatment records are available for the current selection. This does not establish that no patients take the medication."
    patient_count = patient_count_from_data(data)
    sample_count = sample_count_from_data(data)
    if intent == "patient_inventory" and patient_count is not None:
        noun = "patient" if patient_count == 1 else "patients"
        return "This workspace contains %s %s." % (patient_count, noun)
    if intent == "sample_inventory" and sample_count is not None:
        noun = "sample" if sample_count == 1 else "samples"
        return "This workspace contains %s %s." % (sample_count, noun)
    if intent == "timepoint_inventory" and isinstance(data.get("timepoint_count"), int):
        noun = "timepoint" if data["timepoint_count"] == 1 else "timepoints"
        return "This workspace contains %s %s." % (data["timepoint_count"], noun)
    if patient_count is not None and (
        intent in {
            "medication_cohort",
            "disease_cohort",
            "patient_filter_cohort",
            "patient_medication_count_cohort",
            "patient_visit_count_cohort",
            "patient_sex_cohort",
            "patient_transition_cohort",
            "patient_started_after_cohort",
            "patient_temporal_order_cohort",
            "term_patient_visit_count_cohort",
            "negative_medication_cohort",
            "negative_disease_cohort",
        }
        or intent.endswith("_cohort")
    ):
        noun = "patient" if patient_count == 1 else "patients"
        return "%s %s match this query." % (patient_count, noun)
    if patient_count is not None:
        noun = "patient" if patient_count == 1 else "patients"
        return "%s %s match this query." % (patient_count, noun)
    if sample_count is not None:
        noun = "sample" if sample_count == 1 else "samples"
        return "%s %s match this query." % (sample_count, noun)
    if intent in {"llm_error", "llm_unavailable"}:
        return "The model provider could not complete this query. Check its connection and loaded model, then retry."
    if intent == "unsupported":
        return "This query could not be resolved with the available data and permissions. Try a specific disease or medication shown in Dashboard."
    return "No verified count was produced for this query. Try listing the matching patients or asking about a specific medication shown in Dashboard."


def shape_summary_response(payload: Dict[str, Any]) -> Dict[str, Any]:
    intent = str(payload.get("intent") or "")
    data = payload.get("data")
    if not isinstance(data, dict):
        return payload

    if intent in {"patient_summary", "patient_timeline", "patient_visits"}:
        return {
            "query": payload.get("query", ""),
            "intent": intent,
            "reply": "Detailed patient-level answers are not available in Summary mode.",
            "data": {
                "follow_up_suggestions": [
                    "How many patients are in this workspace?",
                    "Which patients have more than 1 medication?",
                ],
            },
        }

    summary_data = dict(data)
    patient_count = patient_count_from_data(summary_data)
    sample_count = sample_count_from_data(summary_data)
    if patient_count is not None:
        summary_data["patient_count"] = patient_count
    if sample_count is not None:
        summary_data["sample_count"] = sample_count

    for key in (
        "patients",
        "patient_ids",
        "sample_ids",
        "original_record_ids",
        "patient_context",
        "conversation_history",
        "timeline",
        "visits",
    ):
        summary_data.pop(key, None)
    summary_data = _strip_identifier_fields(summary_data)
    summary_data.pop("follow_up_suggestions", None)
    summary_data.pop("follow_up_suggestion_metadata", None)

    shaped = dict(payload)
    shaped["reply"] = shape_summary_reply(intent, data, str(payload.get("reply") or ""))
    shaped["data"] = summary_data
    return shaped


def finalize_query_response(
    payload: Dict[str, Any],
    granularity_requested: str,
    granularity_applied: str,
    ai_provider_access: str,
) -> Dict[str, Any]:
    count_only = query_is_count_only(payload)
    action_context = redact_action_context(query_action_context(payload), granularity_applied)
    if count_only:
        action_context = {"patient_ids": [], "record_ids": [], "id_type": "", "analysis_prompt": ""}
    available_actions = query_available_actions(payload, granularity_applied)
    finalized = shape_summary_response(payload) if granularity_applied == "summary" else dict(payload)
    if count_only:
        finalized = shape_count_only_response(finalized)
    data = finalized.get("data")
    finalized_data: Dict[str, Any] = dict(data) if isinstance(data, dict) else {}
    finalized_data["granularity_requested"] = granularity_requested
    finalized_data["granularity_applied"] = granularity_applied
    finalized_data["external_llm_allowed"] = normalize_ai_provider_access(ai_provider_access) != "blocked"
    finalized_data["ai_provider_access"] = normalize_ai_provider_access(ai_provider_access)
    finalized_data["ai_provider_context_granularity"] = ai_provider_context_granularity(
        granularity_applied,
        ai_provider_access,
    )
    finalized_data["available_actions"] = available_actions
    finalized["data"] = finalized_data
    finalized["action_context"] = action_context
    return finalized
