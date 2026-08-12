from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4

from fastapi import HTTPException, Request

from app.auth import auth_enabled, require_authenticated, session_user
from app.bff import extract_patient_id, resolve_project_data_dir
from app.config import BASE_DIR, CONFIG_DIR, DEFAULT_DATA_DIR, STATE_ROOT_DIR
from app.state_io import advisory_file_lock, atomic_write_json
from app.user_state import normalize_user_id, user_state_file


DATASET_REGISTRY_PATH = STATE_ROOT_DIR / "datasets" / "registry.json"
DATASET_REGISTRY_SEED_PATH = CONFIG_DIR / "datasets" / "registry.json"
DATASET_VISIBILITIES = {"admin_only", "all_authenticated", "restricted"}
DATA_CLASSIFICATIONS = {"public", "private"}
DEFAULT_DATA_CLASSIFICATION = "private"
QUERY_GRANULARITY_CEILINGS = {"summary", "detailed"}
DEFAULT_QUERY_GRANULARITY_CEILING = "summary"
AI_PROVIDER_ACCESS_MODES = {"detailed_allowed", "safe_summary", "blocked"}
DEFAULT_AI_PROVIDER_ACCESS = "detailed_allowed"
DEFAULT_DATASET_ID = "default"
_SAFE_DATASET_ID_RE = re.compile(r"[^a-z0-9._-]+")
_SCOPE_PREFIX = "scope--"
CLINICAL_REPRESENTATIONS = {"person", "snapshot"}
DEFAULT_CLINICAL_REPRESENTATION = "unspecified"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _registry_path() -> Path:
    DATASET_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    return DATASET_REGISTRY_PATH


def _selection_path(user_id: str) -> Path:
    return user_state_file("current-dataset.json", user_id)


def _scope_root() -> Path:
    path = STATE_ROOT_DIR / "datasets" / "scopes"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _workspace_clinical_dir(data_dir: str) -> Path:
    root = resolve_project_data_dir(data_dir)
    clinical_dir = root / "clinical"
    return clinical_dir if clinical_dir.is_dir() else root


def _plural(count: int, singular: str, plural: str | None = None) -> str:
    label = singular if count == 1 else (plural or f"{singular}s")
    return f"{count} {label}"


def _clinical_records(path: Path) -> List[Dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        individuals = payload.get("individuals")
        if isinstance(individuals, list):
            return [item for item in individuals if isinstance(item, dict)]
        return [payload]
    return []


def normalize_clinical_representation(value: str | None) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return normalized if normalized in CLINICAL_REPRESENTATIONS else DEFAULT_CLINICAL_REPRESENTATION


def clinical_representation(root_path: str) -> str:
    root = resolve_project_data_dir(root_path)
    if root.name == "clinical" and (root.parent / "manifest.json").is_file():
        root = root.parent
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        return DEFAULT_CLINICAL_REPRESENTATION
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return DEFAULT_CLINICAL_REPRESENTATION
    clinical = manifest.get("clinical") if isinstance(manifest, dict) else None
    if not isinstance(clinical, dict):
        return DEFAULT_CLINICAL_REPRESENTATION
    return normalize_clinical_representation(clinical.get("representation"))


def combined_clinical_representation(representations: List[str]) -> str:
    normalized = {normalize_clinical_representation(item) for item in representations}
    if len(normalized) == 1:
        return normalized.pop()
    return "mixed" if normalized else DEFAULT_CLINICAL_REPRESENTATION


def validate_dataset_release_root(root_path: str) -> Path:
    root = resolve_project_data_dir(root_path)
    clinical_dir = root / "clinical"
    if not clinical_dir.is_dir():
        raise ValueError("Dataset root must contain a clinical/ directory.")
    if not any(path.is_file() for path in clinical_dir.glob("*.json")):
        raise ValueError("Dataset clinical/ directory must contain at least one JSON file.")
    representation = clinical_representation(str(root))
    if representation == DEFAULT_CLINICAL_REPRESENTATION:
        raise ValueError(
            "Dataset manifest.json must declare clinical.representation as person or snapshot."
        )
    return root


def dataset_content_metadata(root_path: str) -> Dict[str, Any]:
    root = resolve_project_data_dir(root_path)
    clinical_dir = root / "clinical"
    assays_dir = root / "assays"
    transcriptomics_dir = assays_dir / "transcriptomics"
    clinical_files = sorted(path for path in (clinical_dir if clinical_dir.is_dir() else root).glob("*.json") if path.is_file())
    discovered_assay_files = sorted(path for path in assays_dir.glob("*/*.csv") if path.is_file()) if assays_dir.is_dir() else []
    assay_files = discovered_assay_files
    assay_manifest_path = assays_dir / "manifest.json"
    if assay_manifest_path.is_file():
        try:
            assay_manifest = json.loads(assay_manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            assay_manifest = None
        manifest_items = assay_manifest.get("assays") if isinstance(assay_manifest, dict) else None
        if isinstance(manifest_items, list):
            declared_files: List[Path] = []
            for item in manifest_items:
                if not isinstance(item, dict):
                    continue
                relative_file = str(item.get("file") or "").strip()
                if not relative_file:
                    continue
                path = (root / relative_file).resolve()
                try:
                    path.relative_to(root.resolve())
                except ValueError:
                    continue
                if path.is_file():
                    declared_files.append(path)
            assay_files = sorted(dict.fromkeys(declared_files))
    transcriptomics_files = [path for path in assay_files if path.parent == transcriptomics_dir.resolve()]
    representation = clinical_representation(str(root))
    patient_ids = set()
    clinical_record_count = 0
    for clinical_file in clinical_files:
        for record in _clinical_records(clinical_file):
            clinical_record_count += 1
            patient_id = extract_patient_id(record)
            if patient_id:
                patient_ids.add(patient_id)
    patient_count = len(patient_ids)
    tags: List[str] = []
    if patient_count:
        tags.append(_plural(patient_count, "patient"))
    if clinical_record_count:
        record_label = "timepoint" if representation == "snapshot" else "person record" if representation == "person" else "clinical record"
        tags.append(_plural(clinical_record_count, record_label))
    if assay_files:
        tags.append(_plural(len(assay_files), "matrix", "matrices"))
    large_hint = "large" in root.name.lower() or any(path.stat().st_size > 1_000_000 for path in transcriptomics_files)
    if large_hint:
        tags.append("large transcriptome")
    elif assay_files:
        tags.append("compact transcriptome")
    if "private" in root.name.lower():
        tags.append("private fixture")
    return {
        "content_tags": tags,
        "content_summary": "",
        "clinical_file_count": len(clinical_files),
        "assay_file_count": len(assay_files),
        "patient_count": patient_count,
        "clinical_record_count": clinical_record_count,
        "clinical_representation": representation,
    }


def workspace_fingerprint_for_data_dir(
    data_dir: str,
    *,
    dataset_id: str = "",
    dataset_ids: List[str] | None = None,
) -> Dict[str, Any]:
    clinical_dir = _workspace_clinical_dir(data_dir)
    items: List[Dict[str, Any]] = []
    for path in sorted(clinical_dir.iterdir()):
        if not path.is_file():
            continue
        if path.suffix not in {".json", ".gz"} and not path.name.endswith(".json.gz"):
            continue
        stat = path.stat()
        items.append(
            {
                "name": path.name,
                "size": int(stat.st_size),
                "mtime_ns": int(getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000))),
            }
        )
    normalized_ids = [normalize_dataset_id(item) for item in (dataset_ids or []) if normalize_dataset_id(item)]
    payload = {
        "dataset_id": str(dataset_id or "").strip(),
        "dataset_ids": normalized_ids,
        "clinical_files": items,
    }
    token = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return {
        **payload,
        "clinical_file_count": len(items),
        "token": token,
    }


def normalize_dataset_id(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    normalized = _SAFE_DATASET_ID_RE.sub("-", raw).strip("._-")
    return normalized


def normalize_query_granularity_ceiling(value: str | None) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in QUERY_GRANULARITY_CEILINGS:
        return normalized
    return DEFAULT_QUERY_GRANULARITY_CEILING


def normalize_data_classification(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in DATA_CLASSIFICATIONS:
        return normalized
    return DEFAULT_DATA_CLASSIFICATION


def normalize_ai_provider_access(value: str | None) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "use_thread_mode": "detailed_allowed",
        "detailed": "detailed_allowed",
        "full": "detailed_allowed",
        "full_context": "detailed_allowed",
        "summary_only": "safe_summary",
        "restricted": "safe_summary",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized in AI_PROVIDER_ACCESS_MODES:
        return normalized
    return DEFAULT_AI_PROVIDER_ACCESS


def _default_dataset_record() -> Dict[str, Any]:
    return {
        "dataset_id": DEFAULT_DATASET_ID,
        "name": "Default dataset",
        "description": "Primary shared development dataset.",
        "root_path": str(Path(DEFAULT_DATA_DIR).resolve()),
        "enabled": True,
        "visibility": "all_authenticated",
        "data_classification": "public",
        "allowed_users": [],
        "allowed_groups": [],
        "query_granularity_ceiling": "detailed",
        "ai_provider_access": DEFAULT_AI_PROVIDER_ACCESS,
        "created_by": "system",
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }


def _seed_dataset_records() -> List[Dict[str, Any]]:
    try:
        payload = json.loads(DATASET_REGISTRY_SEED_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = []
    records = []
    for item in payload if isinstance(payload, list) else []:
        normalized = _normalize_dataset_record(item)
        if normalized is not None:
            records.append(normalized)
    return records or [_default_dataset_record()]


def _normalize_dataset_record(item: Dict[str, Any]) -> Dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    dataset_id = normalize_dataset_id(item.get("dataset_id") or item.get("id"))
    if not dataset_id:
        return None
    root_path = str(item.get("root_path") or "").strip()
    if not root_path:
        return None
    root = Path(root_path).expanduser()
    if not root.is_absolute():
        root = BASE_DIR / root
    try:
        resolved_root = str(resolve_project_data_dir(str(root)))
    except FileNotFoundError:
        resolved_root = str(root.resolve())
    visibility = str(item.get("visibility") or "all_authenticated").strip().lower()
    if visibility not in DATASET_VISIBILITIES:
        visibility = "all_authenticated"
    allowed_users = sorted(
        {
            normalize_user_id(value)
            for value in (item.get("allowed_users") or [])
            if str(value or "").strip()
        }
    )
    allowed_groups = sorted(
        {
            str(value).strip()
            for value in (item.get("allowed_groups") or [])
            if str(value).strip()
        }
    )
    query_granularity_ceiling = normalize_query_granularity_ceiling(item.get("query_granularity_ceiling"))
    if dataset_id == DEFAULT_DATASET_ID and "query_granularity_ceiling" not in item:
        query_granularity_ceiling = "detailed"
    return {
        "dataset_id": dataset_id,
        "name": str(item.get("name") or dataset_id).strip() or dataset_id,
        "description": str(item.get("description") or "").strip(),
        "root_path": resolved_root,
        "enabled": bool(item.get("enabled", True)),
        "visibility": visibility,
        "data_classification": normalize_data_classification(item.get("data_classification")),
        "allowed_users": allowed_users,
        "allowed_groups": allowed_groups,
        "query_granularity_ceiling": query_granularity_ceiling,
        "ai_provider_access": normalize_ai_provider_access(item.get("ai_provider_access")),
        "created_by": str(item.get("created_by") or "system").strip() or "system",
        "created_at": str(item.get("created_at") or _now_iso()),
        "updated_at": str(item.get("updated_at") or _now_iso()),
    }


def _registry_lock_path() -> Path:
    path = _registry_path()
    return path.with_name(f".{path.name}.lock")


def _read_registry_unlocked() -> List[Dict[str, Any]]:
    path = _registry_path()
    if not path.exists():
        items = _seed_dataset_records()
        _write_registry_unlocked(items)
        return items
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError("Dataset registry is invalid; refusing to replace it.") from exc
    except OSError as exc:
        raise RuntimeError("Dataset registry could not be read.") from exc
    if not isinstance(payload, list):
        raise RuntimeError("Dataset registry must contain a JSON array; refusing to replace it.")
    items: List[Dict[str, Any]] = []
    for item in payload:
        normalized = _normalize_dataset_record(item)
        if normalized is not None:
            if str(normalized.get("dataset_id") or "") == DEFAULT_DATASET_ID:
                normalized["root_path"] = str(Path(DEFAULT_DATA_DIR).resolve())
            items.append(normalized)
    if not any(str(item.get("dataset_id") or "") == DEFAULT_DATASET_ID for item in items):
        items.insert(0, _default_dataset_record())
        _write_registry_unlocked(items)
    return items


def _read_registry() -> List[Dict[str, Any]]:
    with advisory_file_lock(_registry_lock_path()):
        return _read_registry_unlocked()


def _write_registry_unlocked(items: List[Dict[str, Any]]) -> None:
    atomic_write_json(_registry_path(), items)


def _write_registry(items: List[Dict[str, Any]]) -> None:
    with advisory_file_lock(_registry_lock_path()):
        _write_registry_unlocked(items)


def list_registered_datasets() -> List[Dict[str, Any]]:
    return _read_registry()


def get_dataset(dataset_id: str) -> Dict[str, Any] | None:
    needle = normalize_dataset_id(dataset_id)
    if not needle:
        return None
    for item in _read_registry():
        if str(item.get("dataset_id") or "") == needle:
            return item
    return None


def _request_user(request: Request | None) -> Dict[str, Any]:
    if request is None:
        return {"username": "local", "role": "admin", "display_name": "Local user"}
    if not auth_enabled():
        return {"username": "local", "role": "admin", "display_name": "Local user"}
    user = session_user(request)
    if user:
        return user
    return require_authenticated(request)


def user_can_access_dataset(user: Dict[str, Any], dataset: Dict[str, Any]) -> bool:
    if not dataset or not bool(dataset.get("enabled", True)):
        return False
    role = str(user.get("role") or "user")
    username = normalize_user_id(str(user.get("username") or ""))
    if role == "admin":
        return True
    visibility = str(dataset.get("visibility") or "all_authenticated")
    if visibility == "all_authenticated":
        return True
    if visibility == "admin_only":
        return False
    allowed_users = {
        normalize_user_id(item)
        for item in (dataset.get("allowed_users") or [])
        if str(item or "").strip()
    }
    if username in allowed_users:
        return True
    user_groups = {
        str(item).strip()
        for item in (user.get("groups") or [])
        if str(item).strip()
    }
    allowed_groups = {
        str(item).strip()
        for item in (dataset.get("allowed_groups") or [])
        if str(item).strip()
    }
    return bool(user_groups.intersection(allowed_groups))


def authorized_datasets_for_user(user: Dict[str, Any]) -> List[Dict[str, Any]]:
    items = [item for item in _read_registry() if user_can_access_dataset(user, item)]
    items.sort(key=lambda item: (str(item.get("name") or "").lower(), str(item.get("dataset_id") or "")))
    return items


def current_dataset_id(user_id: str) -> str:
    selected = current_dataset_ids(user_id)
    return selected[0] if selected else ""


def current_dataset_ids(user_id: str) -> List[str]:
    path = _selection_path(user_id)
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    ids = payload.get("dataset_ids")
    if isinstance(ids, list):
        normalized = []
        seen = set()
        for item in ids:
            value = normalize_dataset_id(item)
            if value and value not in seen:
                seen.add(value)
                normalized.append(value)
        if normalized:
            return normalized
    single = normalize_dataset_id(payload.get("dataset_id"))
    return [single] if single else []


def set_current_dataset(user_id: str, dataset_id: str) -> str:
    selected = set_current_datasets(user_id, [dataset_id])
    if not selected:
        raise ValueError("A dataset id is required.")
    return selected[0]


def set_current_datasets(user_id: str, dataset_ids: List[str]) -> List[str]:
    normalized_user = normalize_user_id(user_id)
    normalized_datasets = []
    seen = set()
    for item in dataset_ids:
        value = normalize_dataset_id(item)
        if value and value not in seen:
            seen.add(value)
            normalized_datasets.append(value)
    path = _selection_path(normalized_user)
    lock_path = path.with_name(f".{path.name}.lock")
    with advisory_file_lock(lock_path):
        atomic_write_json(
            path,
            {
                "dataset_id": normalized_datasets[0] if normalized_datasets else "",
                "dataset_ids": normalized_datasets,
            },
        )
    return normalized_datasets


def dataset_scope_id(dataset_ids: List[str]) -> str:
    normalized = [normalize_dataset_id(item) for item in dataset_ids if normalize_dataset_id(item)]
    normalized = sorted(dict.fromkeys(normalized))
    if not normalized:
        return ""
    if len(normalized) == 1:
        return normalized[0]
    return f"{_SCOPE_PREFIX}{'--'.join(normalized)}"


def parse_scope_dataset_ids(value: str | None) -> List[str]:
    raw = str(value or "").strip()
    if not raw:
        return []
    if "/" in raw or "\\" in raw:
        return []
    if raw.startswith(_SCOPE_PREFIX):
        parts = [normalize_dataset_id(item) for item in raw[len(_SCOPE_PREFIX):].split("--")]
        return [item for item in parts if item]
    normalized = normalize_dataset_id(raw)
    return [normalized] if normalized else []


def _scope_source_files_manifest(dataset_ids: List[str]) -> Dict[str, List[Dict[str, Any]]]:
    manifest = {"clinical_files": [], "assay_files": []}
    for dataset_id in dataset_ids:
        dataset = get_dataset(dataset_id)
        if dataset is None:
            continue
        dataset_root = Path(str(dataset.get("root_path") or "")).resolve()
        for key, directory, patterns in (
            ("clinical_files", dataset_root / "clinical", ("*.json", "*.json.gz")),
            ("assay_files", dataset_root / "assays", ("*/*.csv",)),
        ):
            seen_paths = set()
            for pattern in patterns:
                for path in sorted(directory.glob(pattern)):
                    if not path.is_file() or path in seen_paths:
                        continue
                    seen_paths.add(path)
                    stat = path.stat()
                    target_name = f"{dataset_id}__{path.name}"
                    if key == "assay_files":
                        target_name = f"{dataset_id}__{path.parent.name}__{path.name}"
                    manifest[key].append(
                        {
                            "dataset_id": dataset_id,
                            "source": str(path.resolve()),
                            "target": target_name,
                            "size": int(stat.st_size),
                            "mtime_ns": int(getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000))),
                        }
                    )
    return manifest


def resolve_dataset(request: Request | None = None, dataset_id: str | None = None) -> Dict[str, Any]:
    user = _request_user(request)
    requested_id = normalize_dataset_id(dataset_id)
    candidates = authorized_datasets_for_user(user)

    if requested_id:
        dataset = get_dataset(requested_id)
        if dataset is None or not user_can_access_dataset(user, dataset):
            raise HTTPException(status_code=403, detail="Dataset access denied.")
        if not bool(dataset.get("enabled", True)):
            raise HTTPException(status_code=404, detail="Dataset is disabled.")
        return dataset

    selected_ids = resolve_dataset_ids(request)
    if len(selected_ids) != 1:
        return {}
    return next(
        (item for item in candidates if str(item.get("dataset_id") or "") == selected_ids[0]),
        {},
    )


def resolve_dataset_dir(request: Request | None = None, dataset_id: str | None = None) -> str:
    dataset_ids = resolve_dataset_ids(request, dataset_id)
    if not dataset_ids:
        raise HTTPException(status_code=409, detail="No active workspace. Select and apply a dataset first.")
    if len(dataset_ids) == 1:
        return str(resolve_dataset(request, dataset_ids[0]).get("root_path") or "")
    return materialize_dataset_scope(dataset_ids)


def resolve_dataset_ids(request: Request | None = None, dataset_id: str | None = None) -> List[str]:
    user = _request_user(request)
    requested_ids = parse_scope_dataset_ids(dataset_id)
    candidates = authorized_datasets_for_user(user)
    if not candidates:
        raise HTTPException(status_code=404, detail="No authorized datasets are available.")
    candidate_map = {str(item.get("dataset_id") or ""): item for item in candidates}
    if requested_ids:
        resolved = []
        for item in requested_ids:
            dataset = candidate_map.get(item)
            if dataset is None:
                raise HTTPException(status_code=403, detail="Dataset access denied.")
            resolved.append(item)
        return resolved
    selected_ids = current_dataset_ids(str(user.get("username") or "local"))
    if not selected_ids:
        return []
    if any(item not in candidate_map for item in selected_ids):
        return []
    return selected_ids


def materialize_dataset_scope(dataset_ids: List[str]) -> str:
    normalized = sorted(dict.fromkeys([normalize_dataset_id(item) for item in dataset_ids if normalize_dataset_id(item)]))
    if not normalized:
        raise ValueError("At least one dataset id is required.")
    if len(normalized) == 1:
        dataset = get_dataset(normalized[0])
        if dataset is None:
            raise ValueError("Dataset not found.")
        return str(dataset.get("root_path") or "")
    scope_id = dataset_scope_id(normalized)
    root = _scope_root() / scope_id
    lock_path = root.with_name(f".{scope_id}.lock")
    with advisory_file_lock(lock_path):
        datasets = {dataset_id: get_dataset(dataset_id) for dataset_id in normalized}
        missing = [dataset_id for dataset_id, dataset in datasets.items() if dataset is None]
        if missing:
            raise ValueError(f"Dataset not found: {missing[0]}")
        manifest = {
            "schema_version": 1,
            "dataset_ids": normalized,
            "root_paths": [str(datasets[item].get("root_path") or "") for item in normalized],
            "clinical": {
                "representation": combined_clinical_representation(
                    [clinical_representation(str(datasets[item].get("root_path") or "")) for item in normalized]
                )
            },
            **_scope_source_files_manifest(normalized),
        }
        manifest_path = root / "manifest.json"
        if manifest_path.exists():
            try:
                stored = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                stored = None
            if stored == manifest and (root / "clinical").is_dir() and (root / "assays").is_dir():
                return str(root)

        temporary_root = root.with_name(f".{scope_id}.{uuid4().hex}.tmp")
        backup_root = root.with_name(f".{scope_id}.{uuid4().hex}.old")
        try:
            clinical_dir = temporary_root / "clinical"
            assays_dir = temporary_root / "assays"
            clinical_dir.mkdir(parents=True)
            assays_dir.mkdir(parents=True)
            for dataset_id in normalized:
                dataset_root = Path(str(datasets[dataset_id].get("root_path") or "")).resolve()
                for pattern in ("*.json", "*.json.gz"):
                    for path in sorted((dataset_root / "clinical").glob(pattern)):
                        (clinical_dir / f"{dataset_id}__{path.name}").symlink_to(path.resolve())
                for path in sorted((dataset_root / "assays").glob("*/*.csv")):
                    modality_dir = assays_dir / path.parent.name
                    modality_dir.mkdir(parents=True, exist_ok=True)
                    (modality_dir / f"{dataset_id}__{path.name}").symlink_to(path.resolve())
            atomic_write_json(temporary_root / "manifest.json", manifest)

            replaced_existing = root.exists()
            if replaced_existing:
                root.replace(backup_root)
            try:
                temporary_root.replace(root)
            except Exception:
                if replaced_existing and backup_root.exists():
                    backup_root.replace(root)
                raise
            if replaced_existing:
                shutil.rmtree(backup_root, ignore_errors=True)
        finally:
            shutil.rmtree(temporary_root, ignore_errors=True)
    return str(root)


def effective_query_granularity_ceiling(dataset_ids: List[str]) -> str:
    normalized = [normalize_dataset_id(item) for item in (dataset_ids or []) if normalize_dataset_id(item)]
    if not normalized:
        return DEFAULT_QUERY_GRANULARITY_CEILING
    ceiling = "detailed"
    for dataset_id in normalized:
        dataset = get_dataset(dataset_id)
        if dataset is None:
            continue
        item_ceiling = normalize_query_granularity_ceiling(dataset.get("query_granularity_ceiling"))
        if item_ceiling == "summary":
            return "summary"
    return ceiling


def effective_ai_provider_access(dataset_ids: List[str]) -> str:
    normalized = [normalize_dataset_id(item) for item in (dataset_ids or []) if normalize_dataset_id(item)]
    if not normalized:
        return DEFAULT_AI_PROVIDER_ACCESS
    order = {"blocked": 2, "safe_summary": 1, "detailed_allowed": 0}
    effective = DEFAULT_AI_PROVIDER_ACCESS
    for dataset_id in normalized:
        dataset = get_dataset(dataset_id)
        if dataset is None:
            continue
        item_mode = normalize_ai_provider_access(dataset.get("ai_provider_access"))
        if order[item_mode] > order[effective]:
            effective = item_mode
    return effective


def effective_data_classification(dataset_ids: List[str]) -> str:
    normalized = [normalize_dataset_id(item) for item in (dataset_ids or []) if normalize_dataset_id(item)]
    if not normalized:
        return DEFAULT_DATA_CLASSIFICATION
    for dataset_id in normalized:
        dataset = get_dataset(dataset_id)
        if dataset is None or normalize_data_classification(dataset.get("data_classification")) == "private":
            return "private"
    return "public"


def constrain_ai_provider_access(
    dataset_ids: List[str],
    ai_provider_access: str | None,
    provider_data_boundary: str | None,
) -> str:
    normalized_access = normalize_ai_provider_access(ai_provider_access)
    normalized_boundary = str(provider_data_boundary or "").strip().lower()
    if normalized_boundary != "local" and effective_data_classification(dataset_ids) == "private":
        return "blocked"
    return normalized_access


def register_dataset(
    *,
    name: str,
    root_path: str,
    description: str = "",
    visibility: str = "all_authenticated",
    data_classification: str = DEFAULT_DATA_CLASSIFICATION,
    allowed_users: List[str] | None = None,
    allowed_groups: List[str] | None = None,
    query_granularity_ceiling: str = DEFAULT_QUERY_GRANULARITY_CEILING,
    ai_provider_access: str = DEFAULT_AI_PROVIDER_ACCESS,
    enabled: bool = True,
    created_by: str = "system",
) -> Dict[str, Any]:
    normalized_name = str(name or "").strip()
    if not normalized_name:
        raise ValueError("Dataset name is required.")
    resolved_root = str(validate_dataset_release_root(root_path))
    normalized_visibility = str(visibility or "all_authenticated").strip().lower()
    if normalized_visibility not in DATASET_VISIBILITIES:
        raise ValueError("Invalid dataset visibility.")
    normalized_data_classification = normalize_data_classification(data_classification)
    if str(data_classification or "").strip().lower() not in DATA_CLASSIFICATIONS:
        raise ValueError("Invalid data classification.")
    base_id = normalize_dataset_id(normalized_name) or "dataset"
    now = _now_iso()
    item = {
        "dataset_id": base_id,
        "name": normalized_name,
        "description": str(description or "").strip(),
        "root_path": resolved_root,
        "enabled": bool(enabled),
        "visibility": normalized_visibility,
        "data_classification": normalized_data_classification,
        "allowed_users": sorted(
            {
                normalize_user_id(value)
                for value in (allowed_users or [])
                if str(value or "").strip()
            }
        ),
        "allowed_groups": sorted(
            {
                str(value).strip()
                for value in (allowed_groups or [])
                if str(value).strip()
            }
        ),
        "query_granularity_ceiling": normalize_query_granularity_ceiling(query_granularity_ceiling),
        "ai_provider_access": normalize_ai_provider_access(ai_provider_access),
        "created_by": str(created_by or "system").strip() or "system",
        "created_at": now,
        "updated_at": now,
    }
    with advisory_file_lock(_registry_lock_path()):
        items = _read_registry_unlocked()
        dataset_id = base_id
        suffix = 2
        existing_ids = {str(existing.get("dataset_id") or "") for existing in items}
        while dataset_id in existing_ids:
            dataset_id = f"{base_id}-{suffix}"
            suffix += 1
        item["dataset_id"] = dataset_id
        items.append(item)
        _write_registry_unlocked(items)
    return item


def update_dataset(
    dataset_id: str,
    *,
    name: str | None = None,
    root_path: str | None = None,
    description: str | None = None,
    visibility: str | None = None,
    data_classification: str | None = None,
    allowed_users: List[str] | None = None,
    allowed_groups: List[str] | None = None,
    query_granularity_ceiling: str | None = None,
    ai_provider_access: str | None = None,
    enabled: bool | None = None,
) -> Dict[str, Any]:
    needle = normalize_dataset_id(dataset_id)
    with advisory_file_lock(_registry_lock_path()):
        items = _read_registry_unlocked()
        for index, item in enumerate(items):
            if str(item.get("dataset_id") or "") != needle:
                continue
            updated = dict(item)
            if name is not None:
                updated["name"] = str(name).strip() or updated["name"]
            if root_path is not None:
                updated["root_path"] = str(validate_dataset_release_root(root_path))
            if description is not None:
                updated["description"] = str(description).strip()
            if visibility is not None:
                normalized_visibility = str(visibility or "").strip().lower()
                if normalized_visibility not in DATASET_VISIBILITIES:
                    raise ValueError("Invalid dataset visibility.")
                updated["visibility"] = normalized_visibility
            if data_classification is not None:
                normalized_data_classification = str(data_classification or "").strip().lower()
                if normalized_data_classification not in DATA_CLASSIFICATIONS:
                    raise ValueError("Invalid data classification.")
                updated["data_classification"] = normalized_data_classification
            if allowed_users is not None:
                updated["allowed_users"] = sorted(
                    {
                        normalize_user_id(value)
                        for value in allowed_users
                        if str(value or "").strip()
                    }
                )
            if allowed_groups is not None:
                updated["allowed_groups"] = sorted(
                    {
                        str(value).strip()
                        for value in allowed_groups
                        if str(value).strip()
                    }
                )
            if query_granularity_ceiling is not None:
                updated["query_granularity_ceiling"] = normalize_query_granularity_ceiling(query_granularity_ceiling)
            if ai_provider_access is not None:
                updated["ai_provider_access"] = normalize_ai_provider_access(ai_provider_access)
            if enabled is not None:
                updated["enabled"] = bool(enabled)
            updated["updated_at"] = _now_iso()
            items[index] = updated
            _write_registry_unlocked(items)
            return updated
    raise ValueError("Dataset not found.")


def unregister_dataset(dataset_id: str) -> Dict[str, Any]:
    needle = normalize_dataset_id(dataset_id)
    if not needle:
        raise ValueError("A dataset id is required.")
    if needle == DEFAULT_DATASET_ID:
        raise ValueError("The default dataset cannot be unregistered.")
    with advisory_file_lock(_registry_lock_path()):
        items = _read_registry_unlocked()
        for index, item in enumerate(items):
            if str(item.get("dataset_id") or "") != needle:
                continue
            removed = items.pop(index)
            _write_registry_unlocked(items)
            return removed
    raise ValueError("Dataset not found.")
