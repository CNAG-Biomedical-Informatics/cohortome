import json

from fastapi import HTTPException

import app.cohorts as cohorts_module
import app.query as query_module
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
    assert "Timeline for patient 101:" in payload["reply"]
    assert "week_0_arm_1" in payload["reply"]
    assert "Prednisolone" in payload["reply"]


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
