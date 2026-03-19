import json
import os
import re
from typing import Any, Dict, List, Optional
from urllib import error, request

from app.bff import (
    build_patient_navigator,
    dashboard_summary,
    ensure_data_dir,
    group_patients,
    list_patient_summaries,
    medication_cohort,
    medication_counts,
    normalize_value,
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
        for visit in bundle.context.visits:
            labels = _extract_disease_labels(visit.provenance.raw_bff)
            visit_matches = [label for label in labels if query in label.lower()]
            if not visit_matches:
                continue
            for label in visit_matches:
                if label not in matched_labels:
                    matched_labels.append(label)
            matched_visits.append(
                {
                    "visit_id": visit.visit_id,
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
                    "matched_diseases": matched_labels,
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


def _extract_patient_id(text: str) -> Optional[str]:
    match = re.search(r"\bpatient\s+([A-Za-z0-9:_-]+)\b", text, flags=re.IGNORECASE)
    if match:
        return match.group(1)
    return None


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


def _lm_studio_enabled() -> bool:
    value = os.getenv("LM_STUDIO_ENABLED", "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _lm_studio_base_url() -> str:
    return os.getenv("LM_STUDIO_BASE_URL", "http://192.168.1.41:1234/v1").rstrip("/")


def _lm_studio_timeout() -> float:
    raw = os.getenv("LM_STUDIO_TIMEOUT", "30").strip()
    try:
        return float(raw)
    except ValueError:
        return 30.0


def _lm_studio_api_key() -> str:
    return os.getenv("LM_STUDIO_API_KEY", "lm-studio")


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
            "How many patients are in this cohort?",
            "What diseases appear most often?",
            "Show patient 107",
        ]

    lowered = text.lower()
    if "patient" in lowered:
        return [
            f"List visits for {text}",
            f"What treatments are recorded for {text}?",
            f"Summarize the key evidence for {text}.",
        ]
    if any(keyword in lowered for keyword in ("disease", "diagnosis", "crohn", "colitis")):
        return [
            f"How many patients have {text}?",
            f"Which patients have {text}?",
            f"What treatments are associated with {text}?",
        ]
    if any(keyword in lowered for keyword in ("medication", "drug", "treatment", "prednisolone", "infliximab")):
        return [
            f"How many patients have {text}?",
            f"Which patients have {text}?",
            f"Show the visits mentioning {text}.",
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


def _http_json(url: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {_lm_studio_api_key()}",
    }
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = request.Request(url, data=body, headers=headers, method="POST" if body is not None else "GET")
    with request.urlopen(req, timeout=_lm_studio_timeout()) as response:
        return json.loads(response.read().decode("utf-8"))


def _resolve_lm_studio_model() -> Optional[str]:
    configured = os.getenv("LM_STUDIO_MODEL", "").strip()
    if configured:
        return configured
    try:
        payload = _http_json(f"{_lm_studio_base_url()}/models")
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


def _lm_studio_context(data_dir: str, query: str, history: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
    summaries = list_patient_summaries(data_dir)
    patient_id = _extract_patient_id(query)
    context: Dict[str, Any] = {
        "question": query,
        "dataset_overview": dashboard_summary(data_dir)["totals"],
        "top_medications": [item["medication"] for item in medication_counts(data_dir)[:10]],
        "top_diseases": [item["disease"] for item in disease_counts(data_dir)[:10]],
        "patient_summaries": [
            {
                "patient_id": summary.patient_id,
                "visit_count": summary.visit_count,
                "sex": summary.sex,
                "first_event_date": summary.first_event_date,
                "last_event_date": summary.last_event_date,
                "disease_count": summary.evidence.diseases.count,
                "treatment_count": summary.evidence.treatments.count,
            }
            for summary in summaries[: _lm_studio_max_patient_summaries()]
        ],
    }
    if history:
        max_history_turns = _lm_studio_max_history_turns()
        context["conversation_history"] = history[-max_history_turns:] if max_history_turns else []
    if patient_id is not None and _lm_studio_include_patient_navigator():
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


def _lm_studio_reply(
    data_dir: str,
    query: str,
    history: Optional[List[Dict[str, str]]] = None,
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

    context = _lm_studio_context(data_dir, query, history=history)
    payload = {
        "model": model,
        "temperature": 0.1,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You answer questions about a patient navigation dataset. "
                    "Use only the supplied JSON context. "
                    "If the answer is not supported by the context, say that clearly. "
                    "Prefer short answers. "
                    "Be concise and factual."
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
        response = _http_json(f"{_lm_studio_base_url()}/chat/completions", payload)
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

    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        return {
            "query": query,
            "intent": "llm_error",
            "reply": "LM Studio returned an unexpected response format.",
            "data": {
                "provider": "lm_studio",
                "base_url": _lm_studio_base_url(),
                "response": response,
            },
        }

    message = choices[0].get("message", {})
    content = message.get("content")
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str):
                parts.append(item["text"])
        content = "\n".join(parts).strip()

    if not isinstance(content, str) or not content.strip():
        return {
            "query": query,
            "intent": "llm_error",
            "reply": "LM Studio returned an empty answer.",
            "data": {
                "provider": "lm_studio",
                "base_url": _lm_studio_base_url(),
                "response": response,
            },
        }

    return {
        "query": query,
        "intent": "llm_fallback",
        "reply": content.strip(),
        "data": {
            "provider": "lm_studio",
            "model": model,
            "base_url": _lm_studio_base_url(),
            "context": context,
            "follow_up_suggestions": _follow_up_suggestions(query),
        },
    }


def answer_query(
    data_dir: str,
    query: str,
    history: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    text = query.strip()
    lowered = text.lower()

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

    if lowered.startswith("how many patients have ") or lowered.startswith("which patients have "):
        term = re.sub(r"^(how many patients have|which patients have)\s+", "", text, flags=re.IGNORECASE).strip(" ?.")
        medication = medication_cohort(data_dir, term)
        disease = disease_cohort(data_dir, term)
        if medication["patient_count"] > 0 and disease["patient_count"] == 0:
            if lowered.startswith("how many"):
                reply = "%s patients match medication query '%s'." % (medication["patient_count"], term)
            else:
                patient_ids = [item["patient_id"] for item in medication["patients"]]
                reply = "Patients matching medication query '%s': %s." % (
                    term,
                    ", ".join(patient_ids) if patient_ids else "none",
                )
            return {
                "query": query,
                "intent": "medication_cohort",
                "reply": reply,
                "data": {
                    **medication,
                    "follow_up_suggestions": _follow_up_suggestions(term),
                },
            }

        disease = disease_cohort(data_dir, term)
        if disease["patient_count"] > 0:
            if lowered.startswith("how many"):
                reply = "%s patients match disease query '%s'." % (disease["patient_count"], term)
            else:
                patient_ids = [item["patient_id"] for item in disease["patients"]]
                reply = "Patients matching disease query '%s': %s." % (
                    term,
                    ", ".join(patient_ids) if patient_ids else "none",
                )
            return {
                "query": query,
                "intent": "disease_cohort",
                "reply": reply,
                "data": {
                    **disease,
                    "follow_up_suggestions": _follow_up_suggestions(term),
                },
            }

        if medication["patient_count"] > 0:
            if lowered.startswith("how many"):
                reply = "%s patients match medication query '%s'." % (medication["patient_count"], term)
            else:
                patient_ids = [item["patient_id"] for item in medication["patients"]]
                reply = "Patients matching medication query '%s': %s." % (
                    term,
                    ", ".join(patient_ids) if patient_ids else "none",
                )
            return {
                "query": query,
                "intent": "medication_cohort",
                "reply": reply,
                "data": {
                    **medication,
                    "follow_up_suggestions": _follow_up_suggestions(term),
                },
            }

    medication_match = re.search(
        r"(?:medication|drug|treatment)\s+(.+)",
        lowered,
    )
    if medication_match:
        medication = text[medication_match.start(1):].strip(" ?.")
        cohort = medication_cohort(data_dir, medication)
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
        counts = medication_counts(data_dir)
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
        counts = disease_counts(data_dir)
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
                        "How many patients are in this cohort?",
                    ],
                },
            }
        payload = navigator.model_dump()
        if "visit" in lowered or "timeline" in lowered:
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
                    "List visits for patient %s" % patient_id,
                    "What treatments are recorded for patient %s?" % patient_id,
                    "What diseases are recorded for patient %s?" % patient_id,
                ],
            },
        }

    fallback = _lm_studio_reply(data_dir, query, history=history)
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
