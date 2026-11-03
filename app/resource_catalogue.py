"""Metadata-only Store catalogue, with a last-known-good offline copy."""
import json
import re
from urllib.parse import urlparse

import httpx

from app.config import CONFIG_DIR, STATE_ROOT_DIR
from app.state_io import atomic_write_json

URL = "https://raw.githubusercontent.com/CNAG-Biomedical-Informatics/cohortome-store/main/catalog/catalogue.json"
CACHE = STATE_ROOT_DIR / "resources" / "catalogue.json"
MAX_BYTES = 1024 * 1024
FIELDS = set("dataset_id version name description terms install_mode recipe_version source_bytes archive_bytes archive_sha256 modalities modality_keys synthetic source_page source_policy_url source_label source_policy_label review_statement additional_source_links dataset_schema_version".split())


def bundled():
    return json.loads((CONFIG_DIR / "resources.json").read_text(encoding="utf-8"))


def validate(payload):
    if not isinstance(payload, dict) or payload.get("catalogue_version") != 1:
        raise ValueError("Unsupported catalogue version.")
    if payload.get("dataset_schema_version") != 1:
        raise ValueError("Unsupported dataset schema.")
    entries = payload.get("datasets")
    if not isinstance(entries, list) or not 1 <= len(entries) <= 500:
        raise ValueError("Invalid catalogue entries.")
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) - FIELDS:
            raise ValueError("Invalid dataset entry.")
        for field in ("modalities", "source_label", "source_policy_label", "review_statement", "source_page", "source_policy_url"):
            if field in entry and not isinstance(entry[field], str):
                raise ValueError("Invalid catalogue text.")
        if not isinstance(entry.get("modality_keys", []), list) or not all(isinstance(key, str) for key in entry.get("modality_keys", [])):
            raise ValueError("Invalid modalities.")
        if "synthetic" in entry and type(entry["synthetic"]) is not bool:
            raise ValueError("Invalid synthetic flag.")
        if type(entry.get("dataset_schema_version", 1)) is not int:
            raise ValueError("Invalid dataset schema.")
        for field in ("dataset_id", "version", "name", "description", "terms"):
            if not isinstance(entry.get(field), str) or not entry[field].strip():
                raise ValueError("Incomplete dataset entry.")
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,127}", entry["dataset_id"]):
            raise ValueError("Invalid dataset identity.")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", entry["version"]):
            raise ValueError("Invalid dataset version.")
        if entry["dataset_id"] in seen:
            raise ValueError("Duplicate dataset identity.")
        seen.add(entry["dataset_id"])
        mode = entry.get("install_mode", "archive")
        if mode not in {"included", "source", "archive"}:
            raise ValueError("Unsupported installation mode.")
        if mode == "source":
            if type(entry.get("recipe_version")) is not int or entry["recipe_version"] < 1:
                raise ValueError("Invalid recipe version.")
            if not all(entry.get(key) for key in ("source_page", "source_policy_url", "review_statement")):
                raise ValueError("Missing source terms.")
        size = entry.get("source_bytes" if mode == "source" else "archive_bytes")
        if mode != "included" and (type(size) is not int or size <= 0):
            raise ValueError("Invalid download size.")
        if mode == "archive" and not re.fullmatch(r"[0-9a-f]{64}", str(entry.get("archive_sha256", ""))):
            raise ValueError("Missing archive checksum.")
        for field in ("source_page", "source_policy_url"):
            if entry.get(field):
                parsed = urlparse(entry[field])
                if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
                    raise ValueError("Unsafe source link.")
        if not isinstance(entry.get("additional_source_links", []), list):
            raise ValueError("Invalid source links.")
        for link in entry.get("additional_source_links", []):
            if not isinstance(link, dict) or not isinstance(link.get("url"), str):
                raise ValueError("Invalid source link.")
            parsed = urlparse(link["url"])
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError("Unsafe source link.")
    return entries


def compatible(entry):
    if entry.get("dataset_schema_version", 1) != 1:
        return False
    if entry.get("install_mode") == "included":
        return any(local['dataset_id'] == entry['dataset_id'] and local.get('install_mode') == 'included'
                   for local in bundled())
    if entry.get("install_mode") != "source":
        return True
    # Recipes and their output versions are shipped code, never remote commands.
    return any(local["dataset_id"] == entry["dataset_id"]
               and local.get("install_mode") == "source"
               and local.get("recipe_version") == entry.get("recipe_version")
               and local["version"] == entry["version"] for local in bundled())


def read():
    try:
        return validate(json.loads(CACHE.read_text(encoding="utf-8"))), "cached"
    except (OSError, ValueError, TypeError):
        return bundled(), "bundled"


def refresh():
    try:
        with httpx.Client(timeout=10, follow_redirects=False, trust_env=False) as client:
            with client.stream("GET", URL) as response:
                response.raise_for_status()
                content = bytearray()
                for chunk in response.iter_bytes():
                    content.extend(chunk)
                    if len(content) > MAX_BYTES:
                        raise ValueError("Catalogue exceeds size limit.")
        payload = json.loads(content)
        validate(payload)
        atomic_write_json(CACHE, payload)
        return "Catalogue refreshed from COHORTome-store."
    except (httpx.HTTPError, OSError, ValueError, TypeError):
        return "Could not refresh the catalogue. Showing the saved or bundled list."
