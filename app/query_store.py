from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.bff import (
    build_visit_context,
    ensure_data_dir,
    extract_patient_id,
    extract_treatment_labels,
    normalize_value,
    read_bff_records,
    resolve_project_data_dir,
)

try:
    import duckdb
except ImportError:  # pragma: no cover - optional runtime dependency
    duckdb = None


BASE_DIR = Path(__file__).resolve().parent.parent
QUERY_STORE_DIR = BASE_DIR / ".cache" / "query-store"
MOLECULAR_DATA_DIR: Path | None = None


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


def _store_paths(data_dir: str) -> Tuple[Path, Path]:
    key = _store_key(data_dir)
    QUERY_STORE_DIR.mkdir(parents=True, exist_ok=True)
    return QUERY_STORE_DIR / f"{key}.duckdb", QUERY_STORE_DIR / f"{key}.meta.json"


def _resolve_molecular_data_dir(data_dir: str) -> Path | None:
    if MOLECULAR_DATA_DIR is not None:
        return Path(MOLECULAR_DATA_DIR).expanduser().resolve()
    project_root = resolve_project_data_dir(data_dir)
    candidate = project_root / "molecular"
    if candidate.exists() and candidate.is_dir():
        return candidate.resolve()
    return None


def _molecular_matrix_files(data_dir: str) -> List[Path]:
    molecular_dir = _resolve_molecular_data_dir(data_dir)
    if molecular_dir is None:
        return []
    return [
        path
        for path in sorted(molecular_dir.glob("*.csv"))
        if path.is_file()
    ]


def _source_files_signature(data_dir: str) -> Dict[str, Any]:
    resolved_dir = ensure_data_dir(data_dir)
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
    molecular_files = []
    for path in _molecular_matrix_files(data_dir):
        stat = path.stat()
        molecular_files.append(
            {
                "path": str(path),
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
            }
        )
    return {"data_dir": str(resolved_dir), "files": files, "molecular_files": molecular_files}


def _detect_matrix_delimiter(header_line: str) -> str:
    return ";" if header_line.count(";") >= header_line.count(",") else ","


def _read_molecular_matrix(path: Path) -> Tuple[str, List[str], List[Tuple[str, List[int]]]]:
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


def _patient_id_from_molecular_sample(sample_id: str) -> str:
    value = str(sample_id).strip()
    if ":" in value:
        return value.split(":", 1)[0].strip() or value
    return value


def _connect(data_dir: str):
    if duckdb is None:
        raise RuntimeError("duckdb is not installed")
    db_path, _ = _store_paths(data_dir)
    return duckdb.connect(str(db_path))


def ensure_query_store(data_dir: str) -> None:
    if duckdb is None:
        return
    db_path, meta_path = _store_paths(data_dir)
    current_signature = _source_files_signature(data_dir)
    if db_path.exists() and meta_path.exists():
        try:
            stored_signature = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            stored_signature = None
        if stored_signature == current_signature:
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
            CREATE TABLE molecular_samples (
                dataset_name TEXT,
                sample_id TEXT,
                patient_id TEXT,
                modality TEXT
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
        molecular_sample_rows: List[Tuple[str, str, str, str]] = []
        transcript_count_rows: List[Tuple[str, str, str, str, int]] = []
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

        seen_molecular_samples = set()
        for matrix_path in _molecular_matrix_files(data_dir):
            dataset_name, sample_ids, rows = _read_molecular_matrix(matrix_path)
            for sample_id in sample_ids:
                patient_id = _patient_id_from_molecular_sample(sample_id)
                key = (dataset_name, sample_id)
                if key not in seen_molecular_samples:
                    seen_molecular_samples.add(key)
                    molecular_sample_rows.append((dataset_name, sample_id, patient_id, "transcriptomics_raw_counts"))
            for gene_id, values in rows:
                for sample_id, raw_count in zip(sample_ids, values):
                    transcript_count_rows.append((dataset_name, sample_id, _patient_id_from_molecular_sample(sample_id), gene_id, raw_count))

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
        if molecular_sample_rows:
            con.executemany("INSERT INTO molecular_samples VALUES (?, ?, ?, ?)", molecular_sample_rows)
        if transcript_count_rows:
            con.executemany("INSERT INTO transcript_counts VALUES (?, ?, ?, ?, ?)", transcript_count_rows)

        con.execute("CREATE INDEX idx_patients_patient_id ON patients(patient_id)")
        con.execute("CREATE INDEX idx_timepoints_patient_id ON timepoints(patient_id)")
        con.execute("CREATE INDEX idx_disease_events_disease ON disease_events(disease)")
        con.execute("CREATE INDEX idx_medication_events_medication ON medication_events(medication)")
        con.execute("CREATE INDEX idx_molecular_samples_sample_id ON molecular_samples(sample_id)")
        con.execute("CREATE INDEX idx_molecular_samples_patient_id ON molecular_samples(patient_id)")
        con.execute("CREATE INDEX idx_transcript_counts_gene_id ON transcript_counts(gene_id)")
        con.execute("CREATE INDEX idx_transcript_counts_sample_id ON transcript_counts(sample_id)")
    finally:
        con.close()

    meta_path.write_text(json.dumps(signature, ensure_ascii=False, indent=2), encoding="utf-8")


def patient_inventory(data_dir: str) -> List[str]:
    ensure_query_store(data_dir)
    con = _connect(data_dir)
    try:
        rows = con.execute("SELECT patient_id FROM patients ORDER BY patient_id").fetchall()
    finally:
        con.close()
    return [row[0] for row in rows]


def molecular_dataset_inventory(data_dir: str) -> List[Dict[str, Any]]:
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
                FROM molecular_samples AS s
                LEFT JOIN patients AS p
                    ON s.patient_id = p.patient_id
                GROUP BY s.dataset_name
            )
            SELECT
                s.dataset_name,
                max(s.modality) AS modality,
                max(ds.sample_count) AS sample_count,
                max(ds.patient_count) AS patient_count,
                max(gs.gene_count) AS gene_count,
                max(os.clinical_overlap_patient_count) AS clinical_overlap_patient_count,
                max(ds.mean_total_counts_per_sample) AS mean_total_counts_per_sample,
                max(ds.mean_detected_genes_per_sample) AS mean_detected_genes_per_sample
            FROM molecular_samples AS s
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
                FROM molecular_samples
                GROUP BY dataset_name
                """
            ).fetchall()
        }
        patient_ids_map = {
            dataset_name: list(values or [])
            for dataset_name, values in con.execute(
                """
                SELECT dataset_name, list(DISTINCT patient_id ORDER BY patient_id)
                FROM molecular_samples
                GROUP BY dataset_name
                """
            ).fetchall()
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
                {"gene_id": str(gene_id), "total_raw_count": int(total_raw_count)}
                for gene_id, total_raw_count in top_rows
            ]
    finally:
        con.close()
    return [
        {
            "dataset_name": dataset_name,
            "modality": modality,
            "sample_count": int(sample_count),
            "patient_count": int(patient_count),
            "gene_count": int(gene_count),
            "clinical_overlap_patient_count": int(clinical_overlap_patient_count),
            "mean_total_counts_per_sample": float(mean_total_counts_per_sample or 0),
            "mean_detected_genes_per_sample": float(mean_detected_genes_per_sample or 0),
            "sample_ids": list(sample_ids_map.get(dataset_name) or []),
            "patient_ids": list(patient_ids_map.get(dataset_name) or []),
            "top_genes": list(top_genes_map.get(dataset_name) or []),
        }
        for (
            dataset_name,
            modality,
            sample_count,
            patient_count,
            gene_count,
            clinical_overlap_patient_count,
            mean_total_counts_per_sample,
            mean_detected_genes_per_sample,
        ) in rows
    ]


def molecular_gene_inventory(data_dir: str, dataset_name: str, search: str = "", limit: int = 50) -> List[str]:
    ensure_query_store(data_dir)
    con = _connect(data_dir)
    try:
        if search.strip():
            rows = con.execute(
                """
                SELECT DISTINCT gene_id
                FROM transcript_counts
                WHERE dataset_name = ? AND lower(gene_id) LIKE ?
                ORDER BY gene_id
                LIMIT ?
                """,
                [dataset_name, f"%{search.strip().lower()}%", int(limit)],
            ).fetchall()
        else:
            rows = con.execute(
                """
                SELECT DISTINCT gene_id
                FROM transcript_counts
                WHERE dataset_name = ?
                ORDER BY gene_id
                LIMIT ?
                """,
                [dataset_name, int(limit)],
            ).fetchall()
    finally:
        con.close()
    return [str(row[0]) for row in rows]


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


def molecular_expression_summary(
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
        "scope_a": _summarize_expression_rows(cohort_a_rows, "Cohort A" if cohort_b_ids else "Selected scope"),
    }
    if cohort_b_ids:
        payload["scope_b"] = _summarize_expression_rows(cohort_b_rows, "Cohort B")
    return payload


def molecular_dataset_gene_means(data_dir: str, dataset_name: str, limit: int = 20) -> List[Dict[str, Any]]:
    ensure_query_store(data_dir)
    con = _connect(data_dir)
    try:
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


def molecular_dataset_pairwise_gene_differences(
    data_dir: str,
    dataset_a: str,
    dataset_b: str,
    limit: int = 12,
) -> List[Dict[str, Any]]:
    ensure_query_store(data_dir)
    con = _connect(data_dir)
    try:
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


def molecular_dataset_pairwise_exploratory_volcano(
    data_dir: str,
    dataset_a: str,
    dataset_b: str,
    limit: int = 2000,
) -> List[Dict[str, Any]]:
    ensure_query_store(data_dir)
    con = _connect(data_dir)
    try:
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
                "matched_diseases": [],
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
    matches = [grouped[key] for key in sorted(grouped)]
    return {"query": disease_query, "match_type": "case-insensitive substring", "patient_count": len(matches), "patients": matches}
