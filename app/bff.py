import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from app.models import (
    EvidenceBucket,
    EvidenceFragment,
    EvidenceInventory,
    PatientWorkspaceVisit,
    PatientContext,
    PatientWorkspace,
    PatientSummary,
    RecordProvenance,
    VisitContext,
)


PLACEHOLDER_VALUES = {
    "",
    "1900-01-01",
    "1900-01-01T00:00:00",
    "1900-01-01T00:00:00Z",
    "P999Y",
    "-1",
    -1,
    "unknown",
    "Unknown",
    "UNK",
    "N/A",
    "n/a",
    "NA",
    "None",
    "null",
    None,
}

PATIENT_ID_KEYS = (
    "patient_id",
    "patientId",
    "subject_id",
    "subjectId",
    "individual_id",
    "individualId",
    "id",
)
VISIT_ID_KEYS = ("visit_id", "visitId", "event_id", "eventId", "encounter_id", "encounterId")
DATE_KEYS = ("event_date", "visit_date", "date_of_visit", "index_date", "date")
SEX_KEYS = ("sex", "sex_at_birth", "gender")
DOB_KEYS = ("date_of_birth", "birth_date", "birthDate")
STATUS_KEYS = ("vital_status", "status")
AGE_KEYS = ("age_at_visit", "age", "age_iso8601")
EVENT_TYPE_KEYS = ("event_type", "visit_type", "record_type", "type")
DISEASE_KEYS = ("disease", "disease_label", "primary_diagnosis", "condition")
DIAGNOSIS_KEYS = ("diagnosis", "diagnosis_text", "diagnosis_code")
BIOSAMPLE_KEYS = ("biosample_id", "sample_id", "biosampleId")
PATIENT_CONTAINER_KEYS = ("patient", "subject", "individual")


@dataclass
class PatientBundle:
    summary: PatientSummary
    context: PatientContext


def normalize_value(value: Any) -> Any:
    if isinstance(value, str):
        trimmed = value.strip()
        if trimmed in PLACEHOLDER_VALUES:
            return None
        return trimmed
    if isinstance(value, list):
        return [item for item in (normalize_value(item) for item in value) if item is not None]
    if isinstance(value, dict):
        return {
            key: normalized
            for key, normalized in ((key, normalize_value(val)) for key, val in value.items())
            if normalized is not None
        }
    if value in PLACEHOLDER_VALUES:
        return None
    return value


def deep_get(source: Dict[str, Any], keys: Sequence[str]) -> Optional[Any]:
    for key in keys:
        if key in source:
            normalized = normalize_value(source[key])
            if normalized is not None:
                return normalized
    return None


def nested_get(source: Dict[str, Any], path: Sequence[str]) -> Optional[Any]:
    value: Any = source
    for key in path:
        if not isinstance(value, dict) or key not in value:
            return None
        value = value[key]
    return normalize_value(value)


def extract_event_date(record: Dict[str, Any]) -> Optional[Any]:
    return select_first([
        nested_get(record, ("info", "event_date")),
        deep_get(record, DATE_KEYS),
    ])


def get_patient_node(record: Dict[str, Any]) -> Dict[str, Any]:
    for key in PATIENT_CONTAINER_KEYS:
        value = record.get(key)
        if isinstance(value, dict):
            return value
    return {}


def select_first(values: Sequence[Optional[Any]]) -> Optional[Any]:
    for value in values:
        normalized = normalize_value(value)
        if normalized is not None:
            return normalized
    return None


def first_list_item(record: Dict[str, Any], key: str) -> Dict[str, Any]:
    value = record.get(key)
    if isinstance(value, list) and value and isinstance(value[0], dict):
        return value[0]
    return {}


def split_record_id(record: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    if record.get('_cohortome_source'):
        source_id = record['_cohortome_source'].get('sample_id', '')
        return record.get('patient_id'), source_id.split(':', 1)[-1]
    record_id = normalize_value(record.get("id"))
    if not isinstance(record_id, str):
        return None, None
    if ":" in record_id:
        patient_id, visit_id = record_id.split(":", 1)
        return patient_id, visit_id
    return record_id, record_id


def extract_patient_id(record: Dict[str, Any]) -> Optional[str]:
    if record.get('_cohortome_source'):
        return record.get('patient_id')
    patient_node = get_patient_node(record)
    split_patient_id, _ = split_record_id(record)
    patient_id = select_first(
        [
            split_patient_id,
            deep_get(record, PATIENT_ID_KEYS[:-1]),
            deep_get(patient_node, PATIENT_ID_KEYS),
        ]
    )
    if patient_id is None:
        return None
    return str(patient_id)


def extract_visit_id(record: Dict[str, Any], fallback: str) -> str:
    _, split_visit_id = split_record_id(record)
    visit_id = select_first(
        [
            nested_get(record, ("info", "visit_id")),
            deep_get(record, VISIT_ID_KEYS),
            split_visit_id,
            nested_get(first_list_item(record, "diseases"), ("_visit", "id")),
            nested_get(first_list_item(record, "measures"), ("_visit", "id")),
            nested_get(first_list_item(record, "treatments"), ("_visit", "id")),
            nested_get(first_list_item(record, "phenotypicFeatures"), ("_visit", "id")),
            nested_get(first_list_item(record, "interventionsOrProcedures"), ("_visit", "id")),
            nested_get(first_list_item(record, "exposures"), ("_visit", "id")),
        ]
    )
    if visit_id is None:
        return fallback
    return str(visit_id)


def extract_event_type(record: Dict[str, Any]) -> Optional[str]:
    _, split_visit_id = split_record_id(record)
    return select_first(
        [
            deep_get(record, EVENT_TYPE_KEYS),
            nested_get(first_list_item(record, "diseases"), ("_visit", "id")),
            nested_get(first_list_item(record, "measures"), ("_visit", "id")),
            nested_get(first_list_item(record, "treatments"), ("_visit", "id")),
            split_visit_id,
        ]
    )


def extract_sex(record: Dict[str, Any]) -> Optional[str]:
    patient_node = get_patient_node(record)
    return select_first(
        [
            nested_get(record, ("sex", "label")),
            deep_get(record, SEX_KEYS),
            nested_get(patient_node, ("sex", "label")),
            deep_get(patient_node, SEX_KEYS),
        ]
    )


def extract_disease_label(record: Dict[str, Any]) -> Optional[str]:
    disease = first_list_item(record, "diseases")
    return select_first(
        [
            nested_get(disease, ("diseaseCode", "label")),
            nested_get(disease, ("diseaseCode", "id")),
            deep_get(record, DISEASE_KEYS),
        ]
    )


def extract_diagnosis(record: Dict[str, Any]) -> Optional[str]:
    return select_first(
        [
            deep_get(record, DIAGNOSIS_KEYS),
            extract_disease_label(record),
        ]
    )


def summarize_collections(record: Dict[str, Any]) -> Dict[str, Any]:
    summary: Dict[str, Any] = {}
    for key in (
        "diseases",
        "phenotypicFeatures",
        "measures",
        "treatments",
        "interventionsOrProcedures",
        "exposures",
    ):
        value = record.get(key)
        if isinstance(value, list):
            summary["%s_count" % key] = len(value)
    ethnicity = nested_get(record, ("ethnicity", "label"))
    if ethnicity is not None:
        summary["ethnicity"] = ethnicity
    return summary


def bucket_examples(records: Any, paths: Sequence[Sequence[str]], limit: int = 3) -> List[str]:
    examples: List[str] = []
    if not isinstance(records, list):
        return examples
    for item in records:
        if not isinstance(item, dict):
            continue
        value = None
        for path in paths:
            value = nested_get(item, path)
            if value is not None:
                break
        if value is None:
            continue
        text = str(value)
        if text not in examples:
            examples.append(text)
        if len(examples) >= limit:
            break
    return examples


def build_evidence_inventory(record: Dict[str, Any]) -> EvidenceInventory:
    diseases = record.get("diseases")
    phenotypes = record.get("phenotypicFeatures")
    measures = record.get("measures")
    treatments = record.get("treatments")
    procedures = record.get("interventionsOrProcedures")
    exposures = record.get("exposures")

    return EvidenceInventory(
        diseases=EvidenceBucket(
            count=len(diseases) if isinstance(diseases, list) else 0,
            examples=bucket_examples(diseases, (("diseaseCode", "label"), ("diseaseCode", "id"))),
        ),
        phenotypic_features=EvidenceBucket(
            count=len(phenotypes) if isinstance(phenotypes, list) else 0,
            examples=bucket_examples(phenotypes, (("featureType", "label"), ("notes",))),
        ),
        measures=EvidenceBucket(
            count=len(measures) if isinstance(measures, list) else 0,
            examples=bucket_examples(measures, (("assayCode", "label"), ("notes",))),
        ),
        treatments=EvidenceBucket(
            count=len(treatments) if isinstance(treatments, list) else 0,
            examples=bucket_examples(treatments, (("treatmentCode", "label"), ("_info", "drug_name"))),
        ),
        procedures=EvidenceBucket(
            count=len(procedures) if isinstance(procedures, list) else 0,
            examples=bucket_examples(procedures, (("procedureCode", "label"), ("bodySite", "label"))),
        ),
        exposures=EvidenceBucket(
            count=len(exposures) if isinstance(exposures, list) else 0,
            examples=bucket_examples(exposures, (("exposureCode", "label"), ("unit", "label"), ("_info",))),
        ),
    )


def label_from_item(item: Dict[str, Any], paths: Sequence[Sequence[str]], fallback: str) -> str:
    for path in paths:
        value = nested_get(item, path)
        if value is not None:
            return str(value)
    return fallback


def fragment_snippet(item: Dict[str, Any]) -> Dict[str, Any]:
    normalized = normalize_value(item)
    return normalized if isinstance(normalized, dict) else {}


def build_fragments_for_category(
    record: Dict[str, Any],
    visit: VisitContext,
    provenance: RecordProvenance,
    category: str,
    record_key: str,
    label_paths: Sequence[Sequence[str]],
    limit: int = 2,
) -> List[EvidenceFragment]:
    fragments: List[EvidenceFragment] = []
    items = record.get(record_key)
    if not isinstance(items, list):
        return fragments

    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        fragments.append(
            EvidenceFragment(
                category=category,
                label=label_from_item(item, label_paths, fallback="%s_%s" % (category, index)),
                visit_id=visit.visit_id,
                event_type=visit.event_type,
                event_date=visit.event_date,
                source_file=provenance.source_file,
                record_index=provenance.record_index,
                path="%s[%s]" % (record_key, index),
                snippet=fragment_snippet(item),
            )
        )
        if len(fragments) >= limit:
            break

    return fragments


def build_visit_fragments(record: Dict[str, Any], visit: VisitContext) -> List[EvidenceFragment]:
    provenance = visit.provenance
    fragments: List[EvidenceFragment] = []
    fragments.extend(
        build_fragments_for_category(
            record,
            visit,
            provenance,
            category="disease",
            record_key="diseases",
            label_paths=(("diseaseCode", "label"), ("diseaseCode", "id")),
        )
    )
    fragments.extend(
        build_fragments_for_category(
            record,
            visit,
            provenance,
            category="measure",
            record_key="measures",
            label_paths=(("assayCode", "label"), ("notes",)),
        )
    )
    fragments.extend(
        build_fragments_for_category(
            record,
            visit,
            provenance,
            category="treatment",
            record_key="treatments",
            label_paths=(("treatmentCode", "label"), ("_info", "drug_name")),
        )
    )
    fragments.extend(
        build_fragments_for_category(
            record,
            visit,
            provenance,
            category="procedure",
            record_key="interventionsOrProcedures",
            label_paths=(("procedureCode", "label"), ("bodySite", "label")),
        )
    )
    fragments.extend(
        build_fragments_for_category(
            record,
            visit,
            provenance,
            category="exposure",
            record_key="exposures",
            label_paths=(("exposureCode", "label"), ("unit", "label"), ("_info",)),
        )
    )
    fragments.extend(
        build_fragments_for_category(
            record,
            visit,
            provenance,
            category="phenotype",
            record_key="phenotypicFeatures",
            label_paths=(("featureType", "label"), ("notes",)),
        )
    )
    return fragments


def merge_bucket(target: EvidenceBucket, source: EvidenceBucket, limit: int = 5) -> EvidenceBucket:
    merged = EvidenceBucket(
        count=target.count + source.count,
        examples=list(target.examples),
    )
    for example in source.examples:
        if example not in merged.examples:
            merged.examples.append(example)
        if len(merged.examples) >= limit:
            break
    return merged


def merge_evidence(target: EvidenceInventory, source: EvidenceInventory) -> EvidenceInventory:
    return EvidenceInventory(
        diseases=merge_bucket(target.diseases, source.diseases),
        phenotypic_features=merge_bucket(target.phenotypic_features, source.phenotypic_features),
        measures=merge_bucket(target.measures, source.measures),
        treatments=merge_bucket(target.treatments, source.treatments),
        procedures=merge_bucket(target.procedures, source.procedures),
        exposures=merge_bucket(target.exposures, source.exposures),
    )


def read_bff_records(data_dir: Path) -> Iterable[Tuple[Path, int, Dict[str, Any]]]:
    # Source files stay unchanged. A merged workspace gives every record a
    # dataset-qualified execution identity before any grouping/filtering occurs.
    from app.identities import identity_key
    manifest_path = data_dir.parent / 'manifest.json'
    source_files = {}
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        if len(manifest.get('dataset_ids') or []) > 1:
            source_files = {item['target']: item['dataset_id'] for item in manifest.get('clinical_files', [])}
    for path in sorted(data_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            records = payload
        elif isinstance(payload, dict):
            records = [payload]
        else:
            continue

        for index, record in enumerate(records):
            if isinstance(record, dict):
                # This field is reserved for runtime provenance, never trusted
                # when supplied by a source file.
                record = {key: value for key, value in record.items() if key != '_cohortome_source'}
                dataset = source_files.get(path.name)
                if dataset:
                    pid, sid = extract_patient_id(record), str(normalize_value(record.get('id')) or '')
                    record = dict(record)
                    record['_cohortome_source'] = dict(dataset_id=dataset, patient_id=pid, sample_id=sid)
                    if pid:
                        record['patient_id'] = identity_key(dataset, 'patient', pid)
                    if sid:
                        record['id'] = identity_key(dataset, 'sample', sid)
                yield path, index, record


def relative_study_days(metadata):
    """Read explicit study offsets only; never derive them from visit labels."""
    import math
    for key, factor in (("days_from_baseline", 1), ("week_from_baseline", 7)):
        value = metadata.get(key)
        if value is None or isinstance(value, bool) or str(value).strip() == "":
            continue
        try:
            days = float(value) * factor
        except (ValueError, TypeError):
            continue
        if math.isfinite(days):
            return days
    return None


def build_visit_context(path: Path, index: int, record: Dict[str, Any], patient_id: str) -> VisitContext:
    patient_node = get_patient_node(record)
    normalized_record = normalize_value(record) or {}

    notes = dict(normalized_record)
    for removable in list(VISIT_ID_KEYS) + list(PATIENT_ID_KEYS):
        notes.pop(removable, None)
    notes.pop("info", None)
    notes.update(summarize_collections(record))

    provenance = RecordProvenance(
        source_file=str(path),
        record_index=index,
        raw_bff=record,
    )
    evidence = build_evidence_inventory(record)

    return VisitContext(
        visit_id=extract_visit_id(record, fallback=f"{patient_id}-visit-{index}"),
        patient_id=patient_id,
        event_date=extract_event_date(record),
        event_type=extract_event_type(record),
        age_at_visit=deep_get(record, AGE_KEYS) or deep_get(patient_node, AGE_KEYS),
        sex=extract_sex(record),
        disease_label=extract_disease_label(record),
        diagnosis=extract_diagnosis(record),
        biosample_id=deep_get(record, BIOSAMPLE_KEYS),
        evidence=evidence,
        notes=notes,
        provenance=provenance,
    )


def _pick_patient_field(current: Optional[str], candidate: Optional[Any]) -> Optional[str]:
    normalized = normalize_value(candidate)
    if normalized is None:
        return current
    return str(normalized) if current is None else current


def group_patients(data_dir: Path) -> Dict[str, PatientBundle]:
    bundles: Dict[str, PatientBundle] = {}

    for path, index, record in read_bff_records(data_dir):
        patient_id = extract_patient_id(record)
        if patient_id is None:
            continue

        patient_node = get_patient_node(record)
        visit = build_visit_context(path, index, record, patient_id)
        bundle = bundles.get(patient_id)

        if bundle is None:
            bundle = PatientBundle(
                summary=PatientSummary(patient_id=patient_id, visit_count=0),
                context=PatientContext(patient_id=patient_id),
            )
            bundles[patient_id] = bundle

        bundle.context.sex = _pick_patient_field(
            bundle.context.sex,
            extract_sex(record),
        )
        bundle.context.date_of_birth = _pick_patient_field(
            bundle.context.date_of_birth,
            deep_get(patient_node, DOB_KEYS)
            or deep_get(record, DOB_KEYS)
            or nested_get(record, ("info", "phenopacket", "dateOfBirth")),
        )
        bundle.context.vital_status = _pick_patient_field(
            bundle.context.vital_status,
            deep_get(patient_node, STATUS_KEYS) or deep_get(record, STATUS_KEYS),
        )
        bundle.context.age_at_first_visit = _pick_patient_field(
            bundle.context.age_at_first_visit,
            visit.age_at_visit,
        )
        bundle.context.evidence = merge_evidence(bundle.context.evidence, visit.evidence)

        patient_notes = normalize_value(patient_node)
        if not isinstance(patient_notes, dict):
            patient_notes = {}
        ethnicity = nested_get(record, ("ethnicity", "label"))
        if ethnicity is not None and "ethnicity" not in patient_notes:
            patient_notes["ethnicity"] = ethnicity
        if isinstance(patient_notes, dict):
            for key, value in patient_notes.items():
                if key not in bundle.context.patient_notes and value is not None:
                    bundle.context.patient_notes[key] = value

        bundle.context.visits.append(visit)
        source_file = str(path)
        if source_file not in bundle.context.source_files:
            bundle.context.source_files.append(source_file)

    for bundle in bundles.values():
        bundle.context.visits.sort(key=lambda visit: (visit.event_date or "", visit.visit_id))
        summary = summarize_patient(bundle.context)
        bundle.summary = summary

    return bundles


def summarize_patient(patient: PatientContext) -> PatientSummary:
    dates = [visit.event_date for visit in patient.visits if visit.event_date]
    return PatientSummary(
        patient_id=patient.patient_id,
        sex=patient.sex,
        date_of_birth=patient.date_of_birth,
        vital_status=patient.vital_status,
        visit_count=len(patient.visits),
        first_event_date=min(dates) if dates else None,
        last_event_date=max(dates) if dates else None,
        evidence=patient.evidence,
        source_files=list(patient.source_files),
    )


def resolve_project_data_dir(data_dir: str) -> Path:
    path = Path(data_dir).expanduser().resolve()
    if not path.exists() or not path.is_dir():
        raise FileNotFoundError(f"Data directory does not exist: {path}")
    return path


def ensure_data_dir(data_dir: str) -> Path:
    path = resolve_project_data_dir(data_dir)
    clinical_dir = path / "clinical"
    if clinical_dir.exists() and clinical_dir.is_dir():
        return clinical_dir.resolve()
    if any(path.glob("*.json")):
        return path
    raise FileNotFoundError(
        f"Clinical data directory does not exist under: {path}. Expected JSON files directly in the folder or under {clinical_dir}."
    )


def list_patient_summaries(data_dir: str) -> List[PatientSummary]:
    resolved_dir = ensure_data_dir(data_dir)
    bundles = group_patients(resolved_dir)
    return sorted(
        (bundle.summary for bundle in bundles.values()),
        key=lambda item: item.patient_id,
    )


def get_patient_context(data_dir: str, patient_id: str) -> Optional[PatientContext]:
    resolved_dir = ensure_data_dir(data_dir)
    bundles = group_patients(resolved_dir)
    bundle = bundles.get(patient_id)
    if bundle is None:
        return None
    return bundle.context


def build_patient_workspace(data_dir: str, patient_id: str) -> Optional[PatientWorkspace]:
    patient = get_patient_context(data_dir, patient_id)
    if patient is None:
        return None

    workspace_visits: List[PatientWorkspaceVisit] = []
    key_fragments: List[EvidenceFragment] = []

    for visit in patient.visits:
        record = visit.provenance.raw_bff
        visit_fragments = build_visit_fragments(record, visit)
        workspace_visits.append(
            PatientWorkspaceVisit(
                visit_id=visit.visit_id,
                event_type=visit.event_type,
                event_date=visit.event_date,
                diagnosis=visit.diagnosis,
                evidence=visit.evidence,
                key_fragments=visit_fragments,
                provenance=visit.provenance,
            )
        )
        for fragment in visit_fragments:
            if len(key_fragments) >= 12:
                break
            key_fragments.append(fragment)

    summary = summarize_patient(patient)
    patient_context = {
        "sex": patient.sex,
        "date_of_birth": patient.date_of_birth,
        "age_at_first_visit": patient.age_at_first_visit,
        "vital_status": patient.vital_status,
        "patient_notes": patient.patient_notes,
        "source_files": patient.source_files,
    }

    return PatientWorkspace(
        patient_id=patient.patient_id,
        summary=summary,
        patient_context=patient_context,
        evidence=patient.evidence,
        key_fragments=key_fragments,
        visits=workspace_visits,
    )


def extract_treatment_labels(record: Dict[str, Any]) -> List[str]:
    treatments = record.get("treatments")
    labels = bucket_examples(treatments, (("treatmentCode", "label"), ("_info", "drug_name")), limit=100)
    return sorted(labels)


def medication_cohort(data_dir: str, medication_query: str) -> Dict[str, Any]:
    resolved_dir = ensure_data_dir(data_dir)
    bundles = group_patients(resolved_dir)
    query = medication_query.strip().lower()
    matches: List[Dict[str, Any]] = []

    for patient_id, bundle in sorted(bundles.items()):
        matched_visits: List[Dict[str, Any]] = []
        matched_labels: List[str] = []
        original_record_ids: List[str] = []
        for visit in bundle.context.visits:
            labels = extract_treatment_labels(visit.provenance.raw_bff)
            visit_matches = [label for label in labels if query in label.lower()]
            if not visit_matches:
                continue
            original_id = normalize_value(visit.provenance.raw_bff.get("id"))
            if isinstance(original_id, str) and original_id not in original_record_ids:
                original_record_ids.append(original_id)
            for label in visit_matches:
                if label not in matched_labels:
                    matched_labels.append(label)
            matched_visits.append(
                {
                    "visit_id": visit.visit_id,
                    "original_id": str(original_id) if isinstance(original_id, str) else None,
                    "event_type": visit.event_type,
                    "event_date": visit.event_date,
                    "matched_medications": visit_matches,
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
                    "matched_medications": matched_labels,
                    "original_record_ids": original_record_ids,
                    "visits": matched_visits,
                }
            )

    return {
        "query": medication_query,
        "match_type": "case-insensitive substring",
        "patient_count": len(matches),
        "patients": matches,
    }


def medication_counts(data_dir: str) -> List[Dict[str, Any]]:
    resolved_dir = ensure_data_dir(data_dir)
    bundles = group_patients(resolved_dir)
    counts: Dict[str, Dict[str, Any]] = {}

    for patient_id, bundle in bundles.items():
        seen_for_patient = set()
        for visit in bundle.context.visits:
            for label in extract_treatment_labels(visit.provenance.raw_bff):
                entry = counts.setdefault(
                    label,
                    {
                        "medication": label,
                        "patient_count": 0,
                        "patients": [],
                    },
                )
                if label in seen_for_patient:
                    continue
                seen_for_patient.add(label)
                entry["patient_count"] += 1
                entry["patients"].append(patient_id)

    return sorted(counts.values(), key=lambda item: (-item["patient_count"], item["medication"]))


def dashboard_summary(data_dir: str) -> Dict[str, Any]:
    resolved_dir = ensure_data_dir(data_dir)
    bundles = group_patients(resolved_dir)
    summaries = sorted((bundle.summary for bundle in bundles.values()), key=lambda item: item.patient_id)
    meds = medication_counts(data_dir)[:8]
    diseases = disease_counts_local(bundles)[:8]
    disease_medication_matrix = disease_medication_matrix_local(bundles, diseases, meds)

    sex_counts: Dict[str, int] = {}
    visit_distribution: Dict[str, int] = {}
    timeline_points: List[Dict[str, Any]] = []
    total_visits = 0

    evidence_domains = (
        ("diseases", "Disease"),
        ("treatments", "Treatment"),
        ("phenotypic_features", "Phenotype"),
        ("measures", "Measure"),
        ("procedures", "Procedure"),
        ("exposures", "Exposure"),
    )

    for summary in summaries:
        sex = summary.sex or "Unknown"
        sex_counts[sex] = sex_counts.get(sex, 0) + 1

        visits = summary.visit_count
        total_visits += visits
        bucket = "1" if visits == 1 else "2-4" if visits <= 4 else "5+"
        visit_distribution[bucket] = visit_distribution.get(bucket, 0) + 1

        bundle = bundles.get(summary.patient_id)
        timeline_events: List[Dict[str, Any]] = []
        if bundle is not None:
            for visit in sorted(bundle.context.visits, key=lambda item: (item.event_date or "", item.visit_id)):
                domains: List[Dict[str, Any]] = []
                for key, label in evidence_domains:
                    bucket = getattr(visit.evidence, key)
                    if bucket.count:
                        domains.append(
                            {
                                "key": key,
                                "label": label,
                                "count": bucket.count,
                                "examples": bucket.examples[:3],
                            }
                        )
                timeline_events.append(
                    {
                        "visit_id": visit.visit_id,
                        "event_date": visit.event_date,
                        "event_type": visit.event_type,
                        "days_from_baseline": relative_study_days(
                            visit.provenance.raw_bff.get("info") or {}),
                        "diagnosis": visit.diagnosis or visit.disease_label,
                        "biosample_id": visit.biosample_id,
                        "domains": domains,
                    }
                )

        timeline_points.append(
            {
                "patient_id": summary.patient_id,
                "visit_count": summary.visit_count,
                "first_event_date": summary.first_event_date,
                "last_event_date": summary.last_event_date,
                "events": timeline_events,
            }
        )

    return {
        "totals": {
            "patients": len(summaries),
            "visits": total_visits,
            "avg_visits_per_patient": round(total_visits / len(summaries), 2) if summaries else 0,
            "source_files": len({path for summary in summaries for path in summary.source_files}),
        },
        "sex_counts": sex_counts,
        "visit_distribution": visit_distribution,
        "top_medications": meds,
        "top_diseases": diseases,
        "disease_medication_matrix": disease_medication_matrix,
        "patients": [summary.model_dump() for summary in summaries],
        "timelines": timeline_points,
    }


def disease_counts_local(bundles: Dict[str, PatientBundle]) -> List[Dict[str, Any]]:
    counts: Dict[str, Dict[str, Any]] = {}

    for patient_id, bundle in bundles.items():
        seen_for_patient = set()
        for visit in bundle.context.visits:
            for label in _extract_disease_labels_local(visit.provenance.raw_bff):
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


def disease_medication_matrix_local(
    bundles: Dict[str, PatientBundle],
    diseases: List[Dict[str, Any]],
    medications: List[Dict[str, Any]],
) -> Dict[str, Any]:
    disease_labels = [str(item.get("disease")) for item in diseases if item.get("disease")]
    medication_labels = [str(item.get("medication")) for item in medications if item.get("medication")]
    if not disease_labels or not medication_labels:
        return {"diseases": disease_labels, "medications": medication_labels, "values": []}

    values = [[0 for _ in medication_labels] for _ in disease_labels]
    disease_index = {label: idx for idx, label in enumerate(disease_labels)}
    medication_index = {label: idx for idx, label in enumerate(medication_labels)}

    for _patient_id, bundle in bundles.items():
        patient_diseases = set()
        patient_medications = set()
        for visit in bundle.context.visits:
            patient_diseases.update(
                label for label in _extract_disease_labels_local(visit.provenance.raw_bff) if label in disease_index
            )
            patient_medications.update(
                label for label in extract_treatment_labels(visit.provenance.raw_bff) if label in medication_index
            )
        for disease in patient_diseases:
            disease_idx = disease_index[disease]
            for medication in patient_medications:
                values[disease_idx][medication_index[medication]] += 1

    return {"diseases": disease_labels, "medications": medication_labels, "values": values}


def _extract_disease_labels_local(record: Dict[str, Any]) -> List[str]:
    diseases = record.get("diseases")
    labels: List[str] = []
    if not isinstance(diseases, list):
        return labels
    for item in diseases:
        if not isinstance(item, dict):
            continue
        label = select_first(
            [
                nested_get(item, ("diseaseCode", "label")),
                nested_get(item, ("diseaseCode", "id")),
            ]
        )
        if label is not None and str(label) not in labels:
            labels.append(str(label))
    return labels
