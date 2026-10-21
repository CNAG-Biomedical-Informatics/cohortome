from fastapi import HTTPException
import app.config as config_module
from app.bff import dashboard_summary
from app.bff import ensure_data_dir
from app.bff import get_patient_context
from app.bff import list_patient_summaries
from app.bff import medication_cohort
from app.bff import medication_counts
from app.bff import normalize_value
from app.main import get_medication_counts
from app.main import get_patient
from app.main import get_patients
from app.main import search_medication_cohort
from bff_test_helpers import write_json


def test_snapshot_visit_id_in_info():
    from app.bff import extract_visit_id
    assert extract_visit_id(
        {"id": "patient:other", "info": {"visit_id": "visit_1_week_2"}}, "fallback"
    ) == "visit_1_week_2"


def test_default_branding_uses_cohortome_and_keeps_instance_override(monkeypatch):
    monkeypatch.delenv("COHORTOME_BRAND_NAME", raising=False)
    monkeypatch.delenv("COHORTOME_BRAND_LOGO_ALT", raising=False)

    default_branding = config_module.branding_settings()

    assert default_branding["name"] == "COHORTome"
    assert default_branding["logo_alt"] == "COHORTome logo"

    monkeypatch.setenv("COHORTOME_BRAND_NAME", "Research Portal")
    assert config_module.branding_settings()["name"] == "Research Portal"


def test_ensure_data_dir_accepts_project_root_with_clinical_subdir(tmp_path):
    clinical_dir = tmp_path / "clinical"
    clinical_dir.mkdir()
    write_json(clinical_dir, "records.json", [{"id": "P1:baseline"}])

    assert ensure_data_dir(str(tmp_path)) == clinical_dir.resolve()


def test_dashboard_summary_includes_disease_medication_matrix(tmp_path):
    clinical_dir = tmp_path / "clinical"
    clinical_dir.mkdir()
    write_json(
        clinical_dir,
        "records.json",
        [
            {
                "id": "SYN001:week_0",
                "patient_id": "SYN001",
                "event_date": "2024-01-01",
                "diseases": [{"diseaseCode": {"label": "Crohn Disease"}}],
                "treatments": [{"treatmentCode": {"label": "Infliximab"}}],
            },
            {
                "id": "SYN002:week_0",
                "patient_id": "SYN002",
                "event_date": "2024-01-05",
                "diseases": [{"diseaseCode": {"label": "Ulcerative Colitis"}}],
                "treatments": [{"treatmentCode": {"label": "Vedolizumab"}}],
            },
            {
                "id": "SYN003:week_0",
                "patient_id": "SYN003",
                "event_date": "2024-01-09",
                "diseases": [{"diseaseCode": {"label": "Crohn Disease"}}],
                "treatments": [{"treatmentCode": {"label": "Vedolizumab"}}],
            },
        ],
    )

    payload = dashboard_summary(str(tmp_path))

    matrix = payload["disease_medication_matrix"]
    assert matrix["diseases"] == ["Crohn Disease", "Ulcerative Colitis"]
    assert matrix["medications"] == ["Vedolizumab", "Infliximab"]
    assert matrix["values"] == [
        [1, 1],
        [1, 0],
    ]
    syn001_timeline = next(item for item in payload["timelines"] if item["patient_id"] == "SYN001")
    assert syn001_timeline["events"][0]["event_date"] == "2024-01-01"
    assert {domain["key"] for domain in syn001_timeline["events"][0]["domains"]} == {"diseases", "treatments"}


def test_normalize_placeholder_values():
    assert normalize_value("1900-01-01") is None
    assert normalize_value("P999Y") is None
    assert normalize_value("-1") is None
    assert normalize_value("real-value") == "real-value"


def test_grouping_and_summary(tmp_path):
    write_json(
        tmp_path,
        "records.json",
        [
            {
                "patient_id": "PAT-1",
                "visit_id": "VIS-1",
                "event_date": "2024-01-10",
                "diagnosis": "Dx 1",
                "patient": {"date_of_birth": "1980-03-04", "sex": "female"},
            },
            {
                "patient_id": "PAT-1",
                "visit_id": "VIS-2",
                "event_date": "2024-02-11",
                "diagnosis": "Dx 2",
                "patient": {"date_of_birth": "1980-03-04", "sex": "female"},
            },
            {
                "patient_id": "PAT-2",
                "visit_id": "VIS-3",
                "event_date": "1900-01-01",
                "age_at_visit": "P999Y",
                "diagnosis": "Dx 3",
                "patient": {"sex": "male"},
            },
        ],
    )

    summaries = list_patient_summaries(str(tmp_path))
    assert [item.patient_id for item in summaries] == ["PAT-1", "PAT-2"]

    first = summaries[0]
    assert first.visit_count == 2
    assert first.first_event_date == "2024-01-10"
    assert first.last_event_date == "2024-02-11"
    assert first.evidence.diseases.count == 0

    patient = get_patient_context(str(tmp_path), "PAT-2")
    assert patient is not None
    assert patient.visits[0].event_date is None
    assert patient.visits[0].age_at_visit is None
    assert patient.visits[0].provenance.raw_bff["diagnosis"] == "Dx 3"


def test_grouping_reads_phenopacket_date_of_birth_preserved_in_bff_info(tmp_path):
    write_json(
        tmp_path,
        "records.json",
        [
            {
                "id": "SYN001:baseline",
                "patient_id": "SYN001",
                "info": {
                    "event_date": "2024-01-01",
                    "phenopacket": {"dateOfBirth": "1984-01-01"},
                },
            }
        ],
    )

    patient = get_patient_context(str(tmp_path), "SYN001")

    assert patient is not None
    assert patient.date_of_birth == "1984-01-01"


def test_api_endpoints(tmp_path):
    write_json(
        tmp_path,
        "records.json",
        [
            {
                "patient_id": "PAT-9",
                "visit_id": "VIS-9",
                "event_date": "2025-01-01",
                "event_type": "visit",
                "diagnosis": "Dx 9",
                "patient": {"sex": "female", "date_of_birth": "1979-10-10"},
            }
        ],
    )

    body = get_patients(data_dir=str(tmp_path))
    assert body[0]["patient_id"] == "PAT-9"
    assert body[0]["visit_count"] == 1
    assert body[0]["evidence"]["diseases"]["count"] == 0

    patient = get_patient("PAT-9", data_dir=str(tmp_path))
    assert patient["patient_id"] == "PAT-9"
    assert patient["visits"][0]["provenance"]["record_index"] == 0


def test_missing_patient_returns_404(tmp_path):
    write_json(tmp_path, "records.json", [])
    try:
        get_patient("does-not-exist", data_dir=str(tmp_path))
        assert False, "Expected HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 404


def test_beacon_like_records_group_by_top_level_id_prefix_and_ignore_info(tmp_path):
    write_json(
        tmp_path,
        "individuals.json",
        [
            {
                "id": "107:week_0_arm_1",
                "sex": {"id": "NCIT:C20197", "label": "Male"},
                "ethnicity": {"id": "NCIT:C41261", "label": "White"},
                "info": {
                    "study_id": "WRONG-ID",
                    "redcap_event_name": "wrong_event",
                    "diagnosis": "Wrong Diagnosis",
                },
                "diseases": [
                    {
                        "_visit": {"id": "week_0_arm_1"},
                        "diseaseCode": {"id": "NCIT:C2965", "label": "Crohn Disease"},
                    }
                ],
                "measures": [{"_visit": {"id": "week_0_arm_1"}}],
            },
            {
                "id": "107:week_14_arm_1",
                "sex": {"id": "NCIT:C20197", "label": "Male"},
                "ethnicity": {"id": "NCIT:C41261", "label": "White"},
                "info": {
                    "study_id": "OTHER-WRONG-ID",
                    "redcap_event_name": "another_wrong_event",
                },
                "diseases": [
                    {
                        "_visit": {"id": "week_14_arm_1"},
                        "diseaseCode": {"id": "NCIT:C2965", "label": "Crohn Disease"},
                    }
                ],
                "treatments": [{"_visit": {"id": "week_14_arm_1"}}],
            },
        ],
    )

    summaries = list_patient_summaries(str(tmp_path))
    assert len(summaries) == 1
    assert summaries[0].patient_id == "107"
    assert summaries[0].sex == "Male"

    patient = get_patient_context(str(tmp_path), "107")
    assert patient is not None
    assert [visit.visit_id for visit in patient.visits] == ["week_0_arm_1", "week_14_arm_1"]
    assert patient.visits[0].diagnosis == "Crohn Disease"
    assert patient.visits[0].event_type == "week_0_arm_1"
    assert patient.visits[0].evidence.diseases.count == 1
    assert patient.visits[0].evidence.measures.count == 1
    assert patient.evidence.treatments.count == 1
    assert patient.evidence.diseases.examples == ["Crohn Disease"]
    assert "info" not in patient.visits[0].notes
    assert patient.visits[0].provenance.raw_bff["info"]["study_id"] == "WRONG-ID"


def test_medication_cohort_counts_unique_patients(tmp_path):
    write_json(
        tmp_path,
        "individuals.json",
        [
            {
                "id": "101:week_0_arm_1",
                "treatments": [
                    {"_visit": {"id": "week_0_arm_1"}, "treatmentCode": {"label": "Infliximab"}},
                    {"_visit": {"id": "week_0_arm_1"}, "treatmentCode": {"label": "Azathioprine"}},
                ],
            },
            {
                "id": "101:week_14_arm_1",
                "treatments": [
                    {"_visit": {"id": "week_14_arm_1"}, "treatmentCode": {"label": "Infliximab"}}
                ],
            },
            {
                "id": "202:week_0_arm_1",
                "treatments": [
                    {"_visit": {"id": "week_0_arm_1"}, "treatmentCode": {"label": "Infliximab"}}
                ],
            },
        ],
    )

    counts = medication_counts(str(tmp_path))
    assert counts[0]["medication"] == "Infliximab"
    assert counts[0]["patient_count"] == 2
    assert counts[0]["patients"] == ["101", "202"]

    cohort = medication_cohort(str(tmp_path), "inflix")
    assert cohort["patient_count"] == 2
    assert cohort["patients"][0]["patient_id"] == "101"
    assert cohort["patients"][0]["visit_count"] == 2

    counts_payload = get_medication_counts(data_dir=str(tmp_path))
    assert counts_payload[0]["medication"] == "Infliximab"

    search_payload = search_medication_cohort(medication="Azathioprine", data_dir=str(tmp_path))
    assert search_payload["patient_count"] == 1
    assert search_payload["patients"][0]["matched_medications"] == ["Azathioprine"]
