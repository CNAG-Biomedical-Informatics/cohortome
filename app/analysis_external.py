from __future__ import annotations

import csv
import json
import shutil
import subprocess
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

from app.bff import ensure_data_dir, extract_event_date, extract_patient_id, extract_treatment_labels, normalize_value, read_bff_records


SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
RSCRIPT_RUNNERS = {
    "dummy_scope_snapshot": SCRIPTS_DIR / "analysis_dummy_scope_snapshot.R",
    "clinical_scope_profile": SCRIPTS_DIR / "analysis_r_clinical_profile.R",
    "dummy_long_job": SCRIPTS_DIR / "analysis_dummy_long_job.R",
}


def _split_scope_ids(value: str) -> List[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def _scope_counts(data_dir: str, selected_patient_ids: str = "", compare_selected_patient_ids: str = "") -> Dict[str, Any]:
    clinical_dir = ensure_data_dir(data_dir)
    raw_records = read_bff_records(clinical_dir)
    records = [
        item[2] if isinstance(item, tuple) and len(item) >= 3 and isinstance(item[2], dict) else item
        for item in raw_records
        if isinstance(item, dict) or (isinstance(item, tuple) and len(item) >= 3 and isinstance(item[2], dict))
    ]
    workspace_patient_ids = {extract_patient_id(record) for record in records if extract_patient_id(record)}
    cohort_a_tokens = set(_split_scope_ids(selected_patient_ids))
    cohort_b_tokens = set(_split_scope_ids(compare_selected_patient_ids))

    def in_scope(record: Dict[str, Any], tokens: set[str]) -> bool:
        if not tokens:
            return False
        record_id = str(record.get("id") or "").strip()
        patient_id = extract_patient_id(record)
        return record_id in tokens or patient_id in tokens

    cohort_a_records = [record for record in records if in_scope(record, cohort_a_tokens)]
    cohort_b_records = [record for record in records if in_scope(record, cohort_b_tokens)]
    cohort_a_patients = {extract_patient_id(record) for record in cohort_a_records if extract_patient_id(record)}
    cohort_b_patients = {extract_patient_id(record) for record in cohort_b_records if extract_patient_id(record)}
    return {
        "workspace_record_count": len(records),
        "workspace_patient_count": len(workspace_patient_ids),
        "scope_a_record_count": len(cohort_a_records),
        "scope_a_patient_count": len(cohort_a_patients),
        "scope_b_record_count": len(cohort_b_records),
        "scope_b_patient_count": len(cohort_b_patients),
        "compare_mode": bool(cohort_b_tokens),
    }


def _extract_disease_labels(record: Dict[str, Any]) -> List[str]:
    items = record.get("diseases")
    if not isinstance(items, list):
        return []
    labels: List[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        code = item.get("diseaseCode")
        if isinstance(code, dict):
            label = normalize_value(code.get("label")) or normalize_value(code.get("id"))
            if isinstance(label, str) and label.strip():
                labels.append(label.strip())
    seen = set()
    ordered: List[str] = []
    for label in labels:
        if label in seen:
            continue
        seen.add(label)
        ordered.append(label)
    return ordered


def _record_in_scope(record: Dict[str, Any], tokens: set[str]) -> bool:
    if not tokens:
        return True
    record_id = str(record.get("id") or "").strip()
    patient_id = extract_patient_id(record)
    return record_id in tokens or (patient_id in tokens if patient_id else False)


def _summarize_scope(records: List[Dict[str, Any]], tokens: set[str]) -> Dict[str, Any]:
    scoped_records = [record for record in records if _record_in_scope(record, tokens)]
    patient_ids = {extract_patient_id(record) for record in scoped_records if extract_patient_id(record)}
    disease_patients: Dict[str, set[str]] = defaultdict(set)
    medication_patients: Dict[str, set[str]] = defaultdict(set)
    period_counts: Dict[str, Dict[str, Any]] = {}

    for record in scoped_records:
        patient_id = extract_patient_id(record)
        for label in _extract_disease_labels(record):
            if patient_id:
                disease_patients[label].add(patient_id)
        for label in extract_treatment_labels(record):
            if patient_id:
                medication_patients[label].add(patient_id)
        raw_date = normalize_value(extract_event_date(record))
        if isinstance(raw_date, str) and raw_date.strip():
            date_text = raw_date.strip()
            period = date_text[:7] if len(date_text) >= 7 else date_text
            entry = period_counts.setdefault(period, {"period": period, "timepoint_count": 0, "patients": set()})
            entry["timepoint_count"] += 1
            if patient_id:
                entry["patients"].add(patient_id)

    top_diseases = sorted(
        (
            {"label": label, "patient_count": len(patients)}
            for label, patients in disease_patients.items()
        ),
        key=lambda item: (-item["patient_count"], item["label"]),
    )[:8]
    top_medications = sorted(
        (
            {"label": label, "patient_count": len(patients)}
            for label, patients in medication_patients.items()
        ),
        key=lambda item: (-item["patient_count"], item["label"]),
    )[:8]
    periods = [
        {
            "period": period,
            "timepoint_count": values["timepoint_count"],
            "patient_count": len(values["patients"]),
        }
        for period, values in sorted(period_counts.items())
    ]
    return {
        "record_count": len(scoped_records),
        "patient_count": len(patient_ids),
        "top_diseases": top_diseases,
        "top_medications": top_medications,
        "periods": periods,
    }


def _write_tsv(path: Path, fieldnames: List[str], rows: List[Dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def _clinical_profile_tables(
    data_dir: str,
    selected_patient_ids: str = "",
    compare_selected_patient_ids: str = "",
) -> Dict[str, List[Dict[str, Any]]]:
    clinical_dir = ensure_data_dir(data_dir)
    raw_records = read_bff_records(clinical_dir)
    records = [
        item[2] if isinstance(item, tuple) and len(item) >= 3 and isinstance(item[2], dict) else item
        for item in raw_records
        if isinstance(item, dict) or (isinstance(item, tuple) and len(item) >= 3 and isinstance(item[2], dict))
    ]
    cohort_a_tokens = set(_split_scope_ids(selected_patient_ids))
    cohort_b_tokens = set(_split_scope_ids(compare_selected_patient_ids))
    cohort_a = _summarize_scope(records, cohort_a_tokens)
    compare_mode = bool(cohort_b_tokens)
    cohort_b = _summarize_scope(records, cohort_b_tokens) if compare_mode else {
        "record_count": 0,
        "patient_count": 0,
        "top_diseases": [],
        "top_medications": [],
        "periods": [],
    }
    overview_rows = [
        {
            "cohort": "A",
            "record_count": cohort_a["record_count"],
            "patient_count": cohort_a["patient_count"],
        }
    ]
    if compare_mode:
        overview_rows.append(
            {
                "cohort": "B",
                "record_count": cohort_b["record_count"],
                "patient_count": cohort_b["patient_count"],
            }
        )
    disease_rows = [
        {"cohort": "A", "label": item["label"], "patient_count": item["patient_count"]}
        for item in cohort_a["top_diseases"]
    ]
    if compare_mode:
        disease_rows.extend(
            {"cohort": "B", "label": item["label"], "patient_count": item["patient_count"]}
            for item in cohort_b["top_diseases"]
        )
    medication_rows = [
        {"cohort": "A", "label": item["label"], "patient_count": item["patient_count"]}
        for item in cohort_a["top_medications"]
    ]
    if compare_mode:
        medication_rows.extend(
            {"cohort": "B", "label": item["label"], "patient_count": item["patient_count"]}
            for item in cohort_b["top_medications"]
        )
    period_rows = [
        {
            "cohort": "A",
            "period": item["period"],
            "timepoint_count": item["timepoint_count"],
            "patient_count": item["patient_count"],
        }
        for item in cohort_a["periods"]
    ]
    if compare_mode:
        period_rows.extend(
            {
                "cohort": "B",
                "period": item["period"],
                "timepoint_count": item["timepoint_count"],
                "patient_count": item["patient_count"],
            }
            for item in cohort_b["periods"]
        )
    return {
        "compare_mode": compare_mode,
        "overview": overview_rows,
        "diseases": disease_rows,
        "medications": medication_rows,
        "periods": period_rows,
    }


def run_rscript_analysis(
    runner_ref: str,
    *,
    prompt: str,
    data_dir: str,
    selected_patient_ids: str = "",
    compare_selected_patient_ids: str = "",
    job_dir: Path | None = None,
    timeout_seconds: int = 30,
) -> Dict[str, Any]:
    binary = shutil.which("Rscript")
    if not binary:
        raise RuntimeError("Rscript is not available on this installation.")
    script_path = RSCRIPT_RUNNERS.get(str(runner_ref or "").strip())
    if script_path is None:
        raise RuntimeError(f"Unsupported Rscript analysis runner '{runner_ref}'.")
    if not script_path.exists():
        raise RuntimeError(f"Configured Rscript analysis is missing: {script_path}")
    with tempfile.TemporaryDirectory(prefix="pn-analysis-rscript-") as temp_dir:
        temp_path = job_dir if isinstance(job_dir, Path) else Path(temp_dir)
        temp_path.mkdir(parents=True, exist_ok=True)
        if runner_ref == "dummy_scope_snapshot":
            counts = _scope_counts(
                data_dir,
                selected_patient_ids=selected_patient_ids,
                compare_selected_patient_ids=compare_selected_patient_ids,
            )
            command = [
                binary,
                str(script_path),
                "--prompt",
                str(prompt or ""),
                "--workspace-record-count",
                str(counts["workspace_record_count"]),
                "--workspace-patient-count",
                str(counts["workspace_patient_count"]),
                "--scope-a-record-count",
                str(counts["scope_a_record_count"]),
                "--scope-a-patient-count",
                str(counts["scope_a_patient_count"]),
                "--scope-b-record-count",
                str(counts["scope_b_record_count"]),
                "--scope-b-patient-count",
                str(counts["scope_b_patient_count"]),
                "--compare-mode",
                "true" if counts["compare_mode"] else "false",
            ]
        elif runner_ref == "clinical_scope_profile":
            tables = _clinical_profile_tables(
                data_dir,
                selected_patient_ids=selected_patient_ids,
                compare_selected_patient_ids=compare_selected_patient_ids,
            )
            overview_path = temp_path / "overview.tsv"
            diseases_path = temp_path / "diseases.tsv"
            medications_path = temp_path / "medications.tsv"
            periods_path = temp_path / "periods.tsv"
            _write_tsv(overview_path, ["cohort", "record_count", "patient_count"], tables["overview"])
            _write_tsv(diseases_path, ["cohort", "label", "patient_count"], tables["diseases"])
            _write_tsv(medications_path, ["cohort", "label", "patient_count"], tables["medications"])
            _write_tsv(periods_path, ["cohort", "period", "timepoint_count", "patient_count"], tables["periods"])
            command = [
                binary,
                str(script_path),
                "--prompt",
                str(prompt or ""),
                "--overview-tsv",
                str(overview_path),
                "--diseases-tsv",
                str(diseases_path),
                "--medications-tsv",
                str(medications_path),
                "--periods-tsv",
                str(periods_path),
                "--compare-mode",
                "true" if tables["compare_mode"] else "false",
            ]
        elif runner_ref == "dummy_long_job":
            command = [
                binary,
                str(script_path),
                "--prompt",
                str(prompt or ""),
                "--sleep-seconds",
                "60",
            ]
        else:
            raise RuntimeError(f"Unsupported Rscript analysis runner '{runner_ref}'.")
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=max(1, int(timeout_seconds or 30)),
        )
    if isinstance(job_dir, Path):
        (job_dir / "command.txt").write_text(" ".join(command), encoding="utf-8")
        (job_dir / "stdout.txt").write_text(result.stdout or "", encoding="utf-8")
        (job_dir / "stderr.txt").write_text(result.stderr or "", encoding="utf-8")
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "External Rscript analysis failed.").strip())
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("External Rscript analysis returned invalid JSON.") from exc
    reply = str(payload.get("reply") or "").strip()
    context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    if not reply:
        raise RuntimeError("External Rscript analysis returned an empty reply.")
    return {
        "intent": "analysis_external_rscript",
        "reply": reply,
        "data": {
            "source": "deterministic",
            "execution": "external_runner",
            "context": context,
            "model": None,
            "base_url": "",
            "runner_type": "rscript",
            "runner_ref": str(runner_ref or "").strip(),
            "runner_command": command,
        },
    }
