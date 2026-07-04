from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any, Dict, List
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

from app.env import app_env


DICOM_STUDIES_MANIFEST = Path("assays") / "imaging" / "dicom_studies.json"


def _truthy(value: str) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _clean_url(value: str) -> str:
    return str(value or "").strip().rstrip("/")


def dicom_enabled() -> bool:
    return _truthy(app_env("BRN_DICOM_ENABLED", "false"))


def dicom_public_config() -> Dict[str, Any]:
    return {
        "enabled": dicom_enabled(),
        "ohif_public_url": _clean_url(app_env("BRN_OHIF_PUBLIC_URL", "http://127.0.0.1:3000")),
        "dicomweb_public_url": _clean_url(app_env("BRN_DICOMWEB_PUBLIC_URL", "http://127.0.0.1:8042/dicom-web")),
        "orthanc_configured": bool(_clean_url(app_env("BRN_ORTHANC_INTERNAL_URL", ""))),
    }


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _clean_uid(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    allowed = set("0123456789.")
    return text if all(char in allowed for char in text) and ".." not in text else ""


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _ohif_launch_url(study_instance_uid: str) -> str:
    base = _clean_url(app_env("BRN_OHIF_PUBLIC_URL", "http://127.0.0.1:3000"))
    if not base:
        return ""
    return f"{base}/viewer?StudyInstanceUIDs={quote(study_instance_uid, safe='.')}"


def _normalize_series(raw_series: Any) -> List[Dict[str, Any]]:
    series_items: List[Dict[str, Any]] = []
    for item in raw_series if isinstance(raw_series, list) else []:
        if not isinstance(item, dict):
            continue
        series_uid = _clean_uid(item.get("series_instance_uid"))
        if not series_uid:
            continue
        sop_instance_uids = [
            uid
            for uid in (_clean_uid(value) for value in (item.get("sop_instance_uids") or []))
            if uid
        ]
        instance_count = item.get("instance_count")
        try:
            normalized_count = int(instance_count)
        except (TypeError, ValueError):
            normalized_count = len(sop_instance_uids)
        series_items.append(
            {
                "series_instance_uid": series_uid,
                "series_description": _clean_text(item.get("series_description")),
                "instance_count": max(normalized_count, 0),
                "sop_instance_uids": sop_instance_uids,
            }
        )
    return series_items


def _normalize_study(item: Dict[str, Any], source_dataset_id: str = "") -> Dict[str, Any] | None:
    study_uid = _clean_uid(item.get("study_instance_uid"))
    if not study_uid:
        return None
    study = {
        "study_id": _clean_text(item.get("study_id")) or study_uid,
        "label": _clean_text(item.get("label")) or _clean_text(item.get("study_description")) or study_uid,
        "patient_id": _clean_text(item.get("patient_id")),
        "sample_id": _clean_text(item.get("sample_id")),
        "timepoint": _clean_text(item.get("timepoint")),
        "modality": _clean_text(item.get("modality")) or "MR",
        "study_instance_uid": study_uid,
        "study_description": _clean_text(item.get("study_description")),
        "series": _normalize_series(item.get("series")),
        "ohif_url": _ohif_launch_url(study_uid),
    }
    if source_dataset_id:
        study["source_dataset_id"] = source_dataset_id
    return study


def _manifest_dataset_roots(dataset_root: Path) -> List[tuple[str, Path]]:
    manifest = _read_json(dataset_root / "manifest.json")
    root_paths = manifest.get("root_paths") if isinstance(manifest.get("root_paths"), list) else []
    dataset_ids = manifest.get("dataset_ids") if isinstance(manifest.get("dataset_ids"), list) else []
    roots: List[tuple[str, Path]] = []
    for index, root_path in enumerate(root_paths):
        path = Path(str(root_path or "")).expanduser().resolve()
        dataset_id = str(dataset_ids[index] if index < len(dataset_ids) else "").strip()
        if path.exists():
            roots.append((dataset_id, path))
    return roots


def _candidate_roots(dataset_root: Path) -> List[tuple[str, Path]]:
    scoped = _manifest_dataset_roots(dataset_root)
    if scoped:
        return scoped
    return [("", dataset_root)]


def dicom_manifest_paths(data_dir: str) -> List[Path]:
    dataset_root = Path(data_dir).expanduser().resolve()
    return [root / DICOM_STUDIES_MANIFEST for _, root in _candidate_roots(dataset_root)]


def dicom_studies(data_dir: str) -> List[Dict[str, Any]]:
    dataset_root = Path(data_dir).expanduser().resolve()
    studies: List[Dict[str, Any]] = []
    seen_uids: set[str] = set()
    for source_dataset_id, root in _candidate_roots(dataset_root):
        manifest_path = root / DICOM_STUDIES_MANIFEST
        payload = _read_json(manifest_path)
        raw_studies = payload.get("studies") if isinstance(payload.get("studies"), list) else []
        for item in raw_studies:
            if not isinstance(item, dict):
                continue
            normalized = _normalize_study(item, source_dataset_id=source_dataset_id)
            if not normalized:
                continue
            uid = str(normalized.get("study_instance_uid") or "")
            if uid in seen_uids:
                continue
            seen_uids.add(uid)
            studies.append(normalized)
    return studies


def orthanc_health() -> Dict[str, Any]:
    internal_url = _clean_url(app_env("BRN_ORTHANC_INTERNAL_URL", ""))
    if not dicom_enabled():
        return {"checked": False, "reachable": False, "message": "DICOM integration is disabled."}
    if not internal_url:
        return {"checked": False, "reachable": False, "message": "BRN_ORTHANC_INTERNAL_URL is not configured."}
    request = UrlRequest(f"{internal_url}/system", headers={"Accept": "application/json"})
    username = app_env("BRN_ORTHANC_USERNAME", "").strip()
    password = app_env("BRN_ORTHANC_PASSWORD", "")
    if username or password:
        token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
        request.add_header("Authorization", f"Basic {token}")
    try:
        with urlopen(request, timeout=1.5) as response:
            return {
                "checked": True,
                "reachable": 200 <= int(response.status) < 400,
                "message": "Orthanc is reachable.",
            }
    except (OSError, URLError) as exc:
        return {"checked": True, "reachable": False, "message": str(exc)}


def dicom_status(data_dir: str) -> Dict[str, Any]:
    studies = dicom_studies(data_dir)
    manifest_paths = dicom_manifest_paths(data_dir)
    config = dicom_public_config()
    return {
        **config,
        "manifest_found": any(path.exists() for path in manifest_paths),
        "manifest_count": sum(1 for path in manifest_paths if path.exists()),
        "study_count": len(studies),
        "orthanc": orthanc_health(),
    }
