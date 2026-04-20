from __future__ import annotations

import csv
import json
import os
import shutil
import subprocess
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List

import yaml

from app.bff import ensure_data_dir, extract_event_date, extract_patient_id, extract_treatment_labels, normalize_value, read_bff_records
import app.query_store as query_store_module


SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
RSCRIPT_RUNNERS = {
    "dummy_scope_snapshot": SCRIPTS_DIR / "analysis_dummy_scope_snapshot.R",
    "clinical_scope_profile": SCRIPTS_DIR / "analysis_r_clinical_profile.R",
    "dummy_long_job": SCRIPTS_DIR / "analysis_dummy_long_job.R",
    "molecular_differential_expression": SCRIPTS_DIR / "analysis_r_differential_expression.R",
    "molecular_deseq2_differential_expression": SCRIPTS_DIR / "analysis_r_deseq2_differential_expression.R",
}
SNAKEMAKE_RUNNERS = {
    "dummy_queue_demo": SCRIPTS_DIR / "analysis_dummy_snakemake" / "Snakefile",
}
NEXTFLOW_RUNNERS = {
    "dummy_queue_demo": SCRIPTS_DIR / "analysis_dummy_nextflow" / "main.nf",
}


def _configured_binary(env_var: str, default_name: str) -> str | None:
    configured = str(os.environ.get(env_var) or "").strip()
    if configured:
        path = Path(configured)
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    return shutil.which(default_name)


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


def _write_yaml(path: Path, payload: Dict[str, Any]) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _write_command_logs(
    *,
    target_dir: Path | None,
    command: List[str],
    stdout: str,
    stderr: str,
) -> None:
    if not isinstance(target_dir, Path):
        return
    (target_dir / "command.txt").write_text(" ".join(command), encoding="utf-8")
    (target_dir / "stdout.txt").write_text(stdout or "", encoding="utf-8")
    (target_dir / "stderr.txt").write_text(stderr or "", encoding="utf-8")


def _load_workflow_result_payload(
    *,
    result_path: Path,
    runner_type: str,
    runner_ref: str,
    command: List[str],
) -> Dict[str, Any]:
    if not result_path.exists() or not result_path.is_file():
        raise RuntimeError(f"External {runner_type} analysis did not produce result.json.")
    try:
        payload = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"External {runner_type} analysis returned invalid result.json.") from exc
    reply = str(payload.get("reply") or "").strip()
    context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    if not reply:
        raise RuntimeError(f"External {runner_type} analysis returned an empty reply.")
    return {
        "intent": f"analysis_external_{runner_type}",
        "reply": reply,
        "data": {
            "source": "deterministic",
            "execution": "external_runner",
            "context": context,
            "model": None,
            "base_url": "",
            "runner_type": runner_type,
            "runner_ref": str(runner_ref or "").strip(),
            "runner_command": command,
        },
    }


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


def _molecular_scope_tokens(value: str) -> List[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def _resolve_molecular_scope(value: str) -> Dict[str, List[str]]:
    sample_ids: List[str] = []
    patient_ids: List[str] = []
    seen_samples = set()
    seen_patients = set()
    for item in _molecular_scope_tokens(value):
        normalized = str(item or "").strip()
        if not normalized:
            continue
        if ":" in normalized and normalized not in seen_samples:
            seen_samples.add(normalized)
            sample_ids.append(normalized)
        patient_id = normalized.split(":", 1)[0].strip()
        if patient_id and ":" not in normalized and patient_id not in seen_patients:
            seen_patients.add(patient_id)
            patient_ids.append(patient_id)
    return {"sample_ids": sample_ids, "patient_ids": patient_ids}


def _choose_molecular_dataset(data_dir: str, requested_name: str = "") -> Dict[str, Any]:
    inventory = query_store_module.molecular_dataset_inventory(data_dir)
    if not inventory:
        raise RuntimeError("No molecular datasets are available in the current workspace.")
    wanted = str(requested_name or "").strip()
    if wanted:
        for item in inventory:
            if str(item.get("dataset_name") or "").strip() == wanted:
                return dict(item or {})
        raise RuntimeError(f"Molecular dataset '{wanted}' is not available in the current workspace.")
    if len(inventory) != 1:
        raise RuntimeError("Differential expression requires one explicitly selected molecular dataset.")
    return dict(inventory[0] or {})


def _prepare_molecular_differential_expression_bundle(
    data_dir: str,
    *,
    prompt: str,
    molecular_dataset_name: str,
    selected_patient_ids: str,
    compare_selected_patient_ids: str,
    output_dir: Path,
    method: str = "log2_cpm_welch",
    minimum_samples_per_group: int = 1,
) -> Dict[str, Any]:
    cohort_a_scope = _resolve_molecular_scope(selected_patient_ids)
    cohort_b_scope = _resolve_molecular_scope(compare_selected_patient_ids)
    cohort_a_tokens = cohort_a_scope["sample_ids"] + cohort_a_scope["patient_ids"]
    cohort_b_tokens = cohort_b_scope["sample_ids"] + cohort_b_scope["patient_ids"]
    if not cohort_a_tokens or not cohort_b_tokens:
        raise RuntimeError("Differential expression requires both Cohort A and Cohort B.")
    overlap = sorted(set(cohort_a_tokens) & set(cohort_b_tokens))
    if overlap:
        raise RuntimeError("Differential expression requires disjoint Cohort A and Cohort B selections.")

    dataset = _choose_molecular_dataset(data_dir, molecular_dataset_name)
    dataset_name = str(dataset.get("dataset_name") or "").strip()
    if not dataset_name:
        raise RuntimeError("No valid molecular dataset name is available for differential expression.")

    query_store_module.ensure_query_store(data_dir)
    con = query_store_module._connect(data_dir)
    try:
        where_clauses = ["dataset_name = ?"]
        query_params: List[Any] = [dataset_name]
        wanted_sample_ids = cohort_a_scope["sample_ids"] + cohort_b_scope["sample_ids"]
        wanted_patient_ids = cohort_a_scope["patient_ids"] + cohort_b_scope["patient_ids"]
        if wanted_sample_ids:
            sample_placeholders = ",".join("?" for _ in wanted_sample_ids)
            where_clauses.append(f"sample_id IN ({sample_placeholders})")
            query_params.extend(wanted_sample_ids)
        if wanted_patient_ids:
            patient_placeholders = ",".join("?" for _ in wanted_patient_ids)
            where_clauses.append(f"patient_id IN ({patient_placeholders})")
            query_params.extend(wanted_patient_ids)
        if len(where_clauses) == 1:
            raise RuntimeError("Differential expression requires both Cohort A and Cohort B.")
        sample_rows = con.execute(
            f"""
            SELECT sample_id, patient_id
            FROM molecular_samples
            WHERE {" AND ".join([where_clauses[0], "(" + " OR ".join(where_clauses[1:]) + ")"])}
            ORDER BY sample_id
            """,
            query_params,
        ).fetchall()
        if not sample_rows:
            raise RuntimeError(f"No molecular samples overlap the current Analysis scope for dataset '{dataset_name}'.")

        sample_table_rows: List[Dict[str, Any]] = []
        sample_ids: List[str] = []
        cohort_a_samples = set(cohort_a_scope["sample_ids"])
        cohort_b_samples = set(cohort_b_scope["sample_ids"])
        cohort_a_patients = set(cohort_a_scope["patient_ids"])
        cohort_b_patients = set(cohort_b_scope["patient_ids"])
        for sample_id, patient_id in sample_rows:
            sample_text = str(sample_id or "").strip()
            patient_text = str(patient_id or "").strip()
            if not sample_text or not patient_text:
                continue
            belongs_to_a = sample_text in cohort_a_samples or patient_text in cohort_a_patients
            belongs_to_b = sample_text in cohort_b_samples or patient_text in cohort_b_patients
            if belongs_to_a and belongs_to_b:
                raise RuntimeError("Differential expression requires disjoint sample selections across Cohort A and Cohort B.")
            if belongs_to_a:
                cohort = "A"
            elif belongs_to_b:
                cohort = "B"
            else:
                continue
            sample_ids.append(sample_text)
            sample_table_rows.append(
                {
                    "sample_id": sample_text,
                    "patient_id": patient_text,
                    "cohort": cohort,
                    "group_label": "Cohort A" if cohort == "A" else "Cohort B",
                }
            )
        if not sample_table_rows:
            raise RuntimeError(f"No molecular samples overlap the selected cohorts for dataset '{dataset_name}'.")
        cohort_a_sample_count = sum(1 for row in sample_table_rows if row["cohort"] == "A")
        cohort_b_sample_count = sum(1 for row in sample_table_rows if row["cohort"] == "B")
        if cohort_a_sample_count == 0 or cohort_b_sample_count == 0:
            raise RuntimeError(
                f"Dataset '{dataset_name}' must contain at least one sample in both Cohort A and Cohort B."
            )

        sample_placeholders = ",".join("?" for _ in sample_ids)
        count_rows = con.execute(
            f"""
            SELECT gene_id, sample_id, raw_count
            FROM transcript_counts
            WHERE dataset_name = ? AND sample_id IN ({sample_placeholders})
            ORDER BY gene_id, sample_id
            """,
            [dataset_name, *sample_ids],
        ).fetchall()
    finally:
        con.close()

    matrix_values: Dict[str, Dict[str, int]] = defaultdict(dict)
    for gene_id, sample_id, raw_count in count_rows:
        gene_text = str(gene_id or "").strip()
        sample_text = str(sample_id or "").strip()
        if not gene_text or not sample_text:
            continue
        matrix_values[gene_text][sample_text] = int(raw_count or 0)

    counts_matrix_rows: List[Dict[str, Any]] = []
    for gene_id in sorted(matrix_values):
        row: Dict[str, Any] = {"gene_id": gene_id}
        gene_counts = matrix_values[gene_id]
        for sample_id in sample_ids:
            row[sample_id] = gene_counts.get(sample_id, 0)
        counts_matrix_rows.append(row)
    if not counts_matrix_rows:
        raise RuntimeError(f"No transcript count rows are available for dataset '{dataset_name}' in the selected cohorts.")

    cohort_a_rows = [
        {"patient_id": row["patient_id"], "sample_id": row["sample_id"], "cohort": row["cohort"]}
        for row in sample_table_rows
        if row["cohort"] == "A"
    ]
    cohort_b_rows = [
        {"patient_id": row["patient_id"], "sample_id": row["sample_id"], "cohort": row["cohort"]}
        for row in sample_table_rows
        if row["cohort"] == "B"
    ]

    sample_table_path = output_dir / "sample_table.tsv"
    counts_matrix_path = output_dir / "counts_matrix.tsv"
    cohort_a_path = output_dir / "cohort_a.tsv"
    cohort_b_path = output_dir / "cohort_b.tsv"
    params_path = output_dir / "params.yaml"
    manifest_path = output_dir / "manifest.yaml"
    _write_tsv(sample_table_path, ["sample_id", "patient_id", "cohort", "group_label"], sample_table_rows)
    _write_tsv(counts_matrix_path, ["gene_id", *sample_ids], counts_matrix_rows)
    _write_tsv(cohort_a_path, ["patient_id", "sample_id", "cohort"], cohort_a_rows)
    _write_tsv(cohort_b_path, ["patient_id", "sample_id", "cohort"], cohort_b_rows)
    params_payload = {
        "analysis_type": "differential_expression",
        "method": str(method or "log2_cpm_welch").strip(),
        "prompt": str(prompt or "").strip(),
        "dataset_name": dataset_name,
        "contrast": {"numerator": "Cohort A", "denominator": "Cohort B"},
        "minimum_samples_per_group": max(1, int(minimum_samples_per_group or 1)),
    }
    _write_yaml(params_path, params_payload)
    manifest_payload = {
        "version": 1,
        "analysis_type": "molecular_differential_expression",
        "dataset_name": dataset_name,
        "prompt": str(prompt or "").strip(),
        "cohorts": {
            "A": {
                "label": "Cohort A",
                "patient_count": len({row["patient_id"] for row in cohort_a_rows}),
                "sample_count": cohort_a_sample_count,
                "file": cohort_a_path.name,
            },
            "B": {
                "label": "Cohort B",
                "patient_count": len({row["patient_id"] for row in cohort_b_rows}),
                "sample_count": cohort_b_sample_count,
                "file": cohort_b_path.name,
            },
        },
        "inputs": {
            "sample_table": sample_table_path.name,
            "counts_matrix": counts_matrix_path.name,
            "params": params_path.name,
        },
        "outputs": {
            "results_table": "de_results.tsv",
            "volcano_points": "volcano_points.tsv",
            "summary": "summary.json",
            "plot": "volcano_plot.png",
        },
    }
    _write_yaml(manifest_path, manifest_payload)
    return {
        "dataset_name": dataset_name,
        "manifest_path": manifest_path,
        "params_path": params_path,
        "sample_table_path": sample_table_path,
        "counts_matrix_path": counts_matrix_path,
        "sample_table_rows": sample_table_rows,
        "cohort_a_patient_count": manifest_payload["cohorts"]["A"]["patient_count"],
        "cohort_a_sample_count": cohort_a_sample_count,
        "cohort_b_patient_count": manifest_payload["cohorts"]["B"]["patient_count"],
        "cohort_b_sample_count": cohort_b_sample_count,
        "gene_count": len(counts_matrix_rows),
    }


def _validate_deseq2_bundle(bundle: Dict[str, Any]) -> None:
    sample_rows = list(bundle.get("sample_table_rows") or [])
    cohort_a_sample_count = int(bundle.get("cohort_a_sample_count") or 0)
    cohort_b_sample_count = int(bundle.get("cohort_b_sample_count") or 0)
    if cohort_a_sample_count < 2 or cohort_b_sample_count < 2:
        raise RuntimeError("DESeq2 differential expression requires at least two samples in Cohort A and two samples in Cohort B.")
    patient_counts = Counter(str(row.get("patient_id") or "").strip() for row in sample_rows if str(row.get("patient_id") or "").strip())
    repeated_patients = sorted(patient_id for patient_id, count in patient_counts.items() if count > 1)
    if repeated_patients:
        raise RuntimeError(
            "DESeq2 differential expression v1 requires one sample per patient. "
            "Use a baseline-only dataset or choose one sample per patient before running."
        )


def run_rscript_analysis(
    runner_ref: str,
    *,
    prompt: str,
    data_dir: str,
    molecular_dataset_name: str = "",
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
        elif runner_ref == "molecular_differential_expression":
            bundle = _prepare_molecular_differential_expression_bundle(
                data_dir,
                prompt=prompt,
                molecular_dataset_name=molecular_dataset_name,
                selected_patient_ids=selected_patient_ids,
                compare_selected_patient_ids=compare_selected_patient_ids,
                output_dir=temp_path,
                method="log2_cpm_welch",
                minimum_samples_per_group=1,
            )
            command = [
                binary,
                str(script_path),
                "--job-dir",
                str(temp_path),
                "--manifest",
                str(bundle["manifest_path"]),
                "--params",
                str(bundle["params_path"]),
                "--prompt",
                str(prompt or ""),
                "--dataset-name",
                str(bundle["dataset_name"]),
                "--sample-table",
                str(bundle["sample_table_path"]),
                "--counts-matrix",
                str(bundle["counts_matrix_path"]),
                "--results-table",
                str(temp_path / "de_results.tsv"),
                "--volcano-table",
                str(temp_path / "volcano_points.tsv"),
                "--summary-json",
                str(temp_path / "summary.json"),
                "--plot-file",
                str(temp_path / "volcano_plot.png"),
            ]
        elif runner_ref == "molecular_deseq2_differential_expression":
            bundle = _prepare_molecular_differential_expression_bundle(
                data_dir,
                prompt=prompt,
                molecular_dataset_name=molecular_dataset_name,
                selected_patient_ids=selected_patient_ids,
                compare_selected_patient_ids=compare_selected_patient_ids,
                output_dir=temp_path,
                method="deseq2_apeglm",
                minimum_samples_per_group=2,
            )
            _validate_deseq2_bundle(bundle)
            command = [
                binary,
                str(script_path),
                "--job-dir",
                str(temp_path),
                "--manifest",
                str(bundle["manifest_path"]),
                "--params",
                str(bundle["params_path"]),
                "--prompt",
                str(prompt or ""),
                "--dataset-name",
                str(bundle["dataset_name"]),
                "--sample-table",
                str(bundle["sample_table_path"]),
                "--counts-matrix",
                str(bundle["counts_matrix_path"]),
                "--results-table",
                str(temp_path / "de_results.tsv"),
                "--volcano-table",
                str(temp_path / "volcano_points.tsv"),
                "--summary-json",
                str(temp_path / "summary.json"),
                "--plot-file",
                str(temp_path / "volcano_plot.png"),
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


def run_snakemake_analysis(
    runner_ref: str,
    *,
    prompt: str,
    data_dir: str,
    selected_patient_ids: str = "",
    compare_selected_patient_ids: str = "",
    job_dir: Path | None = None,
    timeout_seconds: int = 30,
) -> Dict[str, Any]:
    binary = shutil.which("snakemake")
    if not binary:
        raise RuntimeError("Snakemake is not available on this installation.")
    workflow_path = SNAKEMAKE_RUNNERS.get(str(runner_ref or "").strip())
    if workflow_path is None:
        raise RuntimeError(f"Unsupported Snakemake analysis runner '{runner_ref}'.")
    if not workflow_path.exists():
        raise RuntimeError(f"Configured Snakemake analysis is missing: {workflow_path}")
    counts = _scope_counts(
        data_dir,
        selected_patient_ids=selected_patient_ids,
        compare_selected_patient_ids=compare_selected_patient_ids,
    )
    with tempfile.TemporaryDirectory(prefix="pn-analysis-snakemake-") as temp_dir:
        temp_path = job_dir if isinstance(job_dir, Path) else Path(temp_dir)
        temp_path.mkdir(parents=True, exist_ok=True)
        result_path = temp_path / "result.json"
        summary_path = temp_path / "summary.txt"
        command = [
            binary,
            "--snakefile",
            str(workflow_path),
            "--directory",
            str(temp_path),
            "--cores",
            "1",
            "--quiet",
            "all",
            "--config",
            f"prompt={str(prompt or '')}",
            f"compare_mode={'true' if counts['compare_mode'] else 'false'}",
            f"workspace_record_count={counts['workspace_record_count']}",
            f"workspace_patient_count={counts['workspace_patient_count']}",
            f"scope_a_record_count={counts['scope_a_record_count']}",
            f"scope_a_patient_count={counts['scope_a_patient_count']}",
            f"scope_b_record_count={counts['scope_b_record_count']}",
            f"scope_b_patient_count={counts['scope_b_patient_count']}",
            f"result_json={result_path}",
            f"summary_txt={summary_path}",
        ]
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=max(1, int(timeout_seconds or 30)),
        )
    _write_command_logs(target_dir=job_dir, command=command, stdout=result.stdout or "", stderr=result.stderr or "")
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "External Snakemake analysis failed.").strip())
    return _load_workflow_result_payload(
        result_path=result_path,
        runner_type="snakemake",
        runner_ref=runner_ref,
        command=command,
    )


def run_nextflow_analysis(
    runner_ref: str,
    *,
    prompt: str,
    data_dir: str,
    selected_patient_ids: str = "",
    compare_selected_patient_ids: str = "",
    job_dir: Path | None = None,
    timeout_seconds: int = 30,
) -> Dict[str, Any]:
    binary = _configured_binary("NEXTFLOW_BIN", "nextflow")
    if not binary:
        raise RuntimeError("Nextflow is not available on this installation.")
    workflow_path = NEXTFLOW_RUNNERS.get(str(runner_ref or "").strip())
    if workflow_path is None:
        raise RuntimeError(f"Unsupported Nextflow analysis runner '{runner_ref}'.")
    if not workflow_path.exists():
        raise RuntimeError(f"Configured Nextflow analysis is missing: {workflow_path}")
    counts = _scope_counts(
        data_dir,
        selected_patient_ids=selected_patient_ids,
        compare_selected_patient_ids=compare_selected_patient_ids,
    )
    with tempfile.TemporaryDirectory(prefix="pn-analysis-nextflow-") as temp_dir:
        temp_path = job_dir if isinstance(job_dir, Path) else Path(temp_dir)
        temp_path.mkdir(parents=True, exist_ok=True)
        result_path = temp_path / "result.json"
        summary_path = temp_path / "summary.txt"
        command = [
            binary,
            "run",
            str(workflow_path),
            "-work-dir",
            str(temp_path / ".nextflow-work"),
            "--job_dir",
            str(temp_path),
            "--prompt",
            str(prompt or ""),
            "--compare_mode",
            "true" if counts["compare_mode"] else "false",
            "--workspace_record_count",
            str(counts["workspace_record_count"]),
            "--workspace_patient_count",
            str(counts["workspace_patient_count"]),
            "--scope_a_record_count",
            str(counts["scope_a_record_count"]),
            "--scope_a_patient_count",
            str(counts["scope_a_patient_count"]),
            "--scope_b_record_count",
            str(counts["scope_b_record_count"]),
            "--scope_b_patient_count",
            str(counts["scope_b_patient_count"]),
            "--result_json",
            str(result_path),
            "--summary_txt",
            str(summary_path),
        ]
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=max(1, int(timeout_seconds or 30)),
        )
    _write_command_logs(target_dir=job_dir, command=command, stdout=result.stdout or "", stderr=result.stderr or "")
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "External Nextflow analysis failed.").strip())
    return _load_workflow_result_payload(
        result_path=result_path,
        runner_type="nextflow",
        runner_ref=runner_ref,
        command=command,
    )


def run_external_analysis(
    runner_type: str,
    runner_ref: str,
    *,
    prompt: str,
    data_dir: str,
    molecular_dataset_name: str = "",
    selected_patient_ids: str = "",
    compare_selected_patient_ids: str = "",
    job_dir: Path | None = None,
    timeout_seconds: int = 30,
) -> Dict[str, Any]:
    normalized = str(runner_type or "").strip().lower()
    if normalized == "rscript":
        return run_rscript_analysis(
            runner_ref,
            prompt=prompt,
            data_dir=data_dir,
            molecular_dataset_name=molecular_dataset_name,
            selected_patient_ids=selected_patient_ids,
            compare_selected_patient_ids=compare_selected_patient_ids,
            job_dir=job_dir,
            timeout_seconds=timeout_seconds,
        )
    if normalized == "snakemake":
        return run_snakemake_analysis(
            runner_ref,
            prompt=prompt,
            data_dir=data_dir,
            selected_patient_ids=selected_patient_ids,
            compare_selected_patient_ids=compare_selected_patient_ids,
            job_dir=job_dir,
            timeout_seconds=timeout_seconds,
        )
    if normalized == "nextflow":
        return run_nextflow_analysis(
            runner_ref,
            prompt=prompt,
            data_dir=data_dir,
            selected_patient_ids=selected_patient_ids,
            compare_selected_patient_ids=compare_selected_patient_ids,
            job_dir=job_dir,
            timeout_seconds=timeout_seconds,
        )
    raise RuntimeError(f"Unsupported analysis runner type '{runner_type}'.")
