from __future__ import annotations

import json
from typing import Any, Dict

from app.user_state import user_state_file


USER_SETTINGS_FILENAME = "settings.json"

DEFAULT_USER_SETTINGS: Dict[str, Any] = {
    "version": 1,
    "landing_tab_mode": "fixed",
    "landing_tab": "dashboard",
    "query_disclosure_default": "detailed",
    "query_default_mode": "auto",
    "analysis_auto_open_jobs": True,
    "pheno_default_metric": "",
    "pheno_advanced_open": False,
    "pheno_render_heatmap": True,
    "pheno_render_mds": True,
    "pheno_render_graph": True,
    "dashboard_molecular_open": False,
    "dataset_compact_view": False,
}

_ALLOWED_VALUES = {
    "landing_tab_mode": {"fixed", "last"},
    "landing_tab": {"dashboard", "datasets", "query", "analysis", "pheno"},
    "query_disclosure_default": {"summary", "detailed"},
    "query_default_mode": {"auto", "planner_only"},
    "pheno_default_metric": {"", "hamming", "jaccard"},
}
_BOOLEAN_FIELDS = {
    "analysis_auto_open_jobs",
    "pheno_advanced_open",
    "pheno_render_heatmap",
    "pheno_render_mds",
    "pheno_render_graph",
    "dashboard_molecular_open",
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
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(normalized, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return normalized


def update_user_settings(patch: Dict[str, Any], user_id: str | None = None) -> Dict[str, Any]:
    current = load_user_settings(user_id)
    for key, value in patch.items():
        if key in DEFAULT_USER_SETTINGS and key != "version":
            current[key] = value
    return save_user_settings(current, user_id)
