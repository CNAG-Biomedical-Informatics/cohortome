"""Bounded, in-memory exports of explicitly selected clinical results."""
import csv
from datetime import datetime, timezone
import io
import json
import zipfile

from fastapi import HTTPException
from fastapi.responses import Response

MAX_EXPORT_ROWS = 100_000
MAX_EXPORT_BYTES = 32 * 1024 * 1024
PATIENT_COLUMNS = ("patient_id", "subject_clarid", "dataset_ids", "sex", "visit_count", "medication_count")
SAMPLE_COLUMNS = ("sample_id", "patient_id", "subject_clarid", "dataset_ids")


def check_size(count):
    if count > MAX_EXPORT_ROWS:
        raise HTTPException(413, "Export exceeds 100,000 rows. Select a smaller cohort or query result.")


def roster_indexes(patients):
    by_patient = {str(p["patient_id"]): p for p in patients}
    by_sample = {}
    for patient in patients:
        for sample_id in patient.get("original_record_ids", []):
            key = str(sample_id)
            by_sample[key] = None if key in by_sample else patient
    return by_patient, by_sample


def identity_columns(patient):
    patient = patient or {}
    return {
        "patient_id": patient.get("patient_id", ""),
        "subject_clarid": (patient.get("clarid") or {}).get("human_id", ""),
        "dataset_ids": json.dumps(patient.get("dataset_ids") or [], ensure_ascii=False),
        "dataset_names": ", ".join(patient.get("dataset_names") or []),
    }


def query_rows(record, patients):
    items = record.get("items") or []
    check_size(len(items))
    by_patient, by_sample = roster_indexes(patients)
    sample_level = record.get("id_type") == "sample"
    rows = []
    for item in items:
        stored = item.get("row") or {}
        if sample_level:
            sample_id = str(item.get("sample_id") or "")
            rows.append({**identity_columns(by_sample.get(sample_id)), "sample_id": sample_id})
        else:
            patient_id = str(item.get("patient_id") or stored.get("patient_id") or "")
            patient = by_patient.get(patient_id, {})
            rows.append({**identity_columns(patient), "patient_id": patient_id,
                         **{key: stored.get(key, patient.get(key, ""))
                            for key in ("sex", "visit_count", "medication_count")}})
    return rows, SAMPLE_COLUMNS if sample_level else PATIENT_COLUMNS


def _cell(value):
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return value
    text = str(value)
    # Quoting CSV fields alone does not stop spreadsheet formula execution.
    if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")):
        return "'" + text
    return text


def table_bytes(rows, columns, delimiter="\t"):
    check_size(len(rows))
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=delimiter, lineterminator="\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow([_cell(row.get(key)) for key in columns])
        if output.tell() > MAX_EXPORT_BYTES:
            raise HTTPException(413, "Export exceeds 32 MiB. Select a smaller result.")
    return bounded_bytes(output.getvalue().encode("utf-8"))


def bounded_bytes(value):
    if len(value) > MAX_EXPORT_BYTES:
        raise HTTPException(413, "Export exceeds 32 MiB. Select a smaller result.")
    return value


def metadata(kind, dataset_ids, row_count, **details):
    return {"schema_version": 1, "application": "COHORTome", "export_kind": kind,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "dataset_ids": dataset_ids, "row_count": row_count,
            "disclosure": "detailed", "encoding": "UTF-8",
            "table_note": "Import identifiers as text to preserve leading zeros. Potential spreadsheet formulas are prefixed with an apostrophe. Dataset ID cells contain JSON arrays. Blank subject links or ClarIDs mean unavailable or ambiguous; no links are inferred from ID prefixes.",
            **details}


def json_bytes(value):
    return bounded_bytes(json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8"))


def attachment(content, filename, media_type):
    return Response(content, media_type=media_type, headers={
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
    })


def cohort_bundle(cohort, patients):
    patient_ids = list(cohort.get("patient_ids") or [])
    sample_ids = list(cohort.get("sample_ids") or [])
    check_size(len(patient_ids) + len(sample_ids))
    by_patient, by_sample = roster_indexes(patients)
    rows = []
    # Separate membership rows preserve both sets without inventing pairings.
    for patient_id in patient_ids:
        rows.append({"member_type": "patient", "member_id": patient_id,
                     **identity_columns(by_patient.get(patient_id)), "patient_id": patient_id})
    for sample_id in sample_ids:
        rows.append({"member_type": "sample", "member_id": sample_id,
                     **identity_columns(by_sample.get(sample_id))})
    members = cohort.get('members')
    if members is not None:
        check_size(len(members))
        rows = [dict(member_type='sample' if m.get('sample_id') else 'patient',
                     member_id=m.get('sample_id') or m['patient_id'], dataset_id=m['dataset_id'],
                     patient_id=m['patient_id'], sample_id=m.get('sample_id', ''),
                     patient_key=m['patient_key'], sample_key=m.get('sample_key', '')) for m in members]
    columns = (("member_type", "member_id", "dataset_id", "patient_id", "sample_id", "patient_key", "sample_key") if members is not None
               else ("member_type", "member_id", "patient_id", "subject_clarid", "dataset_ids"))
    table = table_bytes(rows, columns)
    meta = metadata("saved_cohort", cohort.get("dataset_ids") or [], len(rows),
                    cohort_id=cohort.get("id"), name=cohort.get("name"),
                    created_at=cohort.get("created_at"), updated_at=cohort.get("updated_at"),
                    id_type=cohort.get("id_type"),
                    patient_ids=patient_ids, sample_ids=sample_ids,
                    source={key: (cohort.get("source") or {}).get(key, "") for key in ("kind", "prompt")},
                    membership_note="Saved membership is exported as stored, not recomputed. ClarID and exact sample links are from the current authorized workspace. This is not a full workspace backup.")
    if members is not None:
        meta['members'] = members
        meta['membership_version'] = 2
        meta['membership_note'] = 'Dataset-qualified membership as saved. Source IDs are unchanged; no cross-dataset identity linkage is inferred.'
    meta_bytes = json_bytes(meta)
    if len(table) + len(meta_bytes) > MAX_EXPORT_BYTES:
        raise HTTPException(413, "Export exceeds 32 MiB. Select a smaller cohort.")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("membership.tsv", table)
        archive.writestr("metadata.json", meta_bytes)
    return bounded_bytes(output.getvalue())
