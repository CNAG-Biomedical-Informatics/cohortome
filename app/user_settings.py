from __future__ import annotations

import json
from typing import Any, Dict

from app.state_io import advisory_file_lock, atomic_write_json
from app.user_state import user_state_file


USER_SETTINGS_FILENAME = "settings.json"

DEFAULT_USER_SETTINGS: Dict[str, Any] = {
    "appearance": "light",
    "plot_palette": "default",
    "heatmap_palette": "default",
    "diverging_palette": "default",
    "version": 1,
    "landing_tab_mode": "fixed",
    "landing_tab": "dashboard",
    "query_disclosure_default": "detailed",
    "query_default_mode": "auto",
    "latest_query_details": True,
    "analysis_auto_open_jobs": True,
    "job_notifications": True,
    "run_history_retention_days": 30,
    "pheno_default_metric": "",
    "pheno_advanced_open": False,
    "pheno_render_heatmap": True,
    "pheno_render_mds": True,
    "pheno_render_umap": False,
    "pheno_render_graph": True,
    "dashboard_assays_open": False,
    "dataset_compact_view": False,
    "llm_provider_id": "system-default",
}

_ALLOWED_VALUES = {
    "appearance": {"light", "dark", "system"},
    "plot_palette": {"default", "okabe-ito", "muted"},
    "heatmap_palette": {"default", "viridis", "cividis"},
    "diverging_palette": {"default", "blue-orange", "purple-green"},
    "landing_tab_mode": {"fixed", "last"},
    "landing_tab": {"dashboard", "datasets", "query", "analysis", "pheno"},
    "query_disclosure_default": {"summary", "detailed"},
    "query_default_mode": {"auto", "planner_only"},
    "run_history_retention_days": {0, 7, 30, 90, 180, 365},
    "pheno_default_metric": {"", "hamming", "jaccard"},
}
_BOOLEAN_FIELDS = {
    "latest_query_details",
    "analysis_auto_open_jobs",
    "job_notifications",
    "pheno_advanced_open",
    "pheno_render_heatmap",
    "pheno_render_mds",
    "pheno_render_umap",
    "pheno_render_graph",
    "dashboard_assays_open",
    "dataset_compact_view",
}


def normalize_user_settings(raw: Dict[str, Any] | None) -> Dict[str, Any]:
    settings = dict(DEFAULT_USER_SETTINGS)
    if not isinstance(raw, dict):
        return settings
    for key, value in raw.items():
        if key == "version":
            continue
        if key in _BOOLEAN_FIELDS:
            settings[key] = bool(value)
            continue
        if key == "llm_provider_id":
            normalized = str(value or "").strip()
            settings[key] = normalized or DEFAULT_USER_SETTINGS["llm_provider_id"]
            continue
        if key == "run_history_retention_days":
            try:
                normalized = int(value)
            except (TypeError, ValueError):
                continue
            if normalized in _ALLOWED_VALUES["run_history_retention_days"]:
                settings[key] = normalized
            continue
        allowed = _ALLOWED_VALUES.get(key)
        if allowed is not None:
            normalized = str(value or "").strip().lower()
            if normalized in allowed:
                settings[key] = normalized
    return settings


def load_user_settings(user_id: str | None = None) -> Dict[str, Any]:
    path = user_state_file(USER_SETTINGS_FILENAME, user_id)
    if not path.exists():
        return dict(DEFAULT_USER_SETTINGS)
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        parsed = {}
    return normalize_user_settings(parsed if isinstance(parsed, dict) else {})


def save_user_settings(settings: Dict[str, Any], user_id: str | None = None) -> Dict[str, Any]:
    normalized = normalize_user_settings(settings)
    path = user_state_file(USER_SETTINGS_FILENAME, user_id)
    with advisory_file_lock(path.with_name(f".{path.name}.lock")):
        atomic_write_json(path, normalized)
    return normalized


def update_user_settings(patch: Dict[str, Any], user_id: str | None = None) -> Dict[str, Any]:
    path = user_state_file(USER_SETTINGS_FILENAME, user_id)
    with advisory_file_lock(path.with_name(f".{path.name}.lock")):
        current = load_user_settings(user_id)
        for key, value in patch.items():
            if key in DEFAULT_USER_SETTINGS and key != "version":
                current[key] = value
        normalized = normalize_user_settings(current)
        atomic_write_json(path, normalized)
        return normalized
