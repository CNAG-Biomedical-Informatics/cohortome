from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.bff import (
    build_visit_context,
    ensure_data_dir,
    extract_patient_id,
    extract_treatment_labels,
    normalize_value,
    read_bff_records,
)

try:
    import duckdb
except ImportError:  # pragma: no cover - optional runtime dependency
    duckdb = None


BASE_DIR = Path(__file__).resolve().parent.parent
QUERY_STORE_DIR = BASE_DIR / ".cache" / "query-store"


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
    return {"data_dir": str(resolved_dir), "files": files}


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

        patient_stats: Dict[str, Dict[str, Any]] = {}
        patient_disease_rows: List[Tuple[str, str]] = []
        patient_medication_rows: List[Tuple[str, str]] = []
        timepoint_rows: List[Tuple[str, Optional[str], str, Optional[str], Optional[str], Optional[str], str, int]] = []
        disease_event_rows: List[Tuple[str, Optional[str], str, Optional[str], Optional[str], str, str, int]] = []
        medication_event_rows: List[Tuple[str, Optional[str], str, Optional[str], Optional[str], str, str, int]] = []
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

        con.execute("CREATE INDEX idx_patients_patient_id ON patients(patient_id)")
        con.execute("CREATE INDEX idx_timepoints_patient_id ON timepoints(patient_id)")
        con.execute("CREATE INDEX idx_disease_events_disease ON disease_events(disease)")
        con.execute("CREATE INDEX idx_medication_events_medication ON medication_events(medication)")
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
