from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from app.env import app_env


BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
DATA_ROOT_DIR = BASE_DIR / "datasets/synthetic-longitudinal-demo"
DEFAULT_DATA_DIR = str(DATA_ROOT_DIR.resolve())
TEMPLATES_DIR = BASE_DIR / "templates"


def _runtime_root() -> Path:
    configured = app_env("COHORTOME_RUNTIME_ROOT", "").strip()
    if not configured:
        return (BASE_DIR / "runtime").resolve()
    path = Path(configured).expanduser()
    if not path.is_absolute():
        path = BASE_DIR / path
    return path.resolve()


RUNTIME_ROOT_DIR = _runtime_root()
STATE_ROOT_DIR = RUNTIME_ROOT_DIR / "state"
CACHE_ROOT_DIR = RUNTIME_ROOT_DIR / "cache"
RUNS_ROOT_DIR = RUNTIME_ROOT_DIR / "runs"
DEFAULT_LOCAL_USER_ID = "local"
DEFAULT_HELP_URL = "https://cnag-biomedical-informatics.github.io/cohortome/"


def private_artifact_runtime_is_safe() -> bool:
    """Return whether private artifacts and workspace state have an explicit external root."""
    configured = app_env("COHORTOME_RUNTIME_ROOT", "").strip()
    if not configured:
        return False
    configured_path = Path(configured).expanduser()
    if not configured_path.is_absolute():
        return False
    configured_root = configured_path.resolve()
    active_root = RUNTIME_ROOT_DIR.resolve()
    checkout_root = BASE_DIR.resolve()
    if active_root != configured_root:
        return False
    return active_root != checkout_root and checkout_root not in active_root.parents


def branding_logo_path() -> Path | None:
    configured = app_env("COHORTOME_BRAND_LOGO_PATH", "").strip()
    if configured:
        candidate = Path(configured)
        if not candidate.is_absolute():
            candidate = (BASE_DIR / configured).resolve()
        if candidate.exists() and candidate.is_file():
            return candidate
    default_logo = BASE_DIR / "static" / "img" / "cohortome-logo.svg"
    if default_logo.exists() and default_logo.is_file():
        return default_logo
    matches = sorted((BASE_DIR / "static" / "img").glob("*.*"))
    return matches[0] if matches else None


def branding_settings() -> Dict[str, Any]:
    logo_path = branding_logo_path()
    return {
        "name": app_env("COHORTOME_BRAND_NAME", "COHORTome").strip() or "COHORTome",
        "subtitle": app_env(
            "COHORTOME_BRAND_SUBTITLE",
            "Clinical histories and multimodal assays, connected.",
        ).strip(),
        "logo_url": "/branding/logo" if logo_path else "",
        "logo_alt": app_env("COHORTOME_BRAND_LOGO_ALT", "COHORTome logo").strip() or "COHORTome logo",
        "help_url": app_env("COHORTOME_HELP_URL", DEFAULT_HELP_URL).strip() or DEFAULT_HELP_URL,
    }
