import json

from app.query import (
    _cohort_over_time_summary,
    patient_medication_count_cohort,
    patient_visit_count_cohort,
)


def _workspace(tmp_path):
    records = [
        {
            "id": "P1:baseline",
            "patient_id": "P1",
            "event_date": "2025-01-01",
            "treatments": [{"treatmentCode": {"label": "Drug A"}}],
        },
        {
            "id": "P1:followup",
            "patient_id": "P1",
            "event_date": "2025-02-01",
            "treatments": [{"treatmentCode": {"label": "Drug B"}}],
        },
        {
            "id": "P2:baseline",
            "patient_id": "P2",
            "event_date": "2025-03-01",
            "treatments": [{"treatmentCode": {"label": "Drug C"}}],
        },
    ]
    (tmp_path / "records.json").write_text(json.dumps(records), encoding="utf-8")
    return str(tmp_path)


def test_duckdb_count_helpers_apply_patient_scope(tmp_path):
    data_dir = _workspace(tmp_path)

    medication = patient_medication_count_cohort(data_dir, "gte", 1, scoped_patient_ids=["P1"])
    visits = patient_visit_count_cohort(data_dir, "gte", 1, scoped_patient_ids=["P2"])

    assert [item["patient_id"] for item in medication["patients"]] == ["P1"]
    assert [item["patient_id"] for item in visits["patients"]] == ["P2"]


def test_duckdb_longitudinal_summary_applies_patient_scope(tmp_path):
    summary = _cohort_over_time_summary(_workspace(tmp_path), scoped_patient_ids=["P1"])

    assert summary["patient_count"] == 1
    assert summary["timepoint_count"] == 2
    assert summary["first_event_date"] == "2025-01-01"
    assert summary["last_event_date"] == "2025-02-01"
