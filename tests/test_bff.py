import json

from fastapi import HTTPException

import app.analysis as analysis_module
import app.cohorts as cohorts_module
import app.query as query_module
import app.query_store as query_store_module
from app.bff import (
    build_patient_navigator,
    get_patient_context,
    list_patient_summaries,
    medication_cohort,
    medication_counts,
    normalize_value,
)
from app.main import (
    get_medication_counts,
    get_patient,
    get_patient_navigator,
    get_patients,
    search_medication_cohort,
)
from app.query import answer_query
from app.query_store import (
    cohort_over_time_summary as store_cohort_over_time_summary,
    duckdb_available,
    medication_counts as store_medication_counts,
    molecular_dataset_inventory as store_molecular_dataset_inventory,
    molecular_expression_summary as store_molecular_expression_summary,
    molecular_gene_inventory as store_molecular_gene_inventory,
    patient_inventory as store_patient_inventory,
    patient_visit_count_cohort as store_patient_visit_count_cohort,
)


def write_json(tmp_path, name, payload):
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_saved_cohorts_persist_and_filter_by_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(cohorts_module, "SAVED_COHORTS_PATH", tmp_path / "saved-cohorts.json")

    saved = cohorts_module.save_cohort(
        name="Crohn cohort",
        data_dir="/data/a",
        ids=["P1", "P2", "P2"],
        id_type="patient",
        source_kind="query",
        source_prompt="Which patients have Crohn Disease?",
    )
    assert saved["name"] == "Crohn cohort"
    assert saved["patient_ids"] == ["P1", "P2"]

    other = cohorts_module.save_cohort(
        name="Other cohort",
        data_dir="/data/b",
        ids=["X1"],
        id_type="original_record",
        source_kind="query",
        source_prompt="Other",
    )
    assert other["id_type"] == "original_record"

    listed = cohorts_module.list_saved_cohorts("/data/a")
    assert len(listed) == 1
    assert listed[0]["name"] == "Crohn cohort"

    assert cohorts_module.delete_saved_cohort(saved["id"]) is True
    assert cohorts_module.delete_saved_cohort("missing") is False
    assert cohorts_module.list_saved_cohorts("/data/a") == []


def test_saved_cohorts_auto_suffix_duplicate_names(tmp_path, monkeypatch):
    monkeypatch.setattr(cohorts_module, "SAVED_COHORTS_PATH", tmp_path / "saved-cohorts.json")

    first = cohorts_module.save_cohort(
        name="Crohn cohort",
        data_dir="/data/a",
        ids=["P1"],
        id_type="patient",
        source_kind="query",
        source_prompt="First Crohn cohort",
    )
    second = cohorts_module.save_cohort(
        name="Crohn cohort",
        data_dir="/data/a",
        ids=["P2"],
        id_type="patient",
        source_kind="query",
        source_prompt="Second Crohn cohort",
    )
    third_other_dir = cohorts_module.save_cohort(
        name="Crohn cohort",
        data_dir="/data/b",
        ids=["X1"],
        id_type="patient",
        source_kind="query",
        source_prompt="Crohn cohort in another dataset",
    )

    assert first["name"] == "Crohn cohort"
    assert second["name"] == "Crohn cohort (2)"
    assert third_other_dir["name"] == "Crohn cohort"


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


def test_analysis_survival_kaplan_meier_for_measure_threshold(tmp_path):
    write_json(
        tmp_path,
        "records.json",
        [
            {
                "id": "P1:week0",
                "event_date": "2024-01-01",
                "measures": [
                    {
                        "assayCode": {"label": "Leukocyte Count"},
                        "measurementValue": {"quantity": {"value": 8.0, "unit": {"label": "Cells per Microliter"}}},
                    }
                ],
            },
            {
                "id": "P1:week4",
                "event_date": "2024-01-15",
                "measures": [
                    {
                        "assayCode": {"label": "Leukocyte Count"},
                        "measurementValue": {"quantity": {"value": 11.2, "unit": {"label": "Cells per Microliter"}}},
                    }
                ],
            },
            {
                "id": "P2:week0",
                "event_date": "2024-01-03",
                "measures": [
                    {
                        "assayCode": {"label": "Leukocyte Count"},
                        "measurementValue": {"quantity": {"value": 7.1, "unit": {"label": "Cells per Microliter"}}},
                    }
                ],
            },
            {
                "id": "P2:week4",
                "event_date": "2024-01-21",
                "measures": [
                    {
                        "assayCode": {"label": "Leukocyte Count"},
                        "measurementValue": {"quantity": {"value": 8.4, "unit": {"label": "Cells per Microliter"}}},
                    }
                ],
            },
        ],
    )

    payload = analysis_module.analysis_llm_reply(
        "Show a Kaplan-Meier curve for time to Leukocyte Count > 10",
        str(tmp_path),
    )

    assert payload["intent"] == "analysis_survival"
    context = payload["data"]["context"]
    assert context["mode"] == "survival"
    assert context["measure"] == "Leukocyte Count"
    assert context["patient_count"] == 2
    assert context["event_count"] == 1
    assert context["censored_count"] == 1
    assert context["median_survival_days"] == 14
    assert context["curve_points"][0]["survival_probability"] == 1.0
    assert context["curve_points"][1]["time_days"] == 14
    assert context["curve_points"][1]["survival_probability"] == 0.5


def test_analysis_survival_compare_kaplan_meier(tmp_path):
    write_json(
        tmp_path,
        "records.json",
        [
            {
                "id": "A1:week0",
                "event_date": "2024-01-01",
                "measures": [{"assayCode": {"label": "Hemoglobin"}, "measurementValue": {"quantity": {"value": 12.0}}}],
            },
            {
                "id": "A1:week2",
                "event_date": "2024-01-10",
                "measures": [{"assayCode": {"label": "Hemoglobin"}, "measurementValue": {"quantity": {"value": 10.4}}}],
            },
            {
                "id": "A2:week0",
                "event_date": "2024-01-02",
                "measures": [{"assayCode": {"label": "Hemoglobin"}, "measurementValue": {"quantity": {"value": 12.8}}}],
            },
            {
                "id": "A2:week2",
                "event_date": "2024-01-12",
                "measures": [{"assayCode": {"label": "Hemoglobin"}, "measurementValue": {"quantity": {"value": 12.1}}}],
            },
            {
                "id": "B1:week0",
                "event_date": "2024-01-01",
                "measures": [{"assayCode": {"label": "Hemoglobin"}, "measurementValue": {"quantity": {"value": 12.5}}}],
            },
            {
                "id": "B1:week2",
                "event_date": "2024-01-10",
                "measures": [{"assayCode": {"label": "Hemoglobin"}, "measurementValue": {"quantity": {"value": 12.1}}}],
            },
            {
                "id": "B2:week0",
                "event_date": "2024-01-03",
                "measures": [{"assayCode": {"label": "Hemoglobin"}, "measurementValue": {"quantity": {"value": 12.7}}}],
            },
            {
                "id": "B2:week2",
                "event_date": "2024-01-11",
                "measures": [{"assayCode": {"label": "Hemoglobin"}, "measurementValue": {"quantity": {"value": 12.0}}}],
            },
        ],
    )

    payload = analysis_module.analysis_llm_reply(
        "Compare Cohort A and Cohort B with Kaplan-Meier for time to Hemoglobin < 11",
        str(tmp_path),
        selected_patient_ids="A1,A2",
        compare_mode=True,
        compare_selected_patient_ids="B1,B2",
    )

    assert payload["intent"] == "analysis_survival_compare"
    context = payload["data"]["context"]
    assert context["mode"] == "survival_compare"
    assert context["cohort_a"]["event_count"] == 1
    assert context["cohort_b"]["event_count"] == 0


def test_analysis_survival_reports_unavailable_when_insufficient_dated_measure_data(tmp_path):
    write_json(
        tmp_path,
        "records.json",
        [
            {
                "id": "P1:week0",
                "event_date": "2024-01-01",
                "measures": [{"assayCode": {"label": "CRP"}, "measurementValue": {"quantity": {"value": 8.0}}}],
            },
            {
                "id": "P2:week0",
                "event_date": "1900-01-01",
                "measures": [{"assayCode": {"label": "CRP"}, "measurementValue": {"quantity": {"value": 11.0}}}],
            },
        ],
    )

    payload = analysis_module.analysis_llm_reply(
        "Show a Kaplan-Meier curve for time to CRP > 10",
        str(tmp_path),
    )

    assert payload["intent"] == "analysis_survival"
    context = payload["data"]["context"]
    assert context["mode"] == "survival"
    assert "Kaplan-Meier is unavailable" in context["error"]
    assert context["patient_count"] == 1


def test_analysis_trajectory_for_measure_over_time(tmp_path):
    write_json(
        tmp_path,
        "records.json",
        [
            {
                "id": "P1:week0",
                "event_date": "2024-01-01",
                "measures": [{"assayCode": {"label": "CRP"}, "measurementValue": {"quantity": {"value": 10.0}}}],
            },
            {
                "id": "P1:week2",
                "event_date": "2024-01-10",
                "measures": [{"assayCode": {"label": "CRP"}, "measurementValue": {"quantity": {"value": 6.0}}}],
            },
            {
                "id": "P2:week0",
                "event_date": "2024-01-01",
                "measures": [{"assayCode": {"label": "CRP"}, "measurementValue": {"quantity": {"value": 8.0}}}],
            },
            {
                "id": "P2:week2",
                "event_date": "2024-01-10",
                "measures": [{"assayCode": {"label": "CRP"}, "measurementValue": {"quantity": {"value": 4.0}}}],
            },
        ],
    )

    payload = analysis_module.analysis_llm_reply(
        "Show the trajectory of CRP over time",
        str(tmp_path),
    )

    assert payload["intent"] == "analysis_trajectory"
    context = payload["data"]["context"]
    assert context["mode"] == "trajectory"
    assert context["measure"] == "CRP"
    assert context["patient_count"] == 2
    assert len(context["summary_points"]) == 2


def test_analysis_treatment_response_trajectory(tmp_path):
    write_json(
        tmp_path,
        "records.json",
        [
            {
                "id": "P1:baseline",
                "event_date": "2024-01-01",
                "measures": [{"assayCode": {"label": "CRP"}, "measurementValue": {"quantity": {"value": 12.0}}}],
            },
            {
                "id": "P1:treat",
                "event_date": "2024-01-05",
                "treatments": [{"treatmentCode": {"label": "Infliximab"}}],
                "measures": [{"assayCode": {"label": "CRP"}, "measurementValue": {"quantity": {"value": 11.0}}}],
            },
            {
                "id": "P1:followup",
                "event_date": "2024-01-15",
                "measures": [{"assayCode": {"label": "CRP"}, "measurementValue": {"quantity": {"value": 5.0}}}],
            },
            {
                "id": "P2:baseline",
                "event_date": "2024-01-02",
                "measures": [{"assayCode": {"label": "CRP"}, "measurementValue": {"quantity": {"value": 14.0}}}],
            },
            {
                "id": "P2:treat",
                "event_date": "2024-01-06",
                "treatments": [{"treatmentCode": {"label": "Infliximab"}}],
                "measures": [{"assayCode": {"label": "CRP"}, "measurementValue": {"quantity": {"value": 13.0}}}],
            },
            {
                "id": "P2:followup",
                "event_date": "2024-01-16",
                "measures": [{"assayCode": {"label": "CRP"}, "measurementValue": {"quantity": {"value": 7.0}}}],
            },
        ],
    )

    payload = analysis_module.analysis_llm_reply(
        "Show response to Infliximab using CRP",
        str(tmp_path),
    )

    assert payload["intent"] == "analysis_trajectory"
    context = payload["data"]["context"]
    assert context["mode"] == "trajectory_response"
    assert context["treatment"] == "Infliximab"
    assert context["measure"] == "CRP"
    assert context["patient_count"] == 2


def test_analysis_treatment_response_trajectory_uses_requested_treatment(tmp_path):
    write_json(
        tmp_path,
        "records.json",
        [
            {
                "id": "P1:adalimumab",
                "event_date": "2024-01-03",
                "treatments": [{"treatmentCode": {"label": "Adalimumab"}}],
                "measures": [{"assayCode": {"label": "CRP"}, "measurementValue": {"quantity": {"value": 12.0}}}],
            },
            {
                "id": "P1:infliximab",
                "event_date": "2024-01-10",
                "treatments": [{"treatmentCode": {"label": "Infliximab"}}],
                "measures": [{"assayCode": {"label": "CRP"}, "measurementValue": {"quantity": {"value": 9.0}}}],
            },
            {
                "id": "P1:followup",
                "event_date": "2024-01-20",
                "measures": [{"assayCode": {"label": "CRP"}, "measurementValue": {"quantity": {"value": 4.0}}}],
            },
            {
                "id": "P2:adalimumab",
                "event_date": "2024-01-04",
                "treatments": [{"treatmentCode": {"label": "Adalimumab"}}],
                "measures": [{"assayCode": {"label": "CRP"}, "measurementValue": {"quantity": {"value": 10.0}}}],
            },
            {
                "id": "P2:infliximab",
                "event_date": "2024-01-12",
                "treatments": [{"treatmentCode": {"label": "Infliximab"}}],
                "measures": [{"assayCode": {"label": "CRP"}, "measurementValue": {"quantity": {"value": 8.0}}}],
            },
            {
                "id": "P2:followup",
                "event_date": "2024-01-22",
                "measures": [{"assayCode": {"label": "CRP"}, "measurementValue": {"quantity": {"value": 5.0}}}],
            },
        ],
    )

    payload = analysis_module.analysis_llm_reply(
        "Show response to Infliximab using CRP",
        str(tmp_path),
    )

    assert payload["intent"] == "analysis_trajectory"
    context = payload["data"]["context"]
    assert context["mode"] == "trajectory_response"
    assert context["treatment"] == "Infliximab"
    assert context["summary_points"][0]["x"] == 0
    assert context["summary_points"][-1]["x"] == 10


def test_analysis_compare_trajectory(tmp_path):
    write_json(
        tmp_path,
        "records.json",
        [
            {
                "id": "A1:week0",
                "event_date": "2024-01-01",
                "measures": [{"assayCode": {"label": "Leukocyte Count"}, "measurementValue": {"quantity": {"value": 12.0}}}],
            },
            {
                "id": "A1:week2",
                "event_date": "2024-01-15",
                "measures": [{"assayCode": {"label": "Leukocyte Count"}, "measurementValue": {"quantity": {"value": 8.0}}}],
            },
            {
                "id": "A2:week0",
                "event_date": "2024-01-02",
                "measures": [{"assayCode": {"label": "Leukocyte Count"}, "measurementValue": {"quantity": {"value": 11.0}}}],
            },
            {
                "id": "A2:week2",
                "event_date": "2024-01-16",
                "measures": [{"assayCode": {"label": "Leukocyte Count"}, "measurementValue": {"quantity": {"value": 7.0}}}],
            },
            {
                "id": "B1:week0",
                "event_date": "2024-01-01",
                "measures": [{"assayCode": {"label": "Leukocyte Count"}, "measurementValue": {"quantity": {"value": 9.0}}}],
            },
            {
                "id": "B1:week2",
                "event_date": "2024-01-15",
                "measures": [{"assayCode": {"label": "Leukocyte Count"}, "measurementValue": {"quantity": {"value": 10.0}}}],
            },
            {
                "id": "B2:week0",
                "event_date": "2024-01-02",
                "measures": [{"assayCode": {"label": "Leukocyte Count"}, "measurementValue": {"quantity": {"value": 8.0}}}],
            },
            {
                "id": "B2:week2",
                "event_date": "2024-01-16",
                "measures": [{"assayCode": {"label": "Leukocyte Count"}, "measurementValue": {"quantity": {"value": 9.0}}}],
            },
        ],
    )

    payload = analysis_module.analysis_llm_reply(
        "Compare Cohort A and Cohort B by Leukocyte Count trajectories",
        str(tmp_path),
        selected_patient_ids="A1,A2",
        compare_mode=True,
        compare_selected_patient_ids="B1,B2",
    )

    assert payload["intent"] == "analysis_trajectory_compare"
    context = payload["data"]["context"]
    assert context["mode"] == "trajectory_compare"
    assert context["measure"] == "Leukocyte Count"
    assert context["cohort_a"]["patient_count"] == 2
    assert context["cohort_b"]["patient_count"] == 2


def test_analysis_uses_semantic_planner_for_broad_trajectory_prompt(tmp_path, monkeypatch):
    write_json(
        tmp_path,
        "records.json",
        [
            {
                "id": "P1:baseline",
                "event_date": "2024-01-01",
                "treatments": [{"treatmentCode": {"label": "Infliximab"}}],
                "measures": [{"assayCode": {"label": "CRP"}, "measurementValue": {"quantity": {"value": 10.0}}}],
            },
            {
                "id": "P1:followup",
                "event_date": "2024-01-15",
                "measures": [{"assayCode": {"label": "CRP"}, "measurementValue": {"quantity": {"value": 5.0}}}],
            },
            {
                "id": "P2:baseline",
                "event_date": "2024-01-02",
                "treatments": [{"treatmentCode": {"label": "Infliximab"}}],
                "measures": [{"assayCode": {"label": "CRP"}, "measurementValue": {"quantity": {"value": 12.0}}}],
            },
            {
                "id": "P2:followup",
                "event_date": "2024-01-16",
                "measures": [{"assayCode": {"label": "CRP"}, "measurementValue": {"quantity": {"value": 7.0}}}],
            },
        ],
    )

    monkeypatch.setenv("LM_STUDIO_ENABLED", "true")
    monkeypatch.setenv("LM_STUDIO_MODEL", "local-model")

    calls = []

    def fake_http_json(url, payload=None, log_kind="generic"):
        if url.endswith("/models"):
            return {"data": [{"id": "local-model"}]}
        calls.append(log_kind)
        if log_kind == "analysis_planner":
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "intent": "analysis_plan",
                                    "analysis_type": "trajectory",
                                    "measure_query": "CRP",
                                    "treatment_query": "Infliximab",
                                }
                            )
                        }
                    }
                ]
            }
        return {"choices": [{"message": {"content": "Narrative analysis"}}]}

    monkeypatch.setattr(analysis_module, "http_json", fake_http_json)

    payload = analysis_module.analysis_llm_reply(
        "Analyze CRP response after infliximab",
        str(tmp_path),
    )

    assert payload["intent"] == "analysis_trajectory"
    assert payload["data"]["execution"] == "deterministic"
    assert payload["data"]["planner"]["model"] == "local-model"
    assert payload["data"]["context"]["mode"] == "trajectory_response"
    assert calls == ["analysis_planner"]


def test_analysis_falls_back_to_llm_narrative_when_planner_is_unsupported(tmp_path, monkeypatch):
    write_json(
        tmp_path,
        "records.json",
        [
            {
                "id": "P1:baseline",
                "event_date": "2024-01-01",
                "measures": [{"assayCode": {"label": "CRP"}, "measurementValue": {"quantity": {"value": 10.0}}}],
            }
        ],
    )

    monkeypatch.setenv("LM_STUDIO_ENABLED", "true")
    monkeypatch.setenv("LM_STUDIO_MODEL", "local-model")

    calls = []

    def fake_http_json(url, payload=None, log_kind="generic"):
        if url.endswith("/models"):
            return {"data": [{"id": "local-model"}]}
        calls.append(log_kind)
        if log_kind == "analysis_planner":
            return {"choices": [{"message": {"content": "{\"intent\":\"unsupported\"}"}}]}
        return {"choices": [{"message": {"content": "Narrative analysis"}}]}

    monkeypatch.setattr(analysis_module, "http_json", fake_http_json)

    payload = analysis_module.analysis_llm_reply(
        "What should I inspect next in this cohort?",
        str(tmp_path),
    )

    assert payload["intent"] == "analysis_llm"
    assert payload["reply"] == "Narrative analysis"
    assert calls == ["analysis_planner", "analysis_llm"]


def test_analysis_llm_only_skips_planner(tmp_path, monkeypatch):
    write_json(
        tmp_path,
        "records.json",
        [
            {
                "id": "P1:baseline",
                "event_date": "2024-01-01",
                "measures": [{"assayCode": {"label": "CRP"}, "measurementValue": {"quantity": {"value": 10.0}}}],
            }
        ],
    )

    monkeypatch.setenv("LM_STUDIO_ENABLED", "true")
    monkeypatch.setenv("LM_STUDIO_MODEL", "local-model")

    calls = []

    def fake_http_json(url, payload=None, log_kind="generic"):
        calls.append(log_kind)
        return {"choices": [{"message": {"content": "Narrative analysis"}}]}

    monkeypatch.setattr(analysis_module, "http_json", fake_http_json)

    payload = analysis_module.analysis_llm_reply(
        "Compare Cohort A and Cohort B like a clinical reviewer and summarize the main similarities, differences, and uncertainties.",
        str(tmp_path),
        llm_only=True,
    )

    assert payload["intent"] == "analysis_llm"
    assert payload["reply"] == "Narrative analysis"
    assert calls == ["analysis_llm"]


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


def test_patient_navigator_precomputes_fragment_pointers(tmp_path):
    write_json(
        tmp_path,
        "individuals.json",
        [
            {
                "id": "900:week_0_arm_1",
                "sex": {"label": "Female"},
                "diseases": [
                    {
                        "_visit": {"id": "week_0_arm_1"},
                        "diseaseCode": {"label": "Ulcerative Colitis"},
                    }
                ],
                "measures": [
                    {
                        "_visit": {"id": "week_0_arm_1"},
                        "assayCode": {"label": "C-Reactive Protein Measurement"},
                    }
                ],
                "treatments": [
                    {
                        "_visit": {"id": "week_0_arm_1"},
                        "treatmentCode": {"label": "Infliximab"},
                    }
                ],
            }
        ],
    )

    navigator = build_patient_navigator(str(tmp_path), "900")
    assert navigator is not None
    assert navigator.summary.patient_id == "900"
    assert navigator.evidence.diseases.count == 1
    assert navigator.visits[0].key_fragments[0].path == "diseases[0]"
    assert navigator.visits[0].key_fragments[0].label == "Ulcerative Colitis"
    assert navigator.visits[0].key_fragments[1].path == "measures[0]"
    assert navigator.key_fragments[2].label == "Infliximab"

    navigator_payload = get_patient_navigator("900", data_dir=str(tmp_path))
    assert navigator_payload["patient_id"] == "900"
    assert navigator_payload["visits"][0]["key_fragments"][0]["category"] == "disease"


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


def test_query_uses_lm_studio_fallback_when_enabled(tmp_path, monkeypatch):
    write_json(
        tmp_path,
        "records.json",
        [
            {
                "patient_id": "PAT-1",
                "visit_id": "VIS-1",
                "event_date": "2025-01-01",
                "diagnosis": "Crohn Disease",
                "patient": {"sex": "female"},
            }
        ],
    )

    monkeypatch.setenv("LM_STUDIO_ENABLED", "true")
    monkeypatch.delenv("LM_STUDIO_MODEL", raising=False)

    def fake_http_json(url, payload=None, log_kind="generic"):
        if url.endswith("/models"):
            return {"data": [{"id": "local-model"}]}
        assert url.endswith("/chat/completions")
        assert payload is not None
        assert payload["model"] == "local-model"
        assert payload["messages"][1]["content"].find("Prior question") == -1
        return {"choices": [{"message": {"content": "LM Studio answer"}}]}

    monkeypatch.setattr(query_module, "_http_json", fake_http_json)

    payload = answer_query(str(tmp_path), "What evidence supports the main cohort summary?")
    assert payload["intent"] == "llm_fallback"
    assert payload["reply"] == "LM Studio answer"
    assert payload["data"]["model"] == "local-model"
    assert payload["data"]["base_url"] == "http://192.168.1.42:1234/v1"


def test_query_reports_missing_lm_studio_model(tmp_path, monkeypatch):
    write_json(tmp_path, "records.json", [])

    monkeypatch.setenv("LM_STUDIO_ENABLED", "1")
    monkeypatch.delenv("LM_STUDIO_MODEL", raising=False)
    monkeypatch.setattr(query_module, "_http_json", lambda url, payload=None, log_kind="generic": {"data": []})

    payload = answer_query(str(tmp_path), "Explain the cohort")
    assert payload["intent"] == "llm_unavailable"
    assert "no loaded model" in payload["reply"].lower()


def test_query_needs_clarification_for_short_prompt(tmp_path):
    write_json(tmp_path, "records.json", [])

    payload = answer_query(str(tmp_path), "why")
    assert payload["intent"] == "needs_clarification"
    assert "too short" in payload["reply"].lower()
    assert payload["data"]["follow_up_suggestions"]


def test_follow_up_suggestions_normalize_question_shaped_terms():
    suggestions = query_module._follow_up_suggestions("How many patients have Crohn Disease?")
    assert suggestions == [
        "How many patients have Crohn Disease?",
        "Which patients have Crohn Disease?",
        "What treatments are associated with Crohn Disease?",
    ]


def test_follow_up_suggestions_normalize_take_style_medication_questions():
    suggestions = query_module._follow_up_suggestions("How many patients take esteroids?")
    assert suggestions == [
        "How many patients have esteroids?",
        "Which patients have esteroids?",
        "Show the visits mentioning esteroids.",
    ]


def test_query_passes_history_into_lm_studio_context(tmp_path, monkeypatch):
    write_json(tmp_path, "records.json", [])

    monkeypatch.setenv("LM_STUDIO_ENABLED", "true")
    monkeypatch.delenv("LM_STUDIO_MODEL", raising=False)

    captured = {}

    def fake_http_json(url, payload=None, log_kind="generic"):
        if url.endswith("/models"):
            return {"data": [{"id": "local-model"}]}
        captured["payload"] = payload
        return {"choices": [{"message": {"content": "Context-aware answer"}}]}

    monkeypatch.setattr(query_module, "_http_json", fake_http_json)

    payload = answer_query(
        str(tmp_path),
        "What changed after that?",
        history=[
            {"role": "user", "content": "Show patient 107"},
            {"role": "assistant", "content": "Patient 107 has 2 visits."},
        ],
    )

    assert payload["intent"] == "llm_fallback"
    assert payload["reply"] == "Context-aware answer"
    user_message = captured["payload"]["messages"][1]["content"]
    assert "conversation_history" in user_message
    assert "Show patient 107" in user_message


def test_query_uses_semantic_planner_before_generic_lm_fallback(tmp_path, monkeypatch):
    write_json(
        tmp_path,
        "records.json",
        [
            {
                "id": "P1:v1",
                "event_date": "2024-01-01",
                "diseases": [{"diseaseCode": {"label": "Crohn Disease"}}],
                "treatments": [{"treatmentCode": {"label": "Infliximab"}}],
            },
            {
                "id": "P2:v1",
                "event_date": "2024-01-01",
                "diseases": [{"diseaseCode": {"label": "Ulcerative Colitis"}}],
                "treatments": [{"treatmentCode": {"label": "Mesalamine"}}],
            },
        ],
    )

    monkeypatch.setenv("LM_STUDIO_ENABLED", "true")
    monkeypatch.delenv("LM_STUDIO_MODEL", raising=False)

    calls = []

    def fake_http_json(url, payload=None, log_kind="generic"):
        if url.endswith("/models"):
            return {"data": [{"id": "local-model"}]}
        calls.append(log_kind)
        if log_kind == "query_semantic_plan":
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "intent": "cohort_query",
                                    "output": "patient_list",
                                    "logic": "and",
                                    "filters": [
                                        {
                                            "domain": "treatment",
                                            "operator": "contains",
                                            "value": "Infliximab",
                                            "negate": False,
                                        }
                                    ],
                                }
                            )
                        }
                    }
                ]
            }
        return {"choices": [{"message": {"content": "generic fallback"}}]}

    monkeypatch.setattr(query_module, "_http_json", fake_http_json)

    payload = answer_query(str(tmp_path), "select subjects receiving infliximab")
    assert payload["intent"] == "semantic_cohort_query"
    assert payload["data"]["execution"] == "deterministic"
    assert payload["data"]["planner"]["model"] == "local-model"
    assert payload["data"]["patient_ids"] == ["P1"]
    assert calls == ["query_semantic_plan"]


def test_query_falls_back_to_generic_lm_when_semantic_plan_is_invalid(tmp_path, monkeypatch):
    write_json(tmp_path, "records.json", [])

    monkeypatch.setenv("LM_STUDIO_ENABLED", "true")
    monkeypatch.delenv("LM_STUDIO_MODEL", raising=False)

    calls = []

    def fake_http_json(url, payload=None, log_kind="generic"):
        if url.endswith("/models"):
            return {"data": [{"id": "local-model"}]}
        calls.append(log_kind)
        if log_kind == "query_semantic_plan":
            return {"choices": [{"message": {"content": "{\"intent\":\"unsupported\"}"}}]}
        return {"choices": [{"message": {"content": "LM Studio answer"}}]}

    monkeypatch.setattr(query_module, "_http_json", fake_http_json)

    payload = answer_query(str(tmp_path), "What evidence supports the main cohort summary?")
    assert payload["intent"] == "llm_fallback"
    assert payload["reply"] == "LM Studio answer"
    assert calls == ["query_semantic_plan", "query_fallback"]


def test_query_semantic_planner_can_expand_biologics_category(tmp_path, monkeypatch):
    write_json(
        tmp_path,
        "records.json",
        [
            {
                "id": "P1:v1",
                "event_date": "2024-01-01",
                "treatments": [{"treatmentCode": {"label": "Infliximab"}}],
            },
            {
                "id": "P2:v1",
                "event_date": "2024-01-01",
                "treatments": [{"treatmentCode": {"label": "Vedolizumab"}}],
            },
            {
                "id": "P3:v1",
                "event_date": "2024-01-01",
                "treatments": [{"treatmentCode": {"label": "Mesalamine"}}],
            },
        ],
    )

    monkeypatch.setenv("LM_STUDIO_ENABLED", "true")
    monkeypatch.delenv("LM_STUDIO_MODEL", raising=False)

    captured = {}

    def fake_http_json(url, payload=None, log_kind="generic"):
        if url.endswith("/models"):
            return {"data": [{"id": "local-model"}]}
        if log_kind == "query_semantic_plan":
            captured["payload"] = payload
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "intent": "cohort_query",
                                    "output": "count",
                                    "logic": "or",
                                    "filters": [
                                        {"domain": "treatment", "operator": "eq", "value": "Infliximab", "negate": False},
                                        {"domain": "treatment", "operator": "eq", "value": "Vedolizumab", "negate": False},
                                    ],
                                }
                            )
                        }
                    }
                ]
            }
        return {"choices": [{"message": {"content": "generic fallback"}}]}

    monkeypatch.setattr(query_module, "_http_json", fake_http_json)

    payload = answer_query(str(tmp_path), "How many patients take biologics?")
    assert payload["intent"] == "semantic_cohort_query"
    assert payload["data"]["patient_count"] == 2
    assert "takes 'Infliximab' or takes 'Vedolizumab'" in payload["reply"]
    planner_message = captured["payload"]["messages"][1]["content"]
    assert "known_treatments" in planner_message
    assert "Infliximab" in planner_message
    assert "Vedolizumab" in planner_message


def test_query_planner_only_can_filter_patient_ids_by_substring(tmp_path, monkeypatch):
    write_json(
        tmp_path,
        "records.json",
        [
            {"id": "P10:visit1", "event_date": "2024-01-01"},
            {"id": "P210:visit1", "event_date": "2024-01-01"},
            {"id": "P345:visit1", "event_date": "2024-01-01"},
        ],
    )

    monkeypatch.setenv("LM_STUDIO_ENABLED", "true")
    monkeypatch.setenv("LM_STUDIO_MODEL", "local-model")

    calls = []

    def fake_http_json(url, payload=None, log_kind="generic"):
        calls.append(log_kind)
        if log_kind == "query_semantic_plan":
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "intent": "cohort_query",
                                    "output": "patient_list",
                                    "logic": "and",
                                    "filters": [
                                        {"domain": "patient_id", "operator": "contains", "value": "10", "negate": False}
                                    ],
                                }
                            )
                        }
                    }
                ]
            }
        return {"choices": [{"message": {"content": "generic fallback"}}]}

    monkeypatch.setattr(query_module, "_http_json", fake_http_json)

    payload = answer_query(
        str(tmp_path),
        "Tell me the list of patients with a 10 in the name",
        query_mode="planner_only",
    )

    assert payload["intent"] == "semantic_cohort_query"
    assert payload["data"]["patient_ids"] == ["P10", "P210"]
    assert calls == ["query_semantic_plan"]


def test_query_lists_patients_with_more_than_one_medication(tmp_path):
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
                "id": "202:week_0_arm_1",
                "treatments": [
                    {"_visit": {"id": "week_0_arm_1"}, "treatmentCode": {"label": "Infliximab"}}
                ],
            },
            {
                "id": "303:week_0_arm_1",
                "treatments": [],
            },
        ],
    )

    payload = answer_query(str(tmp_path), "Which patients take more than 1 medication?")
    assert payload["intent"] == "patient_medication_count_cohort"
    assert payload["data"]["patient_count"] == 1
    assert payload["data"]["patients"][0]["patient_id"] == "101"
    assert "more than 1 medication" in payload["reply"]


def test_query_counts_patients_with_exactly_one_medication(tmp_path):
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
                "id": "202:week_0_arm_1",
                "treatments": [
                    {"_visit": {"id": "week_0_arm_1"}, "treatmentCode": {"label": "Infliximab"}}
                ],
            },
            {
                "id": "303:week_0_arm_1",
                "treatments": [],
            },
        ],
    )

    payload = answer_query(str(tmp_path), "How many patients take exactly 1 medication?")
    assert payload["intent"] == "patient_medication_count_cohort"
    assert payload["data"]["patient_count"] == 1
    assert payload["data"]["patients"][0]["patient_id"] == "202"
    assert payload["reply"] == "1 patient has exactly 1 medication."


def test_query_lists_patients_with_no_medications(tmp_path):
    write_json(
        tmp_path,
        "individuals.json",
        [
            {
                "id": "101:week_0_arm_1",
                "treatments": [
                    {"_visit": {"id": "week_0_arm_1"}, "treatmentCode": {"label": "Infliximab"}}
                ],
            },
            {
                "id": "202:week_0_arm_1",
                "treatments": [],
            },
        ],
    )

    payload = answer_query(str(tmp_path), "Which patients have no medications?")
    assert payload["intent"] == "patient_medication_count_cohort"
    assert payload["data"]["patient_count"] == 1
    assert payload["data"]["patients"][0]["patient_id"] == "202"
    assert "no medications" in payload["reply"]


def test_query_lists_all_patients_in_cohort(tmp_path):
    write_json(
        tmp_path,
        "individuals.json",
        [
            {"id": "1:week_0_arm_1", "treatments": []},
            {"id": "1004:week_0_arm_1", "treatments": []},
            {"id": "1005:week_0_arm_1", "treatments": []},
            {"id": "101:week_0_arm_1", "treatments": []},
            {"id": "102:week_0_arm_1", "treatments": []},
            {"id": "1022:week_0_arm_1", "treatments": []},
            {"id": "1024:week_0_arm_1", "treatments": []},
            {"id": "103:week_0_arm_1", "treatments": []},
            {"id": "104:week_0_arm_1", "treatments": []},
            {"id": "105:week_0_arm_1", "treatments": []},
        ],
    )

    payload = answer_query(str(tmp_path), "tell me the list of patients on the cohort")
    assert payload["intent"] == "patient_inventory"
    assert payload["data"]["patient_count"] == 10
    assert payload["data"]["patient_ids"] == [
        "1004:week_0_arm_1",
        "1005:week_0_arm_1",
        "101:week_0_arm_1",
        "1022:week_0_arm_1",
        "1024:week_0_arm_1",
        "102:week_0_arm_1",
        "103:week_0_arm_1",
        "104:week_0_arm_1",
        "105:week_0_arm_1",
        "1:week_0_arm_1",
    ]
    assert "- 104:week_0_arm_1" in payload["reply"]
    assert "- 105:week_0_arm_1" in payload["reply"]


def test_query_supports_negative_disease_cohort(tmp_path):
    write_json(
        tmp_path,
        "individuals.json",
        [
            {
                "id": "101:week_0_arm_1",
                "diseases": [{"_visit": {"id": "week_0_arm_1"}, "diseaseCode": {"label": "Crohn Disease"}}],
            },
            {
                "id": "202:week_0_arm_1",
                "diseases": [{"_visit": {"id": "week_0_arm_1"}, "diseaseCode": {"label": "Ulcerative Colitis"}}],
            },
            {
                "id": "303:week_0_arm_1",
                "diseases": [],
            },
        ],
    )

    payload = answer_query(str(tmp_path), "How many patients don't have Crohn Disease?")
    assert payload["intent"] == "negative_disease_cohort"
    assert payload["data"]["patient_count"] == 2
    assert payload["reply"] == "2 patients do not have 'Crohn Disease'."


def test_query_supports_mixed_include_exclude_patient_filters(tmp_path):
    write_json(
        tmp_path,
        "individuals.json",
        [
            {
                "id": "101:week_0_arm_1",
                "diseases": [{"_visit": {"id": "week_0_arm_1"}, "diseaseCode": {"label": "Crohn Disease"}}],
                "treatments": [{"_visit": {"id": "week_0_arm_1"}, "treatmentCode": {"label": "Infliximab"}}],
            },
            {
                "id": "202:week_0_arm_1",
                "diseases": [{"_visit": {"id": "week_0_arm_1"}, "diseaseCode": {"label": "Ulcerative Colitis"}}],
                "treatments": [{"_visit": {"id": "week_0_arm_1"}, "treatmentCode": {"label": "Infliximab"}}],
            },
            {
                "id": "303:week_0_arm_1",
                "diseases": [{"_visit": {"id": "week_0_arm_1"}, "diseaseCode": {"label": "Ulcerative Colitis"}}],
                "treatments": [{"_visit": {"id": "week_0_arm_1"}, "treatmentCode": {"label": "Mesalamine"}}],
            },
        ],
    )

    payload = answer_query(str(tmp_path), "Which patients don't have Crohn Disease but take Infliximab?")
    assert payload["intent"] == "patient_filter_cohort"
    assert payload["data"]["patient_count"] == 1
    assert payload["data"]["patient_ids"] == ["202"]
    assert payload["data"]["patients"][0]["original_record_ids"] == ["202:week_0_arm_1"]
    assert payload["data"]["conditions"] == [
        {"mode": "exclude", "kind": "disease", "scope": "patient", "term": "Crohn Disease", "matched_patient_count": 1},
        {"mode": "include", "kind": "medication", "scope": "patient", "term": "Infliximab", "matched_patient_count": 2},
    ]


def test_query_counts_mixed_include_exclude_patient_filters(tmp_path):
    write_json(
        tmp_path,
        "individuals.json",
        [
            {
                "id": "101:week_0_arm_1",
                "diseases": [{"_visit": {"id": "week_0_arm_1"}, "diseaseCode": {"label": "Crohn Disease"}}],
                "treatments": [{"_visit": {"id": "week_0_arm_1"}, "treatmentCode": {"label": "Infliximab"}}],
            },
            {
                "id": "202:week_0_arm_1",
                "diseases": [{"_visit": {"id": "week_0_arm_1"}, "diseaseCode": {"label": "Ulcerative Colitis"}}],
                "treatments": [{"_visit": {"id": "week_0_arm_1"}, "treatmentCode": {"label": "Infliximab"}}],
            },
            {
                "id": "303:week_0_arm_1",
                "diseases": [{"_visit": {"id": "week_0_arm_1"}, "diseaseCode": {"label": "Crohn Disease"}}],
                "treatments": [{"_visit": {"id": "week_0_arm_1"}, "treatmentCode": {"label": "Mesalamine"}}],
            },
        ],
    )

    payload = answer_query(str(tmp_path), "How many patients have Ulcerative Colitis but do not take Mesalamine?")
    assert payload["intent"] == "patient_filter_cohort"
    assert payload["data"]["patient_count"] == 1
    assert payload["data"]["patient_ids"] == ["202"]
    assert payload["reply"] == "1 patient match: has 'Ulcerative Colitis' and does not take 'Mesalamine'."


def test_query_supports_temporal_compound_filters(tmp_path):
    write_json(
        tmp_path,
        "individuals.json",
        [
            {
                "id": "101:week_0_arm_1",
                "event_date": "2024-01-10",
                "diseases": [{"_visit": {"id": "week_0_arm_1"}, "diseaseCode": {"label": "Crohn Disease"}}],
                "treatments": [{"_visit": {"id": "week_0_arm_1"}, "treatmentCode": {"label": "Prednisolone"}}],
            },
            {
                "id": "101:week_14_arm_1",
                "event_date": "2024-02-20",
                "diseases": [{"_visit": {"id": "week_14_arm_1"}, "diseaseCode": {"label": "Crohn Disease"}}],
                "treatments": [{"_visit": {"id": "week_14_arm_1"}, "treatmentCode": {"label": "Prednisolone"}}],
            },
            {
                "id": "202:week_0_arm_1",
                "event_date": "2024-01-15",
                "diseases": [{"_visit": {"id": "week_0_arm_1"}, "diseaseCode": {"label": "Ulcerative Colitis"}}],
                "treatments": [{"_visit": {"id": "week_0_arm_1"}, "treatmentCode": {"label": "Prednisolone"}}],
            },
            {
                "id": "202:week_14_arm_1",
                "event_date": "2024-02-18",
                "diseases": [{"_visit": {"id": "week_14_arm_1"}, "diseaseCode": {"label": "Ulcerative Colitis"}}],
                "treatments": [{"_visit": {"id": "week_14_arm_1"}, "treatmentCode": {"label": "Prednisolone"}}],
            },
        ],
    )

    payload = answer_query(str(tmp_path), "Which patients have at least 2 timepoints with Prednisolone but do not have Crohn Disease?")
    assert payload["intent"] == "patient_filter_cohort"
    assert payload["data"]["patient_count"] == 1
    assert payload["data"]["patient_ids"] == ["202"]
    assert payload["data"]["patients"][0]["original_record_ids"] == ["202:week_0_arm_1", "202:week_14_arm_1"]
    assert payload["data"]["conditions"] == [
        {
            "mode": "include",
            "kind": "medication",
            "scope": "timepoint",
            "term": "Prednisolone",
            "operator": "gte",
            "target": 2,
            "matched_patient_count": 2,
            "raw_term_patient_count": 2,
        },
        {
            "mode": "exclude",
            "kind": "disease",
            "scope": "patient",
            "term": "Crohn Disease",
            "matched_patient_count": 1,
        },
    ]


def test_query_counts_temporal_compound_filters(tmp_path):
    write_json(
        tmp_path,
        "individuals.json",
        [
            {
                "id": "101:week_0_arm_1",
                "diseases": [{"_visit": {"id": "week_0_arm_1"}, "diseaseCode": {"label": "Crohn Disease"}}],
                "treatments": [{"_visit": {"id": "week_0_arm_1"}, "treatmentCode": {"label": "Prednisolone"}}],
            },
            {
                "id": "101:week_14_arm_1",
                "diseases": [{"_visit": {"id": "week_14_arm_1"}, "diseaseCode": {"label": "Crohn Disease"}}],
                "treatments": [{"_visit": {"id": "week_14_arm_1"}, "treatmentCode": {"label": "Prednisolone"}}],
            },
            {
                "id": "202:week_0_arm_1",
                "diseases": [{"_visit": {"id": "week_0_arm_1"}, "diseaseCode": {"label": "Ulcerative Colitis"}}],
                "treatments": [{"_visit": {"id": "week_0_arm_1"}, "treatmentCode": {"label": "Prednisolone"}}],
            },
            {
                "id": "202:week_14_arm_1",
                "diseases": [{"_visit": {"id": "week_14_arm_1"}, "diseaseCode": {"label": "Ulcerative Colitis"}}],
                "treatments": [{"_visit": {"id": "week_14_arm_1"}, "treatmentCode": {"label": "Prednisolone"}}],
            },
            {
                "id": "303:week_0_arm_1",
                "diseases": [{"_visit": {"id": "week_0_arm_1"}, "diseaseCode": {"label": "Ulcerative Colitis"}}],
                "treatments": [{"_visit": {"id": "week_0_arm_1"}, "treatmentCode": {"label": "Prednisolone"}}],
            },
        ],
    )

    payload = answer_query(str(tmp_path), "How many patients have at least 2 timepoints with Prednisolone and have Ulcerative Colitis?")
    assert payload["intent"] == "patient_filter_cohort"
    assert payload["data"]["patient_count"] == 1
    assert payload["data"]["patient_ids"] == ["202"]
    assert payload["reply"] == "1 patient match: has at least 2 timepoints with 'Prednisolone' and has 'Ulcerative Colitis'."


def test_query_supports_before_temporal_order_filters(tmp_path):
    write_json(
        tmp_path,
        "individuals.json",
        [
            {
                "id": "101:week_0_arm_1",
                "event_date": "2024-01-10",
                "treatments": [{"_visit": {"id": "week_0_arm_1"}, "treatmentCode": {"label": "Prednisolone"}}],
            },
            {
                "id": "101:week_14_arm_1",
                "event_date": "2024-02-20",
                "diseases": [{"_visit": {"id": "week_14_arm_1"}, "diseaseCode": {"label": "Crohn Disease"}}],
            },
            {
                "id": "202:week_0_arm_1",
                "event_date": "2024-01-15",
                "diseases": [{"_visit": {"id": "week_0_arm_1"}, "diseaseCode": {"label": "Crohn Disease"}}],
            },
            {
                "id": "202:week_14_arm_1",
                "event_date": "2024-02-18",
                "treatments": [{"_visit": {"id": "week_14_arm_1"}, "treatmentCode": {"label": "Prednisolone"}}],
            },
        ],
    )

    payload = answer_query(str(tmp_path), "Which patients had Prednisolone before Crohn Disease?")
    assert payload["intent"] == "patient_temporal_order_cohort"
    assert payload["data"]["patient_count"] == 1
    assert payload["data"]["patient_ids"] == ["101"]
    assert payload["reply"] == "Patients who had 'Prednisolone' before 'Crohn Disease': 101."


def test_query_supports_after_temporal_order_filters(tmp_path):
    write_json(
        tmp_path,
        "individuals.json",
        [
            {
                "id": "101:week_0_arm_1",
                "event_date": "2024-01-10",
                "diseases": [{"_visit": {"id": "week_0_arm_1"}, "diseaseCode": {"label": "Crohn Disease"}}],
            },
            {
                "id": "101:week_14_arm_1",
                "event_date": "2024-02-20",
                "treatments": [{"_visit": {"id": "week_14_arm_1"}, "treatmentCode": {"label": "Infliximab"}}],
            },
            {
                "id": "202:week_0_arm_1",
                "event_date": "2024-01-15",
                "treatments": [{"_visit": {"id": "week_0_arm_1"}, "treatmentCode": {"label": "Infliximab"}}],
            },
            {
                "id": "202:week_14_arm_1",
                "event_date": "2024-02-18",
                "diseases": [{"_visit": {"id": "week_14_arm_1"}, "diseaseCode": {"label": "Crohn Disease"}}],
            },
        ],
    )

    payload = answer_query(str(tmp_path), "How many patients had Infliximab after Crohn Disease?")
    assert payload["intent"] == "patient_temporal_order_cohort"
    assert payload["data"]["patient_count"] == 1
    assert payload["data"]["patient_ids"] == ["101"]
    assert payload["reply"] == "1 patient had 'Infliximab' after 'Crohn Disease'."


def test_query_supports_transition_filters(tmp_path):
    write_json(
        tmp_path,
        "individuals.json",
        [
            {
                "id": "101:week_0_arm_1",
                "event_date": "2024-01-10",
                "diseases": [{"_visit": {"id": "week_0_arm_1"}, "diseaseCode": {"label": "Ulcerative Colitis"}}],
            },
            {
                "id": "101:week_14_arm_1",
                "event_date": "2024-02-20",
                "diseases": [{"_visit": {"id": "week_14_arm_1"}, "diseaseCode": {"label": "Crohn Disease"}}],
            },
            {
                "id": "202:week_0_arm_1",
                "event_date": "2024-01-15",
                "diseases": [{"_visit": {"id": "week_0_arm_1"}, "diseaseCode": {"label": "Crohn Disease"}}],
            },
            {
                "id": "202:week_14_arm_1",
                "event_date": "2024-02-18",
                "diseases": [{"_visit": {"id": "week_14_arm_1"}, "diseaseCode": {"label": "Crohn Disease"}}],
            },
        ],
    )

    payload = answer_query(str(tmp_path), "Which patients changed from Ulcerative Colitis to Crohn Disease?")
    assert payload["intent"] == "patient_transition_cohort"
    assert payload["data"]["patient_count"] == 1
    assert payload["data"]["patient_ids"] == ["101"]
    assert payload["reply"] == "Patients who changed from 'Ulcerative Colitis' to 'Crohn Disease': 101."


def test_query_supports_started_after_filters(tmp_path):
    write_json(
        tmp_path,
        "individuals.json",
        [
            {
                "id": "101:week_0_arm_1",
                "event_date": "2024-01-10",
                "diseases": [{"_visit": {"id": "week_0_arm_1"}, "diseaseCode": {"label": "Crohn Disease"}}],
            },
            {
                "id": "101:week_14_arm_1",
                "event_date": "2024-02-20",
                "treatments": [{"_visit": {"id": "week_14_arm_1"}, "treatmentCode": {"label": "Infliximab"}}],
            },
            {
                "id": "202:week_0_arm_1",
                "event_date": "2024-01-15",
                "treatments": [{"_visit": {"id": "week_0_arm_1"}, "treatmentCode": {"label": "Infliximab"}}],
            },
            {
                "id": "202:week_14_arm_1",
                "event_date": "2024-02-18",
                "diseases": [{"_visit": {"id": "week_14_arm_1"}, "diseaseCode": {"label": "Crohn Disease"}}],
            },
        ],
    )

    payload = answer_query(str(tmp_path), "How many patients started Infliximab after Crohn Disease?")
    assert payload["intent"] == "patient_started_after_cohort"
    assert payload["data"]["patient_count"] == 1
    assert payload["data"]["patient_ids"] == ["101"]
    assert payload["reply"] == "1 patient started 'Infliximab' after 'Crohn Disease'."


def test_duckdb_query_store_indexes_multiple_files(tmp_path):
    if not duckdb_available():
        return

    write_json(
        tmp_path,
        "individuals.json",
        [
            {
                "id": "Beacon_1",
                "diseases": [{"diseaseCode": {"label": "Crohn Disease"}}],
                "treatments": [{"treatmentCode": {"label": "Infliximab"}}],
            },
            {
                "id": "Beacon_2",
                "diseases": [{"diseaseCode": {"label": "Ulcerative Colitis"}}],
                "treatments": [{"treatmentCode": {"label": "Mesalamine"}}],
            },
        ],
    )
    write_json(
        tmp_path,
        "omop-cdm.json",
        [
            {
                "id": "101:week_0",
                "treatments": [{"_visit": {"id": "week_0"}, "treatmentCode": {"label": "Infliximab"}}],
            }
        ],
    )

    assert store_patient_inventory(str(tmp_path)) == ["101", "Beacon_1", "Beacon_2"]
    meds = store_medication_counts(str(tmp_path))
    assert meds[0]["medication"] == "Infliximab"
    assert meds[0]["patient_count"] == 2
    assert meds[0]["patients"] == ["101", "Beacon_1"]


def test_answer_query_supports_longitudinal_timepoint_queries(tmp_path):
    write_json(
        tmp_path,
        "individuals.json",
        [
            {
                "id": "101:week_0_arm_1",
                "event_date": "2024-01-10",
                "treatments": [
                    {"_visit": {"id": "week_0_arm_1"}, "treatmentCode": {"label": "Prednisolone"}}
                ],
                "diseases": [
                    {"_visit": {"id": "week_0_arm_1"}, "diseaseCode": {"label": "Crohn Disease"}}
                ],
            },
            {
                "id": "101:week_14_arm_1",
                "event_date": "2024-02-20",
                "treatments": [
                    {"_visit": {"id": "week_14_arm_1"}, "treatmentCode": {"label": "Prednisolone"}}
                ],
            },
            {
                "id": "202:week_0_arm_1",
                "event_date": "2024-02-05",
                "treatments": [
                    {"_visit": {"id": "week_0_arm_1"}, "treatmentCode": {"label": "Infliximab"}}
                ],
            },
        ],
    )

    payload = answer_query(str(tmp_path), "How many timepoints are in this cohort?")
    assert payload["intent"] == "timepoint_inventory"
    assert payload["data"]["timepoint_count"] == 3

    payload = answer_query(str(tmp_path), "What happened to this cohort over time?")
    assert payload["intent"] == "cohort_over_time"
    assert payload["data"]["first_event_date"] == "2024-01-10"
    assert payload["data"]["last_event_date"] == "2024-02-20"
    assert payload["data"]["periods"][0]["period"] == "2024-01"

    payload = answer_query(str(tmp_path), "Which patients have more than 1 timepoint?")
    assert payload["intent"] == "patient_visit_count_cohort"
    assert [item["patient_id"] for item in payload["data"]["patients"]] == ["101"]

    payload = answer_query(str(tmp_path), "How many timepoints mention Prednisolone?")
    assert payload["intent"] == "medication_timepoint_cohort"
    assert payload["data"]["timepoint_count"] == 2

    payload = answer_query(str(tmp_path), "Which patients have at least 2 timepoints with Prednisolone?")
    assert payload["intent"] == "term_patient_visit_count_cohort"
    assert [item["patient_id"] for item in payload["data"]["patients"]] == ["101"]

    payload = answer_query(str(tmp_path), "Show the timeline for patient 101")
    assert payload["intent"] == "patient_timeline"


def test_answer_query_supports_select_patients_that_take_medication_phrasing(tmp_path):
    write_json(
        tmp_path,
        "records.json",
        [
            {
                "id": "P1:v1",
                "event_date": "2024-01-01",
                "treatments": [{"treatmentCode": {"label": "Infliximab"}}],
            },
            {
                "id": "P2:v1",
                "event_date": "2024-01-01",
                "treatments": [{"treatmentCode": {"label": "Mesalamine"}}],
            },
        ],
    )

    payload = answer_query(str(tmp_path), "select patients that take Infliximab")
    assert payload["intent"] == "medication_cohort"
    assert payload["data"]["patient_count"] == 1
    assert payload["data"]["patients"][0]["patient_id"] == "P1"


def test_query_store_supports_longitudinal_helpers(tmp_path):
    if not duckdb_available():
        return

    write_json(
        tmp_path,
        "individuals.json",
        [
            {
                "id": "700:baseline",
                "event_date": "2024-01-01",
                "treatments": [{"_visit": {"id": "baseline"}, "treatmentCode": {"label": "Azathioprine"}}],
            },
            {
                "id": "700:month_3",
                "event_date": "2024-03-01",
                "treatments": [{"_visit": {"id": "month_3"}, "treatmentCode": {"label": "Azathioprine"}}],
            },
            {
                "id": "800:baseline",
                "event_date": "2024-03-15",
            },
        ],
    )

    summary = store_cohort_over_time_summary(str(tmp_path))
    assert summary["timepoint_count"] == 3
    assert summary["periods"][0]["period"] == "2024-01"

    cohort = store_patient_visit_count_cohort(str(tmp_path), "gt", 1)
    assert [item["patient_id"] for item in cohort["patients"]] == ["700"]


def test_query_store_ingests_molecular_count_matrices(tmp_path):
    if not duckdb_available():
        return

    write_json(
        tmp_path,
        "records.json",
        [
            {"id": "SYN001:baseline", "event_date": "2024-01-01"},
            {"id": "SYN002:baseline", "event_date": "2024-01-01"},
        ],
    )

    original_dir = query_store_module.MOLECULAR_DATA_DIR
    molecular_dir = tmp_path / "molecular"
    molecular_dir.mkdir()
    (molecular_dir / "synthetic_transcriptome_raw_counts.csv").write_text(
        "\n".join(
            [
                "gene_id;SYN001;SYN002",
                "ENSG00000111111;10;20",
                "ENSG00000122222;30;40",
            ]
        ),
        encoding="utf-8",
    )
    query_store_module.MOLECULAR_DATA_DIR = molecular_dir
    try:
        inventory = store_molecular_dataset_inventory(str(tmp_path))
    finally:
        query_store_module.MOLECULAR_DATA_DIR = original_dir

    assert len(inventory) == 1
    item = inventory[0]
    assert item["dataset_name"] == "synthetic_transcriptome_raw_counts"
    assert item["modality"] == "transcriptomics_raw_counts"
    assert item["sample_count"] == 2
    assert item["patient_count"] == 2
    assert item["gene_count"] == 2
    assert item["clinical_overlap_patient_count"] == 2
    assert item["sample_ids"] == ["SYN001", "SYN002"]
    assert item["patient_ids"] == ["SYN001", "SYN002"]
    assert len(item["top_genes"]) == 2


def test_query_store_summarizes_molecular_expression_by_scope(tmp_path):
    if not duckdb_available():
        return

    write_json(
        tmp_path,
        "records.json",
        [
            {"id": "SYN001:baseline", "event_date": "2024-01-01"},
            {"id": "SYN002:baseline", "event_date": "2024-01-01"},
            {"id": "SYN003:baseline", "event_date": "2024-01-01"},
        ],
    )

    original_dir = query_store_module.MOLECULAR_DATA_DIR
    molecular_dir = tmp_path / "molecular"
    molecular_dir.mkdir()
    (molecular_dir / "synthetic_transcriptome_raw_counts.csv").write_text(
        "\n".join(
            [
                "gene_id;SYN001;SYN002;SYN003",
                "ENSG00000111111;10;20;30",
                "ENSG00000122222;7;8;9",
            ]
        ),
        encoding="utf-8",
    )
    query_store_module.MOLECULAR_DATA_DIR = molecular_dir
    try:
        inventory = store_molecular_dataset_inventory(str(tmp_path))
        genes = store_molecular_gene_inventory(str(tmp_path), "synthetic_transcriptome_raw_counts", search="111")
        payload = store_molecular_expression_summary(
            str(tmp_path),
            "synthetic_transcriptome_raw_counts",
            "ENSG00000111111",
            selected_patient_ids="SYN001,SYN002",
            compare_selected_patient_ids="SYN003",
        )
    finally:
        query_store_module.MOLECULAR_DATA_DIR = original_dir

    assert genes == ["ENSG00000111111"]
    assert inventory[0]["clinical_overlap_patient_count"] == 3
    assert inventory[0]["mean_total_counts_per_sample"] == 28
    assert inventory[0]["mean_detected_genes_per_sample"] == 2
    assert payload["scope_a"]["sample_count"] == 2
    assert payload["scope_a"]["mean"] == 15
    assert payload["scope_b"]["sample_count"] == 1
    assert payload["scope_b"]["max"] == 30


def test_analysis_supports_deterministic_molecular_expression_prompt(tmp_path):
    write_json(
        tmp_path,
        "records.json",
        [
            {"id": "SYN001:baseline", "event_date": "2024-01-01"},
            {"id": "SYN002:baseline", "event_date": "2024-01-01"},
            {"id": "SYN003:baseline", "event_date": "2024-01-01"},
        ],
    )

    original_dir = query_store_module.MOLECULAR_DATA_DIR
    molecular_dir = tmp_path / "molecular"
    molecular_dir.mkdir()
    (molecular_dir / "synthetic_transcriptome_raw_counts.csv").write_text(
        "\n".join(
            [
                "gene_id;SYN001;SYN002;SYN003",
                "ENSG00000169429;100;120;140",
            ]
        ),
        encoding="utf-8",
    )
    query_store_module.MOLECULAR_DATA_DIR = molecular_dir
    try:
        payload = analysis_module.analysis_llm_reply(
            "Show expression of ENSG00000169429 in the current Analysis scope.",
            str(tmp_path),
            selected_patient_ids="SYN001,SYN002",
        )
    finally:
        query_store_module.MOLECULAR_DATA_DIR = original_dir

    assert payload["intent"] == "analysis_molecular_expression"
    assert payload["data"]["source"] == "deterministic"
    assert payload["data"]["context"]["mode"] == "molecular_expression"
    assert payload["data"]["context"]["datasets"][0]["scope_a"]["sample_count"] == 2
    assert "Molecular expression summary" in payload["reply"]


def test_analysis_supports_deterministic_molecular_expression_compare_prompt(tmp_path):
    write_json(
        tmp_path,
        "records.json",
        [
            {"id": "SYN001:baseline", "event_date": "2024-01-01"},
            {"id": "SYN002:baseline", "event_date": "2024-01-01"},
            {"id": "SYN003:baseline", "event_date": "2024-01-01"},
        ],
    )

    original_dir = query_store_module.MOLECULAR_DATA_DIR
    molecular_dir = tmp_path / "molecular"
    molecular_dir.mkdir()
    (molecular_dir / "synthetic_transcriptome_raw_counts.csv").write_text(
        "\n".join(
            [
                "gene_id;SYN001;SYN002;SYN003",
                "ENSG00000169429;100;120;140",
            ]
        ),
        encoding="utf-8",
    )
    query_store_module.MOLECULAR_DATA_DIR = molecular_dir
    try:
        payload = analysis_module.analysis_llm_reply(
            "Compare expression of ENSG00000169429 between Cohort A and Cohort B.",
            str(tmp_path),
            selected_patient_ids="SYN001,SYN002",
            compare_mode=True,
            compare_selected_patient_ids="SYN003",
        )
    finally:
        query_store_module.MOLECULAR_DATA_DIR = original_dir

    assert payload["intent"] == "analysis_molecular_expression"
    assert payload["data"]["context"]["compare_mode"] is True
    assert payload["data"]["context"]["datasets"][0]["scope_b"]["sample_count"] == 1
    assert "Cohort A and Cohort B" in payload["reply"]
