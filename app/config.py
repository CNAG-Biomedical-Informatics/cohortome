from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_ROOT_DIR = BASE_DIR / "default_dataset"
DEFAULT_DATA_DIR = str(DATA_ROOT_DIR.resolve())
TEMPLATES_DIR = BASE_DIR / "templates"
STATE_ROOT_DIR = BASE_DIR / "state"
DEFAULT_LOCAL_USER_ID = "local"
DEFAULT_HELP_URL = "https://mrueda.github.io/patient-navigator/"


def branding_logo_path() -> Path | None:
    configured = os.getenv("PN_BRAND_LOGO_PATH", "").strip()
    if configured:
        candidate = Path(configured)
        if not candidate.is_absolute():
            candidate = (BASE_DIR / configured).resolve()
        if candidate.exists() and candidate.is_file():
            return candidate
    docs_logo = BASE_DIR / "docs-site" / "static" / "img" / "patient-navigator-logo.png"
    if docs_logo.exists() and docs_logo.is_file():
        return docs_logo
    default_logo = TEMPLATES_DIR / "img" / "logo-3tr.png"
    if default_logo.exists() and default_logo.is_file():
        return default_logo
    matches = sorted((TEMPLATES_DIR / "img").glob("*.png"))
    return matches[0] if matches else None
def branding_settings() -> Dict[str, Any]:
    logo_path = branding_logo_path()
    return {
        "name": os.getenv("PN_BRAND_NAME", "Patient Navigator").strip() or "Patient Navigator",
        "subtitle": os.getenv(
            "PN_BRAND_SUBTITLE",
            "Clinical and molecular workspace exploration.",
        ).strip(),
        "logo_url": "/branding/logo" if logo_path else "",
        "logo_alt": os.getenv("PN_BRAND_LOGO_ALT", "Patient Navigator logo").strip() or "Patient Navigator logo",
        "help_url": os.getenv("PN_HELP_URL", DEFAULT_HELP_URL).strip() or DEFAULT_HELP_URL,
    }
