import re
from typing import Any, Dict, List, Optional

from app.bff import (
    build_patient_navigator,
    ensure_data_dir,
    group_patients,
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


def answer_query(data_dir: str, query: str) -> Dict[str, Any]:
    text = query.strip()
    lowered = text.lower()

    if not text:
        return {
            "query": query,
            "intent": "empty",
            "reply": "Ask a question about medications, diseases, or a patient timeline.",
            "data": {},
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
                "data": medication,
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
                "data": disease,
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
                "data": medication,
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
            "data": cohort,
        }

    if "what medications" in lowered or "list medications" in lowered:
        counts = medication_counts(data_dir)
        meds = [item["medication"] for item in counts[:20]]
        return {
            "query": query,
            "intent": "medication_inventory",
            "reply": "Known medications: %s." % (", ".join(meds) if meds else "none"),
            "data": {"medications": counts},
        }

    if "what diseases" in lowered or "list diseases" in lowered:
        counts = disease_counts(data_dir)
        labels = [item["disease"] for item in counts[:20]]
        return {
            "query": query,
            "intent": "disease_inventory",
            "reply": "Known diseases: %s." % (", ".join(labels) if labels else "none"),
            "data": {"diseases": counts},
        }

    patient_id = _extract_patient_id(text)
    if patient_id is not None:
        navigator = build_patient_navigator(data_dir, patient_id)
        if navigator is None:
            return {
                "query": query,
                "intent": "patient_lookup",
                "reply": "Patient not found: %s." % patient_id,
                "data": {"patient_id": patient_id},
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
            "data": payload,
        }

    return {
        "query": query,
        "intent": "unsupported",
        "reply": (
            "I can answer common questions about medications, diseases, patient summaries, "
            "and visit timelines. Examples: 'How many patients have Prednisolone?', "
            "'Which patients have Crohn Disease?', 'Show patient 107', 'List visits for patient 107'."
        ),
        "data": {},
    }
