from __future__ import annotations

import os
from pathlib import Path
import shutil
from typing import Any, Dict, List

import yaml

from app.config import CONFIG_DIR
from app.datasets import clinical_representation
from app.query_store import assay_dataset_inventory
from app.env import app_env


ANALYSIS_CATALOG_PATH = CONFIG_DIR / "analysis" / "catalog.yaml"
VALID_EXECUTION_MODES = {"auto", "deterministic", "llm_only"}
VALID_RUNNER_TYPES = {"builtin", "rscript", "snakemake", "nextflow", "workflow", "cli", "container"}
VALID_EXECUTION_BACKENDS = {"sync", "job"}


def analysis_catalog_debug_enabled() -> bool:
    return app_env("COHORTOME_ANALYSIS_CATALOG_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}


def _configured_runtime_available(env_var: str, default_name: str) -> bool:
    configured = str(os.environ.get(env_var) or "").strip()
    if configured:
        path = Path(configured)
        return path.is_file() and os.access(path, os.X_OK)
    return shutil.which(default_name) is not None


def _normalize_catalog_item(raw: Dict[str, Any], index: int) -> Dict[str, Any]:
    item_id = str(raw.get("id") or "").strip()
    if not item_id:
        raise ValueError(f"Analysis catalog item #{index + 1} is missing an id.")
    name = str(raw.get("name") or "").strip()
    if not name:
        raise ValueError(f"Analysis catalog item '{item_id}' is missing a name.")
    prompt = str(raw.get("default_prompt") or "").strip()
    if not prompt:
        raise ValueError(f"Analysis catalog item '{item_id}' is missing a default_prompt.")
    execution_mode = str(raw.get("execution_mode") or "auto").strip().lower()
    if execution_mode not in VALID_EXECUTION_MODES:
        raise ValueError(
            f"Analysis catalog item '{item_id}' uses unsupported execution_mode '{execution_mode}'."
        )
    execution_backend = str(raw.get("execution_backend") or "sync").strip().lower()
    if execution_backend not in VALID_EXECUTION_BACKENDS:
        raise ValueError(
            f"Analysis catalog item '{item_id}' uses unsupported execution_backend '{execution_backend}'."
        )
    category = str(raw.get("category") or "").strip() or "General"
    kind = str(raw.get("kind") or "").strip() or "analysis"
    description = str(raw.get("description") or "").strip()
    guidance = str(raw.get("guidance") or "").strip()
    runner_type = str(raw.get("runner_type") or "builtin").strip().lower()
    if runner_type not in VALID_RUNNER_TYPES:
        raise ValueError(
            f"Analysis catalog item '{item_id}' uses unsupported runner_type '{runner_type}'."
        )
    runner_ref = str(raw.get("runner_ref") or item_id).strip()
    if not runner_ref:
        raise ValueError(f"Analysis catalog item '{item_id}' is missing a runner_ref.")
    tags = [str(item).strip() for item in list(raw.get("tags") or []) if str(item).strip()]
    raw_steps = raw.get("steps") or []
    if raw_steps and not isinstance(raw_steps, list):
        raise ValueError(f"Analysis catalog item '{item_id}' uses invalid steps.")
    steps = [str(item).strip() for item in raw_steps if str(item).strip()]
    timeout_raw = raw.get("job_timeout_seconds")
    try:
        job_timeout_seconds = int(timeout_raw) if timeout_raw not in (None, "") else 0
    except (TypeError, ValueError):
        raise ValueError(
            f"Analysis catalog item '{item_id}' uses invalid job_timeout_seconds '{timeout_raw}'."
        ) from None
    required_clinical_representation = str(raw.get("required_clinical_representation") or "").strip().lower()
    if required_clinical_representation not in {"", "person", "snapshot"}:
        raise ValueError(
            f"Analysis catalog item '{item_id}' uses invalid required_clinical_representation "
            f"'{required_clinical_representation}'."
        )
    return {
        "id": item_id,
        "name": name,
        "category": category,
        "kind": kind,
        "debug_only": bool(raw.get("debug_only", False)),
        "description": description,
        "guidance": guidance,
        "default_prompt": prompt,
        "execution_mode": execution_mode,
        "execution_backend": execution_backend,
        "runner_type": runner_type,
        "runner_ref": runner_ref,
        "steps": steps,
        "expected_runtime": str(raw.get("expected_runtime") or "").strip(),
        "job_timeout_seconds": job_timeout_seconds,
        "job_priority": str(raw.get("job_priority") or "").strip() or "normal",
        "default_compare_mode": bool(raw.get("default_compare_mode", False)),
        "supports_compare_mode": bool(raw.get("supports_compare_mode", False)),
        "requires_detailed_access": bool(raw.get("requires_detailed_access", False)),
        "requires_assays": bool(raw.get("requires_assays", False)),
        "required_modalities": [str(item or "").strip() for item in raw.get("required_modalities", []) if str(item or "").strip()],
        "required_data_types": [str(item or "").strip() for item in raw.get("required_data_types", []) if str(item or "").strip()],
        "analysis_level": str(raw.get("analysis_level") or "patient").strip() or "patient",
        "required_clinical_representation": required_clinical_representation,
        "tags": tags,
    }


def load_analysis_catalog(path: Path = ANALYSIS_CATALOG_PATH) -> List[Dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Analysis catalog not found: {path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError("Analysis catalog must be a YAML mapping with an 'items' list.")
    items = payload.get("items")
    if not isinstance(items, list):
        raise ValueError("Analysis catalog must define an 'items' list.")
    return [_normalize_catalog_item(dict(item or {}), index) for index, item in enumerate(items)]


def _workspace_requirements(item: Dict[str, Any]) -> List[str]:
    requirements: List[str] = []
    if item.get("requires_detailed_access"):
        requirements.append("Requires Detailed in-app access.")
    if item.get("requires_assays"):
        modalities = list(item.get("required_modalities") or [])
        data_types = list(item.get("required_data_types") or [])
        if modalities and data_types:
            requirements.append(f"Requires {', '.join(modalities)} assay data ({', '.join(data_types)}).")
        elif modalities:
            requirements.append(f"Requires {', '.join(modalities)} assay data.")
        else:
            requirements.append("Requires at least one assay in the active workspace.")
    analysis_level = str(item.get("analysis_level") or "patient").strip()
    if analysis_level:
        requirements.append(f"Runs at {analysis_level} level.")
    if item.get("default_compare_mode"):
        requirements.append("Runs in compare mode; select Cohort A and Cohort B before executing.")
    if item.get("required_clinical_representation") == "snapshot":
        requirements.append("Requires longitudinal visit or timepoint records.")
    if item.get("runner_type") == "rscript":
        requirements.append("Uses a curated external Rscript runner.")
    if item.get("runner_type") == "snakemake":
        requirements.append("Uses a curated Snakemake workflow.")
    if item.get("runner_type") == "nextflow":
        requirements.append("Uses a curated Nextflow workflow.")
    if item.get("runner_type") == "workflow":
        requirements.append("Runs a curated multi-step analysis workflow.")
    if item.get("execution_backend") == "job":
        requirements.append("Runs as a background job.")
    return requirements


def _assay_requirement_available(item: Dict[str, Any], assay_datasets: List[Dict[str, Any]]) -> bool:
    if not item.get("requires_assays"):
        return True
    if not assay_datasets:
        return False
    modalities = {str(value or "").strip() for value in item.get("required_modalities", []) if str(value or "").strip()}
    data_types = {str(value or "").strip() for value in item.get("required_data_types", []) if str(value or "").strip()}
    for assay in assay_datasets:
        if modalities and str(assay.get("modality") or "").strip() not in modalities:
            continue
        if data_types and str(assay.get("data_type") or "").strip() not in data_types:
            continue
        return True
    return False


def _availability_for_item(
    item: Dict[str, Any],
    *,
    granularity_ceiling: str,
    assay_datasets: List[Dict[str, Any]] | None = None,
    has_assays: bool | None = None,
    clinical_record_representation: str = "unspecified",
) -> Dict[str, Any]:
    if assay_datasets is None:
        assay_datasets = [{}] if has_assays else []
    unavailable_reason = ""
    if item.get("requires_detailed_access") and granularity_ceiling != "detailed":
        unavailable_reason = "Requires Detailed in-app access for the current workspace."
    elif (
        item.get("required_clinical_representation")
        and item.get("required_clinical_representation") != clinical_record_representation
    ):
        unavailable_reason = (
            "Requires longitudinal visit or timepoint records; "
            f"this workspace uses {clinical_record_representation} representation."
        )
    elif item.get("requires_assays") and not assay_datasets:
        unavailable_reason = "No assays are available in the current workspace."
    elif item.get("requires_assays") and not _assay_requirement_available(item, assay_datasets):
        modalities = ", ".join(item.get("required_modalities") or []) or "required"
        data_types = ", ".join(item.get("required_data_types") or [])
        suffix = f" ({data_types})" if data_types else ""
        unavailable_reason = f"No compatible {modalities} assay{suffix} is available in the current workspace."
    elif item.get("runner_type") == "rscript" and not shutil.which("Rscript"):
        unavailable_reason = "Rscript is not available on this installation."
    elif item.get("runner_type") == "snakemake" and not shutil.which("snakemake"):
        unavailable_reason = "Snakemake is not available on this installation."
    elif item.get("runner_type") == "nextflow" and not _configured_runtime_available("NEXTFLOW_BIN", "nextflow"):
        unavailable_reason = "Nextflow is not available on this installation."
    elif item.get("runner_type") == "workflow" and not shutil.which("Rscript"):
        unavailable_reason = "Rscript is not available on this installation."
    return {
        "available": unavailable_reason == "",
        "unavailable_reason": unavailable_reason,
        "workspace_requirements": _workspace_requirements(item),
    }


def analysis_catalog_payload(
    data_dir: str,
    *,
    granularity_ceiling: str = "detailed",
    ai_provider_access: str = "detailed_allowed",
    path: Path = ANALYSIS_CATALOG_PATH,
) -> Dict[str, Any]:
    items = load_analysis_catalog(path)
    try:
        assay_datasets = assay_dataset_inventory(data_dir)
    except FileNotFoundError:
        assay_datasets = []
    has_assays = bool(assay_datasets)
    record_representation = clinical_representation(data_dir)
    materialized_items = []
    for item in items:
        if item.get("debug_only") and not analysis_catalog_debug_enabled():
            continue
        availability = _availability_for_item(
            item,
            granularity_ceiling=granularity_ceiling,
            assay_datasets=assay_datasets,
            clinical_record_representation=record_representation,
        )
        materialized_items.append({**item, **availability})
    return {
        "items": materialized_items,
        "workspace": {
            "granularity_ceiling": granularity_ceiling,
            "ai_provider_access": ai_provider_access,
            "has_assay_datasets": has_assays,
            "assay_dataset_count": len(assay_datasets),
            "assay_modalities": sorted({str(item.get("modality") or "").strip() for item in assay_datasets if str(item.get("modality") or "").strip()}),
            "assay_data_types": sorted({str(item.get("data_type") or "").strip() for item in assay_datasets if str(item.get("data_type") or "").strip()}),
            "clinical_representation": record_representation,
        },
    }


def get_analysis_catalog_item(item_id: str, path: Path = ANALYSIS_CATALOG_PATH) -> Dict[str, Any] | None:
    wanted = str(item_id or "").strip()
    if not wanted:
        return None
    for item in load_analysis_catalog(path):
        if str(item.get("id") or "") == wanted:
            return item
    return None
