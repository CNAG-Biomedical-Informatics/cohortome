from __future__ import annotations

import csv
import hashlib
import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote
from uuid import uuid4

from app.config import BASE_DIR, CACHE_ROOT_DIR
from app.bff import (
    build_visit_context,
    ensure_data_dir,
    extract_patient_id,
    extract_treatment_labels,
    normalize_value,
    read_bff_records,
    resolve_project_data_dir,
)
from app.datasets import get_dataset, list_registered_datasets, normalize_dataset_id, parse_scope_dataset_ids
from app.state_io import advisory_file_lock, atomic_write_json

try:
    import duckdb
except ImportError:  # pragma: no cover - optional runtime dependency
    duckdb = None


QUERY_STORE_DIR = CACHE_ROOT_DIR / "query-store"
GENE_ANNOTATION_PATH = BASE_DIR / "scripts" / "data" / "hgnc_protein_coding_symbols.tsv"
ASSAY_DATA_DIR: Path | None = None
QUERY_STORE_SCHEMA_VERSION = 4


class QueryStoreNotReadyError(RuntimeError):
    pass


def duckdb_available() -> bool:
    return duckdb is not None


def _extract_disease_labels(record: Dict[str, Any]) -> List[str]:
    diseases = record.get("diseases")
    labels: List[str] = []
    if not isinstance(diseases, list):
        return labels
    for item in diseases:
        if not isinstance(item, dict):
            continue
        code = item.get("diseaseCode")
        if not isinstance(code, dict):
            continue
        label = normalize_value(code.get("label")) or normalize_value(code.get("id"))
        if label is None:
            continue
        text = str(label)
        if text not in labels:
            labels.append(text)
    return labels


def _store_key(data_dir: str) -> str:
    resolved_dir = ensure_data_dir(data_dir)
    digest = hashlib.sha256(str(resolved_dir).encode("utf-8")).hexdigest()
    return digest[:16]


def _store_paths_for_data_dir(data_dir: str) -> Tuple[Path, Path]:
    key = _store_key(data_dir)
    QUERY_STORE_DIR.mkdir(parents=True, exist_ok=True)
    return QUERY_STORE_DIR / f"{key}.duckdb", QUERY_STORE_DIR / f"{key}.meta.json"


def _store_paths(data_dir: str) -> Tuple[Path, Path]:
    return _store_paths_for_data_dir(data_dir)


def _dataset_store_paths(dataset_id: str) -> Tuple[Path, Path, Path]:
    normalized = normalize_dataset_id(dataset_id)
    if not normalized:
        raise ValueError("A dataset id is required.")
    QUERY_STORE_DIR.mkdir(parents=True, exist_ok=True)
    return (
        QUERY_STORE_DIR / f"dataset-{normalized}.duckdb",
        QUERY_STORE_DIR / f"dataset-{normalized}.meta.json",
        QUERY_STORE_DIR / f"dataset-{normalized}.status.json",
    )


def _dataset_root_path(dataset_id: str) -> Path:
    dataset = get_dataset(dataset_id)
    if dataset is None:
        raise ValueError(f"Dataset not found: {dataset_id}")
    root_path = str(dataset.get("root_path") or "").strip()
    if not root_path:
        raise ValueError(f"Dataset root is not configured: {dataset_id}")
    return Path(root_path).expanduser().resolve()


def _scope_manifest_dataset_ids(path: Path) -> List[str]:
    candidates = [path]
    if path.name in {"clinical", "assays", "transcriptomics"}:
        candidates.append(path.parent)
    for candidate in candidates:
        manifest_path = candidate / "manifest.json"
        if not manifest_path.exists():
            continue
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        dataset_ids = payload.get("dataset_ids")
        if isinstance(dataset_ids, list):
            normalized = [normalize_dataset_id(item) for item in dataset_ids if normalize_dataset_id(item)]
            if normalized:
                return normalized
    return []


def _workspace_dataset_ids(workspace_key: str) -> List[str]:
    raw = str(workspace_key or "").strip()
    if not raw:
        return []
    parsed = parse_scope_dataset_ids(raw)
    if parsed:
        return parsed
    try:
        resolved = Path(raw).expanduser().resolve()
    except OSError:
        return []
    scope_ids = _scope_manifest_dataset_ids(resolved)
    if scope_ids:
        return scope_ids
    for dataset in list_registered_datasets():
        dataset_id = normalize_dataset_id(dataset.get("dataset_id"))
        root_path = Path(str(dataset.get("root_path") or "")).expanduser().resolve()
        if resolved in {root_path, root_path / "clinical", root_path / "assays", root_path / "assays" / "transcriptomics"}:
            return [dataset_id]
    return []


def _resolve_assay_transcriptomics_dir(data_dir: str) -> Path | None:
    if ASSAY_DATA_DIR is not None:
        return Path(ASSAY_DATA_DIR).expanduser().resolve()
    project_root = resolve_project_data_dir(data_dir)
    candidate = project_root / "assays" / "transcriptomics"
    if candidate.exists() and candidate.is_dir():
        return candidate.resolve()
    return None


@lru_cache(maxsize=1)
def _gene_annotation_index() -> Dict[str, Dict[str, str]]:
    annotations: Dict[str, Dict[str, str]] = {}
    if not GENE_ANNOTATION_PATH.exists():
        return annotations
    with GENE_ANNOTATION_PATH.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            gene_id = str(row.get("ensembl_gene_id") or "").strip()
            if not gene_id:
                continue
            annotations[gene_id] = {
                "gene_symbol": str(row.get("symbol") or "").strip(),
                "gene_name": str(row.get("name") or "").strip(),
            }
    return annotations


def _ensembl_gene_url(gene_id: str) -> str:
    normalized = str(gene_id or "").strip()
    if not normalized.startswith("ENSG"):
        return ""
    return f"https://www.ensembl.org/Homo_sapiens/Gene/Summary?g={quote(normalized)}"


def _gene_annotation(gene_id: str) -> Dict[str, str]:
    normalized = str(gene_id or "").strip()
    annotation = dict(_gene_annotation_index().get(normalized) or {})
    annotation["gene_symbol"] = str(annotation.get("gene_symbol") or "").strip()
    annotation["gene_name"] = str(annotation.get("gene_name") or "").strip()
    annotation["ensembl_url"] = _ensembl_gene_url(normalized)
    return annotation


def assay_feature_annotations(gene_ids: List[str], data_dir: str = "", dataset_name: str = "") -> Dict[str, Dict[str, str]]:
    item = _manifest_assay_item(data_dir, dataset_name) if data_dir and dataset_name else None
    declared = (item or {}).get("feature_annotations", {})
    if not isinstance(declared, dict):
        declared = {}
    payload: Dict[str, Dict[str, str]] = {}
    for raw_gene_id in gene_ids:
        gene_id = str(raw_gene_id or "").strip()
        if not gene_id:
            continue
        annotation = _gene_annotation(gene_id)
        supplied = declared.get(gene_id, {})
        if isinstance(supplied, dict):
            annotation.update({key: str(supplied[key]).strip() for key in ("label", "description", "unit")
                               if isinstance(supplied.get(key), str) and supplied[key].strip()})
        if any(annotation.values()):
            payload[gene_id] = annotation
    return payload


def _assay_matrix_files(data_dir: str) -> List[Path]:
    assay_dir = _resolve_assay_transcriptomics_dir(data_dir)
    if assay_dir is None:
        return []
    discovered = [path for path in sorted(assay_dir.glob("*.csv")) if path.is_file()]
    root = resolve_project_data_dir(data_dir)
    manifest_path = root / "assays" / "manifest.json"
    if manifest_path.is_file():
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        items = payload.get("assays") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            return []
        declared_count_paths: set[Path] = set()
        excluded_paths: set[Path] = set()
        for item in items:
            if not isinstance(item, dict):
                continue
            modality = str(item.get("modality") or "").strip()
            data_type = str(item.get("data_type") or "").strip()
            relative_file = str(item.get("file") or "").strip()
            if relative_file:
                path = (root / relative_file).resolve()
                try:
                    path.relative_to(root.resolve())
                except ValueError:
                    path = None
                if path is not None:
                    if modality == "transcriptomics" and data_type == "raw_counts":
                        declared_count_paths.add(path)
                    else:
                        excluded_paths.add(path)
            for key, raw_value in item.items():
                if key == "file" or not key.endswith("_file"):
                    continue
                auxiliary_file = str(raw_value or "").strip()
                if not auxiliary_file:
                    continue
                auxiliary_path = (root / auxiliary_file).resolve()
                try:
                    auxiliary_path.relative_to(root.resolve())
                except ValueError:
                    continue
                excluded_paths.add(auxiliary_path)
        return [
            path
            for path in discovered
            if path in declared_count_paths or path not in excluded_paths
        ]
    return discovered


def _assay_source_files(root: Path) -> List[Path]:
    assays_root = root / "assays"
    if not assays_root.exists() or not assays_root.is_dir():
        return []
    paths = []
    manifest_path = assays_root / "manifest.json"
    if manifest_path.is_file():
        paths.append(manifest_path)
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
        for item in payload.get("assays", []) if isinstance(payload, dict) else []:
            if not isinstance(item, dict):
                continue
            for key, raw_value in item.items():
                if key != "file" and not str(key).endswith("_file"):
                    continue
                relative_file = str(raw_value or "").strip()
                if not relative_file:
                    continue
                candidate = (root / relative_file).resolve()
                try:
                    candidate.relative_to(root.resolve())
                except ValueError:
                    continue
                if candidate.is_file():
                    paths.append(candidate)
    paths.extend(path for path in sorted(assays_root.glob("*/*.csv")) if path.is_file())
    return sorted(dict.fromkeys(paths))


def _clarid_subject_config(root: Path) -> Tuple[Dict[str, Any], Path] | None:
    manifest_path = root / "manifest.json"
    manifest = _load_json(manifest_path)
    identifiers = manifest.get("identifiers") if isinstance(manifest, dict) else None
    config = identifiers.get("clarid_subjects") if isinstance(identifiers, dict) else None
    if config is None:
        return None
    if not isinstance(config, dict):
        raise ValueError("Dataset identifiers.clarid_subjects must be an object.")
    relative_file = str(config.get("file") or "").strip()
    if not relative_file:
        raise ValueError("Dataset identifiers.clarid_subjects.file is required.")
    root_resolved = root.resolve()
    path = (root_resolved / relative_file).resolve()
    try:
        path.relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError("ClarID subject data must resolve inside the dataset release.") from exc
    if not path.is_file():
        raise ValueError("ClarID subject data file is missing from the dataset release.")
    if str(config.get("entity") or "subject").strip().lower() != "subject":
        raise ValueError("Dataset identifiers.clarid_subjects.entity must be subject.")
    if not str(config.get("codebook_version") or "").strip():
        raise ValueError("Dataset identifiers.clarid_subjects.codebook_version is required.")
    if not str(config.get("tools_version") or "").strip():
        raise ValueError("Dataset identifiers.clarid_subjects.tools_version is required.")
    return config, path


def _identifier_source_files(root: Path) -> List[Path]:
    configured = _clarid_subject_config(root)
    if configured is None:
        return []
    return [root / "manifest.json", configured[1]]


def _source_files_signature(data_dir: str) -> Dict[str, Any]:
    resolved_dir = ensure_data_dir(data_dir)
    project_root = resolve_project_data_dir(data_dir)
    files = []
    for path in sorted(resolved_dir.glob("*.json")):
        if not path.is_file():
            continue
        stat = path.stat()
        files.append(
            {
                "path": str(path),
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
            }
        )
    assay_files = []
    for path in _assay_source_files(project_root):
        stat = path.stat()
        assay_files.append(
            {
                "path": str(path.resolve()),
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
            }
        )
    identifier_files = []
    for path in _identifier_source_files(project_root):
        stat = path.stat()
        identifier_files.append(
            {
                "path": str(path.resolve()),
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
            }
        )
    payload = {
        "schema_version": QUERY_STORE_SCHEMA_VERSION,
        "data_dir": str(resolved_dir),
        "files": files,
        "assay_files": assay_files,
    }
    if identifier_files:
        payload["identifier_files"] = identifier_files
    return payload


def _detect_matrix_delimiter(header_line: str) -> str:
    candidates = ("\t", ";", ",")
    parsed_widths = {
        delimiter: len(next(csv.reader([str(header_line or "")], delimiter=delimiter), []))
        for delimiter in candidates
    }
    return max(candidates, key=lambda delimiter: parsed_widths[delimiter])


def _read_subject_clarid_rows(root: Path, patient_ids: set[str]) -> List[Tuple[Any, ...]]:
    configured = _clarid_subject_config(root)
    if configured is None:
        return []
    config, path = configured
    required_columns = {
        "unique_id",
        "subject_id",
        "study",
        "type",
        "condition",
        "sex",
        "age_group",
        "clar_id",
        "stub_id",
    }
    codebook_version = str(config.get("codebook_version") or "").strip()
    tools_version = str(config.get("tools_version") or "").strip()
    delimiter = str(config.get("delimiter") or ",")
    if delimiter == "\\t":
        delimiter = "\t"
    if len(delimiter) != 1:
        raise ValueError("ClarID subject delimiter must be one character.")

    rows: List[Tuple[Any, ...]] = []
    seen_patient_ids: set[str] = set()
    seen_subject_ids: set[int] = set()
    seen_human_ids: set[str] = set()
    seen_stub_ids: set[str] = set()
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        fieldnames = {str(item or "").strip() for item in (reader.fieldnames or [])}
        missing_columns = sorted(required_columns - fieldnames)
        if missing_columns:
            raise ValueError(
                "ClarID subject data is missing required columns: " + ", ".join(missing_columns)
            )
        for row_number, raw in enumerate(reader, start=2):
            values = {key: str(raw.get(key) or "").strip() for key in required_columns}
            missing_values = sorted(key for key, value in values.items() if not value)
            if missing_values:
                raise ValueError(
                    f"ClarID subject row {row_number} has empty required values: "
                    + ", ".join(missing_values)
                )
            patient_id = values["unique_id"]
            try:
                subject_id = int(values["subject_id"])
            except ValueError as exc:
                raise ValueError(f"ClarID subject row {row_number} has a non-numeric subject_id.") from exc
            if subject_id < 0:
                raise ValueError(f"ClarID subject row {row_number} has a negative subject_id.")
            if patient_id in seen_patient_ids:
                raise ValueError("ClarID subject data contains duplicate unique_id values.")
            if subject_id in seen_subject_ids:
                raise ValueError("ClarID subject data contains duplicate numeric subject_id values.")
            if values["clar_id"] in seen_human_ids:
                raise ValueError("ClarID subject data contains duplicate human-readable identifiers.")
            if values["stub_id"] in seen_stub_ids:
                raise ValueError("ClarID subject data contains duplicate stub identifiers.")
            seen_patient_ids.add(patient_id)
            seen_subject_ids.add(subject_id)
            seen_human_ids.add(values["clar_id"])
            seen_stub_ids.add(values["stub_id"])
            rows.append(
                (
                    patient_id,
                    subject_id,
                    values["clar_id"],
                    values["stub_id"],
                    values["study"],
                    values["type"],
                    values["condition"],
                    values["sex"],
                    values["age_group"],
                    codebook_version,
                    tools_version,
                    str(raw.get("condition_name") or "").strip(),
                )
            )
    missing_patients = patient_ids - seen_patient_ids
    unknown_patients = seen_patient_ids - patient_ids
    if missing_patients or unknown_patients:
        raise ValueError(
            "ClarID subject coverage must exactly match the clinical patient inventory "
            f"(missing={len(missing_patients)}, unknown={len(unknown_patients)})."
        )
    return rows


def _read_transcriptomics_matrix(path: Path) -> Tuple[str, List[str], List[Tuple[str, List[int]]]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        first_line = handle.readline()
        if not first_line:
            return path.stem, [], []
        delimiter = _detect_matrix_delimiter(first_line)
        handle.seek(0)
        reader = csv.reader(handle, delimiter=delimiter)
        try:
            header = next(reader)
        except StopIteration:
            return path.stem, [], []
        if len(header) < 2:
            return path.stem, [], []
        sample_ids = [str(item).strip() for item in header[1:] if str(item).strip()]
        rows: List[Tuple[str, List[int]]] = []
        for raw_row in reader:
            if not raw_row:
                continue
            gene_id = str(raw_row[0]).strip()
            if not gene_id:
                continue
            values: List[int] = []
            for index, sample_id in enumerate(sample_ids, start=1):
                token = raw_row[index].strip() if index < len(raw_row) else ""
                try:
                    values.append(int(float(token or "0")))
                except ValueError:
                    values.append(0)
            rows.append((gene_id, values))
        return path.stem, sample_ids, rows


def _read_transcriptomics_matrix_header(path: Path) -> Tuple[str, str, List[str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        first_line = handle.readline()
        if not first_line:
            return path.stem, ";", []
        delimiter = _detect_matrix_delimiter(first_line)
        handle.seek(0)
        reader = csv.reader(handle, delimiter=delimiter)
        try:
            header = next(reader)
        except StopIteration:
            return path.stem, delimiter, []
    sample_ids = [str(item).strip() for item in header[1:] if str(item).strip()]
    return path.stem, delimiter, sample_ids


def _patient_id_from_assay_sample(sample_id: str) -> str:
    value = str(sample_id).strip()
    if ":" in value:
        return value.split(":", 1)[0].strip() or value
    return value


def _connect(data_dir: str):
    if duckdb is None:
        raise RuntimeError("duckdb is not installed")
    dataset_ids = _workspace_dataset_ids(data_dir)
    if not dataset_ids:
        db_path, _ = _store_paths_for_data_dir(data_dir)
        return duckdb.connect(str(db_path))
    return _connect_workspace(dataset_ids)


def _load_json(path: Path) -> Dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    atomic_write_json(path, payload)


def _signature_payload(payload: Dict[str, Any] | None) -> Dict[str, Any] | None:
    if payload is None:
        return None
    return {key: value for key, value in payload.items() if key != "built_at"}


def _store_has_required_tables(db_path: Path) -> bool:
    if duckdb is None or not db_path.exists():
        return False
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute("SHOW TABLES").fetchall()
    finally:
        con.close()
    existing = {str(row[0]) for row in rows}
    required = {
        "patients",
        "timepoints",
        "patient_diseases",
        "patient_medications",
        "disease_events",
        "medication_events",
        "assay_samples",
        "transcript_counts",
    }
    return required.issubset(existing)


def _dataset_source_signature(dataset_id: str) -> Dict[str, Any]:
    dataset_root = _dataset_root_path(dataset_id)
    clinical_dir = dataset_root / "clinical"
    files = []
    if clinical_dir.exists():
        for pattern in ("*.json", "*.json.gz"):
            for path in sorted(clinical_dir.glob(pattern)):
                if not path.is_file():
                    continue
                stat = path.stat()
                files.append(
                    {
                        "path": str(path.resolve()),
                        "size": stat.st_size,
                        "mtime_ns": stat.st_mtime_ns,
                    }
                )
    assay_files = []
    for path in _assay_source_files(dataset_root):
        stat = path.stat()
        assay_files.append(
            {
                "path": str(path.resolve()),
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
            }
        )
    identifier_files = []
    for path in _identifier_source_files(dataset_root):
        stat = path.stat()
        identifier_files.append(
            {
                "path": str(path.resolve()),
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
            }
        )
    payload = {
        "schema_version": QUERY_STORE_SCHEMA_VERSION,
        "dataset_id": normalize_dataset_id(dataset_id),
        "root_path": str(dataset_root),
        "files": files,
        "assay_files": assay_files,
    }
    if identifier_files:
        payload["identifier_files"] = identifier_files
    return payload


def dataset_query_store_status(dataset_id: str) -> Dict[str, Any]:
    normalized = normalize_dataset_id(dataset_id)
    if not normalized:
        return {"dataset_id": "", "status": "not_built", "ready": False}
    db_path, meta_path, status_path = _dataset_store_paths(normalized)
    status_payload = _load_json(status_path) or {}
    try:
        current_signature = _dataset_source_signature(normalized)
    except ValueError as exc:
        return {
            "dataset_id": normalized,
            "status": "failed",
            "ready": False,
            "last_built_at": str(status_payload.get("last_built_at") or ""),
            "last_error": str(exc),
        }
    stored_signature = _load_json(meta_path)
    if _signature_payload(stored_signature) == current_signature and _store_has_required_tables(db_path):
        return {
            "dataset_id": normalized,
            "status": "ready",
            "ready": True,
            "last_built_at": str((stored_signature or {}).get("built_at") or status_payload.get("last_built_at") or ""),
            "last_error": "",
        }
    if str(status_payload.get("status") or "").strip().lower() == "building":
        return {
            "dataset_id": normalized,
            "status": "building",
            "ready": False,
            "last_built_at": str(status_payload.get("last_built_at") or ""),
            "last_error": str(status_payload.get("last_error") or ""),
        }
    if stored_signature is not None or db_path.exists():
        return {
            "dataset_id": normalized,
            "status": "stale",
            "ready": False,
            "last_built_at": str((stored_signature or {}).get("built_at") or status_payload.get("last_built_at") or ""),
            "last_error": str(status_payload.get("last_error") or ""),
        }
    if str(status_payload.get("status") or "").strip().lower() == "failed":
        return {
            "dataset_id": normalized,
            "status": "failed",
            "ready": False,
            "last_built_at": str(status_payload.get("last_built_at") or ""),
            "last_error": str(status_payload.get("last_error") or ""),
        }
    return {
        "dataset_id": normalized,
        "status": "not_built",
        "ready": False,
        "last_built_at": "",
        "last_error": str(status_payload.get("last_error") or ""),
    }


def _store_ready_or_raise(dataset_id: str) -> None:
    status = dataset_query_store_status(dataset_id)
    if status.get("ready"):
        return
    dataset = get_dataset(dataset_id) or {"name": dataset_id}
    label = str(dataset.get("name") or dataset_id).strip() or dataset_id
    reason = str(status.get("status") or "not_built")
    detail = str(status.get("last_error") or "").strip()
    message = f'Dataset store not ready for "{label}": {reason}'
    if detail:
        message = f"{message}. {detail}"
    raise QueryStoreNotReadyError(message)


def ensure_dataset_query_stores_ready(dataset_ids: List[str]) -> None:
    for dataset_id in dataset_ids:
        _store_ready_or_raise(dataset_id)


def remove_dataset_query_store(dataset_id: str) -> None:
    normalized = normalize_dataset_id(dataset_id)
    if not normalized:
        raise ValueError("A dataset id is required.")
    db_path, meta_path, status_path = _dataset_store_paths(normalized)
    lock_path = status_path.with_name(f".{status_path.name}.lock")
    with advisory_file_lock(lock_path):
        db_path.unlink(missing_ok=True)
        meta_path.unlink(missing_ok=True)
        status_path.unlink(missing_ok=True)


def prepare_dataset_query_store(dataset_id: str) -> Dict[str, Any]:
    normalized = normalize_dataset_id(dataset_id)
    if not normalized:
        raise ValueError("A dataset id is required.")
    db_path, meta_path, status_path = _dataset_store_paths(normalized)
    lock_path = status_path.with_name(f".{status_path.name}.lock")
    with advisory_file_lock(lock_path):
        dataset_root = _dataset_root_path(normalized)
        current_signature = _dataset_source_signature(normalized)
        previous_status = _load_json(status_path) or {}
        _write_json(
            status_path,
            {
                "dataset_id": normalized,
                "status": "building",
                "last_built_at": str(previous_status.get("last_built_at") or ""),
                "last_error": "",
            },
        )
        temp_suffix = f".tmp.{normalized}.{uuid4().hex}"
        temp_db = db_path.with_name(f"{db_path.stem}{temp_suffix}{db_path.suffix}")
        temp_meta = meta_path.with_name(f"{meta_path.stem}{temp_suffix}{meta_path.suffix}")
        try:
            _build_query_store(str(dataset_root), temp_db, temp_meta, current_signature)
            built_meta = _load_json(temp_meta) or dict(current_signature)
            built_meta["built_at"] = built_meta.get("built_at") or str(Path(temp_db).stat().st_mtime_ns)
            _write_json(temp_meta, built_meta)
            temp_db.replace(db_path)
            temp_meta.replace(meta_path)
            _write_json(
                status_path,
                {
                    "dataset_id": normalized,
                    "status": "ready",
                    "last_built_at": str(built_meta.get("built_at") or ""),
                    "last_error": "",
                },
            )
        except Exception as exc:
            temp_db.unlink(missing_ok=True)
            temp_meta.unlink(missing_ok=True)
            _write_json(
                status_path,
                {
                    "dataset_id": normalized,
                    "status": "failed",
                    "last_built_at": str(previous_status.get("last_built_at") or ""),
                    "last_error": str(exc),
                },
            )
            raise
    return dataset_query_store_status(normalized)


def _sql_literal(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _sql_identifier(value: str) -> str:
    return '"' + str(value).replace('"', '""') + '"'


def _relation_exists(con: Any, relation: str) -> bool:
    try:
        con.execute(f"SELECT 1 FROM {relation} LIMIT 0")
    except Exception:
        return False
    return True


def _union_select(aliases: List[str], expression: str) -> str:
    return " UNION ALL ".join(expression.format(alias=alias) for alias in aliases)


def _insert_transcript_matrix(con: Any, matrix_path: Path) -> List[Tuple[str, str, str, str, str]]:
    dataset_name, delimiter, sample_ids = _read_transcriptomics_matrix_header(matrix_path)
    if not sample_ids:
        return []
    dataset_literal = _sql_literal(dataset_name)
    matrix_literal = _sql_literal(str(matrix_path))
    delimiter_literal = _sql_literal(delimiter)
    sample_identifier_list = ", ".join(_sql_identifier(sample_id) for sample_id in sample_ids)
    con.execute(
        f"""
        INSERT INTO transcript_counts
        SELECT
            {dataset_literal} AS dataset_name,
            sample_id,
            CASE
                WHEN strpos(sample_id, ':') > 0 THEN split_part(sample_id, ':', 1)
                ELSE sample_id
            END AS patient_id,
            gene_id,
            coalesce(try_cast(raw_count AS BIGINT), 0) AS raw_count
        FROM (
            SELECT *
            FROM read_csv(
                {matrix_literal},
                delim={delimiter_literal},
                header=true,
                all_varchar=true
            )
        ) AS matrix
        UNPIVOT(raw_count FOR sample_id IN ({sample_identifier_list}))
        WHERE coalesce(trim(gene_id), '') <> ''
        """
    )
    return [
        (dataset_name, sample_id, _patient_id_from_assay_sample(sample_id), "transcriptomics", "raw_counts")
        for sample_id in sample_ids
    ]


def _connect_workspace(dataset_ids: List[str]):
    if duckdb is None:
        raise RuntimeError("duckdb is not installed")
    normalized = [normalize_dataset_id(item) for item in dataset_ids if normalize_dataset_id(item)]
    if not normalized:
        raise RuntimeError("At least one dataset is required.")
    for dataset_id in normalized:
        _store_ready_or_raise(dataset_id)
    if len(normalized) == 1:
        db_path, _, _ = _dataset_store_paths(normalized[0])
        return duckdb.connect(str(db_path), read_only=True)
    con = duckdb.connect()
    from app.identities import identity_key
    con.create_function('cohortome_identity', identity_key, ['VARCHAR', 'VARCHAR', 'VARCHAR'], 'VARCHAR')
    aliases: List[str] = []
    multi_dataset = len(normalized) > 1
    for index, dataset_id in enumerate(normalized):
        alias = f"ds{index}"
        db_path, _, _ = _dataset_store_paths(dataset_id)
        con.execute(f"ATTACH {_sql_literal(str(db_path))} AS {alias} (READ_ONLY)")
        scoped = f'scoped_ds{index}'
        con.execute(f'CREATE SCHEMA {scoped}')
        for table in ['patients', 'patient_diseases', 'patient_medications', 'patient_clarids',
                      'timepoints', 'disease_events', 'medication_events', 'assay_samples', 'transcript_counts']:
            if not _relation_exists(con, f'{alias}.{table}'):
                continue
            columns = {row[0] for row in con.execute(f'DESCRIBE {alias}.{table}').fetchall()}
            replacements = [f"cohortome_identity({_sql_literal(dataset_id)}, '{kind}', {column}) AS {column}"
                            for column, kind in [('patient_id', 'patient'), ('original_id', 'sample'), ('sample_id', 'sample')]]
            replacements = [expression for expression in replacements if expression.rsplit(' AS ', 1)[1] in columns]
            projection = '* REPLACE (' + ', '.join(replacements) + ')' if replacements else '*'
            con.execute(f'CREATE VIEW {scoped}.{table} AS SELECT {projection} FROM {alias}.{table}')
        aliases.append(scoped)
    patient_rows_sql = _union_select(
        aliases,
        """
        SELECT
            patient_id,
            sex,
            visit_count,
            first_event_date,
            last_event_date,
            source_file_count
        FROM {alias}.patients
        """,
    )
    patient_diseases_sql = _union_select(aliases, "SELECT patient_id, disease FROM {alias}.patient_diseases")
    patient_medications_sql = _union_select(aliases, "SELECT patient_id, medication FROM {alias}.patient_medications")
    patient_clarids_parts = []
    for alias in aliases:
        if _relation_exists(con, f"{alias}.patient_clarids"):
            patient_clarids_parts.append(
                f"""
                SELECT
                    patient_id, subject_id, human_id, stub_id, study, subject_type,
                    condition, sex, age_group, codebook_version, tools_version,
                    {_clarid_condition_name_sql(con, f'{alias}.patient_clarids')} AS condition_name
                FROM {alias}.patient_clarids
                """
            )
    patient_clarids_sql = " UNION ALL ".join(patient_clarids_parts) or """
        SELECT
            CAST(NULL AS VARCHAR) AS patient_id,
            CAST(NULL AS BIGINT) AS subject_id,
            CAST(NULL AS VARCHAR) AS human_id,
            CAST(NULL AS VARCHAR) AS stub_id,
            CAST(NULL AS VARCHAR) AS study,
            CAST(NULL AS VARCHAR) AS subject_type,
            CAST(NULL AS VARCHAR) AS condition,
            CAST(NULL AS VARCHAR) AS sex,
            CAST(NULL AS VARCHAR) AS age_group,
            CAST(NULL AS VARCHAR) AS codebook_version,
            CAST(NULL AS VARCHAR) AS tools_version,
            CAST(NULL AS VARCHAR) AS condition_name
        WHERE false
    """
    timepoints_sql = _union_select(
        aliases,
        """
        SELECT
            patient_id,
            original_id,
            visit_id,
            event_date,
            event_type,
            diagnosis,
            source_file,
            record_index
        FROM {alias}.timepoints
        """,
    )
    disease_events_sql = _union_select(
        aliases,
        """
        SELECT
            patient_id,
            original_id,
            visit_id,
            event_date,
            event_type,
            disease,
            source_file,
            record_index
        FROM {alias}.disease_events
        """,
    )
    medication_events_sql = _union_select(
        aliases,
        """
        SELECT
            patient_id,
            original_id,
            visit_id,
            event_date,
            event_type,
            medication,
            source_file,
            record_index
        FROM {alias}.medication_events
        """,
    )
    assay_samples_parts = []
    transcript_counts_parts = []
    for alias, dataset_id in zip(aliases, normalized):
        dataset_name_expr = f"{_sql_literal(dataset_id + '__')} || dataset_name" if multi_dataset else "dataset_name"
        assay_samples_parts.append(
            f"""
            SELECT
                {dataset_name_expr} AS dataset_name,
                sample_id,
                patient_id,
                modality,
                data_type
            FROM {alias}.assay_samples
            """
        )
        transcript_counts_parts.append(
            f"""
            SELECT
                {dataset_name_expr} AS dataset_name,
                sample_id,
                patient_id,
                gene_id,
                raw_count
            FROM {alias}.transcript_counts
            """
        )
    con.execute(f"CREATE TEMP VIEW patient_rows AS {patient_rows_sql}")
    con.execute(f"CREATE TEMP VIEW timepoints AS {timepoints_sql}")
    con.execute(f"CREATE TEMP VIEW disease_events AS {disease_events_sql}")
    con.execute(f"CREATE TEMP VIEW medication_events AS {medication_events_sql}")
    con.execute(f"CREATE TEMP VIEW patient_diseases AS SELECT DISTINCT patient_id, disease FROM ({patient_diseases_sql})")
    con.execute(f"CREATE TEMP VIEW patient_medications AS SELECT DISTINCT patient_id, medication FROM ({patient_medications_sql})")
    con.execute(f"CREATE TEMP VIEW patient_clarids AS {patient_clarids_sql}")
    con.execute(f"CREATE TEMP VIEW assay_samples AS {' UNION ALL '.join(assay_samples_parts)}")
    con.execute(f"CREATE TEMP VIEW transcript_counts AS {' UNION ALL '.join(transcript_counts_parts)}")
    con.execute(
        """
        CREATE TEMP VIEW patients AS
        WITH medication_counts AS (
            SELECT patient_id, COUNT(*) AS medication_count
            FROM patient_medications
            GROUP BY patient_id
        ),
        disease_counts AS (
            SELECT patient_id, COUNT(*) AS disease_count
            FROM patient_diseases
            GROUP BY patient_id
        )
        SELECT
            patient_id,
            any_value(sex) AS sex,
            sum(visit_count) AS visit_count,
            coalesce(max(medication_counts.medication_count), 0) AS medication_count,
            coalesce(max(disease_counts.disease_count), 0) AS disease_count,
            min(first_event_date) AS first_event_date,
            max(last_event_date) AS last_event_date,
            sum(source_file_count) AS source_file_count
        FROM patient_rows
        LEFT JOIN medication_counts USING (patient_id)
        LEFT JOIN disease_counts USING (patient_id)
        GROUP BY patient_id
        """
    )
    return con


def ensure_query_store(data_dir: str) -> None:
    if duckdb is None:
        return
    dataset_ids = _workspace_dataset_ids(data_dir)
    if dataset_ids:
        for dataset_id in dataset_ids:
            _store_ready_or_raise(dataset_id)
        return
    db_path, meta_path = _store_paths_for_data_dir(data_dir)
    current_signature = _source_files_signature(data_dir)
    if db_path.exists() and meta_path.exists():
        try:
            stored_signature = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            stored_signature = None
        if _signature_payload(stored_signature) == current_signature and _store_has_required_tables(db_path):
            return
    _build_query_store(data_dir, db_path, meta_path, current_signature)


def _build_query_store(data_dir: str, db_path: Path, meta_path: Path, signature: Dict[str, Any]) -> None:
    resolved_dir = ensure_data_dir(data_dir)
    if db_path.exists():
        db_path.unlink()

    con = duckdb.connect(str(db_path))
    try:
        con.execute(
            """
            CREATE TABLE patients (
                patient_id TEXT PRIMARY KEY,
                sex TEXT,
                visit_count INTEGER,
                medication_count INTEGER,
                disease_count INTEGER,
                first_event_date TEXT,
                last_event_date TEXT,
                source_file_count INTEGER
            );
            """
        )
        con.execute(
            """
            CREATE TABLE patient_clarids (
                patient_id TEXT PRIMARY KEY,
                subject_id BIGINT UNIQUE,
                human_id TEXT UNIQUE,
                stub_id TEXT UNIQUE,
                study TEXT,
                subject_type TEXT,
                condition TEXT,
                sex TEXT,
                age_group TEXT,
                codebook_version TEXT,
                tools_version TEXT,
                condition_name TEXT
            );
            """
        )
        con.execute(
            """
            CREATE TABLE timepoints (
                patient_id TEXT,
                original_id TEXT,
                visit_id TEXT,
                event_date TEXT,
                event_type TEXT,
                diagnosis TEXT,
                source_file TEXT,
                record_index INTEGER
            );
            """
        )
        con.execute("CREATE TABLE patient_diseases (patient_id TEXT, disease TEXT);")
        con.execute("CREATE TABLE patient_medications (patient_id TEXT, medication TEXT);")
        con.execute(
            """
            CREATE TABLE disease_events (
                patient_id TEXT,
                original_id TEXT,
                visit_id TEXT,
                event_date TEXT,
                event_type TEXT,
                disease TEXT,
                source_file TEXT,
                record_index INTEGER
            );
            """
        )
        con.execute(
            """
            CREATE TABLE medication_events (
                patient_id TEXT,
                original_id TEXT,
                visit_id TEXT,
                event_date TEXT,
                event_type TEXT,
                medication TEXT,
                source_file TEXT,
                record_index INTEGER
            );
            """
        )
        con.execute(
            """
            CREATE TABLE assay_samples (
                dataset_name TEXT,
                sample_id TEXT,
                patient_id TEXT,
                modality TEXT,
                data_type TEXT
            );
            """
        )
        con.execute(
            """
            CREATE TABLE transcript_counts (
                dataset_name TEXT,
                sample_id TEXT,
                patient_id TEXT,
                gene_id TEXT,
                raw_count BIGINT
            );
            """
        )

        patient_stats: Dict[str, Dict[str, Any]] = {}
        patient_disease_rows: List[Tuple[str, str]] = []
        patient_medication_rows: List[Tuple[str, str]] = []
        timepoint_rows: List[Tuple[str, Optional[str], str, Optional[str], Optional[str], Optional[str], str, int]] = []
        disease_event_rows: List[Tuple[str, Optional[str], str, Optional[str], Optional[str], str, str, int]] = []
        medication_event_rows: List[Tuple[str, Optional[str], str, Optional[str], Optional[str], str, str, int]] = []
        assay_sample_rows: List[Tuple[str, str, str, str, str]] = []
        seen_patient_diseases = set()
        seen_patient_medications = set()

        for path, index, record in read_bff_records(resolved_dir):
            patient_id = extract_patient_id(record)
            if patient_id is None:
                continue

            visit = build_visit_context(path, index, record, patient_id)
            source_label = path.relative_to(resolved_dir).as_posix()
            original_id = normalize_value(record.get("id"))
            stat = patient_stats.setdefault(
                patient_id,
                {
                    "sex": visit.sex,
                    "visit_count": 0,
                    "dates": [],
                    "source_files": set(),
                    "diseases": set(),
                    "medications": set(),
                },
            )
            if not stat["sex"] and visit.sex:
                stat["sex"] = visit.sex
            stat["visit_count"] += 1
            if visit.event_date:
                stat["dates"].append(visit.event_date)
            stat["source_files"].add(source_label)

            timepoint_rows.append(
                (
                    patient_id,
                    str(original_id) if isinstance(original_id, str) else None,
                    visit.visit_id,
                    visit.event_date,
                    visit.event_type,
                    visit.diagnosis,
                    source_label,
                    index,
                )
            )

            for disease in _extract_disease_labels(record):
                stat["diseases"].add(disease)
                key = (patient_id, disease)
                if key not in seen_patient_diseases:
                    seen_patient_diseases.add(key)
                    patient_disease_rows.append(key)
                disease_event_rows.append(
                    (
                        patient_id,
                        str(original_id) if isinstance(original_id, str) else None,
                        visit.visit_id,
                        visit.event_date,
                        visit.event_type,
                        disease,
                        source_label,
                        index,
                    )
                )

            for medication in extract_treatment_labels(record):
                stat["medications"].add(medication)
                key = (patient_id, medication)
                if key not in seen_patient_medications:
                    seen_patient_medications.add(key)
                    patient_medication_rows.append(key)
                medication_event_rows.append(
                    (
                        patient_id,
                        str(original_id) if isinstance(original_id, str) else None,
                        visit.visit_id,
                        visit.event_date,
                        visit.event_type,
                        medication,
                        source_label,
                        index,
                    )
                )

        seen_assay_samples = set()
        for matrix_path in _assay_matrix_files(data_dir):
            for dataset_name, sample_id, patient_id, modality, data_type in _insert_transcript_matrix(con, matrix_path):
                key = (dataset_name, sample_id)
                if key not in seen_assay_samples:
                    seen_assay_samples.add(key)
                    assay_sample_rows.append((dataset_name, sample_id, patient_id, modality, data_type))

        patient_rows: List[Tuple[str, Optional[str], int, int, int, Optional[str], Optional[str], int]] = []
        for patient_id in sorted(patient_stats):
            stat = patient_stats[patient_id]
            dates = sorted(date for date in stat["dates"] if date)
            patient_rows.append(
                (
                    patient_id,
                    stat["sex"],
                    stat["visit_count"],
                    len(stat["medications"]),
                    len(stat["diseases"]),
                    dates[0] if dates else None,
                    dates[-1] if dates else None,
                    len(stat["source_files"]),
                )
            )

        if patient_rows:
            con.executemany("INSERT INTO patients VALUES (?, ?, ?, ?, ?, ?, ?, ?)", patient_rows)
        clarid_rows = _read_subject_clarid_rows(resolve_project_data_dir(data_dir), set(patient_stats))
        if clarid_rows:
            con.executemany(
                "INSERT INTO patient_clarids VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                clarid_rows,
            )
        if timepoint_rows:
            con.executemany("INSERT INTO timepoints VALUES (?, ?, ?, ?, ?, ?, ?, ?)", timepoint_rows)
        if patient_disease_rows:
            con.executemany("INSERT INTO patient_diseases VALUES (?, ?)", patient_disease_rows)
        if patient_medication_rows:
            con.executemany("INSERT INTO patient_medications VALUES (?, ?)", patient_medication_rows)
        if disease_event_rows:
            con.executemany("INSERT INTO disease_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)", disease_event_rows)
        if medication_event_rows:
            con.executemany("INSERT INTO medication_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)", medication_event_rows)
        if assay_sample_rows:
            con.executemany("INSERT INTO assay_samples VALUES (?, ?, ?, ?, ?)", assay_sample_rows)

        con.execute("CREATE INDEX idx_patients_patient_id ON patients(patient_id)")
        con.execute("CREATE INDEX idx_patient_clarids_human_id ON patient_clarids(human_id)")
        con.execute("CREATE INDEX idx_patient_clarids_stub_id ON patient_clarids(stub_id)")
        con.execute("CREATE INDEX idx_timepoints_patient_id ON timepoints(patient_id)")
        con.execute("CREATE INDEX idx_disease_events_disease ON disease_events(disease)")
        con.execute("CREATE INDEX idx_medication_events_medication ON medication_events(medication)")
        con.execute("CREATE INDEX idx_assay_samples_sample_id ON assay_samples(sample_id)")
        con.execute("CREATE INDEX idx_assay_samples_patient_id ON assay_samples(patient_id)")
        con.execute("CREATE INDEX idx_transcript_counts_gene_id ON transcript_counts(gene_id)")
        con.execute("CREATE INDEX idx_transcript_counts_sample_id ON transcript_counts(sample_id)")
    finally:
        con.close()

    signature = {**signature, "built_at": str(int(Path(db_path).stat().st_mtime_ns))}
    _write_json(meta_path, signature)


def patient_inventory(data_dir: str) -> List[str]:
    ensure_query_store(data_dir)
    con = _connect(data_dir)
    try:
        rows = con.execute("SELECT patient_id FROM patients ORDER BY patient_id").fetchall()
    finally:
        con.close()
    return [row[0] for row in rows]


def _clarid_condition_name_sql(con, relation: str = "patient_clarids", prefix: str = "") -> str:
    # Optional additive metadata: older prepared releases remain readable.
    columns = {row[0] for row in con.execute(f"DESCRIBE {relation}").fetchall()}
    return f"{prefix}condition_name" if "condition_name" in columns else "CAST(NULL AS VARCHAR)"


def _clarid_payload(row: Tuple[Any, ...]) -> Dict[str, Any]:
    return {
        "subject_id": int(row[1]),
        "human_id": str(row[2] or ""),
        "stub_id": str(row[3] or ""),
        "study": str(row[4] or ""),
        "type": str(row[5] or ""),
        "condition": str(row[6] or ""),
        "sex": str(row[7] or ""),
        "age_group": str(row[8] or ""),
        "codebook_version": str(row[9] or ""),
        "tools_version": str(row[10] or ""),
        **({"condition_name": str(row[11])} if len(row) > 11 and row[11] else {}),
    }


def patient_clarid_inventory(data_dir: str) -> Dict[str, Dict[str, Any]]:
    ensure_query_store(data_dir)
    con = _connect(data_dir)
    try:
        if not _relation_exists(con, "patient_clarids"):
            return {}
        rows = con.execute(
            f"""
            SELECT
                patient_id,
                subject_id,
                human_id,
                stub_id,
                study,
                subject_type,
                condition,
                sex,
                age_group,
                codebook_version,
                tools_version,
                {_clarid_condition_name_sql(con)} AS condition_name
            FROM patient_clarids
            ORDER BY patient_id, human_id, stub_id
            """
        ).fetchall()
    finally:
        con.close()
    grouped: Dict[str, List[Tuple[Any, ...]]] = {}
    for row in rows:
        grouped.setdefault(str(row[0] or ""), []).append(row)
    payload: Dict[str, Dict[str, Any]] = {}
    for patient_id, candidates in grouped.items():
        distinct = {tuple(candidate[1:]) for candidate in candidates}
        if patient_id and len(distinct) == 1:
            payload[patient_id] = _clarid_payload(candidates[0])
    return payload


def patient_clarid(data_dir: str, patient_id: str) -> Dict[str, Any] | None:
    return patient_clarid_inventory(data_dir).get(str(patient_id or "").strip())


def resolve_patient_identifier(data_dir: str, identifier: str) -> Dict[str, Any] | None:
    normalized = str(identifier or "").strip()
    if not normalized:
        return None
    ensure_query_store(data_dir)
    con = _connect(data_dir)
    try:
        if not _relation_exists(con, "patient_clarids"):
            row = con.execute(
                "SELECT patient_id FROM patients WHERE lower(patient_id) = lower(?)",
                [normalized],
            ).fetchone()
            return {"patient_id": str(row[0]), "clarid": None} if row else None
        rows = con.execute(
            f"""
            SELECT
                p.patient_id,
                c.subject_id,
                c.human_id,
                c.stub_id,
                c.study,
                c.subject_type,
                c.condition,
                c.sex,
                c.age_group,
                c.codebook_version,
                c.tools_version,
                {_clarid_condition_name_sql(con, prefix='c.')} AS condition_name
            FROM patients p
            LEFT JOIN patient_clarids c ON c.patient_id = p.patient_id
            WHERE lower(p.patient_id) = lower(?)
               OR lower(coalesce(c.human_id, '')) = lower(?)
               OR lower(coalesce(c.stub_id, '')) = lower(?)
            ORDER BY p.patient_id
            """,
            [normalized, normalized, normalized],
        ).fetchall()
    finally:
        con.close()
    patient_ids = {str(row[0] or "").strip() for row in rows if str(row[0] or "").strip()}
    if len(patient_ids) != 1:
        return None
    patient_id = next(iter(patient_ids))
    candidates = [row for row in rows if str(row[0] or "").strip() == patient_id]
    clarid_candidates = [row for row in candidates if row[1] is not None]
    clarid_values = {tuple(row[1:]) for row in clarid_candidates}
    clarid = _clarid_payload(clarid_candidates[0]) if len(clarid_values) == 1 else None
    return {"patient_id": patient_id, "clarid": clarid}


def clinical_workspace_inventory(data_dir: str) -> Dict[str, Any]:
    ensure_query_store(data_dir)
    con = _connect(data_dir)
    try:
        patient_rows = con.execute(
            """
            SELECT
                patient_id,
                sex,
                visit_count,
                medication_count,
                disease_count,
                first_event_date,
                last_event_date
            FROM patients
            ORDER BY patient_id
            """
        ).fetchall()
        timepoint_rows = con.execute(
            """
            SELECT patient_id, original_id, visit_id, event_date
            FROM timepoints
            ORDER BY patient_id, event_date, visit_id, original_id
            """
        ).fetchall()
        disease_rows = con.execute(
            """
            SELECT patient_id, disease
            FROM patient_diseases
            ORDER BY patient_id, disease
            """
        ).fetchall()
        medication_rows = con.execute(
            """
            SELECT patient_id, medication
            FROM patient_medications
            ORDER BY patient_id, medication
            """
        ).fetchall()
        clarid_rows = (
            con.execute(
                f"""
                SELECT
                    patient_id, subject_id, human_id, stub_id, study, subject_type,
                    condition, sex, age_group, codebook_version, tools_version,
                    {_clarid_condition_name_sql(con)} AS condition_name
                FROM patient_clarids
                ORDER BY patient_id, human_id, stub_id
                """
            ).fetchall()
            if _relation_exists(con, "patient_clarids")
            else []
        )
    finally:
        con.close()

    diseases_by_patient: Dict[str, List[str]] = {}
    for patient_id, disease in disease_rows:
        patient_key = str(patient_id or "").strip()
        disease_label = str(disease or "").strip()
        if patient_key and disease_label:
            diseases_by_patient.setdefault(patient_key, []).append(disease_label)

    medications_by_patient: Dict[str, List[str]] = {}
    for patient_id, medication in medication_rows:
        patient_key = str(patient_id or "").strip()
        medication_label = str(medication or "").strip()
        if patient_key and medication_label:
            medications_by_patient.setdefault(patient_key, []).append(medication_label)

    clarids_by_patient: Dict[str, Dict[str, Any]] = {}
    clarid_candidates: Dict[str, List[Tuple[Any, ...]]] = {}
    for row in clarid_rows:
        clarid_candidates.setdefault(str(row[0] or "").strip(), []).append(row)
    for patient_key, candidates in clarid_candidates.items():
        if patient_key and len({tuple(item[1:]) for item in candidates}) == 1:
            clarids_by_patient[patient_key] = _clarid_payload(candidates[0])

    patients = []
    for patient_id, sex, visit_count, medication_count, disease_count, first_event_date, last_event_date in patient_rows:
        patient_key = str(patient_id or "").strip()
        if not patient_key:
            continue
        patients.append(
            {
                "patient_id": patient_key,
                "sex": str(sex or "").strip(),
                "visit_count": int(visit_count or 0),
                "medication_count": int(medication_count or 0),
                "disease_count": int(disease_count or 0),
                "first_event_date": str(first_event_date or "").strip(),
                "last_event_date": str(last_event_date or "").strip(),
                "clarid": clarids_by_patient.get(patient_key),
            }
        )

    samples = []
    for patient_id, original_id, visit_id, event_date in timepoint_rows:
        sample_id = str(original_id or "").strip()
        samples.append(
            {
                "patient_id": str(patient_id or "").strip(),
                "sample_id": sample_id,
                "visit_id": str(visit_id or "").strip(),
                "event_date": str(event_date or "").strip(),
            }
        )

    return {
        "patients": patients,
        "patient_ids": [item["patient_id"] for item in patients],
        "samples": samples,
        "sample_ids": sorted({item["sample_id"] for item in samples if item["sample_id"]}),
        "diseases_by_patient": diseases_by_patient,
        "medications_by_patient": medications_by_patient,
    }



def _assay_inventory_metadata(
    modality: Any,
    data_type: Any,
    manifest_item: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    modality_text = str(modality or "").strip() or "assay"
    data_type_text = str(data_type or "").strip() or "feature_matrix"
    if modality_text == "transcriptomics":
        feature_id_type = "ensembl_gene_id"
        feature_label = "genes"
        value_kind = "integer_counts" if data_type_text == "raw_counts" else "expression_values"
        supports_expression_summary = data_type_text == "raw_counts"
        supports_differential_expression = data_type_text == "raw_counts"
    elif modality_text == "methylation":
        feature_id_type = "illumina_cpg_probe_id"
        feature_label = "CpG probes"
        value_kind = "m_values" if data_type_text == "m_values" else "methylation_values"
        supports_expression_summary = False
        supports_differential_expression = False
    elif modality_text in {"olink", "proteomics"}:
        feature_id_type = "protein_id"
        feature_label = "proteins"
        value_kind = "abundance"
        supports_expression_summary = False
        supports_differential_expression = False
    elif modality_text == "flow_cytometry":
        feature_id_type = "immune_cell_population"
        feature_label = "immune-cell populations"
        value_kind = "cell_population_abundance"
        supports_expression_summary = False
        supports_differential_expression = False
    elif modality_text == "serology":
        feature_id_type = "serology_marker"
        feature_label = "serology markers"
        value_kind = "quantitative_measurement"
        supports_expression_summary = False
        supports_differential_expression = False
    elif modality_text == "genotyping":
        feature_id_type = "variant_id"
        feature_label = "variants"
        value_kind = "genotype_calls"
        supports_expression_summary = False
        supports_differential_expression = False
    elif modality_text == "imaging":
        feature_id_type = "dicom_standard_tag"
        feature_label = "DICOM attributes"
        value_kind = "dicom_derived_measurements"
        supports_expression_summary = False
        supports_differential_expression = False
    else:
        feature_id_type = "feature_id"
        feature_label = "features"
        value_kind = "feature_values"
        supports_expression_summary = False
        supports_differential_expression = False
    metadata = {
        "feature_id_type": feature_id_type,
        "feature_label": feature_label,
        "value_kind": value_kind,
        "sample_id_level": "sample",
        "patient_linkage": "sample_id_prefix",
        "analysis_level": "sample",
        "supports_expression_summary": supports_expression_summary,
        "supports_differential_expression": supports_differential_expression,
        "compatible_analysis_levels": ["sample", "patient"],
    }
    item = manifest_item if isinstance(manifest_item, dict) else {}
    text_overrides = {
        "feature_id_type": item.get("feature_namespace"),
        "feature_label": item.get("feature_label"),
        "value_kind": item.get("value_kind"),
        "patient_linkage": item.get("patient_linkage"),
        "analysis_level": item.get("analysis_level"),
    }
    for key, raw_value in text_overrides.items():
        value = str(raw_value or "").strip()
        if value:
            metadata[key] = value
    for key in ("supports_expression_summary", "supports_differential_expression"):
        if isinstance(item.get(key), bool):
            metadata[key] = item[key]
    if modality_text == "transcriptomics" and data_type_text != "raw_counts":
        metadata["supports_expression_summary"] = False
    levels = item.get("compatible_analysis_levels")
    if isinstance(levels, list):
        normalized_levels = [str(value).strip() for value in levels if str(value or "").strip()]
        if normalized_levels:
            metadata["compatible_analysis_levels"] = normalized_levels
    raw_panel = item.get("feature_panel")
    if modality_text == "methylation" and isinstance(raw_panel, dict):
        panel_id = str(raw_panel.get("panel_id") or "").strip()
        panel_version = str(raw_panel.get("panel_version") or "").strip()
        panel_label = str(raw_panel.get("label") or panel_id).strip()
        try:
            matched_feature_count = int(raw_panel.get("matched_feature_count") or 0)
        except (TypeError, ValueError):
            matched_feature_count = 0
        if panel_id and panel_version and matched_feature_count > 0:
            metadata["view_type"] = "feature_panel"
            metadata["feature_panel"] = {
                "panel_id": panel_id,
                "panel_version": panel_version,
                "label": panel_label or panel_id,
                "requested_feature_count": int(raw_panel.get("requested_feature_count") or 0),
                "matched_feature_count": matched_feature_count,
                "missing_feature_count": int(raw_panel.get("missing_feature_count") or 0),
                "excluded_nonfinite_feature_count": int(
                    raw_panel.get("excluded_nonfinite_feature_count") or 0
                ),
                "independent_of_target_cohort": bool(raw_panel.get("independent_of_target_cohort")),
                "source_publication_doi": str(raw_panel.get("source_publication_doi") or "").strip(),
            }
    return metadata


def _assay_manifest_items_for_root(root: Path) -> List[Dict[str, Any]]:
    manifest_path = root / "assays" / "manifest.json"
    if manifest_path.exists():
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
        items = payload.get("assays") if isinstance(payload, dict) else []
        if isinstance(items, list):
            return [
                {key: value for key, value in item.items() if not str(key).startswith("_")}
                for item in items
                if isinstance(item, dict)
            ]
    items: List[Dict[str, Any]] = []
    assays_root = root / "assays"
    for path in sorted(assays_root.glob("*/*.csv")) if assays_root.exists() else []:
        items.append(
            {
                "assay_id": path.stem,
                "label": path.stem.replace("_", " "),
                "modality": path.parent.name,
                "data_type": "raw_counts" if path.parent.name == "transcriptomics" else "feature_matrix",
                "file": str(path.relative_to(root)),
            }
        )
    return items


def _assay_manifest_items(data_dir: str) -> List[Dict[str, Any]]:
    root = resolve_project_data_dir(data_dir)
    dataset_ids = _workspace_dataset_ids(data_dir)
    if len(dataset_ids) <= 1:
        source_root = _dataset_root_path(dataset_ids[0]) if dataset_ids else root
        return _assay_manifest_items_for_root(source_root)

    items: List[Dict[str, Any]] = []
    for dataset_id in dataset_ids:
        source_root = _dataset_root_path(dataset_id)
        for raw_item in _assay_manifest_items_for_root(source_root):
            item = dict(raw_item)
            source_assay_id = str(
                item.get("assay_id") or Path(str(item.get("file") or "")).stem
            ).strip()
            if not source_assay_id:
                continue
            if (
                str(item.get("modality") or "").strip() == "transcriptomics"
                and str(item.get("data_type") or "").strip() == "raw_counts"
            ):
                item["assay_id"] = f"{dataset_id}__{source_assay_id}"
            else:
                item["assay_id"] = f"{dataset_id}::{source_assay_id}"
            item["label"] = (
                f"{dataset_id} — {str(item.get('label') or source_assay_id).strip()}"
            )
            # Internal-only provenance used to validate and open files from the
            # authorized source release. Inventory responses do not expose it.
            item["_release_root"] = str(source_root)
            item["_source_dataset_id"] = dataset_id
            item["_source_assay_id"] = source_assay_id
            items.append(item)
    return items


def _manifest_item_root(data_dir: str, item: Dict[str, Any]) -> Path:
    internal_root = str(item.get("_release_root") or "").strip()
    return Path(internal_root).resolve() if internal_root else resolve_project_data_dir(data_dir).resolve()


def _manifest_assay_sample_patient_links(
    root: Path,
    item: Dict[str, Any],
    sample_ids: List[str],
    *,
    require_complete_metadata: bool = False,
) -> Dict[str, Any]:
    """Resolve matrix sample IDs to patient IDs using the assay manifest contract.

    An explicit exact-sample linkage remains authoritative for non-methylation
    assays even when their sample metadata contains technical fields only.
    Methylation assays and callers requesting complete metadata require an
    explicit sample-to-patient table. Other manifests without a metadata table
    retain the established sample-prefix convention.
    """
    normalized_samples = [str(value or "").strip() for value in sample_ids if str(value or "").strip()]
    modality = str(item.get("modality") or "").strip().lower()
    patient_linkage = str(item.get("patient_linkage") or "").strip().lower()
    strict_metadata_linkage = require_complete_metadata or modality == "methylation"
    if patient_linkage == "exact_sample_id" and not strict_metadata_linkage:
        return {
            "links": {sample_id: sample_id for sample_id in normalized_samples},
            "linkage_source": "exact_sample_id",
            "unlinked_sample_ids": [],
        }

    metadata_file = str(item.get("sample_metadata_file") or "").strip()
    if not metadata_file:
        links = {
            sample_id: _patient_id_from_assay_sample(sample_id)
            for sample_id in normalized_samples
        }
        return {
            "links": links,
            "linkage_source": "sample_id_prefix",
            "unlinked_sample_ids": [],
        }

    resolved_root = root.resolve()
    metadata_path = (resolved_root / metadata_file).resolve()
    try:
        metadata_path.relative_to(resolved_root)
    except ValueError:
        raise ValueError("Assay sample metadata must remain inside the dataset release.") from None
    if not metadata_path.is_file():
        raise ValueError("Assay sample metadata is unavailable.")

    try:
        with metadata_path.open("r", encoding="utf-8-sig", newline="") as handle:
            first_line = handle.readline()
            if not first_line:
                raise ValueError("Assay sample metadata is empty.")
            delimiter = _detect_matrix_delimiter(first_line)
            if "\t" in first_line and first_line.count("\t") > max(first_line.count(";"), first_line.count(",")):
                delimiter = "\t"
            handle.seek(0)
            reader = csv.DictReader(handle, delimiter=delimiter)
            fieldnames = [str(value or "").strip() for value in (reader.fieldnames or [])]
            if "sample_id" not in fieldnames or "patient_id" not in fieldnames:
                raise ValueError("Assay sample metadata must contain sample_id and patient_id columns.")
            metadata_links: Dict[str, str] = {}
            for raw_row in reader:
                row = {
                    str(key or "").strip(): str(value or "").strip()
                    for key, value in raw_row.items()
                }
                sample_id = row.get("sample_id", "")
                if not sample_id:
                    continue
                if sample_id in metadata_links:
                    raise ValueError("Assay sample metadata contains duplicate sample identifiers.")
                metadata_links[sample_id] = row.get("patient_id", "")
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError("Assay sample metadata cannot be read.") from exc

    links = {
        sample_id: metadata_links[sample_id]
        for sample_id in normalized_samples
        if metadata_links.get(sample_id)
    }
    unlinked = [sample_id for sample_id in normalized_samples if sample_id not in links]
    if require_complete_metadata and unlinked:
        raise ValueError("Every selected assay matrix sample must have explicit patient linkage metadata.")
    return {
        "links": links,
        "linkage_source": "sample_metadata_file",
        "unlinked_sample_ids": unlinked,
    }


def _assay_matrix_stats(root: Path, item: Dict[str, Any]) -> Dict[str, Any] | None:
    relative_file = str(item.get("file") or "").strip()
    if not relative_file:
        return None
    path = (root / relative_file).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError:
        return None
    if not path.exists() or not path.is_file():
        return None
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            first_line = handle.readline()
    except (OSError, UnicodeDecodeError):
        return None
    if not first_line:
        return None
    delimiter = _detect_matrix_delimiter(first_line)
    sample_ids: List[str] = []
    declared_feature_count: int | None = None
    try:
        declared_feature_count = int(item.get("feature_count"))
    except (TypeError, ValueError):
        pass
    if declared_feature_count is not None and declared_feature_count < 0:
        declared_feature_count = None
    feature_count = declared_feature_count or 0
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle, delimiter=delimiter)
            header = next(reader, [])
            sample_ids = [str(item or "").strip() for item in header[1:] if str(item or "").strip()]
            if declared_feature_count is None:
                for row in reader:
                    if row and str(row[0] or "").strip():
                        feature_count += 1
    except (OSError, UnicodeDecodeError):
        return None
    try:
        linkage = _manifest_assay_sample_patient_links(root, item, sample_ids)
    except ValueError:
        return None
    links = dict(linkage.get("links") or {})
    if item.get('_source_dataset_id'):
        from app.identities import identity_key
        dataset = item['_source_dataset_id']
        sample_ids = [identity_key(dataset, 'sample', value) for value in sample_ids]
        links = {identity_key(dataset, 'sample', sid): identity_key(dataset, 'patient', pid) for sid, pid in links.items()}
    patient_ids = sorted({str(value or "").strip() for value in links.values() if str(value or "").strip()})
    return {
        "sample_ids": sample_ids,
        "patient_ids": patient_ids,
        "sample_count": len(sample_ids),
        "patient_count": len(patient_ids),
        "feature_count": feature_count,
        "linked_sample_count": len(links),
        "unlinked_sample_count": len(linkage.get("unlinked_sample_ids") or []),
        "linkage_source": str(linkage.get("linkage_source") or ""),
    }


@lru_cache(maxsize=32)
def _expected_count_summary(path_text: str, mtime_ns: int, size: int) -> Dict[str, Any]:
    """Bounded, in-memory Dashboard summary; never materialize the matrix in DuckDB."""
    unavailable = {"mean_total_counts_per_sample": None,
                   "mean_detected_genes_per_sample": None, "top_genes": [],
                   "count_summary_status": "unavailable"}
    if size > 64 * 1024 * 1024:
        return {**unavailable, "count_summary_status": "matrix_too_large"}
    try:
        with Path(path_text).open(encoding="utf-8", newline="") as handle:
            delimiter = _detect_matrix_delimiter(handle.readline())
            handle.seek(0)
            reader = csv.reader(handle, delimiter=delimiter)
            header = next(reader)
            n = len(header) - 1
            if n < 1 or len(set(header[1:])) != n:
                return unavailable
            totals = [0.0] * n
            detected = [0] * n
            top: List[Tuple[str, float]] = []
            genes: set[str] = set()
            for row in reader:
                if not row:
                    continue
                if len(row) != n + 1 or not row[0].strip() or row[0] in genes:
                    return unavailable
                genes.add(row[0])
                values = [float(value) for value in row[1:]]
                if any(not math.isfinite(value) or value < 0 for value in values):
                    return unavailable
                for i, value in enumerate(values):
                    totals[i] += value
                    detected[i] += value > 0
                top = sorted([*top, (row[0], sum(values))], key=lambda item: (-item[1], item[0]))[:5]
            if not genes or not all(math.isfinite(value) for value in totals):
                return unavailable
            return {"mean_total_counts_per_sample": sum(totals) / n,
                    "mean_detected_genes_per_sample": sum(detected) / n,
                    "count_summary_status": "available",
                    "top_genes": [{"gene_id": gene, "total_count": total,
                                   **_gene_annotation(gene)} for gene, total in top]}
    except (OSError, UnicodeError, ValueError, StopIteration, csv.Error):
        return unavailable


def _manifest_assay_inventory(data_dir: str, existing_names: set[str], clinical_patient_ids: set[str]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for item in _assay_manifest_items(data_dir):
        dataset_name = str(item.get("assay_id") or Path(str(item.get("file") or "")).stem).strip()
        if not dataset_name or dataset_name in existing_names:
            continue
        stats = _assay_matrix_stats(_manifest_item_root(data_dir, item), item)
        if not stats:
            continue
        modality = str(item.get("modality") or "assay").strip() or "assay"
        data_type = str(item.get("data_type") or "feature_matrix").strip() or "feature_matrix"
        patient_ids = list(stats["patient_ids"])
        clinical_overlap = len(set(patient_ids).intersection(clinical_patient_ids))
        count_summary: Dict[str, Any] = {}
        if modality == "transcriptomics" and data_type == "rsem_expected_counts":
            root = _manifest_item_root(data_dir, item).resolve()
            path = (root / str(item.get("file") or "")).resolve()
            if path.is_relative_to(root):
                try:
                    stat = path.stat()
                    count_summary = _expected_count_summary(str(path), stat.st_mtime_ns, stat.st_size)
                except OSError:
                    pass
        items.append(
            {
                "assay_id": dataset_name,
                "label": str(item.get("label") or dataset_name).strip() or dataset_name,
                "dataset_name": dataset_name,
                "modality": modality,
                "data_type": data_type,
                "sample_count": int(stats["sample_count"]),
                "patient_count": int(stats["patient_count"]),
                "gene_count": int(stats["feature_count"]),
                "clinical_overlap_patient_count": clinical_overlap,
                "mean_total_counts_per_sample": None,
                "mean_detected_genes_per_sample": None,
                "sample_ids": list(stats["sample_ids"]),
                "patient_ids": patient_ids,
                "top_genes": [],
                "feature_count": int(stats["feature_count"]),
                "linked_sample_count": int(stats.get("linked_sample_count") or 0),
                "unlinked_sample_count": int(stats.get("unlinked_sample_count") or 0),
                "linkage_source": str(stats.get("linkage_source") or ""),
                **_assay_inventory_metadata(modality, data_type, item),
                **count_summary,
            }
        )
    return sorted(items, key=lambda value: str(value.get("dataset_name") or ""))


def assay_dataset_inventory(data_dir: str) -> List[Dict[str, Any]]:
    ensure_query_store(data_dir)
    con = _connect(data_dir)
    try:
        rows = con.execute(
            """
            WITH sample_stats AS (
                SELECT
                    dataset_name,
                    sample_id,
                    patient_id,
                    sum(raw_count) AS total_counts,
                    sum(CASE WHEN raw_count > 0 THEN 1 ELSE 0 END) AS detected_gene_count
                FROM transcript_counts
                GROUP BY dataset_name, sample_id, patient_id
            ),
            dataset_stats AS (
                SELECT
                    dataset_name,
                    count(DISTINCT sample_id) AS sample_count,
                    count(DISTINCT patient_id) AS patient_count,
                    avg(total_counts) AS mean_total_counts_per_sample,
                    avg(detected_gene_count) AS mean_detected_genes_per_sample
                FROM sample_stats
                GROUP BY dataset_name
            ),
            gene_stats AS (
                SELECT
                    dataset_name,
                    count(DISTINCT gene_id) AS gene_count
                FROM transcript_counts
                GROUP BY dataset_name
            ),
            overlap_stats AS (
                SELECT
                    s.dataset_name,
                    count(DISTINCT CASE WHEN p.patient_id IS NOT NULL THEN s.patient_id END) AS clinical_overlap_patient_count
                FROM assay_samples AS s
                LEFT JOIN patients AS p
                    ON s.patient_id = p.patient_id
                GROUP BY s.dataset_name
            )
            SELECT
                s.dataset_name,
                max(s.modality) AS modality,
                max(s.data_type) AS data_type,
                max(ds.sample_count) AS sample_count,
                max(ds.patient_count) AS patient_count,
                max(gs.gene_count) AS gene_count,
                max(os.clinical_overlap_patient_count) AS clinical_overlap_patient_count,
                max(ds.mean_total_counts_per_sample) AS mean_total_counts_per_sample,
                max(ds.mean_detected_genes_per_sample) AS mean_detected_genes_per_sample
            FROM assay_samples AS s
            LEFT JOIN dataset_stats AS ds
                ON s.dataset_name = ds.dataset_name
            LEFT JOIN gene_stats AS gs
                ON s.dataset_name = gs.dataset_name
            LEFT JOIN overlap_stats AS os
                ON s.dataset_name = os.dataset_name
            GROUP BY s.dataset_name
            ORDER BY s.dataset_name
            """
        ).fetchall()
        dataset_names = [str(row[0]) for row in rows]
        sample_ids_map = {
            dataset_name: list(values or [])
            for dataset_name, values in con.execute(
                """
                SELECT dataset_name, list(sample_id ORDER BY sample_id)
                FROM assay_samples
                GROUP BY dataset_name
                """
            ).fetchall()
        }
        patient_ids_map = {
            dataset_name: list(values or [])
            for dataset_name, values in con.execute(
                """
                SELECT dataset_name, list(DISTINCT patient_id ORDER BY patient_id)
                FROM assay_samples
                GROUP BY dataset_name
                """
            ).fetchall()
        }
        clinical_patient_ids = {
            str(row[0])
            for row in con.execute("SELECT patient_id FROM patients").fetchall()
            if row and row[0] is not None
        }
        top_genes_map: Dict[str, List[Dict[str, Any]]] = {}
        for dataset_name in dataset_names:
            top_rows = con.execute(
                """
                SELECT gene_id, sum(raw_count) AS total_raw_count
                FROM transcript_counts
                WHERE dataset_name = ?
                GROUP BY gene_id
                ORDER BY total_raw_count DESC, gene_id
                LIMIT 5
                """,
                [dataset_name],
            ).fetchall()
            top_genes_map[dataset_name] = [
                {
                    "gene_id": str(gene_id),
                    "total_raw_count": int(total_raw_count),
                    **_gene_annotation(str(gene_id)),
                }
                for gene_id, total_raw_count in top_rows
            ]
    finally:
        con.close()
    transcriptomics_items = [
        {
            "assay_id": dataset_name,
            "label": dataset_name,
            "dataset_name": dataset_name,
            "modality": modality,
            "data_type": data_type,
            "sample_count": int(sample_count),
            "patient_count": int(patient_count),
            "gene_count": int(gene_count),
            "clinical_overlap_patient_count": int(clinical_overlap_patient_count),
            "mean_total_counts_per_sample": float(mean_total_counts_per_sample or 0),
            "mean_detected_genes_per_sample": float(mean_detected_genes_per_sample or 0),
            "sample_ids": list(sample_ids_map.get(dataset_name) or []),
            "patient_ids": list(patient_ids_map.get(dataset_name) or []),
            "top_genes": list(top_genes_map.get(dataset_name) or []),
            "feature_count": int(gene_count),
            **_assay_inventory_metadata(modality, data_type),
        }
        for (
            dataset_name,
            modality,
            data_type,
            sample_count,
            patient_count,
            gene_count,
            clinical_overlap_patient_count,
            mean_total_counts_per_sample,
            mean_detected_genes_per_sample,
        ) in rows
    ]
    manifest_items = _manifest_assay_inventory(data_dir, set(dataset_names), clinical_patient_ids)
    return sorted([*transcriptomics_items, *manifest_items], key=lambda value: str(value.get("dataset_name") or ""))


def assay_feature_inventory(data_dir: str, dataset_name: str, search: str = "", limit: int = 50) -> List[str]:
    ensure_query_store(data_dir)
    con = _connect(data_dir)
    try:
        rows = con.execute(
            """
            SELECT DISTINCT gene_id
            FROM transcript_counts
            WHERE dataset_name = ?
            ORDER BY gene_id
            """,
            [dataset_name],
        ).fetchall()
    finally:
        con.close()
    gene_ids = [str(row[0]) for row in rows]
    # Compact manifest matrices can remain external to DuckDB.
    if not gene_ids:
        item = _manifest_assay_item(data_dir, dataset_name)
        if item:
            path = _external_assay_matrix_path(data_dir, item)
            if path.stat().st_size > 64 * 1024 * 1024:
                raise ValueError("Feature browsing requires a prepared store or a matrix panel of at most 64 MiB.")
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                first_line = handle.readline()
                reader = csv.reader(handle, delimiter=_detect_matrix_delimiter(first_line))
                gene_ids = sorted({str(row[0]).strip() for row in reader if row and str(row[0]).strip()})
    needle = str(search or "").strip().lower()
    if not needle:
        return gene_ids[: int(limit)]
    matches: List[str] = []
    annotations = assay_feature_annotations(gene_ids, data_dir, dataset_name)
    for gene_id in gene_ids:
        annotation = annotations.get(gene_id, {})
        haystacks = [
            gene_id.lower(),
            str(annotation.get("gene_symbol") or "").lower(),
            str(annotation.get("gene_name") or "").lower(),
            str(annotation.get("label") or "").lower(),
            str(annotation.get("description") or "").lower(),
            str(annotation.get("unit") or "").lower(),
        ]
        if any(needle in value for value in haystacks if value):
            matches.append(gene_id)
        if len(matches) >= int(limit):
            break
    return matches


def _coerce_matrix_preview_value(value: Any) -> Any:
    text = str(value or "").strip()
    if text == "":
        return None
    try:
        number = float(text)
    except ValueError:
        return text
    if not math.isfinite(number):
        return text
    if number.is_integer():
        return int(number)
    return number


def _manifest_assay_item(data_dir: str, dataset_name: str) -> Dict[str, Any] | None:
    wanted = str(dataset_name or "").strip()
    if not wanted:
        return None
    for item in _assay_manifest_items(data_dir):
        assay_id = str(item.get("assay_id") or Path(str(item.get("file") or "")).stem).strip()
        if assay_id == wanted:
            return item
    return None


def _manifest_assay_matrix_preview(data_dir: str, dataset_name: str, feature_limit: int) -> Dict[str, Any] | None:
    item = _manifest_assay_item(data_dir, dataset_name)
    if not item:
        return None
    root = _manifest_item_root(data_dir, item)
    relative_file = str(item.get("file") or "").strip()
    if not relative_file:
        return None
    path = (root / relative_file).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError:
        return None
    if not path.exists() or not path.is_file():
        return None
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            first_line = handle.readline()
            if not first_line:
                return None
            delimiter = _detect_matrix_delimiter(first_line)
            handle.seek(0)
            reader = csv.reader(handle, delimiter=delimiter)
            header = next(reader, [])
            sample_ids = [str(value or "").strip() for value in header[1:] if str(value or "").strip()]
            if item.get('_source_dataset_id'):
                from app.identities import identity_key
                sample_ids = [identity_key(item['_source_dataset_id'], 'sample', sid) for sid in sample_ids]
            features: List[Dict[str, Any]] = []
            sample_values: Dict[str, Dict[str, Any]] = {sample_id: {} for sample_id in sample_ids}
            for raw_row in reader:
                if len(features) >= max(1, int(feature_limit)):
                    break
                if not raw_row:
                    continue
                feature_id = str(raw_row[0] or "").strip()
                if not feature_id:
                    continue
                features.append({"feature_id": feature_id, "label": feature_id})
                for index, sample_id in enumerate(sample_ids, start=1):
                    sample_values.setdefault(sample_id, {})[feature_id] = _coerce_matrix_preview_value(raw_row[index] if index < len(raw_row) else "")
    except (OSError, UnicodeDecodeError):
        return None
    modality = str(item.get("modality") or "assay").strip() or "assay"
    data_type = str(item.get("data_type") or "feature_matrix").strip() or "feature_matrix"
    return {
        "dataset_name": dataset_name,
        "label": str(item.get("label") or dataset_name).strip() or dataset_name,
        "modality": modality,
        "data_type": data_type,
        "features": features,
        "sample_ids": sample_ids,
        "sample_values": sample_values,
        **_assay_inventory_metadata(modality, data_type, item),
    }


def assay_dataset_matrix_preview(data_dir: str, dataset_name: str, feature_limit: int = 3) -> Dict[str, Any] | None:
    ensure_query_store(data_dir)
    normalized_name = str(dataset_name or "").strip()
    if not normalized_name:
        return None
    limit = max(1, int(feature_limit or 3))
    con = _connect(data_dir)
    try:
        stored = con.execute(
            """
            SELECT max(modality), max(data_type), count(*)
            FROM assay_samples
            WHERE dataset_name = ?
            """,
            [normalized_name],
        ).fetchone()
        stored_count = int(stored[2] or 0) if stored else 0
        if stored_count:
            feature_rows = con.execute(
                """
                SELECT gene_id, avg(raw_count) AS mean_raw_count
                FROM transcript_counts
                WHERE dataset_name = ?
                GROUP BY gene_id
                ORDER BY mean_raw_count DESC, gene_id
                LIMIT ?
                """,
                [normalized_name, limit],
            ).fetchall()
            feature_ids = [str(row[0]) for row in feature_rows if row and str(row[0] or "").strip()]
            sample_ids = [
                str(row[0])
                for row in con.execute(
                    """
                    SELECT sample_id
                    FROM assay_samples
                    WHERE dataset_name = ?
                    ORDER BY sample_id
                    """,
                    [normalized_name],
                ).fetchall()
                if row and str(row[0] or "").strip()
            ]
            sample_values: Dict[str, Dict[str, Any]] = {sample_id: {} for sample_id in sample_ids}
            if feature_ids:
                placeholders = ",".join("?" for _ in feature_ids)
                value_rows = con.execute(
                    f"""
                    SELECT sample_id, gene_id, raw_count
                    FROM transcript_counts
                    WHERE dataset_name = ? AND gene_id IN ({placeholders})
                    ORDER BY sample_id, gene_id
                    """,
                    [normalized_name, *feature_ids],
                ).fetchall()
                for sample_id, gene_id, raw_count in value_rows:
                    sample_values.setdefault(str(sample_id), {})[str(gene_id)] = int(raw_count or 0)
            modality = str(stored[0] or "transcriptomics").strip() or "transcriptomics"
            data_type = str(stored[1] or "raw_counts").strip() or "raw_counts"
            return {
                "dataset_name": normalized_name,
                "label": normalized_name,
                "modality": modality,
                "data_type": data_type,
                "features": [
                    {
                        "feature_id": feature_id,
                        "label": _gene_annotation(feature_id).get("gene_symbol") or feature_id,
                    }
                    for feature_id in feature_ids
                ],
                "sample_ids": sample_ids,
                "sample_values": sample_values,
                **_assay_inventory_metadata(modality, data_type),
            }
    finally:
        con.close()
    return _manifest_assay_matrix_preview(data_dir, normalized_name, limit)


QUERYABLE_EXTERNAL_ASSAY_MODALITIES = {"flow_cytometry", "serology"}
_EXTERNAL_ASSAY_MISSING_VALUES = {"", "na", "n/a", "nan", "null", "none", "."}


def _queryable_external_assay_item(
    data_dir: str,
    assay_id: str = "",
    modality: str = "",
) -> Dict[str, Any] | None:
    wanted_id = str(assay_id or "").strip()
    wanted_modality = str(modality or "").strip().lower()
    matches: List[Dict[str, Any]] = []
    for item in _assay_manifest_items(data_dir):
        item_modality = str(item.get("modality") or "").strip().lower()
        if item_modality not in QUERYABLE_EXTERNAL_ASSAY_MODALITIES:
            continue
        item_id = str(item.get("assay_id") or Path(str(item.get("file") or "")).stem).strip()
        if wanted_id and item_id != wanted_id:
            continue
        if wanted_modality and item_modality != wanted_modality:
            continue
        matches.append(item)
    return matches[0] if len(matches) == 1 else None


def _external_assay_matrix_path(data_dir: str, item: Dict[str, Any]) -> Path:
    root = _manifest_item_root(data_dir, item).resolve()
    relative_file = str(item.get("file") or "").strip()
    if not relative_file:
        raise ValueError("The assay matrix file is not declared.")
    path = (root / relative_file).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        raise ValueError("The assay matrix must remain inside the authorized release.") from None
    if not path.is_file():
        raise ValueError("The assay matrix is unavailable.")
    return path


def _external_assay_header(data_dir: str, item: Dict[str, Any]) -> Tuple[Path, str, List[str], Dict[str, str]]:
    path = _external_assay_matrix_path(data_dir, item)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        first_line = handle.readline()
    if not first_line:
        raise ValueError("The assay matrix is empty.")
    delimiter = _detect_matrix_delimiter(first_line)
    header = next(csv.reader([first_line], delimiter=delimiter), [])
    sample_ids = [str(value or "").strip() for value in header[1:]]
    if not sample_ids or any(not value for value in sample_ids) or len(sample_ids) != len(set(sample_ids)):
        raise ValueError("The assay matrix has invalid sample identifiers.")
    linkage = _manifest_assay_sample_patient_links(_manifest_item_root(data_dir, item), item, sample_ids)
    links = {str(key): str(value) for key, value in dict(linkage.get("links") or {}).items() if str(value)}
    if len(links) != len(sample_ids):
        raise ValueError("Every assay sample must have explicit patient linkage before it can be queried.")
    if item.get('_source_dataset_id'):
        from app.identities import identity_key
        dataset = item['_source_dataset_id']
        links = {identity_key(dataset, 'sample', sid): identity_key(dataset, 'patient', pid)
                 for sid, pid in links.items()}
        sample_ids = [identity_key(dataset, 'sample', sid) for sid in sample_ids]
    return path, delimiter, sample_ids, links


def external_assay_feature_catalog(
    data_dir: str,
    modality: str = "",
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """Return bounded non-patient feature metadata for compact external assays."""
    ensure_query_store(data_dir)
    wanted_modality = str(modality or "").strip().lower()
    maximum = max(1, min(int(limit or 100), 200))
    payload: List[Dict[str, Any]] = []
    for item in _assay_manifest_items(data_dir):
        item_modality = str(item.get("modality") or "").strip().lower()
        if item_modality not in QUERYABLE_EXTERNAL_ASSAY_MODALITIES:
            continue
        if wanted_modality and item_modality != wanted_modality:
            continue
        assay_id = str(item.get("assay_id") or Path(str(item.get("file") or "")).stem).strip()
        path, delimiter, _, _ = _external_assay_header(data_dir, item)
        features: List[str] = []
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle, delimiter=delimiter)
            next(reader, None)
            for row in reader:
                feature_id = str(row[0] if row else "").strip()
                if feature_id:
                    features.append(feature_id)
                if len(features) >= maximum:
                    break
        payload.append(
            {
                "assay_id": assay_id,
                "label": str(item.get("label") or assay_id).strip() or assay_id,
                "modality": item_modality,
                "data_type": str(item.get("data_type") or "feature_matrix").strip(),
                "feature_count": int(item.get("feature_count") or len(features)),
                "features": features,
            }
        )
    return sorted(payload, key=lambda value: (value["modality"], value["assay_id"]))


def _external_numeric_value(token: Any) -> float | None:
    text = str(token or "").strip()
    if text.lower() in _EXTERNAL_ASSAY_MISSING_VALUES:
        return None
    try:
        value = float(text)
    except ValueError:
        raise ValueError("The selected assay contains a non-numeric measurement.") from None
    if not math.isfinite(value):
        raise ValueError("The selected assay contains a non-finite measurement.")
    return value


def _summarize_external_values(
    values: List[Tuple[str, str, float]],
    *,
    scope_sample_count: int,
) -> Dict[str, Any]:
    numeric = sorted(value for _, _, value in values)
    if not numeric:
        return {
            "sample_count": 0,
            "patient_count": 0,
            "missing_count": scope_sample_count,
            "mean": None,
            "median": None,
            "min": None,
            "max": None,
        }
    middle = len(numeric) // 2
    median = numeric[middle] if len(numeric) % 2 else (numeric[middle - 1] + numeric[middle]) / 2
    return {
        "sample_count": len(numeric),
        "patient_count": len({patient_id for patient_id, _, _ in values}),
        "missing_count": max(0, scope_sample_count - len(numeric)),
        "mean": sum(numeric) / len(numeric),
        "median": median,
        "min": numeric[0],
        "max": numeric[-1],
    }


def _external_assay_feature_values(
    data_dir: str,
    *,
    assay_id: str = "",
    modality: str = "",
    feature_query: str = "",
    limit: int = 20,
) -> Dict[str, Any]:
    item = _queryable_external_assay_item(data_dir, assay_id=assay_id, modality=modality)
    if item is None:
        raise ValueError("Choose exactly one immune-cell or quantitative-serology assay.")
    path, delimiter, sample_ids, links = _external_assay_header(data_dir, item)
    needle = str(feature_query or "").strip().lower()
    maximum = max(1, min(int(limit or 20), 100))
    exact_rows: List[Tuple[str, List[str]]] = []
    partial_rows: List[Tuple[str, List[str]]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle, delimiter=delimiter)
        next(reader, None)
        seen_features: set[str] = set()
        for row in reader:
            if not row:
                continue
            feature_id = str(row[0] or "").strip()
            if not feature_id:
                continue
            if feature_id in seen_features:
                raise ValueError("The selected assay contains duplicate feature identifiers.")
            seen_features.add(feature_id)
            if len(row) != len(sample_ids) + 1:
                raise ValueError("The selected assay contains an invalid matrix row width.")
            if not needle:
                partial_rows.append((feature_id, row))
            elif feature_id.lower() == needle:
                exact_rows.append((feature_id, row))
            elif needle in feature_id.lower():
                partial_rows.append((feature_id, row))
            if len(exact_rows) >= maximum or (not needle and len(partial_rows) >= maximum):
                break
    selected_rows = (exact_rows or partial_rows)[:maximum]
    features: List[Dict[str, Any]] = []
    for feature_id, row in selected_rows:
        feature_values: List[Tuple[str, str, float]] = []
        for index, sample_id in enumerate(sample_ids, start=1):
            value = _external_numeric_value(row[index] if index < len(row) else "")
            patient_id = links[sample_id]
            if value is not None:
                feature_values.append((patient_id, sample_id, value))
        features.append(
            {
                "feature_id": feature_id,
                "values": feature_values,
            }
        )
    assay_id_value = str(item.get("assay_id") or path.stem).strip()
    return {
        "assay_id": assay_id_value,
        "label": str(item.get("label") or assay_id_value).strip() or assay_id_value,
        "modality": str(item.get("modality") or "assay").strip(),
        "data_type": str(item.get("data_type") or "feature_matrix").strip(),
        "sample_ids": sample_ids,
        "links": links,
        "features": features,
    }


def external_assay_feature_summary(
    data_dir: str,
    *,
    assay_id: str = "",
    modality: str = "",
    feature_query: str = "",
    selected_patient_ids: List[str] | None = None,
    limit: int = 20,
) -> Dict[str, Any]:
    """Compute bounded aggregate statistics without returning measurement rows."""
    ensure_query_store(data_dir)
    source = _external_assay_feature_values(
        data_dir,
        assay_id=assay_id,
        modality=modality,
        feature_query=feature_query,
        limit=limit,
    )
    selected = {str(value).strip() for value in (selected_patient_ids or []) if str(value).strip()}
    scoped_samples = [
        sample_id
        for sample_id in source["sample_ids"]
        if not selected or source["links"].get(sample_id) in selected
    ]
    rows: List[Dict[str, Any]] = []
    for feature in source["features"]:
        values = [
            item for item in feature["values"]
            if not selected or item[0] in selected
        ]
        rows.append(
            {
                "feature_id": feature["feature_id"],
                **_summarize_external_values(values, scope_sample_count=len(scoped_samples)),
            }
        )
    return {
        "assay_id": source["assay_id"],
        "label": source["label"],
        "modality": source["modality"],
        "data_type": source["data_type"],
        "scope_sample_count": len(scoped_samples),
        "scope_patient_count": len({source["links"][sample_id] for sample_id in scoped_samples}),
        "features": rows,
    }


def external_assay_feature_comparison(
    data_dir: str,
    *,
    assay_id: str = "",
    modality: str = "",
    feature_query: str = "",
    cohort_a_patient_ids: List[str],
    cohort_b_patient_ids: List[str],
    limit: int = 20,
) -> Dict[str, Any]:
    """Compare two disjoint cohorts descriptively; inferential tests belong in Analysis."""
    cohort_a = {str(value).strip() for value in cohort_a_patient_ids if str(value).strip()}
    cohort_b = {str(value).strip() for value in cohort_b_patient_ids if str(value).strip()}
    if not cohort_a or not cohort_b:
        raise ValueError("Both assay comparison cohorts must contain patients.")
    if cohort_a.intersection(cohort_b):
        raise ValueError("Assay comparison cohorts must be disjoint.")
    source = _external_assay_feature_values(
        data_dir,
        assay_id=assay_id,
        modality=modality,
        feature_query=feature_query,
        limit=limit,
    )
    sample_counts = {
        "a": sum(1 for sample_id in source["sample_ids"] if source["links"].get(sample_id) in cohort_a),
        "b": sum(1 for sample_id in source["sample_ids"] if source["links"].get(sample_id) in cohort_b),
    }
    rows: List[Dict[str, Any]] = []
    for feature in source["features"]:
        values_a = [item for item in feature["values"] if item[0] in cohort_a]
        values_b = [item for item in feature["values"] if item[0] in cohort_b]
        summary_a = _summarize_external_values(values_a, scope_sample_count=sample_counts["a"])
        summary_b = _summarize_external_values(values_b, scope_sample_count=sample_counts["b"])
        difference = None
        if summary_a["mean"] is not None and summary_b["mean"] is not None:
            difference = summary_a["mean"] - summary_b["mean"]
        rows.append(
            {
                "feature_id": feature["feature_id"],
                "cohort_a": summary_a,
                "cohort_b": summary_b,
                "mean_difference_a_minus_b": difference,
            }
        )
    return {
        "assay_id": source["assay_id"],
        "label": source["label"],
        "modality": source["modality"],
        "data_type": source["data_type"],
        "cohort_a_patient_count": len(cohort_a),
        "cohort_b_patient_count": len(cohort_b),
        "features": rows,
    }


def _parse_patient_scope(scope: str) -> List[str]:
    return [item.strip() for item in str(scope or "").split(",") if item.strip()]


def _expression_summary_rows(
    con,
    dataset_name: str,
    gene_id: str,
    patient_ids: List[str],
) -> List[Tuple[str, str, int]]:
    if patient_ids:
        placeholders = ", ".join(["?"] * len(patient_ids))
        return con.execute(
            f"""
            SELECT patient_id, sample_id, raw_count
            FROM transcript_counts
            WHERE dataset_name = ? AND gene_id = ? AND patient_id IN ({placeholders})
            ORDER BY patient_id, sample_id
            """,
            [dataset_name, gene_id, *patient_ids],
        ).fetchall()
    return con.execute(
        """
        SELECT patient_id, sample_id, raw_count
        FROM transcript_counts
        WHERE dataset_name = ? AND gene_id = ?
        ORDER BY patient_id, sample_id
        """,
        [dataset_name, gene_id],
    ).fetchall()


def _summarize_expression_rows(rows: List[Tuple[str, str, int]], label: str) -> Dict[str, Any]:
    values = [int(row[2]) for row in rows]
    if not values:
        return {
            "label": label,
            "sample_count": 0,
            "patient_count": 0,
            "min": None,
            "median": None,
            "mean": None,
            "max": None,
            "values": [],
        }
    sorted_values = sorted(values)
    middle = len(sorted_values) // 2
    if len(sorted_values) % 2:
        median = float(sorted_values[middle])
    else:
        median = (sorted_values[middle - 1] + sorted_values[middle]) / 2
    mean = sum(sorted_values) / len(sorted_values)
    return {
        "label": label,
        "sample_count": len(rows),
        "patient_count": len({row[0] for row in rows}),
        "min": sorted_values[0],
        "median": median,
        "mean": mean,
        "max": sorted_values[-1],
        "values": [
            {"patient_id": str(patient_id), "sample_id": str(sample_id), "raw_count": int(raw_count)}
            for patient_id, sample_id, raw_count in rows
        ],
    }


def assay_expression_summary(
    data_dir: str,
    dataset_name: str,
    gene_id: str,
    selected_patient_ids: str = "",
    compare_selected_patient_ids: str = "",
) -> Dict[str, Any]:
    ensure_query_store(data_dir)
    cohort_a_ids = _parse_patient_scope(selected_patient_ids)
    cohort_b_ids = _parse_patient_scope(compare_selected_patient_ids)
    con = _connect(data_dir)
    try:
        cohort_a_rows = _expression_summary_rows(con, dataset_name, gene_id, cohort_a_ids)
        cohort_b_rows = _expression_summary_rows(con, dataset_name, gene_id, cohort_b_ids) if cohort_b_ids else []
    finally:
        con.close()
    payload = {
        "dataset_name": dataset_name,
        "gene_id": gene_id,
        **_gene_annotation(gene_id),
        "scope_a": _summarize_expression_rows(cohort_a_rows, "Cohort A" if cohort_b_ids else "Selected scope"),
    }
    if cohort_b_ids:
        payload["scope_b"] = _summarize_expression_rows(cohort_b_rows, "Cohort B")
    return payload


def assay_dataset_feature_means(data_dir: str, dataset_name: str, limit: int = 20) -> List[Dict[str, Any]]:
    return assay_dataset_feature_means_scoped(data_dir, dataset_name, selected_patient_ids=None, limit=limit)


def assay_dataset_feature_means_scoped(
    data_dir: str,
    dataset_name: str,
    selected_patient_ids: List[str] | None = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    ensure_query_store(data_dir)
    con = _connect(data_dir)
    try:
        scope_ids = [str(item).strip() for item in (selected_patient_ids or []) if str(item).strip()]
        if scope_ids:
            placeholders = ",".join("?" for _ in scope_ids)
            rows = con.execute(
                f"""
                SELECT
                    gene_id,
                    avg(raw_count) AS mean_raw_count,
                    min(raw_count) AS min_raw_count,
                    max(raw_count) AS max_raw_count,
                    count(*) AS sample_count
                FROM transcript_counts
                WHERE dataset_name = ? AND patient_id IN ({placeholders})
                GROUP BY gene_id
                ORDER BY mean_raw_count DESC, gene_id
                LIMIT ?
                """,
                [dataset_name, *scope_ids, int(limit)],
            ).fetchall()
        else:
            rows = con.execute(
                """
                SELECT
                    gene_id,
                    avg(raw_count) AS mean_raw_count,
                    min(raw_count) AS min_raw_count,
                    max(raw_count) AS max_raw_count,
                    count(*) AS sample_count
                FROM transcript_counts
                WHERE dataset_name = ?
                GROUP BY gene_id
                ORDER BY mean_raw_count DESC, gene_id
                LIMIT ?
                """,
                [dataset_name, int(limit)],
            ).fetchall()
    finally:
        con.close()
    return [
        {
            "gene_id": str(gene_id),
            "mean_raw_count": float(mean_raw_count),
            "min_raw_count": int(min_raw_count),
            "max_raw_count": int(max_raw_count),
            "sample_count": int(sample_count),
        }
        for gene_id, mean_raw_count, min_raw_count, max_raw_count, sample_count in rows
    ]


def assay_dataset_pairwise_feature_differences(
    data_dir: str,
    dataset_a: str,
    dataset_b: str,
    selected_patient_ids: List[str] | None = None,
    limit: int = 12,
) -> List[Dict[str, Any]]:
    ensure_query_store(data_dir)
    con = _connect(data_dir)
    try:
        scope_ids = [str(item).strip() for item in (selected_patient_ids or []) if str(item).strip()]
        if scope_ids:
            placeholders = ",".join("?" for _ in scope_ids)
            rows = con.execute(
                f"""
                WITH dataset_means AS (
                    SELECT dataset_name, gene_id, avg(raw_count) AS mean_raw_count
                    FROM transcript_counts
                    WHERE dataset_name IN (?, ?) AND patient_id IN ({placeholders})
                    GROUP BY dataset_name, gene_id
                )
                SELECT
                    a.gene_id,
                    a.mean_raw_count AS mean_a,
                    b.mean_raw_count AS mean_b,
                    abs(a.mean_raw_count - b.mean_raw_count) AS abs_delta
                FROM dataset_means AS a
                INNER JOIN dataset_means AS b
                    ON a.gene_id = b.gene_id
                WHERE a.dataset_name = ? AND b.dataset_name = ?
                ORDER BY abs_delta DESC, a.gene_id
                LIMIT ?
                """,
                [dataset_a, dataset_b, *scope_ids, dataset_a, dataset_b, int(limit)],
            ).fetchall()
        else:
            rows = con.execute(
                """
                WITH dataset_means AS (
                    SELECT dataset_name, gene_id, avg(raw_count) AS mean_raw_count
                    FROM transcript_counts
                    WHERE dataset_name IN (?, ?)
                    GROUP BY dataset_name, gene_id
                )
                SELECT
                    a.gene_id,
                    a.mean_raw_count AS mean_a,
                    b.mean_raw_count AS mean_b,
                    abs(a.mean_raw_count - b.mean_raw_count) AS abs_delta
                FROM dataset_means AS a
                INNER JOIN dataset_means AS b
                    ON a.gene_id = b.gene_id
                WHERE a.dataset_name = ? AND b.dataset_name = ?
                ORDER BY abs_delta DESC, a.gene_id
                LIMIT ?
                """,
                [dataset_a, dataset_b, dataset_a, dataset_b, int(limit)],
            ).fetchall()
    finally:
        con.close()
    return [
        {
            "gene_id": str(gene_id),
            "mean_a": float(mean_a),
            "mean_b": float(mean_b),
            "abs_delta": float(abs_delta),
            "dominant_dataset": dataset_a if float(mean_a) >= float(mean_b) else dataset_b,
        }
        for gene_id, mean_a, mean_b, abs_delta in rows
    ]


def assay_dataset_pairwise_exploratory_volcano(
    data_dir: str,
    dataset_a: str,
    dataset_b: str,
    selected_patient_ids: List[str] | None = None,
    limit: int = 2000,
) -> List[Dict[str, Any]]:
    ensure_query_store(data_dir)
    con = _connect(data_dir)
    try:
        scope_ids = [str(item).strip() for item in (selected_patient_ids or []) if str(item).strip()]
        if scope_ids:
            placeholders = ",".join("?" for _ in scope_ids)
            rows = con.execute(
                f"""
                SELECT dataset_name, sample_id, gene_id, raw_count
                FROM transcript_counts
                WHERE dataset_name IN (?, ?) AND patient_id IN ({placeholders})
                ORDER BY dataset_name, sample_id, gene_id
                """,
                [dataset_a, dataset_b, *scope_ids],
            ).fetchall()
        else:
            rows = con.execute(
                """
                SELECT dataset_name, sample_id, gene_id, raw_count
                FROM transcript_counts
                WHERE dataset_name IN (?, ?)
                ORDER BY dataset_name, sample_id, gene_id
                """,
                [dataset_a, dataset_b],
            ).fetchall()
    finally:
        con.close()

    if not rows:
        return []

    sample_totals: Dict[Tuple[str, str], float] = {}
    for dataset_name, sample_id, _gene_id, raw_count in rows:
        key = (str(dataset_name), str(sample_id))
        sample_totals[key] = sample_totals.get(key, 0.0) + float(raw_count or 0)

    gene_values_a: Dict[str, List[float]] = {}
    gene_values_b: Dict[str, List[float]] = {}
    for dataset_name, sample_id, gene_id, raw_count in rows:
        key = (str(dataset_name), str(sample_id))
        library_size = max(sample_totals.get(key, 0.0), 1.0)
        cpm = (float(raw_count or 0) / library_size) * 1_000_000.0
        log2_cpm = math.log2(cpm + 1.0)
        gene_key = str(gene_id)
        if str(dataset_name) == dataset_a:
            gene_values_a.setdefault(gene_key, []).append(log2_cpm)
        elif str(dataset_name) == dataset_b:
            gene_values_b.setdefault(gene_key, []).append(log2_cpm)

    genes = sorted(set(gene_values_a.keys()) & set(gene_values_b.keys()))
    points: List[Dict[str, Any]] = []

    def _mean(values: List[float]) -> float:
        return sum(values) / max(len(values), 1)

    def _sample_variance(values: List[float], mean_value: float) -> float:
        if len(values) < 2:
            return 0.0
        return sum((value - mean_value) ** 2 for value in values) / (len(values) - 1)

    for gene_id in genes:
        values_a = gene_values_a.get(gene_id) or []
        values_b = gene_values_b.get(gene_id) or []
        if not values_a or not values_b:
            continue
        mean_a = _mean(values_a)
        mean_b = _mean(values_b)
        var_a = _sample_variance(values_a, mean_a)
        var_b = _sample_variance(values_b, mean_b)
        denom = math.sqrt((var_a / max(len(values_a), 1)) + (var_b / max(len(values_b), 1)))
        if denom > 0:
            z_score = (mean_a - mean_b) / denom
            p_value = max(math.erfc(abs(z_score) / math.sqrt(2.0)), 1e-300)
        else:
            z_score = 0.0
            p_value = 1.0
        points.append(
            {
                "gene_id": gene_id,
                "mean_log2_cpm_a": float(mean_a),
                "mean_log2_cpm_b": float(mean_b),
                "log2_fold_change": float(mean_a - mean_b),
                "p_value": float(p_value),
                "neg_log10_p": float(-math.log10(max(p_value, 1e-300))),
                "sample_count_a": len(values_a),
                "sample_count_b": len(values_b),
            }
        )

    points.sort(key=lambda item: (item["neg_log10_p"], abs(item["log2_fold_change"])), reverse=True)
    return points[: int(limit)]


def patient_query_index(data_dir: str) -> List[Dict[str, Any]]:
    ensure_query_store(data_dir)
    con = _connect(data_dir)
    try:
        rows = con.execute(
            """
            SELECT patient_id, sex, visit_count, medication_count, disease_count
            FROM patients
            ORDER BY patient_id
            """
        ).fetchall()
        medications = {
            patient_id: values
            for patient_id, values in con.execute(
                """
                SELECT patient_id, list(medication ORDER BY medication)
                FROM patient_medications
                GROUP BY patient_id
                """
            ).fetchall()
        }
        diseases = {
            patient_id: values
            for patient_id, values in con.execute(
                """
                SELECT patient_id, list(disease ORDER BY disease)
                FROM patient_diseases
                GROUP BY patient_id
                """
            ).fetchall()
        }
        original_ids = {
            patient_id: values
            for patient_id, values in con.execute(
                """
                SELECT patient_id, list(DISTINCT original_id ORDER BY original_id)
                FROM timepoints
                WHERE original_id IS NOT NULL AND original_id <> ''
                GROUP BY patient_id
                """
            ).fetchall()
        }
        clarid_rows = (
            con.execute(
                f"""
                SELECT
                    patient_id, subject_id, human_id, stub_id, study, subject_type,
                    condition, sex, age_group, codebook_version, tools_version,
                    {_clarid_condition_name_sql(con)} AS condition_name
                FROM patient_clarids
                ORDER BY patient_id, human_id, stub_id
                """
            ).fetchall()
            if _relation_exists(con, "patient_clarids")
            else []
        )
    finally:
        con.close()

    clarid_candidates: Dict[str, List[Tuple[Any, ...]]] = {}
    for row in clarid_rows:
        clarid_candidates.setdefault(str(row[0] or "").strip(), []).append(row)
    clarids: Dict[str, Dict[str, Any]] = {}
    for patient_key, candidates in clarid_candidates.items():
        if patient_key and len({tuple(item[1:]) for item in candidates}) == 1:
            clarids[patient_key] = _clarid_payload(candidates[0])

    payload: List[Dict[str, Any]] = []
    for patient_id, sex, visit_count, medication_count, disease_count in rows:
        payload.append(
            {
                "patient_id": patient_id,
                "sex": sex,
                "visit_count": visit_count,
                "medications": list(medications.get(patient_id) or []),
                "medication_count": medication_count,
                "diseases": list(diseases.get(patient_id) or []),
                "disease_count": disease_count,
                "original_record_ids": list(original_ids.get(patient_id) or []),
                "clarid": clarids.get(str(patient_id)),
            }
        )
    return payload


def patient_medication_count_cohort(data_dir: str, operator: str, target: int) -> Dict[str, Any]:
    sql_operator = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<=", "eq": "="}.get(operator, "=")
    ensure_query_store(data_dir)
    con = _connect(data_dir)
    try:
        rows = con.execute(
            f"""
            SELECT patient_id, sex, visit_count, medication_count, disease_count
            FROM patients
            WHERE medication_count {sql_operator} ?
            ORDER BY patient_id
            """,
            [target],
        ).fetchall()
    finally:
        con.close()
    return {
        "operator": operator,
        "target": target,
        "patient_count": len(rows),
        "patients": [
            {
                "patient_id": patient_id,
                "sex": sex,
                "visit_count": visit_count,
                "medication_count": medication_count,
                "disease_count": disease_count,
            }
            for patient_id, sex, visit_count, medication_count, disease_count in rows
        ],
    }


def patient_visit_count_cohort(data_dir: str, operator: str, target: int) -> Dict[str, Any]:
    sql_operator = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<=", "eq": "="}.get(operator, "=")
    ensure_query_store(data_dir)
    con = _connect(data_dir)
    try:
        rows = con.execute(
            f"""
            SELECT patient_id, sex, visit_count, medication_count, disease_count
            FROM patients
            WHERE visit_count {sql_operator} ?
            ORDER BY patient_id
            """,
            [target],
        ).fetchall()
    finally:
        con.close()
    return {
        "operator": operator,
        "target": target,
        "patient_count": len(rows),
        "patients": [
            {
                "patient_id": patient_id,
                "sex": sex,
                "visit_count": visit_count,
                "medication_count": medication_count,
                "disease_count": disease_count,
            }
            for patient_id, sex, visit_count, medication_count, disease_count in rows
        ],
    }


def cohort_over_time_summary(
    data_dir: str,
    scoped_patient_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    ensure_query_store(data_dir)
    scope_ids = sorted({str(value or "").strip() for value in scoped_patient_ids or [] if str(value or "").strip()})
    scope_clause = ""
    if scope_ids:
        placeholders = ", ".join("?" for _ in scope_ids)
        scope_clause = f"WHERE patient_id IN ({placeholders})"
    con = _connect(data_dir)
    try:
        totals_row = con.execute(
            f"""
            WITH scoped_timepoints AS (
                SELECT * FROM timepoints
                {scope_clause}
            )
            SELECT
                COUNT(*) AS timepoint_count,
                COUNT(DISTINCT patient_id) AS patient_count,
                COUNT(event_date) AS dated_timepoint_count,
                MIN(event_date) AS first_event_date,
                MAX(event_date) AS last_event_date
            FROM scoped_timepoints
            """,
            scope_ids,
        ).fetchone()
        period_rows = con.execute(
            f"""
            WITH scoped_timepoints AS (
                SELECT * FROM timepoints
                {scope_clause}
            )
            SELECT
                SUBSTR(event_date, 1, 7) AS period,
                COUNT(*) AS timepoint_count,
                COUNT(DISTINCT patient_id) AS patient_count
            FROM scoped_timepoints
            WHERE event_date IS NOT NULL AND event_date <> ''
            GROUP BY period
            ORDER BY period
            """,
            scope_ids,
        ).fetchall()
        undated_row = con.execute(
            f"""
            WITH scoped_timepoints AS (
                SELECT * FROM timepoints
                {scope_clause}
            )
            SELECT COUNT(*) FROM scoped_timepoints
            WHERE event_date IS NULL OR event_date = ''
            """,
            scope_ids,
        ).fetchone()
    finally:
        con.close()

    timepoint_count, patient_count, dated_timepoint_count, first_event_date, last_event_date = totals_row or (0, 0, 0, None, None)
    undated_timepoint_count = int(undated_row[0]) if undated_row else 0
    periods = [
        {
            "period": period,
            "timepoint_count": timepoint_total,
            "patient_count": patient_total,
        }
        for period, timepoint_total, patient_total in period_rows
        if period
    ]
    return {
        "timepoint_count": int(timepoint_count or 0),
        "patient_count": int(patient_count or 0),
        "dated_timepoint_count": int(dated_timepoint_count or 0),
        "undated_timepoint_count": undated_timepoint_count,
        "first_event_date": first_event_date,
        "last_event_date": last_event_date,
        "periods": periods,
    }


def medication_counts(data_dir: str) -> List[Dict[str, Any]]:
    ensure_query_store(data_dir)
    con = _connect(data_dir)
    try:
        rows = con.execute(
            """
            SELECT medication, COUNT(DISTINCT patient_id) AS patient_count, list(DISTINCT patient_id ORDER BY patient_id) AS patients
            FROM patient_medications
            GROUP BY medication
            ORDER BY patient_count DESC, medication
            """
        ).fetchall()
    finally:
        con.close()
    return [
        {"medication": medication, "patient_count": patient_count, "patients": list(patients or [])}
        for medication, patient_count, patients in rows
    ]


def disease_counts(data_dir: str) -> List[Dict[str, Any]]:
    ensure_query_store(data_dir)
    con = _connect(data_dir)
    try:
        rows = con.execute(
            """
            SELECT disease, COUNT(DISTINCT patient_id) AS patient_count, list(DISTINCT patient_id ORDER BY patient_id) AS patients
            FROM patient_diseases
            GROUP BY disease
            ORDER BY patient_count DESC, disease
            """
        ).fetchall()
    finally:
        con.close()
    return [
        {"disease": disease, "patient_count": patient_count, "patients": list(patients or [])}
        for disease, patient_count, patients in rows
    ]


def medication_cohort(data_dir: str, medication_query: str) -> Dict[str, Any]:
    ensure_query_store(data_dir)
    query = medication_query.strip()
    if not query:
        return {"query": medication_query, "match_type": "case-insensitive substring", "patient_count": 0, "patients": []}
    like_value = f"%{query.lower()}%"
    con = _connect(data_dir)
    try:
        rows = con.execute(
            """
            SELECT
                patient_id,
                original_id,
                ANY_VALUE(event_type) AS event_type,
                ANY_VALUE(event_date) AS event_date,
                visit_id,
                source_file,
                record_index,
                list(DISTINCT medication ORDER BY medication) AS matched_medications
            FROM medication_events
            WHERE lower(medication) LIKE ?
            GROUP BY patient_id, original_id, visit_id, source_file, record_index
            ORDER BY patient_id, event_date, visit_id
            """,
            [like_value],
        ).fetchall()
        sex_map = {patient_id: sex for patient_id, sex in con.execute("SELECT patient_id, sex FROM patients").fetchall()}
    finally:
        con.close()

    grouped: Dict[str, Dict[str, Any]] = {}
    for patient_id, original_id, event_type, event_date, visit_id, source_file, record_index, matched_medications in rows:
        patient = grouped.setdefault(
            patient_id,
            {
                "patient_id": patient_id,
                "sex": sex_map.get(patient_id),
                "visit_count": 0,
                "matched_medications": [],
                "medication_count": 0,
                "original_record_ids": [],
                "visits": [],
            },
        )
        if original_id and original_id not in patient["original_record_ids"]:
            patient["original_record_ids"].append(original_id)
        labels = list(matched_medications or [])
        for label in labels:
            if label not in patient["matched_medications"]:
                patient["matched_medications"].append(label)
        patient["visits"].append(
            {
                "visit_id": visit_id,
                "original_id": original_id,
                "event_type": event_type,
                "event_date": event_date,
                "matched_medications": labels,
                "source_file": source_file,
                "record_index": record_index,
            }
        )
        patient["visit_count"] = len(patient["visits"])
        patient["medication_count"] = len(patient["matched_medications"])
    matches = [grouped[key] for key in sorted(grouped)]
    return {"query": medication_query, "match_type": "case-insensitive substring", "patient_count": len(matches), "patients": matches}


def disease_cohort(data_dir: str, disease_query: str) -> Dict[str, Any]:
    ensure_query_store(data_dir)
    query = disease_query.strip()
    if not query:
        return {"query": disease_query, "match_type": "case-insensitive substring", "patient_count": 0, "patients": []}
    like_value = f"%{query.lower()}%"
    con = _connect(data_dir)
    try:
        rows = con.execute(
            """
            SELECT
                patient_id,
                original_id,
                ANY_VALUE(event_type) AS event_type,
                ANY_VALUE(event_date) AS event_date,
                visit_id,
                source_file,
                record_index,
                list(DISTINCT disease ORDER BY disease) AS matched_diseases
            FROM disease_events
            WHERE lower(disease) LIKE ?
            GROUP BY patient_id, original_id, visit_id, source_file, record_index
            ORDER BY patient_id, event_date, visit_id
            """,
            [like_value],
        ).fetchall()
        sex_map = {patient_id: sex for patient_id, sex in con.execute("SELECT patient_id, sex FROM patients").fetchall()}
    finally:
        con.close()

    grouped: Dict[str, Dict[str, Any]] = {}
    for patient_id, original_id, event_type, event_date, visit_id, source_file, record_index, matched_diseases in rows:
        patient = grouped.setdefault(
            patient_id,
            {
                "patient_id": patient_id,
                "sex": sex_map.get(patient_id),
                "visit_count": 0,
                "medication_count": 0,
                "matched_diseases": [],
                "medications": [],
                "original_record_ids": [],
                "visits": [],
            },
        )
        if original_id and original_id not in patient["original_record_ids"]:
            patient["original_record_ids"].append(original_id)
        labels = list(matched_diseases or [])
        for label in labels:
            if label not in patient["matched_diseases"]:
                patient["matched_diseases"].append(label)
        patient["visits"].append(
            {
                "visit_id": visit_id,
                "original_id": original_id,
                "event_type": event_type,
                "event_date": event_date,
                "matched_diseases": labels,
                "source_file": source_file,
                "record_index": record_index,
            }
        )
        patient["visit_count"] = len(patient["visits"])
    if grouped:
        con = _connect(data_dir)
        try:
            medication_rows = con.execute(
                """
                SELECT patient_id, list(DISTINCT medication ORDER BY medication) AS medications
                FROM medication_events
                GROUP BY patient_id
                """
            ).fetchall()
        finally:
            con.close()
        medication_map = {patient_id: list(medications or []) for patient_id, medications in medication_rows}
        for patient_id, patient in grouped.items():
            meds = medication_map.get(patient_id, [])
            patient["medications"] = meds
            patient["medication_count"] = len(meds)
    matches = [grouped[key] for key in sorted(grouped)]
    return {"query": disease_query, "match_type": "case-insensitive substring", "patient_count": len(matches), "patients": matches}
