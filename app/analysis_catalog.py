from __future__ import annotations

from pathlib import Path
import shutil
from typing import Any, Dict, List

import yaml

from app.query_store import molecular_dataset_inventory


ANALYSIS_CATALOG_PATH = Path(__file__).resolve().parent.parent / "state" / "analysis" / "catalog.yaml"
VALID_EXECUTION_MODES = {"auto", "deterministic", "llm_only"}
VALID_RUNNER_TYPES = {"builtin", "rscript", "cli", "container"}
VALID_EXECUTION_BACKENDS = {"sync", "job"}


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
    timeout_raw = raw.get("job_timeout_seconds")
    try:
        job_timeout_seconds = int(timeout_raw) if timeout_raw not in (None, "") else 0
    except (TypeError, ValueError):
        raise ValueError(
            f"Analysis catalog item '{item_id}' uses invalid job_timeout_seconds '{timeout_raw}'."
        ) from None
    return {
        "id": item_id,
        "name": name,
        "category": category,
        "kind": kind,
        "description": description,
        "guidance": guidance,
        "default_prompt": prompt,
        "execution_mode": execution_mode,
        "execution_backend": execution_backend,
        "runner_type": runner_type,
        "runner_ref": runner_ref,
        "expected_runtime": str(raw.get("expected_runtime") or "").strip(),
        "job_timeout_seconds": job_timeout_seconds,
        "job_priority": str(raw.get("job_priority") or "").strip() or "normal",
        "default_compare_mode": bool(raw.get("default_compare_mode", False)),
        "supports_compare_mode": bool(raw.get("supports_compare_mode", False)),
        "requires_detailed_access": bool(raw.get("requires_detailed_access", False)),
        "requires_molecular": bool(raw.get("requires_molecular", False)),
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
    if item.get("requires_molecular"):
        requirements.append("Requires at least one molecular dataset in the active workspace.")
    if item.get("default_compare_mode"):
        requirements.append("Runs in compare mode; select Cohort A and Cohort B before executing.")
    if item.get("runner_type") == "rscript":
        requirements.append("Uses a curated external Rscript runner.")
    if item.get("execution_backend") == "job":
        requirements.append("Runs as a background job.")
    return requirements


def _availability_for_item(item: Dict[str, Any], *, granularity_ceiling: str, has_molecular: bool) -> Dict[str, Any]:
    unavailable_reason = ""
    if item.get("requires_detailed_access") and granularity_ceiling != "detailed":
        unavailable_reason = "Requires Detailed in-app access for the current workspace."
    elif item.get("requires_molecular") and not has_molecular:
        unavailable_reason = "No molecular datasets are available in the current workspace."
    elif item.get("runner_type") == "rscript" and not shutil.which("Rscript"):
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
        molecular_datasets = molecular_dataset_inventory(data_dir)
    except FileNotFoundError:
        molecular_datasets = []
    has_molecular = bool(molecular_datasets)
    materialized_items = []
    for item in items:
        availability = _availability_for_item(
            item,
            granularity_ceiling=granularity_ceiling,
            has_molecular=has_molecular,
        )
        materialized_items.append({**item, **availability})
    return {
        "items": materialized_items,
        "workspace": {
            "granularity_ceiling": granularity_ceiling,
            "ai_provider_access": ai_provider_access,
            "has_molecular_datasets": has_molecular,
            "molecular_dataset_count": len(molecular_datasets),
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
