from __future__ import annotations

import csv
import hashlib
import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

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

try:
    import duckdb
except ImportError:  # pragma: no cover - optional runtime dependency
    duckdb = None


BASE_DIR = Path(__file__).resolve().parent.parent
QUERY_STORE_DIR = BASE_DIR / ".cache" / "query-store"
GENE_ANNOTATION_PATH = BASE_DIR / "scripts" / "data" / "hgnc_protein_coding_symbols.tsv"
ASSAY_DATA_DIR: Path | None = None
QUERY_STORE_SCHEMA_VERSION = 3


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


def assay_feature_annotations(gene_ids: List[str]) -> Dict[str, Dict[str, str]]:
    payload: Dict[str, Dict[str, str]] = {}
    for raw_gene_id in gene_ids:
        gene_id = str(raw_gene_id or "").strip()
        if not gene_id:
            continue
        annotation = _gene_annotation(gene_id)
        if any(annotation.values()):
            payload[gene_id] = annotation
    return payload


def _assay_matrix_files(data_dir: str) -> List[Path]:
    assay_dir = _resolve_assay_transcriptomics_dir(data_dir)
    if assay_dir is None:
        return []
    return [
        path
        for path in sorted(assay_dir.glob("*.csv"))
        if path.is_file()
    ]


def _assay_source_files(root: Path) -> List[Path]:
    assays_root = root / "assays"
    if not assays_root.exists() or not assays_root.is_dir():
        return []
    paths = []
    manifest_path = assays_root / "manifest.json"
    if manifest_path.is_file():
        paths.append(manifest_path)
    paths.extend(path for path in sorted(assays_root.glob("*/*.csv")) if path.is_file())
    return sorted(dict.fromkeys(paths))


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
    return {
        "schema_version": QUERY_STORE_SCHEMA_VERSION,
        "data_dir": str(resolved_dir),
        "files": files,
        "assay_files": assay_files,
    }


def _detect_matrix_delimiter(header_line: str) -> str:
    return ";" if header_line.count(";") >= header_line.count(",") else ","


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
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _signature_payload(payload: Dict[str, Any] | None) -> Dict[str, Any] | None:
    if payload is None:
        return None
    return {key: value for key, value in payload.items() if key != "built_at"}


def _store_has_required_tables(db_path: Path) -> bool:
    if duckdb is None or not db_path.exists():
        return False
    con = duckdb.connect(str(db_path))
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
    return {
        "schema_version": QUERY_STORE_SCHEMA_VERSION,
        "dataset_id": normalize_dataset_id(dataset_id),
        "root_path": str(dataset_root),
        "files": files,
        "assay_files": assay_files,
    }


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


def prepare_dataset_query_store(dataset_id: str) -> Dict[str, Any]:
    normalized = normalize_dataset_id(dataset_id)
    if not normalized:
        raise ValueError("A dataset id is required.")
    dataset_root = _dataset_root_path(normalized)
    db_path, meta_path, status_path = _dataset_store_paths(normalized)
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
    temp_suffix = f".tmp.{normalized}"
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
                "last_built_at": str((_load_json(status_path) or {}).get("last_built_at") or ""),
                "last_error": str(exc),
            },
        )
        raise
    return dataset_query_store_status(normalized)


def _sql_literal(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _sql_identifier(value: str) -> str:
    return '"' + str(value).replace('"', '""') + '"'


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
    con = duckdb.connect()
    aliases: List[str] = []
    multi_dataset = len(normalized) > 1
    for index, dataset_id in enumerate(normalized):
        alias = f"ds{index}"
        aliases.append(alias)
        db_path, _, _ = _dataset_store_paths(dataset_id)
        con.execute(f"ATTACH {_sql_literal(str(db_path))} AS {alias}")
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
            stat["source_files"].add(str(path))

            timepoint_rows.append(
                (
                    patient_id,
                    str(original_id) if isinstance(original_id, str) else None,
                    visit.visit_id,
                    visit.event_date,
                    visit.event_type,
                    visit.diagnosis,
                    str(path),
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
                        str(path),
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
                        str(path),
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
    meta_path.write_text(json.dumps(signature, ensure_ascii=False, indent=2), encoding="utf-8")


def patient_inventory(data_dir: str) -> List[str]:
    ensure_query_store(data_dir)
    con = _connect(data_dir)
    try:
        rows = con.execute("SELECT patient_id FROM patients ORDER BY patient_id").fetchall()
    finally:
        con.close()
    return [row[0] for row in rows]


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



def _assay_inventory_metadata(modality: Any, data_type: Any) -> Dict[str, Any]:
    modality_text = str(modality or "").strip() or "assay"
    data_type_text = str(data_type or "").strip() or "feature_matrix"
    if modality_text == "transcriptomics":
        feature_id_type = "ensembl_gene_id"
        feature_label = "genes"
        value_kind = "integer_counts" if data_type_text == "raw_counts" else "expression_values"
        supports_expression_summary = True
        supports_differential_expression = data_type_text == "raw_counts"
    elif modality_text in {"olink", "proteomics"}:
        feature_id_type = "protein_id"
        feature_label = "proteins"
        value_kind = "abundance"
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
    return {
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


def _assay_manifest_items(data_dir: str) -> List[Dict[str, Any]]:
    root = resolve_project_data_dir(data_dir)
    manifest_path = root / "assays" / "manifest.json"
    if manifest_path.exists():
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
        items = payload.get("assays") if isinstance(payload, dict) else []
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
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
        first_line = path.read_text(encoding="utf-8").splitlines()[0]
    except (OSError, IndexError, UnicodeDecodeError):
        return None
    delimiter = ";" if first_line.count(";") >= first_line.count(",") else ","
    sample_ids: List[str] = []
    feature_count = 0
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle, delimiter=delimiter)
            header = next(reader, [])
            sample_ids = [str(item or "").strip() for item in header[1:] if str(item or "").strip()]
            for row in reader:
                if row and str(row[0] or "").strip():
                    feature_count += 1
    except (OSError, UnicodeDecodeError):
        return None
    patient_ids = sorted({sample_id.split(":", 1)[0] for sample_id in sample_ids if sample_id.split(":", 1)[0]})
    return {
        "sample_ids": sample_ids,
        "patient_ids": patient_ids,
        "sample_count": len(sample_ids),
        "patient_count": len(patient_ids),
        "feature_count": feature_count,
    }


def _manifest_assay_inventory(data_dir: str, existing_names: set[str], clinical_patient_ids: set[str]) -> List[Dict[str, Any]]:
    root = resolve_project_data_dir(data_dir)
    items: List[Dict[str, Any]] = []
    for item in _assay_manifest_items(data_dir):
        dataset_name = str(item.get("assay_id") or Path(str(item.get("file") or "")).stem).strip()
        if not dataset_name or dataset_name in existing_names:
            continue
        stats = _assay_matrix_stats(root, item)
        if not stats:
            continue
        modality = str(item.get("modality") or "assay").strip() or "assay"
        data_type = str(item.get("data_type") or "feature_matrix").strip() or "feature_matrix"
        patient_ids = list(stats["patient_ids"])
        clinical_overlap = len(set(patient_ids).intersection(clinical_patient_ids))
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
                "mean_total_counts_per_sample": 0.0,
                "mean_detected_genes_per_sample": 0.0,
                "sample_ids": list(stats["sample_ids"]),
                "patient_ids": patient_ids,
                "top_genes": [],
                "feature_count": int(stats["feature_count"]),
                **_assay_inventory_metadata(modality, data_type),
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
    needle = str(search or "").strip().lower()
    if not needle:
        return gene_ids[: int(limit)]
    matches: List[str] = []
    for gene_id in gene_ids:
        annotation = _gene_annotation(gene_id)
        haystacks = [
            gene_id.lower(),
            str(annotation.get("gene_symbol") or "").lower(),
            str(annotation.get("gene_name") or "").lower(),
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
    root = resolve_project_data_dir(data_dir)
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
        **_assay_inventory_metadata(modality, data_type),
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
    finally:
        con.close()

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


def cohort_over_time_summary(data_dir: str) -> Dict[str, Any]:
    ensure_query_store(data_dir)
    con = _connect(data_dir)
    try:
        totals_row = con.execute(
            """
            SELECT
                COUNT(*) AS timepoint_count,
                COUNT(DISTINCT patient_id) AS patient_count,
                COUNT(event_date) AS dated_timepoint_count,
                MIN(event_date) AS first_event_date,
                MAX(event_date) AS last_event_date
            FROM timepoints
            """
        ).fetchone()
        period_rows = con.execute(
            """
            SELECT
                SUBSTR(event_date, 1, 7) AS period,
                COUNT(*) AS timepoint_count,
                COUNT(DISTINCT patient_id) AS patient_count
            FROM timepoints
            WHERE event_date IS NOT NULL AND event_date <> ''
            GROUP BY period
            ORDER BY period
            """
        ).fetchall()
        undated_row = con.execute(
            """
            SELECT COUNT(*) FROM timepoints
            WHERE event_date IS NULL OR event_date = ''
            """
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
