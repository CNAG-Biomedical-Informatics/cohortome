from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = str((BASE_DIR / "data").resolve())
TEMPLATES_DIR = BASE_DIR / "templates"


def branding_logo_path() -> Path | None:
    configured = os.getenv("PN_BRAND_LOGO_PATH", "").strip()
    if configured:
        candidate = Path(configured)
        if not candidate.is_absolute():
            candidate = (BASE_DIR / configured).resolve()
        if candidate.exists() and candidate.is_file():
            return candidate
    default_logo = TEMPLATES_DIR / "img" / "logo-3tr.png"
    if default_logo.exists() and default_logo.is_file():
        return default_logo
    matches = sorted((TEMPLATES_DIR / "img").glob("*.png"))
    return matches[0] if matches else None


def branding_settings() -> Dict[str, Any]:
    logo_path = branding_logo_path()
    return {
        "name": os.getenv("PN_BRAND_NAME", "3TR").strip() or "3TR",
        "subtitle": os.getenv(
            "PN_BRAND_SUBTITLE",
            "Explore patient timelines, inspect visit evidence, and analyze private longitudinal cohort data.",
        ).strip(),
        "logo_url": "/branding/logo" if logo_path else "",
        "logo_alt": os.getenv("PN_BRAND_LOGO_ALT", "3TR logo").strip() or "3TR logo",
    }
