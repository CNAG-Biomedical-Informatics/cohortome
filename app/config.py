from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from app.env import app_env


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_ROOT_DIR = BASE_DIR / "default_dataset"
DEFAULT_DATA_DIR = str(DATA_ROOT_DIR.resolve())
TEMPLATES_DIR = BASE_DIR / "templates"
STATE_ROOT_DIR = BASE_DIR / "state"
DEFAULT_LOCAL_USER_ID = "local"
DEFAULT_HELP_URL = "https://mrueda.github.io/cohortome/"


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
