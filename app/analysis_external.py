from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List

import yaml

from app.bff import (
    ensure_data_dir,
    extract_event_date,
    extract_patient_id,
    extract_treatment_labels,
    normalize_value,
    read_bff_records,
    resolve_project_data_dir,
)
import app.query_store as query_store_module


SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
_ADAPTER_SOURCE = Path(__file__).read_text(encoding="utf-8")
RSCRIPT_RUNNERS = {
    "dummy_scope_snapshot": SCRIPTS_DIR / "analysis_dummy_scope_snapshot.R",
    "clinical_scope_profile": SCRIPTS_DIR / "analysis_r_clinical_profile.R",
    "dummy_long_job": SCRIPTS_DIR / "analysis_dummy_long_job.R",
    "transcriptomics_deseq2_differential_expression": SCRIPTS_DIR / "analysis_r_deseq2_differential_expression.R",
    "transcriptomics_limma_voom_differential_expression": SCRIPTS_DIR / "analysis_r_limma_voom_differential_expression.R",
    "transcriptomics_hallmark_pathway_enrichment": SCRIPTS_DIR / "analysis_r_hallmark_pathway_enrichment.R",
    "methylation_qc_pca": SCRIPTS_DIR / "analysis_r_methylation_qc_pca.R",
    "methylation_limma_differential_methylation": SCRIPTS_DIR / "analysis_r_methylation_limma.R",
    "quantitative_assay_wilcoxon_comparison": SCRIPTS_DIR / "analysis_r_quantitative_assay_comparison.R",
}
SNAKEMAKE_RUNNERS = {
    "dummy_queue_demo": SCRIPTS_DIR / "analysis_dummy_snakemake" / "Snakefile",
}
NEXTFLOW_RUNNERS = {
    "dummy_queue_demo": SCRIPTS_DIR / "analysis_dummy_nextflow" / "main.nf",
}
WORKFLOW_RUNNERS = {
    "transcriptomics_signature": {
        "id": "transcriptomics_signature",
        "name": "Assay signature workflow",
        "steps": [
            {
                "id": "deseq2",
                "label": "DESeq2 differential expression",
                "runner_type": "rscript",
                "runner_ref": "transcriptomics_deseq2_differential_expression",
                "artifact_dir": "workflow/01-deseq2",
                "prompt": "Run DESeq2 differential expression between Cohort A and Cohort B for the selected assay.",
            },
            {
                "id": "hallmark",
                "label": "Hallmark pathway enrichment",
                "runner_type": "rscript",
                "runner_ref": "transcriptomics_hallmark_pathway_enrichment",
                "artifact_dir": "workflow/02-hallmark",
                "prompt": "Run Hallmark pathway enrichment between Cohort A and Cohort B for the selected assay.",
            },
        ],
    },
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


def _redact_command_value(command: List[str], flag: str, replacement: str) -> List[str]:
    """Return a persisted/public command with one sensitive argument hidden."""
    redacted = list(command)
    try:
        index = redacted.index(flag)
    except ValueError:
        return redacted
    if index + 1 < len(redacted):
        redacted[index + 1] = replacement
    return redacted


def _redact_command_job_paths(command: List[str], job_root: Path) -> List[str]:
    redacted: List[str] = []
    root = job_root.resolve()
    for raw_value in command:
        value = str(raw_value)
        try:
            path = Path(value)
            resolved = path.resolve() if path.is_absolute() else None
            relative = resolved.relative_to(root) if resolved is not None else None
        except (OSError, ValueError):
            relative = None
        if relative is None:
            redacted.append(value)
        elif str(relative) == ".":
            redacted.append("[job artifacts]")
        else:
            redacted.append(f"[job artifacts]/{relative.as_posix()}")
    return redacted


def _write_workflow_manifest(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _workflow_step_payload(
    *,
    step: Dict[str, Any],
    payload: Dict[str, Any],
    status: str,
    error: str = "",
) -> Dict[str, Any]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    context = data.get("context") if isinstance(data.get("context"), dict) else {}
    return {
        "id": str(step.get("id") or "").strip(),
        "label": str(step.get("label") or "").strip(),
        "runner_type": str(step.get("runner_type") or "").strip(),
        "runner_ref": str(step.get("runner_ref") or "").strip(),
        "artifact_dir": str(step.get("artifact_dir") or "").strip(),
        "status": status,
        "error": error,
        "reply": str(payload.get("reply") or "").strip(),
        "context": context,
    }


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


def _assay_scope_tokens(value: str) -> List[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def _resolve_assay_scope(value: str) -> Dict[str, List[str]]:
    sample_ids: List[str] = []
    patient_ids: List[str] = []
    seen_samples = set()
    seen_patients = set()
    for item in _assay_scope_tokens(value):
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


def _choose_transcriptomics_assay(data_dir: str, requested_name: str = "") -> Dict[str, Any]:
    inventory = query_store_module.assay_dataset_inventory(data_dir)
    if not inventory:
        raise RuntimeError("No transcriptomics assays are available in the current workspace.")
    wanted = str(requested_name or "").strip()
    if wanted:
        for item in inventory:
            if str(item.get("dataset_name") or "").strip() == wanted:
                return dict(item or {})
        raise RuntimeError(f"Assay '{wanted}' is not available in the current workspace.")
    if len(inventory) != 1:
        raise RuntimeError("Differential expression requires one explicitly selected assay.")
    return dict(inventory[0] or {})


def _export_manifest_count_like_matrix(
    data_dir: str,
    *,
    dataset_name: str,
    cohort_a_scope: Dict[str, List[str]],
    cohort_b_scope: Dict[str, List[str]],
    output_path: Path,
) -> Dict[str, Any]:
    item = query_store_module._manifest_assay_item(data_dir, dataset_name)
    if not item:
        raise RuntimeError(f"Assay '{dataset_name}' is missing its declared matrix metadata.")
    relative_file = str(item.get("file") or "").strip()
    root = query_store_module._manifest_item_root(data_dir, item)
    matrix_path = (root / relative_file).resolve()
    try:
        matrix_path.relative_to(root)
    except ValueError:
        raise RuntimeError(f"Assay '{dataset_name}' uses an invalid matrix location.") from None
    if not relative_file or not matrix_path.is_file():
        raise RuntimeError(f"Assay '{dataset_name}' matrix is unavailable.")

    with matrix_path.open("r", encoding="utf-8", newline="") as handle:
        first_line = handle.readline()
        if not first_line:
            raise RuntimeError(f"Assay '{dataset_name}' matrix is empty.")
        delimiter = query_store_module._detect_matrix_delimiter(first_line)
        handle.seek(0)
        reader = csv.reader(handle, delimiter=delimiter)
        header = next(reader, [])

    if len(header) < 2:
        raise RuntimeError(f"Assay '{dataset_name}' matrix has no sample columns.")
    source_sample_ids = [str(value or "").strip() for value in header[1:]]
    if any(not sample_id for sample_id in source_sample_ids):
        raise RuntimeError(f"Assay '{dataset_name}' matrix contains an empty sample identifier.")
    if len(set(source_sample_ids)) != len(source_sample_ids):
        raise RuntimeError(f"Assay '{dataset_name}' matrix contains duplicate sample identifiers.")

    covariates = _manifest_analysis_covariates(item, assay_label="Transcriptomics")
    covariate_types = _manifest_analysis_covariate_types(item, covariates, assay_label="Transcriptomics")
    try:
        linkage = query_store_module._manifest_assay_sample_patient_links(root, item, source_sample_ids)
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc
    patient_links = dict(linkage.get("links") or {})
    if any(not patient_links.get(sample_id) for sample_id in source_sample_ids):
        raise RuntimeError("Transcriptomics matrix samples must have complete patient linkage.")
    metadata = None
    if covariates or item.get("sample_metadata_file"):
        metadata = _read_manifest_sample_metadata(
            data_dir, item, covariates, assay_label="Transcriptomics",
            exact_sample_ids=str(item.get("patient_linkage") or "").strip().lower() == "exact_sample_id",
        )
        if any(sample_id not in metadata for sample_id in source_sample_ids):
            raise RuntimeError("Transcriptomics sample metadata must explicitly link every matrix sample.")

    cohort_a_samples = set(cohort_a_scope["sample_ids"])
    cohort_b_samples = set(cohort_b_scope["sample_ids"])
    cohort_a_patients = set(cohort_a_scope["patient_ids"])
    cohort_b_patients = set(cohort_b_scope["patient_ids"])
    selected_columns: List[tuple[int, str]] = []
    sample_table_rows: List[Dict[str, Any]] = []
    for source_index, sample_id in enumerate(source_sample_ids, start=1):
        patient_id = patient_links[sample_id]
        belongs_to_a = sample_id in cohort_a_samples or patient_id in cohort_a_patients
        belongs_to_b = sample_id in cohort_b_samples or patient_id in cohort_b_patients
        if belongs_to_a and belongs_to_b:
            raise RuntimeError("Differential expression requires disjoint sample selections across Cohort A and Cohort B.")
        if not belongs_to_a and not belongs_to_b:
            continue
        cohort = "A" if belongs_to_a else "B"
        selected_columns.append((source_index, sample_id))
        row = {"sample_id": sample_id, "patient_id": patient_id, "cohort": cohort,
               "group_label": "Cohort A" if cohort == "A" else "Cohort B"}
        for covariate in covariates:
            row[covariate] = metadata[sample_id][covariate]
        sample_table_rows.append(row)

    if not selected_columns:
        raise RuntimeError(f"No assay samples overlap the selected cohorts for dataset '{dataset_name}'.")
    cohort_a_sample_count = sum(1 for row in sample_table_rows if row["cohort"] == "A")
    cohort_b_sample_count = sum(1 for row in sample_table_rows if row["cohort"] == "B")
    if cohort_a_sample_count == 0 or cohort_b_sample_count == 0:
        raise RuntimeError(f"Dataset '{dataset_name}' must contain at least one sample in both Cohort A and Cohort B.")

    missing_tokens = {"", "na", "n/a", "nan", "null", "none", "."}
    for covariate in covariates:
        values = [row[covariate] for row in sample_table_rows]
        if any(value.lower() in missing_tokens for value in values):
            raise RuntimeError(
                f"limma-voom requires complete selected covariate '{covariate}'. "
                "Select a documented complete-case cohort or correct the assay metadata."
            )
        if covariate_types[covariate] == "numeric":
            try:
                values = [float(value) for value in values]
            except ValueError:
                raise RuntimeError(f"Transcriptomics numeric covariate '{covariate}' contains a non-numeric value.") from None
            if any(not math.isfinite(value) for value in values):
                raise RuntimeError(f"Transcriptomics numeric covariate '{covariate}' must be finite.")
        if len(set(values)) < 2:
            raise RuntimeError(
                f"Transcriptomics covariate '{covariate}' is constant in the selected cohorts. "
                "Review the declared model; requested covariates are not dropped automatically."
            )

    feature_count = 0
    seen_features: set[str] = set()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with matrix_path.open("r", encoding="utf-8", newline="") as source, output_path.open(
        "w", encoding="utf-8", newline=""
    ) as target:
        reader = csv.reader(source, delimiter=delimiter)
        next(reader, None)
        writer = csv.writer(target, delimiter="\t", lineterminator="\n")
        writer.writerow(["gene_id", *[sample_id for _, sample_id in selected_columns]])
        for raw_row in reader:
            if not raw_row:
                continue
            feature_id = str(raw_row[0] or "").strip()
            if not feature_id:
                continue
            if feature_id in seen_features:
                raise RuntimeError(f"Assay '{dataset_name}' matrix contains duplicate feature identifiers.")
            seen_features.add(feature_id)
            selected_values: List[str] = []
            for source_index, _sample_id in selected_columns:
                value = str(raw_row[source_index] if source_index < len(raw_row) else "").strip()
                try:
                    numeric_value = float(value)
                except ValueError:
                    raise RuntimeError(f"Assay '{dataset_name}' contains a non-numeric count-like value.") from None
                if not math.isfinite(numeric_value) or numeric_value < 0:
                    raise RuntimeError(f"Assay '{dataset_name}' contains an invalid count-like value.")
                selected_values.append(value)
            writer.writerow([feature_id, *selected_values])
            feature_count += 1

    if feature_count < 2:
        raise RuntimeError(f"Assay '{dataset_name}' has too few features for differential expression.")
    return {
        "sample_ids": [sample_id for _, sample_id in selected_columns],
        "sample_table_rows": sample_table_rows,
        "cohort_a_sample_count": cohort_a_sample_count,
        "cohort_b_sample_count": cohort_b_sample_count,
        "gene_count": feature_count,
        "analysis_covariates": covariates,
        "analysis_covariate_types": covariate_types,
    }


def _prepare_transcriptomics_differential_expression_bundle(
    data_dir: str,
    *,
    prompt: str,
    assay_id: str,
    selected_patient_ids: str,
    compare_selected_patient_ids: str,
    output_dir: Path,
    method: str = "log2_cpm_welch",
    minimum_samples_per_group: int = 1,
    required_data_type: str = "raw_counts",
) -> Dict[str, Any]:
    cohort_a_scope = _resolve_assay_scope(selected_patient_ids)
    cohort_b_scope = _resolve_assay_scope(compare_selected_patient_ids)
    cohort_a_tokens = cohort_a_scope["sample_ids"] + cohort_a_scope["patient_ids"]
    cohort_b_tokens = cohort_b_scope["sample_ids"] + cohort_b_scope["patient_ids"]
    if not cohort_a_tokens or not cohort_b_tokens:
        raise RuntimeError("Differential expression requires both Cohort A and Cohort B.")
    overlap = sorted(set(cohort_a_tokens) & set(cohort_b_tokens))
    if overlap:
        raise RuntimeError("Differential expression requires disjoint Cohort A and Cohort B selections.")

    dataset = _choose_transcriptomics_assay(data_dir, assay_id)
    dataset_name = str(dataset.get("dataset_name") or "").strip()
    if not dataset_name:
        raise RuntimeError("No valid assay name is available for differential expression.")
    dataset_data_type = str(dataset.get("data_type") or "").strip()
    expected_data_type = str(required_data_type or "").strip()
    if expected_data_type and dataset_data_type != expected_data_type:
        raise RuntimeError(
            f"Differential expression method '{method}' requires assay data type "
            f"'{expected_data_type}', not '{dataset_data_type or 'unspecified'}'."
        )

    counts_matrix_path = output_dir / "counts_matrix.tsv"
    covariates: List[str] = []
    covariate_types: Dict[str, str] = {}
    if dataset_data_type == "raw_counts":
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
            sample_rows = con.execute(
                f"""
                SELECT sample_id, patient_id
                FROM assay_samples
                WHERE {" AND ".join([where_clauses[0], "(" + " OR ".join(where_clauses[1:]) + ")"])}
                ORDER BY sample_id
                """,
                query_params,
            ).fetchall()
            if not sample_rows:
                raise RuntimeError(f"No assay samples overlap the current Analysis scope for assay '{dataset_name}'.")

            sample_table_rows = []
            sample_ids = []
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
                    raise RuntimeError(
                        "Differential expression requires disjoint sample selections across Cohort A and Cohort B."
                    )
                if not belongs_to_a and not belongs_to_b:
                    continue
                cohort = "A" if belongs_to_a else "B"
                sample_ids.append(sample_text)
                sample_table_rows.append(
                    {
                        "sample_id": sample_text,
                        "patient_id": patient_text,
                        "cohort": cohort,
                        "group_label": "Cohort A" if cohort == "A" else "Cohort B",
                    }
                )
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
            if gene_text and sample_text:
                matrix_values[gene_text][sample_text] = int(raw_count or 0)
        counts_matrix_rows: List[Dict[str, Any]] = []
        for gene_id in sorted(matrix_values):
            row: Dict[str, Any] = {"gene_id": gene_id}
            gene_counts = matrix_values[gene_id]
            for sample_id in sample_ids:
                row[sample_id] = gene_counts.get(sample_id, 0)
            counts_matrix_rows.append(row)
        if not counts_matrix_rows:
            raise RuntimeError(
                f"No transcript count rows are available for dataset '{dataset_name}' in the selected cohorts."
            )
        _write_tsv(counts_matrix_path, ["gene_id", *sample_ids], counts_matrix_rows)
        gene_count = len(counts_matrix_rows)
    elif dataset_data_type == "rsem_expected_counts":
        exported = _export_manifest_count_like_matrix(
            data_dir,
            dataset_name=dataset_name,
            cohort_a_scope=cohort_a_scope,
            cohort_b_scope=cohort_b_scope,
            output_path=counts_matrix_path,
        )
        sample_ids = list(exported["sample_ids"])
        sample_table_rows = list(exported["sample_table_rows"])
        cohort_a_sample_count = int(exported["cohort_a_sample_count"])
        cohort_b_sample_count = int(exported["cohort_b_sample_count"])
        gene_count = int(exported["gene_count"])
        covariates = list(exported["analysis_covariates"])
        covariate_types = dict(exported["analysis_covariate_types"])
    else:
        raise RuntimeError(f"Assay data type '{dataset_data_type or 'unspecified'}' is not a supported count-like matrix.")

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
    cohort_a_path = output_dir / "cohort_a.tsv"
    cohort_b_path = output_dir / "cohort_b.tsv"
    params_path = output_dir / "params.yaml"
    manifest_path = output_dir / "manifest.yaml"
    _write_tsv(sample_table_path, ["sample_id", "patient_id", "cohort", "group_label", *covariates], sample_table_rows)
    _write_tsv(cohort_a_path, ["patient_id", "sample_id", "cohort"], cohort_a_rows)
    _write_tsv(cohort_b_path, ["patient_id", "sample_id", "cohort"], cohort_b_rows)
    params_payload = {
        "analysis_type": "differential_expression",
        "method": str(method or "log2_cpm_welch").strip(),
        "input_data_type": dataset_data_type,
        "prompt": str(prompt or "").strip(),
        "dataset_name": dataset_name,
        "contrast": {"numerator": "Cohort A", "denominator": "Cohort B"},
        "minimum_samples_per_group": max(1, int(minimum_samples_per_group or 1)),
    }
    _write_yaml(params_path, params_payload)
    manifest_payload = {
        "version": 1,
        "analysis_type": "transcriptomics_differential_expression",
        "dataset_name": dataset_name,
        "input_data_type": dataset_data_type,
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
    covariates_path = None
    if method == "limma_voom":
        covariates_path = output_dir / "analysis_covariates.tsv"
        _write_tsv(covariates_path, ["name", "type"],
                   [{"name": name, "type": covariate_types[name]} for name in covariates])
        params_payload.update(
            analysis_covariates=covariates,
            analysis_covariate_types=covariate_types,
            adjustment_status="covariate_adjusted" if covariates else "unadjusted_exploratory",
            missing_covariate_policy="reject_selected_missing",
        )
        _write_yaml(params_path, params_payload)
        manifest_payload["inputs"]["analysis_covariates"] = covariates_path.name
        manifest_payload["outputs"].update(
            design_matrix="design_matrix.tsv", contrast="contrast.tsv", gene_filter="gene_filter.tsv",
            model="model.json", normalization_factors="normalization_factors.tsv", session_info="session_info.txt",
        )
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
        "gene_count": gene_count,
        "data_type": dataset_data_type,
        "covariates_path": covariates_path,
        "analysis_covariates": covariates,
        "analysis_covariate_types": covariate_types,
    }


def _tabular_delimiter(header_line: str) -> str:
    candidates = ("\t", ";", ",")
    parsed_widths = {
        delimiter: len(next(csv.reader([str(header_line or "")], delimiter=delimiter), []))
        for delimiter in candidates
    }
    return max(candidates, key=lambda value: parsed_widths[value])


def _delimiter_name(delimiter: str) -> str:
    return {"\t": "tab", ";": "semicolon", ",": "comma"}.get(delimiter, "comma")


def _prepare_quantitative_assay_comparison_bundle(
    data_dir: str,
    *,
    prompt: str,
    assay_id: str,
    selected_patient_ids: str,
    compare_selected_patient_ids: str,
    output_dir: Path,
) -> Dict[str, Any]:
    if len(query_store_module._workspace_dataset_ids(data_dir)) > 1:
        raise RuntimeError(
            "Compact-assay comparison v1 supports single-dataset workspaces only; "
            "select exactly one dataset before running this analysis."
        )
    wanted_assay = str(assay_id or "").strip()
    if not wanted_assay:
        raise RuntimeError("Compact-assay comparison requires one explicitly selected assay.")
    item = query_store_module._queryable_external_assay_item(data_dir, assay_id=wanted_assay)
    if item is None:
        raise RuntimeError("The selected assay is not a queryable immune-cell or quantitative-serology assay.")

    modality = str(item.get("modality") or "").strip().lower()
    data_type = str(item.get("data_type") or "").strip().lower()
    allowed_contracts = {
        ("flow_cytometry", "cell_population_abundance"),
        ("serology", "quantitative_measurement"),
    }
    if (modality, data_type) not in allowed_contracts:
        raise RuntimeError("The selected assay does not use a supported quantitative compact-assay contract.")
    if not str(item.get("sample_metadata_file") or "").strip():
        raise RuntimeError(
            "Compact-assay inference requires a declared sample_metadata_file with explicit sample-to-patient linkage."
        )

    try:
        matrix_path = query_store_module._external_assay_matrix_path(data_dir, item)
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc
    try:
        with matrix_path.open("r", encoding="utf-8-sig", newline="") as handle:
            first_line = handle.readline()
    except (OSError, UnicodeDecodeError, csv.Error):
        raise RuntimeError("The selected assay matrix header cannot be read.") from None
    if not first_line:
        raise RuntimeError("The selected assay matrix is empty.")
    delimiter = _tabular_delimiter(first_line)
    header = next(csv.reader([first_line], delimiter=delimiter), [])
    if len(header) < 2:
        raise RuntimeError("The selected assay matrix has no sample columns.")
    matrix_sample_ids = [str(value or "").strip() for value in header[1:]]
    if any(not value for value in matrix_sample_ids) or len(matrix_sample_ids) != len(set(matrix_sample_ids)):
        raise RuntimeError("The selected assay matrix contains invalid sample identifiers.")

    root = query_store_module._manifest_item_root(data_dir, item)
    try:
        linkage = query_store_module._manifest_assay_sample_patient_links(
            root,
            item,
            matrix_sample_ids,
            require_complete_metadata=True,
        )
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc
    links = {
        str(sample_id or "").strip(): str(patient_id or "").strip()
        for sample_id, patient_id in dict(linkage.get("links") or {}).items()
        if str(sample_id or "").strip() and str(patient_id or "").strip()
    }
    if len(links) != len(matrix_sample_ids) or any(sample_id not in links for sample_id in matrix_sample_ids):
        raise RuntimeError("Every compact-assay sample must have explicit patient linkage metadata.")

    cohort_a_tokens = set(_assay_scope_tokens(selected_patient_ids))
    cohort_b_tokens = set(_assay_scope_tokens(compare_selected_patient_ids))
    if not cohort_a_tokens or not cohort_b_tokens:
        raise RuntimeError("Compact-assay comparison requires both Cohort A and Cohort B.")
    if cohort_a_tokens.intersection(cohort_b_tokens):
        raise RuntimeError("Compact-assay comparison requires disjoint Cohort A and Cohort B selections.")

    sample_rows: List[Dict[str, Any]] = []
    for sample_id in matrix_sample_ids:
        patient_id = links[sample_id]
        belongs_to_a = sample_id in cohort_a_tokens or patient_id in cohort_a_tokens
        belongs_to_b = sample_id in cohort_b_tokens or patient_id in cohort_b_tokens
        if belongs_to_a and belongs_to_b:
            raise RuntimeError("Compact-assay comparison requires disjoint linked samples across cohorts.")
        if not belongs_to_a and not belongs_to_b:
            continue
        cohort = "A" if belongs_to_a else "B"
        sample_rows.append(
            {
                "sample_id": sample_id,
                "patient_id": patient_id,
                "cohort": cohort,
                "group_label": "Cohort A" if cohort == "A" else "Cohort B",
            }
        )
    cohort_counts = Counter(row["cohort"] for row in sample_rows)
    if cohort_counts.get("A", 0) < 3 or cohort_counts.get("B", 0) < 3:
        raise RuntimeError(
            "Compact-assay comparison requires at least three linked samples in Cohort A and Cohort B."
        )
    patient_counts = Counter(str(row["patient_id"]) for row in sample_rows)
    if any(count > 1 for count in patient_counts.values()):
        raise RuntimeError(
            "Compact-assay comparison v1 requires one independent sample per patient."
        )
    clinical_patient_ids = set(query_store_module.patient_inventory(data_dir))
    selected_patient_set = set(patient_counts)
    missing_clinical = selected_patient_set - clinical_patient_ids
    if not clinical_patient_ids or missing_clinical:
        raise RuntimeError(
            "Compact-assay comparison requires complete clinical linkage for every selected patient."
        )

    feature_count = 0
    seen_features: set[str] = set()
    try:
        with matrix_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle, delimiter=delimiter)
            next(reader, None)
            for row in reader:
                if not row:
                    continue
                if len(row) != len(matrix_sample_ids) + 1:
                    raise RuntimeError("The selected assay contains an invalid matrix row width.")
                feature_id = str(row[0] or "").strip()
                if not feature_id:
                    raise RuntimeError("The selected assay contains an empty feature identifier.")
                if feature_id in seen_features:
                    raise RuntimeError("The selected assay contains duplicate feature identifiers.")
                seen_features.add(feature_id)
                for token in row[1:]:
                    try:
                        query_store_module._external_numeric_value(token)
                    except ValueError as exc:
                        raise RuntimeError(str(exc)) from exc
                feature_count += 1
    except (OSError, UnicodeDecodeError, csv.Error):
        raise RuntimeError("The selected assay matrix cannot be read.") from None
    if feature_count < 1:
        raise RuntimeError("The selected assay contains no quantitative features.")
    try:
        declared_feature_count = int(item.get("feature_count") or 0)
    except (TypeError, ValueError):
        raise RuntimeError("The selected assay declares an invalid feature_count.") from None
    if declared_feature_count and declared_feature_count != feature_count:
        raise RuntimeError("The selected assay feature count does not match its manifest declaration.")

    dataset_name = str(item.get("assay_id") or wanted_assay).strip()
    assay_label = str(item.get("label") or dataset_name).strip() or dataset_name
    output_dir.mkdir(parents=True, exist_ok=True)
    private_input_dir = output_dir / ".analysis-private"
    private_input_dir.mkdir(mode=0o700, exist_ok=True)
    sample_table_path = private_input_dir / "sample_table.tsv"
    params_path = output_dir / "params.yaml"
    manifest_path = output_dir / "manifest.yaml"
    _write_tsv(
        sample_table_path,
        ["sample_id", "patient_id", "cohort", "group_label"],
        sample_rows,
    )
    source_sha256 = str(item.get("sha256") or item.get("checksum") or "").strip()
    source_fingerprint_status = "declared_not_recomputed" if source_sha256 else "not_declared"
    _write_yaml(
        params_path,
        {
            "analysis_type": "quantitative_compact_assay_comparison",
            "method": "two_sided_wilcoxon_rank_sum",
            "multiple_testing": "benjamini_hochberg_across_tested_features",
            "minimum_complete_samples_per_group": 3,
            "effect_size": "rank_biserial_2U_over_nA_nB_minus_1",
            "adjustment_status": "unadjusted_exploratory",
            "input_scale": "supplied_values_untransformed",
            "missing_value_handling": "featurewise_complete_cases",
            "dataset_name": dataset_name,
            "modality": modality,
            "data_type": data_type,
            "prompt": str(prompt or "").strip(),
            "source_matrix": "manifest_backed_external_file",
            "source_matrix_materialized_in_duckdb": False,
            "source_matrix_copied_to_job": False,
            "source_sha256": source_sha256,
            "source_fingerprint_status": source_fingerprint_status,
            "contrast": {"numerator": "Cohort A", "denominator": "Cohort B"},
        },
    )
    _write_yaml(
        manifest_path,
        {
            "version": 1,
            "analysis_type": "quantitative_compact_assay_comparison",
            "dataset_name": dataset_name,
            "assay_label": assay_label,
            "modality": modality,
            "data_type": data_type,
            "feature_count": feature_count,
            "patient_count": len(selected_patient_set),
            "cohort_sample_counts": dict(cohort_counts),
            "inputs": {
                "matrix": "manifest-backed external assay (not copied)",
                "sample_linkage": "temporary protected runtime input (removed after execution)",
                "params": params_path.name,
            },
            "outputs": {
                "results_table": "compact_assay_results.tsv",
                "summary": "summary.json",
                "plot": "effect_plot.png",
            },
        },
    )
    return {
        "dataset_name": dataset_name,
        "assay_label": assay_label,
        "modality": modality,
        "data_type": data_type,
        "matrix_path": matrix_path,
        "delimiter_name": _delimiter_name(delimiter),
        "sample_table_path": sample_table_path,
        "params_path": params_path,
        "manifest_path": manifest_path,
        "feature_count": feature_count,
        "sample_count": len(sample_rows),
        "patient_count": len(selected_patient_set),
        "cohort_a_sample_count": int(cohort_counts.get("A", 0)),
        "cohort_b_sample_count": int(cohort_counts.get("B", 0)),
        "cohort_a_patient_count": len({row["patient_id"] for row in sample_rows if row["cohort"] == "A"}),
        "cohort_b_patient_count": len({row["patient_id"] for row in sample_rows if row["cohort"] == "B"}),
        "source_sha256": source_sha256,
        "source_fingerprint_status": source_fingerprint_status,
        "clinical_linkage_status": "complete_selected_scope",
    }


def _choose_methylation_assay(data_dir: str, requested_name: str = "") -> Dict[str, Any]:
    compatible: List[Dict[str, Any]] = []
    for raw_item in query_store_module._assay_manifest_items(data_dir):
        item = dict(raw_item or {})
        modality = str(item.get("modality") or "").strip().lower().replace("-", "_")
        data_type = str(item.get("data_type") or "").strip().lower()
        if modality not in {"methylation", "dna_methylation"} or data_type != "m_values":
            continue
        assay_id = str(item.get("assay_id") or Path(str(item.get("file") or "")).stem).strip()
        if not assay_id:
            continue
        item["assay_id"] = assay_id
        compatible.append(item)

    wanted = str(requested_name or "").strip()
    if wanted:
        for item in compatible:
            if item["assay_id"] == wanted:
                return item
        raise RuntimeError(f"Methylation M-value assay '{wanted}' is not available in the current workspace.")
    if not compatible:
        raise RuntimeError("No manifest-backed methylation M-value assay is available in the current workspace.")
    if len(compatible) != 1:
        raise RuntimeError("Methylation analysis requires one explicitly selected M-value assay.")
    return compatible[0]


def _resolve_assay_manifest_file(
    data_dir: str,
    item: Dict[str, Any],
    field: str,
    *,
    required: bool,
) -> Path | None:
    relative_file = str(item.get(field) or "").strip()
    if not relative_file:
        if required:
            raise RuntimeError(f"Assay '{item.get('assay_id') or 'selected assay'}' is missing its {field} declaration.")
        return None
    root = query_store_module._manifest_item_root(data_dir, item)
    path = (root / relative_file).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        raise RuntimeError(f"Assay '{item.get('assay_id') or 'selected assay'}' uses an invalid {field} location.") from None
    if not path.is_file():
        raise RuntimeError(f"Assay '{item.get('assay_id') or 'selected assay'}' declared {field} is unavailable.")
    return path


def _methylation_matrix_header(matrix_path: Path, assay_id: str) -> List[str]:
    try:
        with matrix_path.open("r", encoding="utf-8-sig", newline="") as handle:
            first_line = handle.readline()
            if not first_line:
                raise RuntimeError(f"Methylation assay '{assay_id}' matrix is empty.")
            delimiter = _tabular_delimiter(first_line)
            handle.seek(0)
            header = next(csv.reader(handle, delimiter=delimiter), [])
    except (OSError, UnicodeDecodeError) as exc:
        raise RuntimeError(f"Methylation assay '{assay_id}' matrix header cannot be read.") from exc
    if len(header) < 3:
        raise RuntimeError(f"Methylation assay '{assay_id}' requires a feature column and at least two sample columns.")
    sample_ids = [str(value or "").strip() for value in header[1:]]
    if any(not value for value in sample_ids):
        raise RuntimeError(f"Methylation assay '{assay_id}' matrix contains an empty sample identifier.")
    if len(set(sample_ids)) != len(sample_ids):
        raise RuntimeError(f"Methylation assay '{assay_id}' matrix contains duplicate sample identifiers.")
    return sample_ids


def _methylation_feature_panel(data_dir: str, item: Dict[str, Any]) -> Dict[str, Any] | None:
    raw_panel = item.get("feature_panel")
    if raw_panel is None:
        return None
    if not isinstance(raw_panel, dict):
        raise RuntimeError("Methylation feature_panel must be an object.")
    panel_id = str(raw_panel.get("panel_id") or "").strip()
    panel_version = str(raw_panel.get("panel_version") or "").strip()
    label = str(raw_panel.get("label") or panel_id).strip()
    if not panel_id or not panel_version or not label:
        raise RuntimeError("Methylation feature_panel requires panel_id, panel_version, and label.")
    counts: Dict[str, int] = {}
    for field in ("requested_feature_count", "matched_feature_count", "missing_feature_count"):
        try:
            counts[field] = int(raw_panel.get(field))
        except (TypeError, ValueError):
            raise RuntimeError(f"Methylation feature_panel requires an integer {field}.") from None
        if counts[field] < 0:
            raise RuntimeError(f"Methylation feature_panel {field} must not be negative.")
    if counts["matched_feature_count"] < 1:
        raise RuntimeError("Methylation feature_panel must contain at least one matched feature.")
    try:
        excluded_feature_count = int(raw_panel.get("excluded_nonfinite_feature_count") or 0)
    except (TypeError, ValueError):
        raise RuntimeError("Methylation feature_panel excluded_nonfinite_feature_count must be an integer.") from None
    if excluded_feature_count < 0:
        raise RuntimeError("Methylation feature_panel excluded_nonfinite_feature_count must not be negative.")
    if counts["requested_feature_count"] != (
        counts["matched_feature_count"] + counts["missing_feature_count"] + excluded_feature_count
    ):
        raise RuntimeError("Methylation feature_panel match counts are inconsistent.")
    declared_feature_count = int(item.get("feature_count") or 0)
    if declared_feature_count and declared_feature_count != counts["matched_feature_count"]:
        raise RuntimeError("Methylation feature_panel matched count does not match the assay feature_count.")
    panel_file = str(raw_panel.get("panel_file") or "").strip()
    panel_sha256 = str(raw_panel.get("panel_sha256") or "").strip().lower()
    if not panel_file or not re.fullmatch(r"[0-9a-f]{64}", panel_sha256):
        raise RuntimeError("Methylation feature_panel requires a panel_file and SHA-256 fingerprint.")
    root = query_store_module._manifest_item_root(data_dir, item)
    panel_path = (root / panel_file).resolve()
    try:
        panel_path.relative_to(root)
    except ValueError:
        raise RuntimeError("Methylation feature_panel uses an invalid panel_file location.") from None
    if not panel_path.is_file():
        raise RuntimeError("Methylation feature_panel definition is unavailable.")
    digest = hashlib.sha256(panel_path.read_bytes()).hexdigest()
    if digest != panel_sha256:
        raise RuntimeError("Methylation feature_panel definition does not match its SHA-256 fingerprint.")
    return {
        "panel_id": panel_id,
        "panel_version": panel_version,
        "label": label,
        **counts,
        "excluded_nonfinite_feature_count": excluded_feature_count,
        "panel_sha256": panel_sha256,
        "source_matrix_sha256": str(raw_panel.get("source_matrix_sha256") or "").strip().lower(),
        "source_publication_doi": str(raw_panel.get("source_publication_doi") or "").strip(),
        "source_publication_url": str(raw_panel.get("source_publication_url") or "").strip(),
        "scientific_selection_rule": str(raw_panel.get("scientific_selection_rule") or "").strip(),
        "independent_of_target_cohort": bool(raw_panel.get("independent_of_target_cohort")),
    }


def _manifest_analysis_covariates(item: Dict[str, Any], *, assay_label: str = "Methylation") -> List[str]:
    raw_covariates = item.get("analysis_covariates")
    if raw_covariates is None:
        return []
    if not isinstance(raw_covariates, list):
        raise RuntimeError(f"{assay_label} analysis_covariates must be a list.")
    covariates: List[str] = []
    reserved = {"sample_id", "patient_id", "cohort", "group_label"}
    for raw_value in raw_covariates:
        value = str(raw_value or "").strip()
        if not value:
            raise RuntimeError(f"{assay_label} analysis_covariates must not contain empty names.")
        if value in reserved:
            raise RuntimeError(f"{assay_label} analysis covariate '{value}' is reserved.")
        if value in covariates:
            raise RuntimeError(f"{assay_label} analysis covariate '{value}' is declared more than once.")
        if "\n" in value or "\r" in value or "\t" in value or "," in value:
            raise RuntimeError(f"{assay_label} analysis covariate names must not contain tabs, commas, or newlines.")
        covariates.append(value)
    return covariates


def _manifest_analysis_covariate_types(
    item: Dict[str, Any], covariates: List[str], *, assay_label: str = "Methylation"
) -> Dict[str, str]:
    raw_types = item.get("analysis_covariate_types")
    if not covariates:
        if raw_types not in (None, {}):
            raise RuntimeError(f"{assay_label} analysis_covariate_types requires matching analysis_covariates.")
        return {}
    if not isinstance(raw_types, dict):
        raise RuntimeError(
            f"{assay_label} analysis_covariate_types must declare numeric or categorical for every analysis covariate."
        )
    extra_names = sorted(str(value or "").strip() for value in raw_types if str(value or "").strip() not in covariates)
    if extra_names:
        raise RuntimeError(
            f"{assay_label} analysis_covariate_types includes undeclared covariates: " + ", ".join(extra_names) + "."
        )
    normalized: Dict[str, str] = {}
    for covariate in covariates:
        value = str(raw_types.get(covariate) or "").strip().lower()
        if value not in {"numeric", "categorical"}:
            raise RuntimeError(
                f"{assay_label} analysis covariate '{covariate}' must have type numeric or categorical."
            )
        normalized[covariate] = value
    return normalized


def _read_manifest_sample_metadata(
    data_dir: str,
    item: Dict[str, Any],
    covariates: List[str],
    *,
    assay_label: str = "Methylation",
    exact_sample_ids: bool = False,
) -> Dict[str, Dict[str, str]]:
    metadata_path = _resolve_assay_manifest_file(
        data_dir,
        item,
        "sample_metadata_file",
        required=True,
    )
    assert metadata_path is not None
    try:
        with metadata_path.open("r", encoding="utf-8-sig", newline="") as handle:
            first_line = handle.readline()
            if not first_line:
                raise RuntimeError(f"{assay_label} assay '{item['assay_id']}' sample metadata is empty.")
            delimiter = _tabular_delimiter(first_line)
            handle.seek(0)
            reader = csv.DictReader(handle, delimiter=delimiter)
            fieldnames = [str(value or "").strip() for value in (reader.fieldnames or [])]
            if any(not value for value in fieldnames) or len(set(fieldnames)) != len(fieldnames):
                raise RuntimeError(f"{assay_label} sample metadata contains empty or duplicate column names.")
            required_columns = {"sample_id"} if exact_sample_ids else {"sample_id", "patient_id"}
            if not required_columns.issubset(fieldnames):
                raise RuntimeError(f"{assay_label} sample metadata must contain sample_id and patient_id columns.")
            missing_covariates = [value for value in covariates if value not in fieldnames]
            if missing_covariates:
                raise RuntimeError(
                    f"{assay_label} sample metadata is missing declared analysis covariates: "
                    + ", ".join(missing_covariates)
                    + "."
                )
            rows: Dict[str, Dict[str, str]] = {}
            for raw_row in reader:
                if None in raw_row:
                    raise RuntimeError(f"{assay_label} sample metadata contains an ambiguous row with extra fields.")
                row = {str(key or "").strip(): str(value or "").strip() for key, value in raw_row.items()}
                sample_id = row.get("sample_id", "")
                if not sample_id:
                    raise RuntimeError(f"{assay_label} sample metadata contains an empty sample identifier.")
                if sample_id in rows:
                    raise RuntimeError(f"{assay_label} sample metadata contains duplicate sample identifiers.")
                if exact_sample_ids:
                    row["patient_id"] = sample_id
                if not row.get("patient_id", ""):
                    raise RuntimeError(f"{assay_label} sample metadata contains an empty patient identifier.")
                rows[sample_id] = row
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        raise RuntimeError(f"{assay_label} assay '{item['assay_id']}' sample metadata cannot be read.") from exc
    return rows


def _methylation_sample_rows(
    sample_ids: List[str],
    metadata: Dict[str, Dict[str, str]],
    *,
    covariates: List[str],
    selected_patient_ids: str,
    compare_selected_patient_ids: str,
    require_compare: bool,
) -> List[Dict[str, str]]:
    cohort_a_tokens = set(_assay_scope_tokens(selected_patient_ids))
    cohort_b_tokens = set(_assay_scope_tokens(compare_selected_patient_ids))
    cohort_a_selected = bool(cohort_a_tokens)
    cohort_b_selected = bool(cohort_b_tokens)
    if require_compare and (not cohort_a_selected or not cohort_b_selected):
        raise RuntimeError("Differential methylation requires both Cohort A and Cohort B.")

    use_workspace = not cohort_a_selected and not cohort_b_selected
    rows: List[Dict[str, str]] = []
    for sample_id in sample_ids:
        source = dict(metadata[sample_id])
        patient_id = str(source["patient_id"]).strip()
        belongs_to_a = sample_id in cohort_a_tokens or patient_id in cohort_a_tokens
        belongs_to_b = sample_id in cohort_b_tokens or patient_id in cohort_b_tokens
        if belongs_to_a and belongs_to_b:
            raise RuntimeError("Methylation analysis requires disjoint sample selections across Cohort A and Cohort B.")
        if use_workspace:
            cohort = "Workspace"
        elif belongs_to_a:
            cohort = "A"
        elif belongs_to_b:
            cohort = "B"
        else:
            continue
        row = {
            "sample_id": sample_id,
            "patient_id": patient_id,
            "cohort": cohort,
            "group_label": "Workspace" if cohort == "Workspace" else f"Cohort {cohort}",
        }
        for covariate in covariates:
            row[covariate] = str(source.get(covariate) or "").strip()
        rows.append(row)

    if not rows:
        raise RuntimeError("No methylation samples overlap the current Analysis scope.")
    if require_compare:
        cohort_a_count = sum(row["cohort"] == "A" for row in rows)
        cohort_b_count = sum(row["cohort"] == "B" for row in rows)
        if cohort_a_count < 2 or cohort_b_count < 2:
            raise RuntimeError(
                "Differential methylation requires at least two samples in Cohort A and two samples in Cohort B."
            )
        patient_counts = Counter(row["patient_id"] for row in rows)
        if any(value > 1 for value in patient_counts.values()):
            raise RuntimeError(
                "Differential methylation v1 requires one sample per patient and cannot reuse a patient across cohorts."
            )
    elif len(rows) < 2:
        raise RuntimeError("Methylation QC and PCA requires at least two samples in the current scope.")
    return rows


def _prepare_methylation_analysis_bundle(
    data_dir: str,
    *,
    prompt: str,
    assay_id: str,
    selected_patient_ids: str,
    compare_selected_patient_ids: str,
    output_dir: Path,
    analysis_type: str,
) -> Dict[str, Any]:
    if analysis_type not in {"qc_pca", "differential_methylation"}:
        raise RuntimeError(f"Unsupported methylation analysis type '{analysis_type}'.")
    if len(query_store_module._workspace_dataset_ids(data_dir)) > 1:
        raise RuntimeError(
            "Methylation analysis v1 supports single-dataset workspaces only; "
            "select exactly one dataset before running this analysis."
        )
    item = _choose_methylation_assay(data_dir, assay_id)
    dataset_name = str(item["assay_id"])
    matrix_path = _resolve_assay_manifest_file(data_dir, item, "file", required=True)
    assert matrix_path is not None
    feature_panel = _methylation_feature_panel(data_dir, item)
    matrix_sample_ids = _methylation_matrix_header(matrix_path, dataset_name)
    declared_covariates = _manifest_analysis_covariates(item)
    covariate_types = _manifest_analysis_covariate_types(item, declared_covariates)
    if not str(item.get("sample_metadata_file") or "").strip():
        raise RuntimeError(
            f"Assay '{dataset_name}' is missing its sample_metadata_file declaration; "
            "methylation runners require explicit sample-to-patient linkage."
        )
    root = query_store_module._manifest_item_root(data_dir, item)
    try:
        linkage = query_store_module._manifest_assay_sample_patient_links(
            root,
            item,
            matrix_sample_ids,
            require_complete_metadata=True,
        )
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc
    metadata = _read_manifest_sample_metadata(data_dir, item, declared_covariates)
    explicit_links = dict(linkage.get("links") or {})
    for sample_id, patient_id in explicit_links.items():
        if str(metadata[sample_id].get("patient_id") or "").strip() != str(patient_id or "").strip():
            raise RuntimeError("Methylation sample metadata produced ambiguous patient linkage.")
    sample_rows = _methylation_sample_rows(
        matrix_sample_ids,
        metadata,
        covariates=declared_covariates,
        selected_patient_ids=selected_patient_ids,
        compare_selected_patient_ids=compare_selected_patient_ids,
        require_compare=analysis_type == "differential_methylation",
    )
    clinical_patient_ids = set(query_store_module.patient_inventory(data_dir))
    selected_patient_ids_set = {str(row.get("patient_id") or "").strip() for row in sample_rows}
    selected_patient_ids_set.discard("")
    missing_clinical_link_count = len(selected_patient_ids_set - clinical_patient_ids)
    if not clinical_patient_ids or missing_clinical_link_count:
        raise RuntimeError(
            "Methylation analysis requires explicit clinical linkage for every selected patient; "
            f"{missing_clinical_link_count or len(selected_patient_ids_set)} selected patient(s) are not linked."
        )

    invalid_numeric_covariates: List[str] = []
    for covariate, covariate_type in covariate_types.items():
        if covariate_type != "numeric":
            continue
        for row in sample_rows:
            raw_value = str(row.get(covariate) or "").strip()
            if not raw_value:
                continue
            try:
                numeric_value = float(raw_value)
            except ValueError:
                invalid_numeric_covariates.append(covariate)
                break
            if not math.isfinite(numeric_value):
                invalid_numeric_covariates.append(covariate)
                break
    if invalid_numeric_covariates:
        raise RuntimeError(
            "Methylation numeric covariates contain non-numeric or non-finite values: "
            + ", ".join(sorted(set(invalid_numeric_covariates)))
            + "."
        )

    incomplete_covariates = [
        covariate
        for covariate in declared_covariates
        if any(not str(row.get(covariate) or "").strip() for row in sample_rows)
    ]
    if incomplete_covariates and analysis_type == "differential_methylation":
        raise RuntimeError(
            "Differential methylation requires complete declared covariates; missing values were found for: "
            + ", ".join(incomplete_covariates)
            + "."
        )
    usable_covariates: List[str] = []
    dropped_covariates: List[Dict[str, str]] = []
    for covariate in declared_covariates:
        if covariate in incomplete_covariates:
            dropped_covariates.append({"name": covariate, "reason": "incomplete"})
            continue
        levels = {str(row.get(covariate) or "").strip() for row in sample_rows}
        if len(levels) < 2:
            dropped_covariates.append({"name": covariate, "reason": "constant_in_scope"})
            continue
        usable_covariates.append(covariate)

    try:
        pca_feature_limit = int(item.get("pca_feature_limit") or 5_000)
    except (TypeError, ValueError):
        raise RuntimeError("Methylation pca_feature_limit must be an integer.") from None
    if pca_feature_limit < 100 or pca_feature_limit > 50_000:
        raise RuntimeError("Methylation pca_feature_limit must be between 100 and 50000.")

    output_dir.mkdir(parents=True, exist_ok=True)
    sample_table_path = output_dir / "sample_table.tsv"
    covariates_path = output_dir / "analysis_covariates.tsv"
    params_path = output_dir / "params.yaml"
    manifest_path = output_dir / "manifest.yaml"
    _write_tsv(
        sample_table_path,
        ["sample_id", "patient_id", "cohort", "group_label", *declared_covariates],
        sample_rows,
    )
    _write_tsv(
        covariates_path,
        ["name", "type"],
        [{"name": value, "type": covariate_types[value]} for value in usable_covariates],
    )
    cohort_counts = Counter(row["cohort"] for row in sample_rows)
    source_sha256 = str(item.get("sha256") or item.get("checksum") or "").strip()
    source_fingerprint_status = "declared_not_recomputed" if source_sha256 else "not_declared"
    adjustment_status = "covariate_adjusted" if usable_covariates else "unadjusted_exploratory"
    params_payload = {
        "analysis_type": analysis_type,
        "method": "streaming_sample_gram_pca" if analysis_type == "qc_pca" else "limma_m_values",
        "input_data_type": "m_values",
        "dataset_name": dataset_name,
        "prompt": str(prompt or "").strip(),
        "source_matrix": "manifest_backed_external_file",
        "source_matrix_materialized_in_duckdb": False,
        "source_matrix_copied_to_job": False,
        "source_sha256": source_sha256,
        "source_fingerprint_status": source_fingerprint_status,
        "source_fingerprint_verified_for_run": False,
        "declared_feature_count": int(item.get("feature_count") or 0),
        "feature_view": "feature_panel" if feature_panel else "complete_assay",
        "feature_panel": feature_panel,
        "declared_covariates": declared_covariates,
        "analysis_covariate_types": covariate_types,
        "covariates_used": usable_covariates,
        "covariates_dropped": dropped_covariates,
        "adjustment_status": adjustment_status if analysis_type == "differential_methylation" else None,
        "clinical_linkage_status": "complete_selected_scope",
        "clinical_linked_patient_count": len(selected_patient_ids_set),
        "pca_feature_limit": pca_feature_limit if analysis_type == "qc_pca" else None,
        "missing_value_handling": (
            "probe_mean_for_pca_and_explicit_sample_qc_counts"
            if analysis_type == "qc_pca"
            else "exclude_probes_with_any_missing_selected_sample_value"
        ),
        "contrast": {"numerator": "Cohort A", "denominator": "Cohort B"}
        if analysis_type == "differential_methylation"
        else None,
    }
    _write_yaml(params_path, params_payload)
    outputs = {
        "sample_qc": "sample_qc.tsv",
        "pca_scores": "pca_scores.tsv",
        "pca_variance": "pca_variance.tsv",
        "covariate_associations": "pca_covariate_associations.tsv",
        "summary": "summary.json",
        "plot": "pca_plot.png",
    } if analysis_type == "qc_pca" else {
        "results_table": "dm_results.tsv",
        "volcano_points": "volcano_points.tsv",
        "summary": "summary.json",
        "plot": "volcano_plot.png",
    }
    _write_yaml(
        manifest_path,
        {
            "version": 1,
            "analysis_type": f"methylation_{analysis_type}",
            "dataset_name": dataset_name,
            "input_data_type": "m_values",
            "feature_view": "feature_panel" if feature_panel else "complete_assay",
            "feature_panel": feature_panel,
            "sample_count": len(sample_rows),
            "patient_count": len({row["patient_id"] for row in sample_rows}),
            "cohort_sample_counts": dict(cohort_counts),
            "inputs": {
                "matrix": "manifest-backed external assay (not copied)",
                "sample_table": sample_table_path.name,
                "analysis_covariates": covariates_path.name,
                "params": params_path.name,
            },
            "outputs": outputs,
        },
    )
    return {
        "dataset_name": dataset_name,
        "matrix_path": matrix_path,
        "sample_table_path": sample_table_path,
        "covariates_path": covariates_path,
        "params_path": params_path,
        "manifest_path": manifest_path,
        "sample_rows": sample_rows,
        "sample_count": len(sample_rows),
        "patient_count": len({row["patient_id"] for row in sample_rows}),
        "cohort_counts": dict(cohort_counts),
        "declared_covariates": declared_covariates,
        "analysis_covariate_types": covariate_types,
        "covariates_used": usable_covariates,
        "covariates_dropped": dropped_covariates,
        "pca_feature_limit": pca_feature_limit,
        "source_sha256": source_sha256,
        "source_fingerprint_status": source_fingerprint_status,
        "source_fingerprint_verified_for_run": False,
        "feature_view": "feature_panel" if feature_panel else "complete_assay",
        "feature_panel": feature_panel,
        "adjustment_status": adjustment_status if analysis_type == "differential_methylation" else "not_applicable",
        "clinical_linkage_status": "complete_selected_scope",
        "clinical_linked_patient_count": len(selected_patient_ids_set),
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


def _validate_limma_voom_bundle(bundle: Dict[str, Any]) -> None:
    sample_rows = list(bundle.get("sample_table_rows") or [])
    cohort_a_sample_count = int(bundle.get("cohort_a_sample_count") or 0)
    cohort_b_sample_count = int(bundle.get("cohort_b_sample_count") or 0)
    if cohort_a_sample_count < 2 or cohort_b_sample_count < 2:
        raise RuntimeError(
            "limma-voom differential expression requires at least two samples in Cohort A and two samples in Cohort B."
        )
    patient_counts = Counter(
        str(row.get("patient_id") or "").strip()
        for row in sample_rows
        if str(row.get("patient_id") or "").strip()
    )
    if any(count > 1 for count in patient_counts.values()):
        raise RuntimeError(
            "limma-voom differential expression v1 requires one sample per patient. "
            "Use a cross-sectional dataset or choose one sample per patient before running."
        )


def _prepare_rscript_run(
    runner_ref: str,
    *,
    binary: str,
    script_path: Path,
    prompt: str,
    data_dir: str,
    assay_id: str,
    selected_patient_ids: str,
    compare_selected_patient_ids: str,
    temp_path: Path,
) -> Dict[str, Any]:
    sensitive_command_values: List[str] = []
    private_input_paths: List[Path] = []
    methylation_bundle: Dict[str, Any] | None = None
    quantitative_assay_bundle: Dict[str, Any] | None = None
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
    elif runner_ref == "transcriptomics_deseq2_differential_expression":
        bundle = _prepare_transcriptomics_differential_expression_bundle(
            data_dir,
            prompt=prompt,
            assay_id=assay_id,
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
            "--heatmap-file",
            str(temp_path / "top_genes_heatmap.png"),
            "--heatmap-table",
            str(temp_path / "top_genes_heatmap.tsv"),
            "--heatmap-clustering",
            str(temp_path / "top_genes_heatmap_clustering.json"),
        ]
    elif runner_ref == "transcriptomics_limma_voom_differential_expression":
        bundle = _prepare_transcriptomics_differential_expression_bundle(
            data_dir, prompt=prompt, assay_id=assay_id,
            selected_patient_ids=selected_patient_ids,
            compare_selected_patient_ids=compare_selected_patient_ids,
            output_dir=temp_path, method="limma_voom",
            minimum_samples_per_group=2, required_data_type="rsem_expected_counts",
        )
        _validate_limma_voom_bundle(bundle)
        command = [binary, str(script_path), "--job-dir", str(temp_path),
            "--manifest", str(bundle["manifest_path"]), "--params", str(bundle["params_path"]),
            "--prompt", str(prompt or ""), "--dataset-name", str(bundle["dataset_name"]),
            "--sample-table", str(bundle["sample_table_path"]), "--counts-matrix", str(bundle["counts_matrix_path"]),
            "--covariates-file", str(bundle["covariates_path"]),
            "--results-table", str(temp_path / "de_results.tsv"), "--volcano-table", str(temp_path / "volcano_points.tsv"),
            "--summary-json", str(temp_path / "summary.json"), "--plot-file", str(temp_path / "volcano_plot.png")]
    elif runner_ref == "transcriptomics_hallmark_pathway_enrichment":
        bundle = _prepare_transcriptomics_differential_expression_bundle(
            data_dir,
            prompt=prompt,
            assay_id=assay_id,
            selected_patient_ids=selected_patient_ids,
            compare_selected_patient_ids=compare_selected_patient_ids,
            output_dir=temp_path,
            method="deseq2_fgsea_hallmark",
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
            str(temp_path / "pathway_results.tsv"),
            "--rankings-table",
            str(temp_path / "gene_rankings.tsv"),
            "--summary-json",
            str(temp_path / "summary.json"),
            "--plot-file",
            str(temp_path / "pathway_plot.png"),
        ]
    elif runner_ref == "methylation_qc_pca":
        bundle = _prepare_methylation_analysis_bundle(
            data_dir,
            prompt=prompt,
            assay_id=assay_id,
            selected_patient_ids=selected_patient_ids,
            compare_selected_patient_ids=compare_selected_patient_ids,
            output_dir=temp_path,
            analysis_type="qc_pca",
        )
        methylation_bundle = bundle
        matrix_path = str(bundle["matrix_path"])
        sensitive_command_values.append(matrix_path)
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
            "--matrix",
            matrix_path,
            "--sample-table",
            str(bundle["sample_table_path"]),
            "--covariates-file",
            str(bundle["covariates_path"]),
            "--feature-limit",
            str(bundle["pca_feature_limit"]),
            "--sample-qc",
            str(temp_path / "sample_qc.tsv"),
            "--pca-scores",
            str(temp_path / "pca_scores.tsv"),
            "--pca-variance",
            str(temp_path / "pca_variance.tsv"),
            "--covariate-associations",
            str(temp_path / "pca_covariate_associations.tsv"),
            "--summary-json",
            str(temp_path / "summary.json"),
            "--plot-file",
            str(temp_path / "pca_plot.png"),
        ]
    elif runner_ref == "methylation_limma_differential_methylation":
        bundle = _prepare_methylation_analysis_bundle(
            data_dir,
            prompt=prompt,
            assay_id=assay_id,
            selected_patient_ids=selected_patient_ids,
            compare_selected_patient_ids=compare_selected_patient_ids,
            output_dir=temp_path,
            analysis_type="differential_methylation",
        )
        methylation_bundle = bundle
        matrix_path = str(bundle["matrix_path"])
        sensitive_command_values.append(matrix_path)
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
            "--matrix",
            matrix_path,
            "--sample-table",
            str(bundle["sample_table_path"]),
            "--covariates-file",
            str(bundle["covariates_path"]),
            "--results-table",
            str(temp_path / "dm_results.tsv"),
            "--volcano-table",
            str(temp_path / "volcano_points.tsv"),
            "--summary-json",
            str(temp_path / "summary.json"),
            "--plot-file",
            str(temp_path / "volcano_plot.png"),
        ]
    elif runner_ref == "quantitative_assay_wilcoxon_comparison":
        bundle = _prepare_quantitative_assay_comparison_bundle(
            data_dir,
            prompt=prompt,
            assay_id=assay_id,
            selected_patient_ids=selected_patient_ids,
            compare_selected_patient_ids=compare_selected_patient_ids,
            output_dir=temp_path,
        )
        quantitative_assay_bundle = bundle
        private_input_paths.append(bundle["sample_table_path"])
        matrix_path = str(bundle["matrix_path"])
        sensitive_command_values.append(matrix_path)
        command = [
            binary,
            str(script_path),
            "--prompt",
            str(prompt or ""),
            "--dataset-name",
            str(bundle["dataset_name"]),
            "--assay-label",
            str(bundle["assay_label"]),
            "--modality",
            str(bundle["modality"]),
            "--data-type",
            str(bundle["data_type"]),
            "--matrix",
            matrix_path,
            "--delimiter-name",
            str(bundle["delimiter_name"]),
            "--sample-table",
            str(bundle["sample_table_path"]),
            "--results-table",
            str(temp_path / "compact_assay_results.tsv"),
            "--summary-json",
            str(temp_path / "summary.json"),
            "--plot-file",
            str(temp_path / "effect_plot.png"),
        ]
    else:
        raise RuntimeError(f"Unsupported Rscript analysis runner '{runner_ref}'.")
    return {
        "command": command,
        "sensitive_command_values": sensitive_command_values,
        "private_input_paths": private_input_paths,
        "methylation_bundle": methylation_bundle,
        "quantitative_assay_bundle": quantitative_assay_bundle,
    }


def run_rscript_analysis(
    runner_ref: str,
    *,
    prompt: str,
    data_dir: str,
    assay_id: str = "",
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
        # Execute the same script bytes that are retained in this run's artifacts.
        audit_dir = temp_path / "audit"
        audit_dir.mkdir(exist_ok=True)
        snapshot = audit_dir / script_path.name
        snapshot.write_bytes(script_path.read_bytes())
        if runner_ref in {"methylation_qc_pca", "methylation_limma_differential_methylation"}:
            common = script_path.parent / "analysis_r_methylation_common.R"
            (audit_dir / common.name).write_bytes(common.read_bytes())
        script_path = snapshot
        plan = _prepare_rscript_run(
            runner_ref,
            binary=binary,
            script_path=script_path,
            prompt=prompt,
            data_dir=data_dir,
            assay_id=assay_id,
            selected_patient_ids=selected_patient_ids,
            compare_selected_patient_ids=compare_selected_patient_ids,
            temp_path=temp_path,
        )
        command = plan["command"]
        sensitive_command_values = plan["sensitive_command_values"]
        private_input_paths = plan["private_input_paths"]
        methylation_bundle = plan["methylation_bundle"]
        quantitative_assay_bundle = plan["quantitative_assay_bundle"]
        try:
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=max(1, int(timeout_seconds or 30)),
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError("External Rscript analysis exceeded its configured time limit.") from None
        except OSError:
            raise RuntimeError("External Rscript analysis could not be started.") from None
        finally:
            for private_input_path in private_input_paths:
                try:
                    private_input_path.unlink(missing_ok=True)
                    private_input_path.parent.rmdir()
                except OSError:
                    # Hidden runtime inputs are also denied by the job-artifact
                    # boundary if an interrupted process prevents cleanup.
                    pass
    public_command = list(command)
    public_stdout = result.stdout or ""
    public_stderr = result.stderr or ""
    if methylation_bundle is not None or quantitative_assay_bundle is not None:
        public_command = _redact_command_job_paths(public_command, temp_path)
        public_stdout = public_stdout.replace(str(temp_path), "[job artifacts]")
        public_stderr = public_stderr.replace(str(temp_path), "[job artifacts]")
    for sensitive_value in sensitive_command_values:
        public_command = _redact_command_value(public_command, "--matrix", "[protected assay matrix]")
        public_stdout = public_stdout.replace(sensitive_value, "[protected assay matrix]")
        public_stderr = public_stderr.replace(sensitive_value, "[protected assay matrix]")
    _write_command_logs(
        target_dir=job_dir,
        command=public_command,
        stdout=public_stdout,
        stderr=public_stderr,
    )
    if result.returncode != 0:
        raise RuntimeError((public_stderr or public_stdout or "External Rscript analysis failed.").strip())
    try:
        payload = json.loads(public_stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("External Rscript analysis returned invalid JSON.") from exc
    reply = str(payload.get("reply") or "").strip()
    context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    if methylation_bundle is not None:
        context["declared_covariates"] = list(methylation_bundle.get("declared_covariates") or [])
        context["analysis_covariate_types"] = dict(methylation_bundle.get("analysis_covariate_types") or {})
        context["covariates_used"] = list(methylation_bundle.get("covariates_used") or [])
        context["covariates_dropped"] = list(methylation_bundle.get("covariates_dropped") or [])
        context["source_matrix_copied_to_job"] = False
        context["source_sha256"] = str(methylation_bundle.get("source_sha256") or "")
        context["source_fingerprint_status"] = str(
            methylation_bundle.get("source_fingerprint_status") or "not_declared"
        )
        context["source_fingerprint_verified_for_run"] = bool(
            methylation_bundle.get("source_fingerprint_verified_for_run")
        )
        context["feature_view"] = str(methylation_bundle.get("feature_view") or "complete_assay")
        if isinstance(methylation_bundle.get("feature_panel"), dict):
            context["feature_panel"] = dict(methylation_bundle["feature_panel"])
        context["adjustment_status"] = str(methylation_bundle.get("adjustment_status") or "not_applicable")
        context["clinical_linkage_status"] = str(methylation_bundle.get("clinical_linkage_status") or "")
        context["clinical_linked_patient_count"] = int(
            methylation_bundle.get("clinical_linked_patient_count") or 0
        )
    if quantitative_assay_bundle is not None:
        context["dataset_name"] = str(quantitative_assay_bundle.get("dataset_name") or "")
        context["assay_label"] = str(quantitative_assay_bundle.get("assay_label") or "")
        context["modality"] = str(quantitative_assay_bundle.get("modality") or "")
        context["data_type"] = str(quantitative_assay_bundle.get("data_type") or "")
        context["cohort_a_sample_count"] = int(
            quantitative_assay_bundle.get("cohort_a_sample_count") or 0
        )
        context["cohort_b_sample_count"] = int(
            quantitative_assay_bundle.get("cohort_b_sample_count") or 0
        )
        context["source_matrix_materialized_in_duckdb"] = False
        context["source_matrix_copied_to_job"] = False
        context["source_sha256"] = str(quantitative_assay_bundle.get("source_sha256") or "")
        context["source_fingerprint_status"] = str(
            quantitative_assay_bundle.get("source_fingerprint_status") or "not_declared"
        )
        context["source_fingerprint_verified_for_run"] = False
        context["clinical_linkage_status"] = str(
            quantitative_assay_bundle.get("clinical_linkage_status") or ""
        )
        context["cohort_a_patient_count"] = int(
            quantitative_assay_bundle.get("cohort_a_patient_count") or 0
        )
        context["cohort_b_patient_count"] = int(
            quantitative_assay_bundle.get("cohort_b_patient_count") or 0
        )
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
            "runner_command": public_command,
        },
    }


def run_snakemake_analysis(
    runner_ref: str,
    *,
    prompt: str,
    data_dir: str,
    assay_id: str = "",
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
    assay_id: str = "",
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


def run_workflow_analysis(
    runner_ref: str,
    *,
    prompt: str,
    data_dir: str,
    assay_id: str = "",
    selected_patient_ids: str = "",
    compare_selected_patient_ids: str = "",
    job_dir: Path | None = None,
    timeout_seconds: int = 30,
) -> Dict[str, Any]:
    workflow = WORKFLOW_RUNNERS.get(str(runner_ref or "").strip())
    if workflow is None:
        raise RuntimeError(f"Unsupported analysis workflow '{runner_ref}'.")
    with tempfile.TemporaryDirectory(prefix="pn-analysis-workflow-") as temp_dir:
        root = job_dir if isinstance(job_dir, Path) else Path(temp_dir)
        root.mkdir(parents=True, exist_ok=True)
        workflow_root = root / "workflow"
        workflow_root.mkdir(parents=True, exist_ok=True)
        manifest_path = workflow_root / "manifest.json"
        steps = list(workflow.get("steps") or [])
        manifest = {
            "workflow_id": str(workflow.get("id") or runner_ref),
            "workflow_name": str(workflow.get("name") or "Analysis workflow"),
            "runner_ref": str(runner_ref or "").strip(),
            "prompt": str(prompt or ""),
            "data_dir": str(data_dir or ""),
            "assay_id": str(assay_id or ""),
            "selected_patient_ids": str(selected_patient_ids or ""),
            "compare_selected_patient_ids": str(compare_selected_patient_ids or ""),
            "steps": [
                {
                    "id": str(step.get("id") or "").strip(),
                    "label": str(step.get("label") or "").strip(),
                    "runner_type": str(step.get("runner_type") or "").strip(),
                    "runner_ref": str(step.get("runner_ref") or "").strip(),
                    "artifact_dir": str(step.get("artifact_dir") or "").strip(),
                    "status": "pending",
                    "error": "",
                }
                for step in steps
            ],
        }
        _write_workflow_manifest(manifest_path, manifest)
        completed_steps: List[Dict[str, Any]] = []
        step_timeout = max(1, int(timeout_seconds or 30) // max(1, len(steps)))
        for index, step in enumerate(steps):
            manifest["steps"][index]["status"] = "running"
            _write_workflow_manifest(manifest_path, manifest)
            step_dir = root / str(step.get("artifact_dir") or f"workflow/{index + 1:02d}-{step.get('id') or 'step'}")
            try:
                if str(step.get("runner_type") or "").strip().lower() != "rscript":
                    raise RuntimeError(f"Unsupported workflow step runner '{step.get('runner_type')}'.")
                step_payload = run_rscript_analysis(
                    str(step.get("runner_ref") or "").strip(),
                    prompt=str(step.get("prompt") or prompt or ""),
                    data_dir=data_dir,
                    assay_id=assay_id,
                    selected_patient_ids=selected_patient_ids,
                    compare_selected_patient_ids=compare_selected_patient_ids,
                    job_dir=step_dir,
                    timeout_seconds=step_timeout,
                )
                step_record = _workflow_step_payload(step=step, payload=step_payload, status="completed")
                completed_steps.append(step_record)
                manifest["steps"][index].update(
                    {
                        "status": "completed",
                        "reply": step_record["reply"],
                        "context": step_record["context"],
                    }
                )
            except Exception as exc:
                error_text = str(exc).strip() or "Workflow step failed."
                manifest["steps"][index]["status"] = "failed"
                manifest["steps"][index]["error"] = error_text
                _write_workflow_manifest(manifest_path, manifest)
                raise RuntimeError(
                    f"{str(step.get('label') or step.get('id') or 'Workflow step').strip()} failed: {error_text}"
                ) from exc
            _write_workflow_manifest(manifest_path, manifest)
        deseq2_context = next(
            (step["context"] for step in completed_steps if step.get("id") == "deseq2"),
            {},
        )
        hallmark_context = next(
            (step["context"] for step in completed_steps if step.get("id") == "hallmark"),
            {},
        )
        dataset_name = (
            str(deseq2_context.get("dataset_name") or "").strip()
            or str(hallmark_context.get("dataset_name") or "").strip()
            or str(assay_id or "").strip()
        )
        significant_genes = int(deseq2_context.get("significant_gene_count") or 0) if isinstance(deseq2_context, dict) else 0
        significant_pathways = int(hallmark_context.get("significant_pathway_count") or 0) if isinstance(hallmark_context, dict) else 0
        reply = (
            f"Assay signature workflow completed for {dataset_name or 'the selected assay'}. "
            f"DESeq2 found {significant_genes} significant genes and Hallmark enrichment found "
            f"{significant_pathways} significant pathways."
        )
        manifest["status"] = "completed"
        _write_workflow_manifest(manifest_path, manifest)
        return {
            "intent": "analysis_workflow",
            "reply": reply,
            "data": {
                "source": "deterministic",
                "execution": "external_runner",
                "context": {
                    "mode": "workflow_transcriptomics_signature",
                    "workflow_id": str(workflow.get("id") or runner_ref),
                    "workflow_name": str(workflow.get("name") or "Analysis workflow"),
                    "dataset_name": dataset_name,
                    "step_count": len(completed_steps),
                    "steps": completed_steps,
                    "deseq2": deseq2_context,
                    "hallmark": hallmark_context,
                    "workflow_manifest": "workflow/manifest.json",
                },
                "model": None,
                "base_url": "",
                "runner_type": "workflow",
                "runner_ref": str(runner_ref or "").strip(),
                "workflow_id": str(workflow.get("id") or runner_ref),
            },
        }


from app.script_analysis import run_script_analysis


EXTERNAL_ANALYSIS_RUNNERS = {
    "container": run_script_analysis,
    "rscript": run_rscript_analysis,
    "snakemake": run_snakemake_analysis,
    "nextflow": run_nextflow_analysis,
    "workflow": run_workflow_analysis,
}


def run_external_analysis(
    runner_type: str,
    runner_ref: str,
    *,
    prompt: str,
    data_dir: str,
    assay_id: str = "",
    selected_patient_ids: str = "",
    compare_selected_patient_ids: str = "",
    job_dir: Path | None = None,
    timeout_seconds: int = 30,
) -> Dict[str, Any]:
    normalized = str(runner_type or "").strip().lower()
    if job_dir is not None:
        audit_dir = Path(job_dir) / "audit"
        audit_dir.mkdir(parents=True, exist_ok=True)
        (audit_dir / "runner_adapter.py").write_text(_ADAPTER_SOURCE, encoding="utf-8")
    runner = EXTERNAL_ANALYSIS_RUNNERS.get(normalized)
    if runner is None:
        raise RuntimeError(f"Unsupported analysis runner type '{runner_type}'.")
    return runner(
        runner_ref,
        prompt=prompt,
        data_dir=data_dir,
        assay_id=assay_id,
        selected_patient_ids=selected_patient_ids,
        compare_selected_patient_ids=compare_selected_patient_ids,
        job_dir=job_dir,
        timeout_seconds=timeout_seconds,
    )
