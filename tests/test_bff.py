import json
from datetime import datetime, timezone
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

import app.analysis as analysis_module
import app.analysis_catalog as analysis_catalog_module
import app.analysis_external as analysis_external_module
import app.analysis_sessions as analysis_sessions_module
import app.auth as auth_module
import app.cohorts as cohorts_module
import app.datasets as datasets_module
import app.jobs as jobs_module
import app.pheno as pheno_module
import app.query as query_module
import app.query_policy as query_policy_module
import app.query_scope as query_scope_module
import app.query_store as query_store_module
import app.routes as routes_module
import app.user_state as user_state_module
from app.bff import (
    build_patient_navigator,
    dashboard_summary,
    ensure_data_dir,
    get_patient_context,
    list_patient_summaries,
    medication_cohort,
    medication_counts,
    normalize_value,
)
from app.main import (
    app,
    get_medication_counts,
    get_patient,
    get_patient_navigator,
    get_patients,
    search_medication_cohort,
)
from fastapi.testclient import TestClient
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


def isolate_auth_store(monkeypatch, tmp_path):
    monkeypatch.setattr(auth_module, "AUTH_USERS_PATH", tmp_path / "state" / "auth" / "users.json")


def isolate_jobs_store(monkeypatch, tmp_path):
    monkeypatch.setattr(
        jobs_module,
        "user_state_dir",
        lambda user_id=None: tmp_path / "state" / "users" / user_state_module.normalize_user_id(user_id),
    )


def make_request(session=None):
    return SimpleNamespace(session=session or {})


def test_ensure_data_dir_accepts_project_root_with_clinical_subdir(tmp_path):
    clinical_dir = tmp_path / "clinical"
    clinical_dir.mkdir()
    write_json(clinical_dir, "records.json", [{"id": "P1:baseline"}])

    assert ensure_data_dir(str(tmp_path)) == clinical_dir.resolve()


def test_pheno_plan_marks_unknown_patient_token_as_blocking(tmp_path):
    clinical_dir = tmp_path / "clinical"
    clinical_dir.mkdir()
    write_json(
        clinical_dir,
        "records.json",
        [
            {"id": "SYN001:week_0", "patient_id": "SYN001"},
            {"id": "SYN002:week_0", "patient_id": "SYN002"},
        ],
    )

    payload = pheno_module.plan_pheno_ranker(
        "Find closest matches to Beacon_5 by disease",
        str(tmp_path),
    )

    assert payload["source"] == "deterministic"
    assert payload["plan"]["mode"] == "patient"
    assert payload["plan"]["patient_id"] == "Beacon_5"
    assert payload["plan"]["invalid_patient_id"] == "Beacon_5"
    assert "not present in the current Pheno-Ranker reference dataset" in " ".join(payload["reasoning"])


def test_pheno_plan_ai_provider_restricted_skips_lm_studio_and_sets_metadata(tmp_path, monkeypatch):
    clinical_dir = tmp_path / "clinical"
    clinical_dir.mkdir()
    write_json(
        clinical_dir,
        "records.json",
        [
            {"id": "SYN001:week_0", "patient_id": "SYN001"},
            {"id": "SYN002:week_0", "patient_id": "SYN002"},
        ],
    )

    monkeypatch.setenv("LM_STUDIO_ENABLED", "true")
    calls = []

    def fake_http_json(url, payload=None, log_kind="generic"):
        calls.append(log_kind)
        return {"choices": [{"message": {"content": "{}"}}]}

    monkeypatch.setattr(pheno_module, "http_json", fake_http_json)

    payload = pheno_module.plan_pheno_ranker(
        "Compare this cohort",
        str(tmp_path),
        ai_provider_access="safe_summary",
    )

    assert payload["intent"] == "pheno_plan"
    assert payload["source"] == "deterministic"
    assert payload["data"]["source"] == "deterministic"
    assert payload["data"]["execution"] == "planning"
    assert payload["data"]["ai_provider_access"] == "safe_summary"
    assert payload["data"]["ai_provider_context_granularity"] == "safe_summary"
    assert calls == []


def test_pheno_plan_uses_lm_studio_when_allowed_and_sets_planner_metadata(tmp_path, monkeypatch):
    clinical_dir = tmp_path / "clinical"
    clinical_dir.mkdir()
    write_json(
        clinical_dir,
        "records.json",
        [
            {"id": "SYN001:week_0", "patient_id": "SYN001"},
            {"id": "SYN002:week_0", "patient_id": "SYN002"},
        ],
    )

    monkeypatch.setenv("LM_STUDIO_ENABLED", "true")
    monkeypatch.setenv("LM_STUDIO_MODEL", "local-model")

    def fake_http_json(url, payload=None, log_kind="generic"):
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "action": "compare",
                                "mode": "cohort",
                                "include_terms": [],
                                "exclude_terms": [],
                                "reasoning": ["Planned by LM Studio."],
                            }
                        )
                    }
                }
            ]
        }

    monkeypatch.setattr(pheno_module, "http_json", fake_http_json)

    payload = pheno_module.plan_pheno_ranker(
        "Compare this cohort",
        str(tmp_path),
        ai_provider_access="detailed_allowed",
    )

    assert payload["intent"] == "pheno_plan"
    assert payload["source"] == "lm_studio"
    assert payload["data"]["source"] == "llm"
    assert payload["data"]["execution"] == "planning"
    assert payload["data"]["planner"]["provider"] == "lm_studio"
    assert payload["data"]["planner"]["model"] == "local-model"
    assert payload["data"]["model"] == "local-model"


def test_generate_mds_points_transforms_jaccard_similarity_to_distance(tmp_path):
    hamming_matrix_path = tmp_path / "matrix_hamming.txt"
    hamming_matrix_path.write_text(
        "\tC1_SYN001:week_0\tC2_SYN002:week_0\n"
        "C1_SYN001:week_0\t0.0\t0.8\n"
        "C2_SYN002:week_0\t0.8\t0.0\n",
        encoding="utf-8",
    )
    jaccard_matrix_path = tmp_path / "matrix_jaccard.txt"
    jaccard_matrix_path.write_text(
        "\tC1_SYN001:week_0\tC2_SYN002:week_0\n"
        "C1_SYN001:week_0\t1.0\t0.8\n"
        "C2_SYN002:week_0\t0.8\t1.0\n",
        encoding="utf-8",
    )

    hamming_payload = pheno_module.generate_mds_points(hamming_matrix_path, "hamming")
    hamming_rows = (tmp_path / "mds_points.tsv").read_text(encoding="utf-8").strip().splitlines()
    hamming_values = [row.split("\t") for row in hamming_rows[1:]]
    hamming_distance = (
        (float(hamming_values[0][2]) - float(hamming_values[1][2])) ** 2
        + (float(hamming_values[0][3]) - float(hamming_values[1][3])) ** 2
    ) ** 0.5

    jaccard_payload = pheno_module.generate_mds_points(jaccard_matrix_path, "jaccard")
    jaccard_rows = (tmp_path / "mds_points.tsv").read_text(encoding="utf-8").strip().splitlines()
    jaccard_values = [row.split("\t") for row in jaccard_rows[1:]]
    jaccard_distance = (
        (float(jaccard_values[0][2]) - float(jaccard_values[1][2])) ** 2
        + (float(jaccard_values[0][3]) - float(jaccard_values[1][3])) ** 2
    ) ** 0.5

    assert hamming_payload["returncode"] == "0"
    assert jaccard_payload["returncode"] == "0"
    assert "hamming distance" in hamming_payload["stdout"].lower()
    assert "jaccard distance" in jaccard_payload["stdout"].lower()


def test_query_follow_up_can_refine_previous_subset_by_sex(tmp_path):
    clinical_dir = tmp_path / "clinical"
    clinical_dir.mkdir()
    write_json(
        clinical_dir,
        "records.json",
        [
            {"id": "P1:baseline", "patient_id": "P1", "patient": {"sex": "female"}, "diseases": [{"diseaseCode": {"label": "Crohn Disease"}}]},
            {"id": "P2:baseline", "patient_id": "P2", "patient": {"sex": "male"}, "diseases": [{"diseaseCode": {"label": "Crohn Disease"}}]},
            {"id": "P3:baseline", "patient_id": "P3", "patient": {"sex": "male"}, "diseases": [{"diseaseCode": {"label": "Ulcerative Colitis"}}]},
        ],
    )

    payload = answer_query(
        str(tmp_path),
        "How many patients are male?",
        history=[
            {"role": "user", "content": "How many patients have Crohn Disease?"},
            {"role": "assistant", "content": "2 patients match disease query 'Crohn Disease'."},
        ],
        scoped_patient_ids=["P1", "P2"],
    )

    assert payload["intent"] == "patient_sex_cohort"
    assert payload["data"]["patient_ids"] == ["P2"]
    assert payload["data"]["patient_count"] == 1
    assert "1 patient" in payload["reply"]


def test_query_follow_up_can_refine_previous_subset_by_plural_sex_shorthand(tmp_path):
    clinical_dir = tmp_path / "clinical"
    clinical_dir.mkdir()
    write_json(
        clinical_dir,
        "records.json",
        [
            {"id": "P1:baseline", "patient_id": "P1", "patient": {"sex": "female"}, "diseases": [{"diseaseCode": {"label": "Crohn Disease"}}]},
            {"id": "P2:baseline", "patient_id": "P2", "patient": {"sex": "male"}, "diseases": [{"diseaseCode": {"label": "Crohn Disease"}}]},
            {"id": "P3:baseline", "patient_id": "P3", "patient": {"sex": "female"}, "diseases": [{"diseaseCode": {"label": "Crohn Disease"}}]},
            {"id": "P4:baseline", "patient_id": "P4", "patient": {"sex": "female"}, "diseases": [{"diseaseCode": {"label": "Ulcerative Colitis"}}]},
        ],
    )

    payload = answer_query(
        str(tmp_path),
        "How many are females?",
        history=[
            {"role": "user", "content": "How many patients have Crohn Disease?"},
            {"role": "assistant", "content": "3 patients match disease query 'Crohn Disease'."},
        ],
        scoped_patient_ids=["P1", "P2", "P3"],
    )

    assert payload["intent"] == "patient_sex_cohort"
    assert payload["data"]["patient_ids"] == ["P1", "P3"]
    assert payload["data"]["patient_count"] == 2
    assert "2 patients are female" in payload["reply"]


def test_query_full_workspace_override_ignores_memory_for_adjective_style_sex_prompt(tmp_path):
    clinical_dir = tmp_path / "clinical"
    clinical_dir.mkdir()
    write_json(
        clinical_dir,
        "records.json",
        [
            {"id": "P1:baseline", "patient_id": "P1", "patient": {"sex": "female"}, "diseases": [{"diseaseCode": {"label": "Crohn Disease"}}]},
            {"id": "P2:baseline", "patient_id": "P2", "patient": {"sex": "male"}, "diseases": [{"diseaseCode": {"label": "Crohn Disease"}}]},
            {"id": "P3:baseline", "patient_id": "P3", "patient": {"sex": "female"}, "diseases": [{"diseaseCode": {"label": "Crohn Disease"}}]},
            {"id": "P4:baseline", "patient_id": "P4", "patient": {"sex": "female"}, "diseases": [{"diseaseCode": {"label": "Ulcerative Colitis"}}]},
        ],
    )

    payload = answer_query(
        str(tmp_path),
        "How many female patients are in the full workspace?",
        history=[
            {"role": "user", "content": "How many patients have Crohn Disease?"},
            {"role": "assistant", "content": "3 patients match disease query 'Crohn Disease'."},
        ],
        scoped_patient_ids=["P1", "P2", "P3"],
    )

    assert payload["intent"] == "patient_sex_cohort"
    assert payload["data"]["patient_ids"] == ["P1", "P3", "P4"]
    assert payload["data"]["patient_count"] == 3
    assert payload["data"]["scoped_follow_up"] is False


def test_query_semantic_follow_up_respects_previous_subset_scope(tmp_path, monkeypatch):
    write_json(
        tmp_path,
        "individuals.json",
        [
            {"id": "SYN001:week_0", "patient_id": "SYN001"},
            {"id": "SYN004:week_0", "patient_id": "SYN004"},
            {"id": "SYN005:week_0", "patient_id": "SYN005"},
            {"id": "SYN014:week_0", "patient_id": "SYN014"},
            {"id": "SYN015:week_0", "patient_id": "SYN015"},
        ],
    )

    monkeypatch.setenv("LM_STUDIO_ENABLED", "true")
    monkeypatch.setenv("LM_STUDIO_MODEL", "local-model")

    def fake_http_json(url, payload, log_kind=None):
        if url.endswith("/models"):
            return {"data": [{"id": "local-model"}]}
        assert log_kind == "query_semantic_plan"
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "intent": "cohort_query",
                                "output": "patient_list",
                                "logic": "or",
                                "filters": [
                                    {"domain": "patient_id", "operator": "contains", "value": "4", "negate": False},
                                    {"domain": "patient_id", "operator": "contains", "value": "5", "negate": False},
                                ],
                            }
                        )
                    }
                }
            ]
        }

    monkeypatch.setattr(query_module, "_http_json", fake_http_json)

    payload = answer_query(
        str(tmp_path),
        "How many patients have 4 or 5 in the name",
        history=[
            {"role": "user", "content": "How many patients have Crohn Disease?"},
            {"role": "assistant", "content": "5 patients match disease query 'Crohn Disease'."},
        ],
        scoped_patient_ids=["SYN014", "SYN015", "SYN021", "SYN024", "SYN025"],
    )

    assert payload["intent"] == "semantic_cohort_query"
    assert payload["data"]["patient_ids"] == ["SYN014", "SYN015"]
    assert payload["data"]["patient_count"] == 2
    assert payload["data"]["scoped_follow_up"] is True


def test_query_scoped_disease_inventory_uses_prompt_scope(tmp_path):
    clinical_dir = tmp_path / "clinical"
    clinical_dir.mkdir()
    write_json(
        clinical_dir,
        "records.json",
        [
            {"id": "P1:baseline", "patient_id": "P1", "diseases": [{"diseaseCode": {"label": "Crohn Disease"}}]},
            {"id": "P2:baseline", "patient_id": "P2", "diseases": [{"diseaseCode": {"label": "Crohn Disease"}}]},
            {"id": "P3:baseline", "patient_id": "P3", "diseases": [{"diseaseCode": {"label": "Ulcerative Colitis"}}]},
        ],
    )

    payload = answer_query(
        str(tmp_path),
        "List diseases in this workspace",
        history=[
            {"role": "user", "content": "How many patients have Crohn Disease?"},
            {"role": "assistant", "content": "2 patients match disease query 'Crohn Disease'."},
        ],
        scoped_patient_ids=["P1", "P2"],
    )

    assert payload["intent"] == "disease_inventory"
    assert [item["disease"] for item in payload["data"]["diseases"]] == ["Crohn Disease"]


def test_query_medication_shortcut_respects_prompt_scope(tmp_path):
    clinical_dir = tmp_path / "clinical"
    clinical_dir.mkdir()
    write_json(
        clinical_dir,
        "records.json",
        [
            {"id": "P1:baseline", "patient_id": "P1", "treatments": [{"treatmentCode": {"label": "Infliximab"}}]},
            {"id": "P2:baseline", "patient_id": "P2", "treatments": [{"treatmentCode": {"label": "Infliximab"}}]},
            {"id": "P3:baseline", "patient_id": "P3", "treatments": [{"treatmentCode": {"label": "Vedolizumab"}}]},
        ],
    )

    payload = answer_query(
        str(tmp_path),
        "Find patients who take Infliximab",
        history=[
            {"role": "user", "content": "Which patients are male?"},
            {"role": "assistant", "content": "Patients who are male: P2, P3."},
        ],
        scoped_patient_ids=["P2", "P3"],
    )

    assert payload["intent"] == "medication_cohort"
    assert payload["data"]["patient_ids"] == ["P2"]
    assert payload["data"]["patient_count"] == 1


def test_query_follow_up_scopes_disease_match_to_previous_subset(tmp_path):
    clinical_dir = tmp_path / "clinical"
    clinical_dir.mkdir()
    write_json(
        clinical_dir,
        "records.json",
        [
            {"id": "P1:baseline", "patient_id": "P1", "patient": {"sex": "female"}, "diseases": [{"diseaseCode": {"label": "Crohn Disease"}}]},
            {"id": "P2:baseline", "patient_id": "P2", "patient": {"sex": "male"}, "diseases": [{"diseaseCode": {"label": "Crohn Disease"}}]},
            {"id": "P3:baseline", "patient_id": "P3", "patient": {"sex": "male"}, "diseases": [{"diseaseCode": {"label": "Crohn Disease"}}]},
        ],
    )

    payload = answer_query(
        str(tmp_path),
        "How many patients have Crohn Disease?",
        history=[
            {"role": "user", "content": "Which patients are male?"},
            {"role": "assistant", "content": "Patients who are male: P2, P3."},
        ],
        scoped_patient_ids=["P2", "P3"],
    )

    assert payload["intent"] == "disease_cohort"
    assert payload["data"]["patient_ids"] == ["P2", "P3"]
    assert payload["data"]["patient_count"] == 2


def test_deterministic_patient_inventory_prefers_patient_ids_over_sample_ids(tmp_path):
    clinical_dir = tmp_path / "clinical"
    clinical_dir.mkdir()
    write_json(
        clinical_dir,
        "records.json",
        [
            {"id": "SYN001:week_0", "patient_id": "SYN001"},
            {"id": "SYN001:week_2", "patient_id": "SYN001"},
            {"id": "SYN002:week_0", "patient_id": "SYN002"},
        ],
    )

    payload = answer_query(str(tmp_path), "Tell me the list of patients on the cohort")

    assert payload["intent"] == "patient_inventory"
    assert payload["data"]["patient_ids"] == ["SYN001", "SYN002"]
    assert "SYN001:week_0" not in payload["reply"]
    assert "SYN001:week_2" not in payload["reply"]


def test_deterministic_patient_inventory_supports_subject_individual_and_participant_synonyms(tmp_path):
    clinical_dir = tmp_path / "clinical"
    clinical_dir.mkdir()
    write_json(
        clinical_dir,
        "records.json",
        [
            {"id": "SYN001:week_0", "patient_id": "SYN001"},
            {"id": "SYN001:week_2", "patient_id": "SYN001"},
            {"id": "SYN002:week_0", "patient_id": "SYN002"},
        ],
    )

    payload_subject = answer_query(str(tmp_path), "Tell me the list of subjects on the cohort")
    payload_individual = answer_query(str(tmp_path), "Tell me the list of individuals on the cohort")
    payload_participant = answer_query(str(tmp_path), "Tell me the list of participants on the cohort")

    assert payload_subject["intent"] == "patient_inventory"
    assert payload_subject["data"]["patient_ids"] == ["SYN001", "SYN002"]
    assert payload_individual["intent"] == "patient_inventory"
    assert payload_individual["data"]["patient_ids"] == ["SYN001", "SYN002"]
    assert payload_participant["intent"] == "patient_inventory"
    assert payload_participant["data"]["patient_ids"] == ["SYN001", "SYN002"]


def test_answer_query_defaults_to_detailed_granularity_metadata(tmp_path):
    clinical_dir = tmp_path / "clinical"
    clinical_dir.mkdir()
    write_json(
        clinical_dir,
        "records.json",
        [
            {"id": "SYN001:week_0", "patient_id": "SYN001"},
            {"id": "SYN001:week_2", "patient_id": "SYN001"},
            {"id": "SYN002:week_0", "patient_id": "SYN002"},
        ],
    )

    payload = answer_query(str(tmp_path), "Tell me the list of patients on the cohort")

    assert payload["data"]["granularity_requested"] == "detailed"
    assert payload["data"]["granularity_applied"] == "detailed"
    assert payload["data"]["external_llm_allowed"] is True
    assert payload["data"]["available_actions"] == {
        "open_in_analysis": True,
        "save_cohort": True,
        "copy_patient_ids": True,
        "use_in_pheno_ranker": True,
    }


def test_answer_query_summary_granularity_disables_copy_patient_ids(tmp_path):
    clinical_dir = tmp_path / "clinical"
    clinical_dir.mkdir()
    write_json(
        clinical_dir,
        "records.json",
        [
            {"id": "SYN001:week_0", "patient_id": "SYN001"},
            {"id": "SYN001:week_2", "patient_id": "SYN001"},
            {"id": "SYN002:week_0", "patient_id": "SYN002"},
        ],
    )

    payload = answer_query(str(tmp_path), "Tell me the list of patients on the cohort", granularity_mode="summary")

    assert payload["reply"] == "This workspace contains 2 patients."
    assert payload["data"]["granularity_requested"] == "summary"
    assert payload["data"]["granularity_applied"] == "summary"
    assert payload["data"]["external_llm_allowed"] is True
    assert "patient_ids" not in payload["data"]
    assert "sample_ids" not in payload["data"]
    assert payload["action_context"] == {
        "patient_ids": [],
        "record_ids": [],
        "id_type": "",
        "analysis_prompt": "",
    }
    assert payload["data"]["available_actions"] == {
        "open_in_analysis": False,
        "save_cohort": False,
        "copy_patient_ids": False,
        "use_in_pheno_ranker": False,
    }


def test_query_post_accepts_granularity_mode_summary(tmp_path):
    clinical_dir = tmp_path / "clinical"
    clinical_dir.mkdir()
    write_json(
        clinical_dir,
        "records.json",
        [
            {"id": "SYN001:week_0", "patient_id": "SYN001"},
            {"id": "SYN002:week_0", "patient_id": "SYN002"},
        ],
    )

    client = TestClient(app)
    response = client.post(
        "/query",
        json={
            "q": "Tell me the list of patients on the cohort",
            "data_dir": str(tmp_path),
            "granularity_mode": "summary",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["granularity_requested"] == "summary"
    assert payload["data"]["granularity_applied"] == "summary"


def test_answer_query_summary_blocks_direct_patient_detail_lookup(tmp_path):
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
        ],
    )

    payload = answer_query(str(tmp_path), "Show the timeline for patient 101", granularity_mode="summary")

    assert payload["intent"] == "patient_timeline"
    assert "not available in Summary mode" in payload["reply"]
    assert "timeline" not in payload["data"]
    assert payload["action_context"] == {
        "patient_ids": [],
        "record_ids": [],
        "id_type": "",
        "analysis_prompt": "",
    }
    assert payload["data"]["available_actions"] == {
        "open_in_analysis": False,
        "save_cohort": False,
        "copy_patient_ids": False,
        "use_in_pheno_ranker": False,
    }


def test_query_can_build_explicit_patient_id_cohort_from_prompt(tmp_path):
    clinical_dir = tmp_path / "clinical"
    clinical_dir.mkdir()
    write_json(
        clinical_dir,
        "records.json",
        [
            {"id": "SYN019:week_2", "patient_id": "SYN019"},
            {"id": "SYN019:week_6", "patient_id": "SYN019"},
            {"id": "SYN020:week_2", "patient_id": "SYN020"},
            {"id": "SYN021:week_2", "patient_id": "SYN021"},
        ],
    )

    payload = answer_query(str(tmp_path), "Create a cohort with patients SYN019 and SYN020")

    assert payload["intent"] == "explicit_patient_id_cohort"
    assert payload["reply"] == "Selected patients: SYN019, SYN020."
    assert payload["data"]["patient_ids"] == ["SYN019", "SYN020"]
    assert payload["data"]["sample_ids"] == ["SYN019:week_2", "SYN019:week_6", "SYN020:week_2"]
    assert payload["data"]["available_actions"] == {
        "open_in_analysis": True,
        "save_cohort": True,
        "copy_patient_ids": True,
        "use_in_pheno_ranker": True,
    }


def test_query_can_build_explicit_patient_id_cohort_from_pasted_ids(tmp_path):
    clinical_dir = tmp_path / "clinical"
    clinical_dir.mkdir()
    write_json(
        clinical_dir,
        "records.json",
        [
            {"id": "SYN019:week_2", "patient_id": "SYN019"},
            {"id": "SYN020:week_2", "patient_id": "SYN020"},
            {"id": "SYN021:week_2", "patient_id": "SYN021"},
        ],
    )

    payload = answer_query(str(tmp_path), "patient ids: SYN019, SYN020")

    assert payload["intent"] == "explicit_patient_id_cohort"
    assert payload["data"]["patient_ids"] == ["SYN019", "SYN020"]
    assert payload["data"]["invalid_patient_ids"] == []


def test_answer_query_dataset_ceiling_downgrades_detailed_request(tmp_path):
    clinical_dir = tmp_path / "clinical"
    clinical_dir.mkdir()
    write_json(
        clinical_dir,
        "records.json",
        [
            {"id": "SYN001:week_0", "patient_id": "SYN001"},
            {"id": "SYN002:week_0", "patient_id": "SYN002"},
        ],
    )

    payload = answer_query(
        str(tmp_path),
        "Tell me the list of patients on the cohort",
        granularity_mode="detailed",
        granularity_ceiling="summary",
    )

    assert payload["reply"] == "This workspace contains 2 patients."
    assert payload["data"]["granularity_requested"] == "detailed"
    assert payload["data"]["granularity_applied"] == "summary"
    assert payload["data"]["available_actions"] == {
        "open_in_analysis": False,
        "save_cohort": False,
        "copy_patient_ids": False,
        "use_in_pheno_ranker": False,
    }
    assert payload["action_context"] == {
        "patient_ids": [],
        "record_ids": [],
        "id_type": "",
        "analysis_prompt": "",
    }


def test_deterministic_sample_inventory_returns_sample_ids(tmp_path):
    clinical_dir = tmp_path / "clinical"
    clinical_dir.mkdir()
    write_json(
        clinical_dir,
        "records.json",
        [
            {"id": "SYN001:week_0", "patient_id": "SYN001"},
            {"id": "SYN001:week_2", "patient_id": "SYN001"},
            {"id": "SYN002:week_0", "patient_id": "SYN002"},
        ],
    )

    payload = answer_query(str(tmp_path), "Tell me the list of samples on the cohort")

    assert payload["intent"] == "sample_inventory"
    assert payload["data"]["sample_ids"] == ["SYN001:week_0", "SYN001:week_2", "SYN002:week_0"]
    assert "SYN001:week_0" in payload["reply"]
    assert "SYN001:week_2" in payload["reply"]


def test_deterministic_sample_inventory_supports_biospecimen_synonyms(tmp_path):
    clinical_dir = tmp_path / "clinical"
    clinical_dir.mkdir()
    write_json(
        clinical_dir,
        "records.json",
        [
            {"id": "SYN001:week_0", "patient_id": "SYN001"},
            {"id": "SYN001:week_2", "patient_id": "SYN001"},
            {"id": "SYN002:week_0", "patient_id": "SYN002"},
        ],
    )

    payload_biosample = answer_query(str(tmp_path), "Tell me the list of biosamples on the cohort")
    payload_specimen = answer_query(str(tmp_path), "Tell me the list of specimens on the cohort")

    assert payload_biosample["intent"] == "sample_inventory"
    assert payload_biosample["data"]["sample_ids"] == ["SYN001:week_0", "SYN001:week_2", "SYN002:week_0"]
    assert payload_specimen["intent"] == "sample_inventory"
    assert payload_specimen["data"]["sample_ids"] == ["SYN001:week_0", "SYN001:week_2", "SYN002:week_0"]


def test_pheno_scope_expansion_derives_record_ids_from_patient_ids() -> None:
    records = [
        {"id": "SYN001:week_0", "patient_id": "SYN001"},
        {"id": "SYN001:week_2", "patient_id": "SYN001"},
        {"id": "SYN002:week_0", "patient_id": "SYN002"},
        {"id": "SYN003:week_0", "patient_id": "SYN003"},
    ]

    payload = pheno_module.expand_scope_ids_to_record_ids(records, ["SYN001", "SYN002:week_0", "SYN999"])

    assert payload["record_ids"] == ["SYN001:week_0", "SYN001:week_2", "SYN002:week_0"]
    assert payload["expanded_patient_ids"] == ["SYN001"]
    assert payload["invalid_ids"] == ["SYN999"]
    assert payload["expanded_record_count"] == 3


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
                "diseases": [{"diseaseCode": {"label": "Crohn Disease"}}],
                "treatments": [{"treatmentCode": {"label": "Infliximab"}}],
            },
            {
                "id": "SYN002:week_0",
                "patient_id": "SYN002",
                "diseases": [{"diseaseCode": {"label": "Ulcerative Colitis"}}],
                "treatments": [{"treatmentCode": {"label": "Vedolizumab"}}],
            },
            {
                "id": "SYN003:week_0",
                "patient_id": "SYN003",
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


def test_saved_cohorts_persist_and_filter_by_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(cohorts_module, "USER_STATE_ROOT", tmp_path / "users")
    monkeypatch.setattr(cohorts_module, "LEGACY_SAVED_COHORTS_PATH", tmp_path / "legacy-saved-cohorts.json")

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


def test_saved_cohort_delete_is_blocked_when_referenced_by_analysis_session(tmp_path, monkeypatch):
    monkeypatch.setattr(cohorts_module, "USER_STATE_ROOT", tmp_path / "users")
    monkeypatch.setattr(cohorts_module, "LEGACY_SAVED_COHORTS_PATH", tmp_path / "legacy-saved-cohorts.json")
    monkeypatch.setattr(analysis_sessions_module, "USER_STATE_ROOT", tmp_path / "users")
    monkeypatch.setattr(analysis_sessions_module, "LEGACY_ANALYSIS_SESSIONS_PATH", tmp_path / "legacy-analysis-sessions.json")

    saved = cohorts_module.save_cohort(
        name="Crohn cohort",
        data_dir="/data/a",
        sample_ids=["SYN001:week_0", "SYN002:week_0"],
        patient_ids=["SYN001", "SYN002"],
        id_type="sample",
        source_kind="query",
        source_prompt="Which patients have Crohn Disease?",
    )

    analysis_sessions_module.save_analysis_session({
        "id": "session-1",
        "title": "Crohn comparison",
        "data_dir": "/data/a",
        "scope": "",
        "saved_cohort_id_a": saved["id"],
        "compare_mode": False,
        "compare_scope": "",
        "saved_cohort_id_b": "",
        "history": [],
        "turns": [],
    })

    client = TestClient(app)
    response = client.delete(f"/saved-cohorts/{saved['id']}")

    assert response.status_code == 409
    assert "analysis session" in response.json()["detail"].lower()
    assert cohorts_module.list_saved_cohorts("/data/a")


def test_saved_cohort_marks_full_dataset_when_scope_matches_all_records(tmp_path, monkeypatch):
    clinical_dir = tmp_path / "clinical"
    clinical_dir.mkdir()
    write_json(
        clinical_dir,
        "records.json",
        [
            {"id": "SYN001:week_0", "patient_id": "SYN001"},
            {"id": "SYN001:week_2", "patient_id": "SYN001"},
            {"id": "SYN002:week_0", "patient_id": "SYN002"},
        ],
    )
    monkeypatch.setattr(cohorts_module, "USER_STATE_ROOT", tmp_path / "users")
    monkeypatch.setattr(cohorts_module, "LEGACY_SAVED_COHORTS_PATH", tmp_path / "legacy-saved-cohorts.json")

    saved = cohorts_module.save_cohort(
        name="Full dataset cohort",
        data_dir=str(tmp_path),
        sample_ids=["SYN001:week_0", "SYN001:week_2", "SYN002:week_0"],
        patient_ids=["SYN001", "SYN002"],
        id_type="sample",
        source_kind="query",
    )

    assert saved["is_full_dataset"] is True


def test_pheno_saved_full_dataset_cohort_skips_jq_subset_extraction(tmp_path, monkeypatch):
    reference_path = tmp_path / "reference.json"
    reference_path.write_text("[]", encoding="utf-8")
    fake_bin = tmp_path / "pheno-ranker"
    fake_bin.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_bin.chmod(0o755)
    job_dir = tmp_path / "runs" / "job"
    job_dir.mkdir(parents=True)

    monkeypatch.setattr(pheno_module, "PHENO_RANKER_BIN", fake_bin)
    monkeypatch.setattr(pheno_module, "pheno_ranker_job_dir", lambda: job_dir)
    monkeypatch.setattr(pheno_module, "resolve_pheno_ranker_reference_paths", lambda data_dir: [reference_path])
    monkeypatch.setattr(
        pheno_module,
        "get_saved_cohorts_by_ids",
        lambda cohort_ids, data_dir: [
            {
                "id": "cohort_full",
                "name": "Full dataset",
                "sample_ids": ["SYN001:week_0", "SYN002:week_0"],
                "patient_ids": ["SYN001", "SYN002"],
                "is_full_dataset": True,
            }
        ],
    )

    jq_calls = []

    def _unexpected_jq(*args, **kwargs):
        jq_calls.append((args, kwargs))
        raise AssertionError("jq_extract_records should not be called for a full-dataset saved cohort")

    monkeypatch.setattr(pheno_module, "jq_extract_records", _unexpected_jq)

    executed_commands = []

    def _fake_run(command, capture_output, text, check, **kwargs):
        executed_commands.append(command)
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(pheno_module.subprocess, "run", _fake_run)

    payload = pheno_module.run_pheno_ranker(
        SimpleNamespace(
            action="compare",
            mode="cohort",
            data_dir=str(tmp_path),
            patient_id="",
            selected_patient_ids="",
            selected_saved_cohort_ids=["cohort_full"],
            disease_filter="",
            include_terms=[],
            exclude_terms=[],
            similarity_metric_cohort="",
            sort_by="",
            max_out=10,
            align=False,
            render_heatmap=False,
            render_mds=False,
            render_graph=False,
        )
    )

    assert jq_calls == []
    assert executed_commands
    assert str(reference_path) in executed_commands[0]
    assert payload["pre_commands"] == []


def test_saved_cohorts_are_user_scoped(tmp_path, monkeypatch):
    monkeypatch.setattr(cohorts_module, "USER_STATE_ROOT", tmp_path / "users")
    monkeypatch.setattr(cohorts_module, "LEGACY_SAVED_COHORTS_PATH", tmp_path / "legacy-saved-cohorts.json")

    cohorts_module.save_cohort(
        name="Local cohort",
        data_dir="/data/a",
        ids=["P1"],
        id_type="patient",
        source_kind="query",
        user_id="local",
    )
    cohorts_module.save_cohort(
        name="Alice cohort",
        data_dir="/data/a",
        ids=["P2"],
        id_type="patient",
        source_kind="query",
        user_id="alice",
    )

    assert [item["name"] for item in cohorts_module.list_saved_cohorts("/data/a", user_id="local")] == ["Local cohort"]
    assert [item["name"] for item in cohorts_module.list_saved_cohorts("/data/a", user_id="alice")] == ["Alice cohort"]


def test_saved_cohorts_auto_suffix_duplicate_names(tmp_path, monkeypatch):
    monkeypatch.setattr(cohorts_module, "USER_STATE_ROOT", tmp_path / "users")
    monkeypatch.setattr(cohorts_module, "LEGACY_SAVED_COHORTS_PATH", tmp_path / "legacy-saved-cohorts.json")

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


def test_analysis_sessions_are_user_scoped(tmp_path, monkeypatch):
    monkeypatch.setattr(analysis_sessions_module, "USER_STATE_ROOT", tmp_path / "users")
    monkeypatch.setattr(
        analysis_sessions_module,
        "LEGACY_ANALYSIS_SESSIONS_PATH",
        tmp_path / "legacy-analysis-sessions.json",
    )

    analysis_sessions_module.save_analysis_session(
        {"id": "session_local", "title": "Local session", "turns": []},
        user_id="local",
    )
    analysis_sessions_module.save_analysis_session(
        {"id": "session_alice", "title": "Alice session", "turns": []},
        user_id="alice",
    )

    assert [item["title"] for item in analysis_sessions_module.list_analysis_sessions(user_id="local")] == ["Local session"]
    assert [item["title"] for item in analysis_sessions_module.list_analysis_sessions(user_id="alice")] == ["Alice session"]


def test_local_auth_login_logout_cycle(monkeypatch, tmp_path):
    isolate_auth_store(monkeypatch, tmp_path)
    monkeypatch.setenv("PN_AUTH_MODE", "local")
    monkeypatch.setenv(
        "PN_LOCAL_USERS_JSON",
        json.dumps([{"username": "alice", "password": "secret", "role": "admin", "display_name": "Alice"}]),
    )
    client = TestClient(app)

    me_before = client.get("/auth/me")
    assert me_before.status_code == 200
    assert me_before.json()["authenticated"] is False

    login = client.post("/auth/login", json={"username": "alice", "password": "secret"})
    assert login.status_code == 200
    assert login.json()["user"]["username"] == "alice"
    assert login.json()["user"]["role"] == "admin"

    me_after = client.get("/auth/me")
    assert me_after.status_code == 200
    assert me_after.json()["authenticated"] is True
    assert me_after.json()["user"]["username"] == "alice"

    logout = client.post("/auth/logout")
    assert logout.status_code == 200
    assert logout.json()["authenticated"] is False


def test_auth_enabled_protects_workspace_routes(monkeypatch, tmp_path):
    isolate_auth_store(monkeypatch, tmp_path)
    monkeypatch.setenv("PN_AUTH_MODE", "local")
    monkeypatch.setenv(
        "PN_LOCAL_USERS_JSON",
        json.dumps(
            [
                {
                    "username": "alice",
                    "password": "secret",
                    "role": "user",
                    "display_name": "Alice",
                }
            ]
        ),
    )
    client = TestClient(app)

    assert client.get("/saved-cohorts").status_code == 401
    assert client.get("/analysis-sessions").status_code == 401
    assert client.get("/patients").status_code == 401

    login = client.post("/auth/login", json={"username": "alice", "password": "secret"})
    assert login.status_code == 200

    assert client.get("/saved-cohorts").status_code == 200
    assert client.get("/analysis-sessions").status_code == 200


def test_auth_users_requires_admin(monkeypatch, tmp_path):
    isolate_auth_store(monkeypatch, tmp_path)
    monkeypatch.setenv("PN_AUTH_MODE", "local")
    monkeypatch.setenv(
        "PN_LOCAL_USERS_JSON",
        json.dumps(
            [
                {
                    "username": "admin",
                    "password": "secret",
                    "role": "admin",
                    "display_name": "Admin User",
                },
                {
                    "username": "maria",
                    "password": "demo",
                    "role": "user",
                    "display_name": "Maria",
                },
            ]
        ),
    )
    client = TestClient(app)

    assert client.get("/auth/users").status_code == 403

    login_user = client.post("/auth/login", json={"username": "maria", "password": "demo"})
    assert login_user.status_code == 200
    assert client.get("/auth/users").status_code == 403

    client.post("/auth/logout")
    login_admin = client.post("/auth/login", json={"username": "admin", "password": "secret"})
    assert login_admin.status_code == 200
    payload = client.get("/auth/users")
    assert payload.status_code == 200
    assert [item["username"] for item in payload.json()["users"]] == ["admin", "maria"]


def test_auth_admin_can_create_update_reset_and_delete_local_users(monkeypatch, tmp_path):
    isolate_auth_store(monkeypatch, tmp_path)
    monkeypatch.setenv("PN_AUTH_MODE", "local")
    monkeypatch.setenv(
        "PN_LOCAL_USERS_JSON",
        json.dumps([{"username": "admin", "password": "secret", "role": "admin", "display_name": "Admin User"}]),
    )
    client = TestClient(app)

    login_admin = client.post("/auth/login", json={"username": "admin", "password": "secret"})
    assert login_admin.status_code == 200

    created = client.post(
        "/auth/users",
        json={
            "username": "alice",
            "password": "first-secret",
            "display_name": "Alice Example",
            "role": "user",
            "groups": ["cnag", "analysts"],
            "enabled": True,
        },
    )
    assert created.status_code == 200
    assert created.json()["username"] == "alice"
    assert created.json()["groups"] == ["analysts", "cnag"]
    assert created.json()["enabled"] is True

    updated = client.patch(
        "/auth/users/alice",
        json={
            "display_name": "Alice Updated",
            "role": "admin",
            "groups": ["cnag"],
            "enabled": False,
        },
    )
    assert updated.status_code == 200
    assert updated.json()["display_name"] == "Alice Updated"
    assert updated.json()["role"] == "admin"
    assert updated.json()["groups"] == ["cnag"]
    assert updated.json()["enabled"] is False

    disabled_login = client.post("/auth/login", json={"username": "alice", "password": "first-secret"})
    assert disabled_login.status_code == 401

    reenabled = client.patch("/auth/users/alice", json={"enabled": True})
    assert reenabled.status_code == 200
    assert reenabled.json()["enabled"] is True

    reset = client.post("/auth/users/alice/password", json={"password": "second-secret"})
    assert reset.status_code == 200

    old_password_login = client.post("/auth/login", json={"username": "alice", "password": "first-secret"})
    assert old_password_login.status_code == 401
    new_password_login = client.post("/auth/login", json={"username": "alice", "password": "second-secret"})
    assert new_password_login.status_code == 200

    client.post("/auth/logout")
    client.post("/auth/login", json={"username": "admin", "password": "secret"})
    deleted = client.delete("/auth/users/alice")
    assert deleted.status_code == 200
    assert deleted.json() == {
        "deleted": True,
        "id": "alice",
        "deleted_generated_data": False,
        "deleted_job_count": 0,
    }
    listing = client.get("/auth/users")
    assert listing.status_code == 200
    assert [item["username"] for item in listing.json()["users"]] == ["admin"]


def test_auth_admin_cannot_delete_last_enabled_admin(monkeypatch, tmp_path):
    isolate_auth_store(monkeypatch, tmp_path)
    monkeypatch.setenv("PN_AUTH_MODE", "local")
    monkeypatch.setenv(
        "PN_LOCAL_USERS_JSON",
        json.dumps(
            [
                {"username": "admin", "password": "secret", "role": "admin", "display_name": "Admin User"},
                {"username": "mrueda", "password": "demo", "role": "user", "display_name": "mrueda", "groups": ["admin"]},
            ]
        ),
    )
    client = TestClient(app)

    login_admin = client.post("/auth/login", json={"username": "mrueda", "password": "demo"})
    assert login_admin.status_code == 200

    delete_response = client.delete("/auth/users/admin")
    assert delete_response.status_code == 400
    assert "last enabled admin" in delete_response.json()["detail"].lower()


def test_auth_admin_group_member_can_access_admin_endpoints(monkeypatch, tmp_path):
    isolate_auth_store(monkeypatch, tmp_path)
    monkeypatch.setenv("PN_AUTH_MODE", "local")
    monkeypatch.setenv(
        "PN_LOCAL_USERS_JSON",
        json.dumps(
            [
                {"username": "mrueda", "password": "secret", "role": "user", "display_name": "mrueda", "groups": ["admin"]},
                {"username": "alice", "password": "demo", "role": "user", "display_name": "Alice"},
            ]
        ),
    )
    client = TestClient(app)

    login = client.post("/auth/login", json={"username": "mrueda", "password": "secret"})
    assert login.status_code == 200
    payload = client.get("/auth/users")
    assert payload.status_code == 200
    assert sorted(item["username"] for item in payload.json()["users"]) == ["alice", "mrueda"]


def test_auth_admin_cannot_delete_disable_or_demote_self(monkeypatch, tmp_path):
    isolate_auth_store(monkeypatch, tmp_path)
    monkeypatch.setenv("PN_AUTH_MODE", "local")
    monkeypatch.setenv(
        "PN_LOCAL_USERS_JSON",
        json.dumps([{"username": "mrueda", "password": "secret", "role": "admin", "display_name": "mrueda"}]),
    )
    client = TestClient(app)

    login = client.post("/auth/login", json={"username": "mrueda", "password": "secret"})
    assert login.status_code == 200

    delete_response = client.delete("/auth/users/mrueda")
    assert delete_response.status_code == 400
    assert "currently signed into this session" in delete_response.json()["detail"]

    disable_response = client.patch("/auth/users/mrueda", json={"enabled": False})
    assert disable_response.status_code == 400
    assert "cannot disable" in disable_response.json()["detail"].lower()

    demote_response = client.patch("/auth/users/mrueda", json={"role": "user"})
    assert demote_response.status_code == 400
    assert "cannot remove your own admin access" in demote_response.json()["detail"].lower()


def test_dataset_registry_filters_by_user_and_persists_current_selection(tmp_path, monkeypatch):
    isolate_auth_store(monkeypatch, tmp_path)
    monkeypatch.setenv("PN_AUTH_MODE", "local")
    monkeypatch.setenv(
        "PN_LOCAL_USERS_JSON",
        json.dumps(
            [
                {"username": "admin", "password": "secret", "role": "admin", "display_name": "Admin"},
                {"username": "maria", "password": "demo", "role": "user", "display_name": "Maria"},
            ]
        ),
    )
    monkeypatch.setattr(datasets_module, "DATASET_REGISTRY_PATH", tmp_path / "state" / "datasets" / "registry.json")
    monkeypatch.setattr(user_state_module, "STATE_ROOT_DIR", tmp_path / "state")

    restricted_root = tmp_path / "restricted"
    restricted_clinical = restricted_root / "clinical"
    restricted_clinical.mkdir(parents=True)
    write_json(restricted_clinical, "records.json", [{"id": "M1:week_0", "patient_id": "M1"}])

    admin_root = tmp_path / "admin-only"
    admin_clinical = admin_root / "clinical"
    admin_clinical.mkdir(parents=True)
    write_json(admin_clinical, "records.json", [{"id": "A1:week_0", "patient_id": "A1"}])

    registry = [
        {
            "dataset_id": "default",
            "name": "Default dataset",
            "root_path": str(admin_root),
            "enabled": True,
            "visibility": "admin_only",
            "allowed_users": [],
            "created_by": "system",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        },
        {
            "dataset_id": "maria-dataset",
            "name": "Maria dataset",
            "root_path": str(restricted_root),
            "enabled": True,
            "visibility": "restricted",
            "allowed_users": ["maria"],
            "created_by": "admin",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        },
    ]
    datasets_module.DATASET_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    datasets_module.DATASET_REGISTRY_PATH.write_text(json.dumps(registry), encoding="utf-8")

    client = TestClient(app)
    login = client.post("/auth/login", json={"username": "maria", "password": "demo"})
    assert login.status_code == 200

    listed = client.get("/datasets")
    assert listed.status_code == 200
    assert [item["dataset_id"] for item in listed.json()["datasets"]] == ["maria-dataset"]
    assert listed.json()["current_dataset_id"] == "maria-dataset"

    denied = client.get("/patients?dataset_id=default")
    assert denied.status_code == 403

    selected = client.post("/datasets/select", json={"dataset_id": "maria-dataset"})
    assert selected.status_code == 200
    assert selected.json()["current_dataset_id"] == "maria-dataset"

    patients = client.get("/patients")
    assert patients.status_code == 200
    assert patients.json()[0]["patient_id"] == "M1"


def test_dataset_registry_allows_group_based_access(tmp_path, monkeypatch):
    isolate_auth_store(monkeypatch, tmp_path)
    monkeypatch.setenv("PN_AUTH_MODE", "local")
    monkeypatch.setenv(
        "PN_LOCAL_USERS_JSON",
        json.dumps(
            [
                {"username": "admin", "password": "secret", "role": "admin", "display_name": "Admin"},
                {"username": "mrueda", "password": "demo", "role": "user", "display_name": "mrueda", "groups": ["cnag"]},
                {"username": "outsider", "password": "demo", "role": "user", "display_name": "outsider", "groups": ["other"]},
            ]
        ),
    )
    monkeypatch.setattr(datasets_module, "DATASET_REGISTRY_PATH", tmp_path / "state" / "datasets" / "registry.json")
    monkeypatch.setattr(user_state_module, "STATE_ROOT_DIR", tmp_path / "state")

    shared_root = tmp_path / "shared"
    shared_clinical = shared_root / "clinical"
    shared_clinical.mkdir(parents=True)
    write_json(shared_clinical, "records.json", [{"id": "CNAG1:week_0", "patient_id": "CNAG1"}])

    registry = [
        {
            "dataset_id": "cnag-dataset",
            "name": "CNAG dataset",
            "root_path": str(shared_root),
            "enabled": True,
            "visibility": "restricted",
            "allowed_users": [],
            "allowed_groups": ["cnag"],
            "created_by": "admin",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        },
    ]
    datasets_module.DATASET_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    datasets_module.DATASET_REGISTRY_PATH.write_text(json.dumps(registry), encoding="utf-8")

    client = TestClient(app)

    login = client.post("/auth/login", json={"username": "mrueda", "password": "demo"})
    assert login.status_code == 200
    listed = client.get("/datasets")
    assert listed.status_code == 200
    assert "cnag-dataset" in [item["dataset_id"] for item in listed.json()["datasets"]]
    selected = client.post("/datasets/select", json={"dataset_id": "cnag-dataset"})
    assert selected.status_code == 200
    patients = client.get("/patients")
    assert patients.status_code == 200
    assert patients.json()[0]["patient_id"] == "CNAG1"

    client.post("/auth/logout")
    login_outsider = client.post("/auth/login", json={"username": "outsider", "password": "demo"})
    assert login_outsider.status_code == 200
    outsider_listed = client.get("/datasets")
    assert outsider_listed.status_code == 200
    assert "cnag-dataset" not in [item["dataset_id"] for item in outsider_listed.json()["datasets"]]


def test_query_route_respects_dataset_query_granularity_ceiling(tmp_path, monkeypatch):
    isolate_auth_store(monkeypatch, tmp_path)
    monkeypatch.setenv("PN_AUTH_MODE", "local")
    monkeypatch.setenv(
        "PN_LOCAL_USERS_JSON",
        json.dumps(
            [
                {"username": "admin", "password": "secret", "role": "admin", "display_name": "Admin"},
                {"username": "maria", "password": "demo", "role": "user", "display_name": "Maria"},
            ]
        ),
    )
    monkeypatch.setattr(datasets_module, "DATASET_REGISTRY_PATH", tmp_path / "state" / "datasets" / "registry.json")
    monkeypatch.setattr(user_state_module, "STATE_ROOT_DIR", tmp_path / "state")

    restricted_root = tmp_path / "restricted"
    restricted_clinical = restricted_root / "clinical"
    restricted_clinical.mkdir(parents=True)
    write_json(
        restricted_clinical,
        "records.json",
        [
            {"id": "M1:week_0", "patient_id": "M1"},
            {"id": "M2:week_0", "patient_id": "M2"},
        ],
    )

    registry = [
        {
            "dataset_id": "maria-dataset",
            "name": "Maria dataset",
            "root_path": str(restricted_root),
            "enabled": True,
            "visibility": "restricted",
            "allowed_users": ["maria"],
            "allowed_groups": [],
            "query_granularity_ceiling": "summary",
            "created_by": "admin",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        },
    ]
    datasets_module.DATASET_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    datasets_module.DATASET_REGISTRY_PATH.write_text(json.dumps(registry), encoding="utf-8")

    client = TestClient(app)
    login = client.post("/auth/login", json={"username": "maria", "password": "demo"})
    assert login.status_code == 200

    listed = client.get("/datasets")
    assert listed.status_code == 200
    listed_dataset = next(item for item in listed.json()["datasets"] if item["dataset_id"] == "maria-dataset")
    assert listed_dataset["query_granularity_ceiling"] == "summary"

    response = client.post(
        "/query",
        json={
            "q": "Tell me the list of patients on the cohort",
            "dataset_id": "maria-dataset",
            "granularity_mode": "detailed",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["granularity_requested"] == "detailed"
    assert payload["data"]["granularity_applied"] == "summary"
    assert payload["data"]["available_actions"] == {
        "open_in_analysis": False,
        "save_cohort": False,
        "copy_patient_ids": False,
        "use_in_pheno_ranker": False,
    }


def test_query_route_respects_dataset_ai_provider_access(tmp_path, monkeypatch):
    isolate_auth_store(monkeypatch, tmp_path)
    monkeypatch.setenv("PN_AUTH_MODE", "local")
    monkeypatch.setenv(
        "PN_LOCAL_USERS_JSON",
        json.dumps(
            [
                {"username": "admin", "password": "secret", "role": "admin", "display_name": "Admin"},
                {"username": "maria", "password": "demo", "role": "user", "display_name": "Maria"},
            ]
        ),
    )
    monkeypatch.setenv("LM_STUDIO_ENABLED", "true")
    monkeypatch.setattr(datasets_module, "DATASET_REGISTRY_PATH", tmp_path / "state" / "datasets" / "registry.json")
    monkeypatch.setattr(user_state_module, "STATE_ROOT_DIR", tmp_path / "state")

    restricted_root = tmp_path / "restricted"
    restricted_clinical = restricted_root / "clinical"
    restricted_clinical.mkdir(parents=True)
    write_json(
        restricted_clinical,
        "records.json",
        [
            {"id": "M1:week_0", "patient_id": "M1"},
            {"id": "M2:week_0", "patient_id": "M2"},
        ],
    )

    registry = [
        {
            "dataset_id": "maria-dataset",
            "name": "Maria dataset",
            "root_path": str(restricted_root),
            "enabled": True,
            "visibility": "restricted",
            "allowed_users": ["maria"],
            "allowed_groups": [],
            "query_granularity_ceiling": "detailed",
            "ai_provider_access": "blocked",
            "created_by": "admin",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        },
    ]
    datasets_module.DATASET_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    datasets_module.DATASET_REGISTRY_PATH.write_text(json.dumps(registry), encoding="utf-8")

    calls = []

    def fake_http_json(url, payload=None, log_kind="generic"):
        calls.append((url, log_kind))
        return {"data": [{"id": "local-model"}]}

    monkeypatch.setattr(query_module, "_http_json", fake_http_json)

    client = TestClient(app)
    login = client.post("/auth/login", json={"username": "maria", "password": "demo"})
    assert login.status_code == 200

    listed = client.get("/datasets")
    assert listed.status_code == 200
    dataset_payload = next(item for item in listed.json()["datasets"] if item["dataset_id"] == "maria-dataset")
    assert dataset_payload["ai_provider_access"] == "blocked"

    response = client.post(
        "/query",
        json={
            "q": "What evidence supports the main cohort summary?",
            "dataset_id": "maria-dataset",
            "granularity_mode": "detailed",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["intent"] == "unsupported"
    assert payload["data"]["external_llm_allowed"] is False
    assert payload["data"]["ai_provider_access"] == "blocked"
    assert calls == []


def test_restricted_dataset_clamps_ai_provider_access_to_safe_summary(tmp_path, monkeypatch):
    monkeypatch.setattr(datasets_module, "DATASET_REGISTRY_PATH", tmp_path / "state" / "datasets" / "registry.json")
    dataset_root = tmp_path / "restricted-dataset"
    (dataset_root / "clinical").mkdir(parents=True)
    write_json(dataset_root / "clinical", "records.json", [{"id": "P1:v1", "patient_id": "P1"}])

    item = datasets_module.register_dataset(
        name="Restricted dataset",
        root_path=str(dataset_root),
        visibility="restricted",
        ai_provider_access="detailed_allowed",
        created_by="admin",
    )

    assert item["visibility"] == "restricted"
    assert item["ai_provider_access"] == "safe_summary"

    stored = datasets_module.get_dataset(item["dataset_id"])
    assert stored is not None
    assert stored["ai_provider_access"] == "safe_summary"


def test_generate_mds_points_skips_oversized_matrix(tmp_path, monkeypatch):
    matrix_path = tmp_path / "matrix.txt"
    matrix_path.write_text(
        "\tA\tB\tC\n"
        "A\t0\t1\t1\n"
        "B\t1\t0\t1\n"
        "C\t1\t1\t0\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(pheno_module, "pheno_mds_max_records", lambda: 2)

    payload = pheno_module.generate_mds_points(matrix_path)

    assert payload["script"] == "mds_points"
    assert payload["returncode"] == "0"
    assert "skipped mds" in payload["stdout"].lower()
    assert not (tmp_path / "mds_points.tsv").exists()


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


def test_analysis_catalog_loader_normalizes_yaml_entries(tmp_path):
    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text(
        """
items:
  - id: clinical-summary
    name: Clinical cohort summary
    description: Summarize the active cohort.
    default_prompt: Summarize the active cohort.
    execution_mode: deterministic
    tags: [clinical, summary]
""".strip(),
        encoding="utf-8",
    )

    items = analysis_catalog_module.load_analysis_catalog(catalog_path)

    assert len(items) == 1
    assert items[0]["id"] == "clinical-summary"
    assert items[0]["category"] == "General"
    assert items[0]["execution_mode"] == "deterministic"
    assert items[0]["runner_type"] == "builtin"
    assert items[0]["runner_ref"] == "clinical-summary"
    assert items[0]["tags"] == ["clinical", "summary"]


def test_analysis_catalog_loader_keeps_external_runner_metadata(tmp_path):
    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text(
        """
items:
  - id: external-r
    name: External R
    description: Demo.
    default_prompt: Run it.
    runner_type: rscript
    runner_ref: dummy_scope_snapshot
""".strip(),
        encoding="utf-8",
    )

    items = analysis_catalog_module.load_analysis_catalog(catalog_path)

    assert items[0]["runner_type"] == "rscript"
    assert items[0]["runner_ref"] == "dummy_scope_snapshot"
    assert items[0]["execution_backend"] == "sync"


def test_analysis_catalog_loader_accepts_workflow_runner_types(tmp_path):
    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text(
        """
items:
  - id: snakemake-demo
    name: Snakemake demo
    description: Demo.
    default_prompt: Run it.
    runner_type: snakemake
    runner_ref: dummy_queue_demo
    execution_backend: job
  - id: nextflow-demo
    name: Nextflow demo
    description: Demo.
    default_prompt: Run it.
    runner_type: nextflow
    runner_ref: dummy_queue_demo
    execution_backend: job
""".strip(),
        encoding="utf-8",
    )

    items = analysis_catalog_module.load_analysis_catalog(catalog_path)

    assert items[0]["runner_type"] == "snakemake"
    assert items[0]["execution_backend"] == "job"
    assert items[1]["runner_type"] == "nextflow"
    assert items[1]["execution_backend"] == "job"


def test_analysis_catalog_nextflow_availability_accepts_env_override(tmp_path, monkeypatch):
    catalog_item = {
        "id": "nextflow-demo",
        "name": "Nextflow demo",
        "description": "Demo.",
        "default_prompt": "Run it.",
        "runner_type": "nextflow",
        "runner_ref": "dummy_queue_demo",
        "execution_backend": "job",
    }
    nextflow_path = tmp_path / "nextflow"
    nextflow_path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    nextflow_path.chmod(0o755)

    monkeypatch.setattr(analysis_catalog_module.shutil, "which", lambda name: None)
    monkeypatch.setenv("NEXTFLOW_BIN", str(nextflow_path))

    availability = analysis_catalog_module._availability_for_item(
        catalog_item,
        granularity_ceiling="detailed",
        has_molecular=True,
    )

    assert availability["available"] is True
    assert availability["unavailable_reason"] == ""


def test_analysis_stale_catalog_item_does_not_override_nonmatching_prompt(tmp_path):
    write_json(
        tmp_path,
        "records.json",
        [
            {
                "id": "P1:baseline",
                "event_date": "2025-01-10",
                "diseases": [{"diseaseCode": {"label": "Multiple Sclerosis"}}],
                "treatments": [{"treatmentCode": {"label": "Ocrelizumab"}}],
            }
        ],
    )

    payload = analysis_module.analysis_llm_reply(
        "Summarize the main clinical patterns in this workspace and tell me what stands out.",
        str(tmp_path),
        catalog_item_id="external-r-scope-snapshot",
        deterministic_only=True,
    )

    assert payload["intent"] == "analysis_deterministic"
    assert payload["data"]["source"] == "deterministic"
    assert "Deterministic Workspace Summary" in payload["reply"]


def test_analysis_catalog_payload_marks_unavailable_items_for_workspace_limits(tmp_path):
    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text(
        """
items:
  - id: detailed-only
    name: Detailed analysis
    description: Needs detailed access.
    default_prompt: Show the detailed analysis.
    requires_detailed_access: true
  - id: molecular-only
    name: Molecular analysis
    description: Needs molecular data.
    default_prompt: Show the molecular analysis.
    requires_molecular: true
""".strip(),
        encoding="utf-8",
    )
    write_json(tmp_path, "records.json", [{"id": "P1:baseline", "patient_id": "P1"}])

    payload = analysis_catalog_module.analysis_catalog_payload(
        str(tmp_path),
        granularity_ceiling="summary",
        ai_provider_access="safe_summary",
        path=catalog_path,
    )

    assert payload["workspace"]["granularity_ceiling"] == "summary"
    assert payload["workspace"]["ai_provider_access"] == "safe_summary"
    items = {item["id"]: item for item in payload["items"]}
    assert items["detailed-only"]["available"] is False
    assert "Detailed" in items["detailed-only"]["unavailable_reason"]
    assert items["molecular-only"]["available"] is False
    assert "molecular datasets" in items["molecular-only"]["unavailable_reason"]


def test_analysis_catalog_route_uses_workspace_policy(tmp_path, monkeypatch):
    captured = {}

    monkeypatch.setattr(routes_module, "require_authenticated", lambda request: None)
    monkeypatch.setattr(routes_module, "resolve_dataset_ids", lambda request, dataset_id="": ["default"])
    monkeypatch.setattr(routes_module, "resolve_dataset_dir", lambda request, dataset_id="": str(tmp_path))
    monkeypatch.setattr(routes_module, "effective_query_granularity_ceiling", lambda dataset_ids: "summary")
    monkeypatch.setattr(routes_module, "effective_ai_provider_access", lambda dataset_ids: "safe_summary")

    def fake_catalog_payload(data_dir, *, granularity_ceiling="detailed", ai_provider_access="detailed_allowed", path=None):
        captured["data_dir"] = data_dir
        captured["granularity_ceiling"] = granularity_ceiling
        captured["ai_provider_access"] = ai_provider_access
        return {"items": [], "workspace": {"granularity_ceiling": granularity_ceiling}}

    monkeypatch.setattr(routes_module, "analysis_catalog_payload", fake_catalog_payload)

    request = Request({"type": "http", "headers": []})
    payload = routes_module.get_analysis_catalog(request, dataset_id="default")

    assert captured == {
        "data_dir": str(tmp_path),
        "granularity_ceiling": "summary",
        "ai_provider_access": "safe_summary",
    }
    assert payload["workspace"]["granularity_ceiling"] == "summary"


def test_analysis_external_rscript_runner_executes_curated_catalog_item(tmp_path):
    if shutil.which("Rscript") is None:
        pytest.skip("Rscript is not available")

    write_json(
        tmp_path,
        "records.json",
        [
            {"id": "P1:baseline", "patient_id": "P1"},
            {"id": "P1:week4", "patient_id": "P1"},
            {"id": "P2:baseline", "patient_id": "P2"},
        ],
    )

    payload = analysis_module.analysis_llm_reply(
        "Run the external R cohort snapshot analysis for the current Analysis scope.",
        str(tmp_path),
        catalog_item_id="external-r-scope-snapshot",
        selected_patient_ids="P1",
    )

    assert payload["intent"] == "analysis_external_rscript"
    assert "External R scope snapshot" in payload["reply"]
    assert payload["data"]["execution"] == "external_runner"
    assert payload["data"]["runner_type"] == "rscript"
    assert payload["data"]["catalog_item_id"] == "external-r-scope-snapshot"
    assert payload["data"]["context"]["mode"] == "external_rscript"
    assert payload["data"]["context"]["scope_a_patient_count"] == 1


def test_analysis_external_rscript_clinical_profile_runner_executes(tmp_path):
    if shutil.which("Rscript") is None:
        pytest.skip("Rscript is not available")

    write_json(
        tmp_path,
        "records.json",
        [
            {
                "id": "P1:baseline",
                "event_date": "2025-01-10",
                "diseases": [{"diseaseCode": {"label": "Multiple Sclerosis"}}],
                "treatments": [{"treatmentCode": {"label": "Ocrelizumab"}}],
            },
            {
                "id": "P1:week4",
                "event_date": "2025-01-24",
                "diseases": [{"diseaseCode": {"label": "Multiple Sclerosis"}}],
                "treatments": [{"treatmentCode": {"label": "Ocrelizumab"}}],
            },
            {
                "id": "P2:baseline",
                "event_date": "2025-02-01",
                "diseases": [{"diseaseCode": {"label": "Healthy Control"}}],
                "treatments": [{"treatmentCode": {"label": "Mesalamine"}}],
            },
        ],
    )

    payload = analysis_external_module.run_rscript_analysis(
        "clinical_scope_profile",
        prompt="Run the external R clinical scope profile for the current Analysis scope.",
        data_dir=str(tmp_path),
        selected_patient_ids="P1",
    )

    assert payload["intent"] == "analysis_external_rscript"
    assert "External R clinical scope profile" in payload["reply"]
    assert "Cohort A top disease: Multiple Sclerosis" in payload["reply"]
    assert payload["data"]["execution"] == "external_runner"
    assert payload["data"]["runner_type"] == "rscript"
    assert payload["data"]["runner_ref"] == "clinical_scope_profile"
    assert payload["data"]["context"]["mode"] == "external_rscript_profile"
    assert payload["data"]["context"]["cohort_a_top_disease"] == "Multiple Sclerosis"
    assert payload["data"]["context"]["cohort_a_top_medication"] == "Ocrelizumab"
    assert payload["data"]["context"]["cohort_a_patient_count"] == 1


def test_analysis_external_rscript_molecular_differential_expression_runner_executes(tmp_path):
    if shutil.which("Rscript") is None or not duckdb_available():
        pytest.skip("Rscript and duckdb are required")

    write_json(
        tmp_path,
        "records.json",
        [
            {"id": "SYN001:week_0", "event_date": "2024-01-01"},
            {"id": "SYN001:week_2", "event_date": "2024-01-15"},
            {"id": "SYN002:week_0", "event_date": "2024-01-01"},
            {"id": "SYN002:week_2", "event_date": "2024-01-15"},
        ],
    )

    original_dir = query_store_module.MOLECULAR_DATA_DIR
    molecular_dir = tmp_path / "molecular"
    molecular_dir.mkdir()
    (molecular_dir / "synthetic_transcriptome_raw_counts.csv").write_text(
        "\n".join(
            [
                "gene_id;SYN001:week_0;SYN001:week_2;SYN002:week_0;SYN002:week_2",
                "ENSG00000111111;100;120;5;7",
                "ENSG00000122222;6;8;90;110",
                "ENSG00000133333;40;42;38;39",
            ]
        ),
        encoding="utf-8",
    )
    query_store_module.MOLECULAR_DATA_DIR = molecular_dir
    try:
        job_dir = tmp_path / "job-output"
        payload = analysis_external_module.run_rscript_analysis(
            "molecular_differential_expression",
            prompt="Run differential expression between Cohort A and Cohort B for the current molecular workspace.",
            data_dir=str(tmp_path),
            molecular_dataset_name="synthetic_transcriptome_raw_counts",
            selected_patient_ids="SYN001",
            compare_selected_patient_ids="SYN002",
            job_dir=job_dir,
            timeout_seconds=60,
        )
    finally:
        query_store_module.MOLECULAR_DATA_DIR = original_dir

    assert payload["intent"] == "analysis_external_rscript"
    assert "External R differential expression" in payload["reply"]
    assert payload["data"]["execution"] == "external_runner"
    assert payload["data"]["runner_type"] == "rscript"
    assert payload["data"]["runner_ref"] == "molecular_differential_expression"
    assert payload["data"]["context"]["mode"] == "external_rscript_molecular_differential_expression"
    assert payload["data"]["context"]["dataset_name"] == "synthetic_transcriptome_raw_counts"
    assert payload["data"]["context"]["cohort_a_sample_count"] == 2
    assert payload["data"]["context"]["cohort_b_sample_count"] == 2
    assert payload["data"]["context"]["gene_count"] == 3
    assert (job_dir / "manifest.yaml").exists()
    assert (job_dir / "sample_table.tsv").exists()
    assert (job_dir / "counts_matrix.tsv").exists()
    assert (job_dir / "de_results.tsv").exists()
    assert (job_dir / "volcano_points.tsv").exists()
    assert (job_dir / "summary.json").exists()
    assert (job_dir / "volcano_plot.png").exists()


def test_analysis_external_rscript_molecular_differential_expression_runner_accepts_sample_scopes(tmp_path):
    if shutil.which("Rscript") is None or not duckdb_available():
        pytest.skip("Rscript and duckdb are required")

    write_json(
        tmp_path,
        "records.json",
        [
            {"id": "SYN001:week_0", "event_date": "2024-01-01"},
            {"id": "SYN001:week_2", "event_date": "2024-01-15"},
            {"id": "SYN002:week_0", "event_date": "2024-01-01"},
            {"id": "SYN002:week_2", "event_date": "2024-01-15"},
        ],
    )

    original_dir = query_store_module.MOLECULAR_DATA_DIR
    molecular_dir = tmp_path / "molecular"
    molecular_dir.mkdir()
    (molecular_dir / "synthetic_transcriptome_raw_counts.csv").write_text(
        "\n".join(
            [
                "gene_id;SYN001:week_0;SYN001:week_2;SYN002:week_0;SYN002:week_2",
                "ENSG00000111111;100;120;5;7",
                "ENSG00000122222;6;8;90;110",
                "ENSG00000133333;40;42;38;39",
            ]
        ),
        encoding="utf-8",
    )
    query_store_module.MOLECULAR_DATA_DIR = molecular_dir
    try:
        job_dir = tmp_path / "job-output-sample-scope"
        payload = analysis_external_module.run_rscript_analysis(
            "molecular_differential_expression",
            prompt="Run differential expression between Cohort A and Cohort B for the current molecular workspace.",
            data_dir=str(tmp_path),
            molecular_dataset_name="synthetic_transcriptome_raw_counts",
            selected_patient_ids="SYN001:week_0,SYN001:week_2",
            compare_selected_patient_ids="SYN002:week_0,SYN002:week_2",
            job_dir=job_dir,
            timeout_seconds=60,
        )
    finally:
        query_store_module.MOLECULAR_DATA_DIR = original_dir

    assert payload["intent"] == "analysis_external_rscript"
    assert payload["data"]["context"]["dataset_name"] == "synthetic_transcriptome_raw_counts"
    assert payload["data"]["context"]["cohort_a_sample_count"] == 2
    assert payload["data"]["context"]["cohort_b_sample_count"] == 2
    sample_table = (job_dir / "sample_table.tsv").read_text(encoding="utf-8")
    assert "SYN001:week_0\tSYN001\tA" in sample_table
    assert "SYN001:week_2\tSYN001\tA" in sample_table
    assert "SYN002:week_0\tSYN002\tB" in sample_table
    assert "SYN002:week_2\tSYN002\tB" in sample_table


def test_analysis_external_rscript_molecular_deseq2_runner_executes(tmp_path, monkeypatch):
    write_json(
        tmp_path,
        "records.json",
        [
            {"id": "SYN001:baseline", "event_date": "2024-01-01"},
            {"id": "SYN002:baseline", "event_date": "2024-01-01"},
            {"id": "SYN003:baseline", "event_date": "2024-01-01"},
            {"id": "SYN004:baseline", "event_date": "2024-01-01"},
        ],
    )

    original_dir = query_store_module.MOLECULAR_DATA_DIR
    molecular_dir = tmp_path / "molecular"
    molecular_dir.mkdir()
    (molecular_dir / "synthetic_transcriptome_raw_counts.csv").write_text(
        "\n".join(
            [
                "gene_id;SYN001:baseline;SYN002:baseline;SYN003:baseline;SYN004:baseline",
                "ENSG00000111111;120;118;5;7",
                "ENSG00000122222;9;11;96;101",
                "ENSG00000133333;40;42;38;39",
            ]
        ),
        encoding="utf-8",
    )
    query_store_module.MOLECULAR_DATA_DIR = molecular_dir
    monkeypatch.setattr(
        analysis_external_module.shutil,
        "which",
        lambda name: "/usr/bin/Rscript" if name == "Rscript" else None,
    )

    def fake_run(command, **kwargs):
        results_path = Path(command[command.index("--results-table") + 1])
        volcano_path = Path(command[command.index("--volcano-table") + 1])
        summary_path = Path(command[command.index("--summary-json") + 1])
        plot_path = Path(command[command.index("--plot-file") + 1])
        heatmap_path = Path(command[command.index("--heatmap-file") + 1])
        heatmap_table_path = Path(command[command.index("--heatmap-table") + 1])
        heatmap_clustering_path = Path(command[command.index("--heatmap-clustering") + 1])
        for path in (results_path, volcano_path, summary_path, plot_path, heatmap_path, heatmap_table_path, heatmap_clustering_path):
            path.parent.mkdir(parents=True, exist_ok=True)
        results_path.write_text("gene_id\tbase_mean\tlog2_fold_change\tadj_p_value\nGENE1\t100\t2.3\t0.001\n", encoding="utf-8")
        volcano_path.write_text("gene_id\tlog2_fold_change\tp_value\tadj_p_value\tneg_log10_p\nGENE1\t2.3\t1e-5\t0.001\t5\n", encoding="utf-8")
        summary_path.write_text('{"significant_gene_count":1,"shrinkage_method":"apeglm"}\n', encoding="utf-8")
        plot_path.write_text("png", encoding="utf-8")
        heatmap_path.write_text("png", encoding="utf-8")
        heatmap_table_path.write_text("gene_id\tSYN001:baseline\tSYN002:baseline\tSYN003:baseline\tSYN004:baseline\nGENE1\t1.2\t1.0\t-1.1\t-1.0\n", encoding="utf-8")
        heatmap_clustering_path.write_text('{"order":[1],"merge":[],"height":[],"labels":["GENE1"]}\n', encoding="utf-8")
        payload = {
            "reply": "### External R DESeq2 differential expression\n\n- Significant genes (BH < 0.05): 1",
            "context": {
                "mode": "external_rscript_molecular_deseq2_differential_expression",
                "runner": "molecular_deseq2_differential_expression",
                "dataset_name": "synthetic_transcriptome_raw_counts",
                "cohort_a_sample_count": 2,
                "cohort_b_sample_count": 2,
                "tested_gene_count": 3,
                "filtered_gene_count": 3,
                "significant_gene_count": 1,
                "shrinkage_method": "apeglm",
            },
        }
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(analysis_external_module.subprocess, "run", fake_run)

    try:
        job_dir = tmp_path / "job-output-deseq2"
        payload = analysis_external_module.run_rscript_analysis(
            "molecular_deseq2_differential_expression",
            prompt="Run DESeq2 differential expression between Cohort A and Cohort B for the selected molecular dataset.",
            data_dir=str(tmp_path),
            molecular_dataset_name="synthetic_transcriptome_raw_counts",
            selected_patient_ids="SYN001,SYN002",
            compare_selected_patient_ids="SYN003,SYN004",
            job_dir=job_dir,
            timeout_seconds=60,
        )
    finally:
        query_store_module.MOLECULAR_DATA_DIR = original_dir

    assert payload["intent"] == "analysis_external_rscript"
    assert payload["data"]["runner_ref"] == "molecular_deseq2_differential_expression"
    assert payload["data"]["context"]["mode"] == "external_rscript_molecular_deseq2_differential_expression"
    assert payload["data"]["context"]["shrinkage_method"] == "apeglm"
    assert (job_dir / "de_results.tsv").exists()
    assert (job_dir / "volcano_points.tsv").exists()
    assert (job_dir / "summary.json").exists()
    assert (job_dir / "volcano_plot.png").exists()
    assert (job_dir / "top_genes_heatmap.png").exists()
    assert (job_dir / "top_genes_heatmap.tsv").exists()
    assert (job_dir / "top_genes_heatmap_clustering.json").exists()


def test_analysis_external_rscript_molecular_deseq2_runner_rejects_repeated_patient_samples(tmp_path):
    write_json(
        tmp_path,
        "records.json",
        [
            {"id": "SYN001:week_0", "event_date": "2024-01-01"},
            {"id": "SYN001:week_2", "event_date": "2024-01-15"},
            {"id": "SYN002:week_0", "event_date": "2024-01-01"},
            {"id": "SYN002:week_2", "event_date": "2024-01-15"},
            {"id": "SYN003:week_0", "event_date": "2024-01-01"},
            {"id": "SYN004:week_0", "event_date": "2024-01-01"},
        ],
    )

    original_dir = query_store_module.MOLECULAR_DATA_DIR
    molecular_dir = tmp_path / "molecular"
    molecular_dir.mkdir()
    (molecular_dir / "synthetic_transcriptome_raw_counts.csv").write_text(
        "\n".join(
            [
                "gene_id;SYN001:week_0;SYN001:week_2;SYN002:week_0;SYN002:week_2;SYN003:week_0;SYN004:week_0",
                "ENSG00000111111;100;120;90;110;5;7",
                "ENSG00000122222;6;8;7;9;90;110",
            ]
        ),
        encoding="utf-8",
    )
    query_store_module.MOLECULAR_DATA_DIR = molecular_dir
    try:
        with pytest.raises(RuntimeError, match="one sample per patient"):
            analysis_external_module.run_rscript_analysis(
                "molecular_deseq2_differential_expression",
                prompt="Run DESeq2 differential expression between Cohort A and Cohort B for the selected molecular dataset.",
                data_dir=str(tmp_path),
                molecular_dataset_name="synthetic_transcriptome_raw_counts",
                selected_patient_ids="SYN001:week_0,SYN001:week_2",
                compare_selected_patient_ids="SYN002:week_0,SYN002:week_2",
                job_dir=tmp_path / "job-output-deseq2-invalid",
                timeout_seconds=60,
            )
    finally:
        query_store_module.MOLECULAR_DATA_DIR = original_dir


def test_analysis_external_rscript_molecular_hallmark_pathway_runner_executes(tmp_path, monkeypatch):
    write_json(
        tmp_path,
        "records.json",
        [
            {"id": "SYN001:baseline", "event_date": "2024-01-01"},
            {"id": "SYN002:baseline", "event_date": "2024-01-01"},
            {"id": "SYN003:baseline", "event_date": "2024-01-01"},
            {"id": "SYN004:baseline", "event_date": "2024-01-01"},
        ],
    )

    original_dir = query_store_module.MOLECULAR_DATA_DIR
    molecular_dir = tmp_path / "molecular"
    molecular_dir.mkdir()
    (molecular_dir / "synthetic_transcriptome_raw_counts.csv").write_text(
        "\n".join(
            [
                "gene_id;SYN001:baseline;SYN002:baseline;SYN003:baseline;SYN004:baseline",
                "ENSG00000111111;120;118;5;7",
                "ENSG00000122222;9;11;96;101",
                "ENSG00000133333;40;42;38;39",
            ]
        ),
        encoding="utf-8",
    )
    query_store_module.MOLECULAR_DATA_DIR = molecular_dir
    monkeypatch.setattr(
        analysis_external_module.shutil,
        "which",
        lambda name: "/usr/bin/Rscript" if name == "Rscript" else None,
    )

    def fake_run(command, **kwargs):
        results_path = Path(command[command.index("--results-table") + 1])
        rankings_path = Path(command[command.index("--rankings-table") + 1])
        summary_path = Path(command[command.index("--summary-json") + 1])
        plot_path = Path(command[command.index("--plot-file") + 1])
        for path in (results_path, rankings_path, summary_path, plot_path):
            path.parent.mkdir(parents=True, exist_ok=True)
        results_path.write_text("pathway\tNES\tpadj\tleadingEdge\nHALLMARK_TNFA_SIGNALING_VIA_NFKB\t2.1\t0.01\tENSG1,ENSG2\n", encoding="utf-8")
        rankings_path.write_text("gene_id\tstatistic\tlog2_fold_change\tadjusted_p_value\nENSG1\t4.2\t1.8\t0.01\n", encoding="utf-8")
        summary_path.write_text('{"significant_pathway_count":1,"pathway_collection":"MSigDB Hallmark"}\n', encoding="utf-8")
        plot_path.write_text("png", encoding="utf-8")
        payload = {
            "reply": "### Hallmark pathway enrichment\n\n- Significant pathways (BH < 0.05): 1",
            "context": {
                "mode": "external_rscript_molecular_hallmark_pathway_enrichment",
                "runner": "molecular_hallmark_pathway_enrichment",
                "dataset_name": "synthetic_transcriptome_raw_counts",
                "cohort_a_sample_count": 2,
                "cohort_b_sample_count": 2,
                "ranked_gene_count": 3,
                "pathway_count": 50,
                "significant_pathway_count": 1,
                "pathway_collection": "MSigDB Hallmark",
                "top_positive_pathways": ["HALLMARK_TNFA_SIGNALING_VIA_NFKB"],
                "top_negative_pathways": [],
                "top_positive_pathway_labels": ["TNFA Signaling Via NFKB"],
                "top_negative_pathway_labels": [],
            },
        }
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(analysis_external_module.subprocess, "run", fake_run)

    try:
        job_dir = tmp_path / "job-output-pathway"
        payload = analysis_external_module.run_rscript_analysis(
            "molecular_hallmark_pathway_enrichment",
            prompt="Run Hallmark pathway enrichment between Cohort A and Cohort B for the selected molecular dataset.",
            data_dir=str(tmp_path),
            molecular_dataset_name="synthetic_transcriptome_raw_counts",
            selected_patient_ids="SYN001,SYN002",
            compare_selected_patient_ids="SYN003,SYN004",
            job_dir=job_dir,
            timeout_seconds=60,
        )
    finally:
        query_store_module.MOLECULAR_DATA_DIR = original_dir

    assert payload["intent"] == "analysis_external_rscript"
    assert payload["data"]["runner_ref"] == "molecular_hallmark_pathway_enrichment"
    assert payload["data"]["context"]["mode"] == "external_rscript_molecular_hallmark_pathway_enrichment"
    assert payload["data"]["context"]["pathway_collection"] == "MSigDB Hallmark"
    assert payload["data"]["context"]["top_positive_pathway_labels"] == ["TNFA Signaling Via NFKB"]
    assert (job_dir / "pathway_results.tsv").exists()
    assert (job_dir / "gene_rankings.tsv").exists()
    assert (job_dir / "summary.json").exists()
    assert (job_dir / "pathway_plot.png").exists()


def test_analysis_external_rscript_molecular_hallmark_pathway_runner_rejects_repeated_patient_samples(tmp_path):
    write_json(
        tmp_path,
        "records.json",
        [
            {"id": "SYN001:week_0", "event_date": "2024-01-01"},
            {"id": "SYN001:week_2", "event_date": "2024-01-15"},
            {"id": "SYN002:week_0", "event_date": "2024-01-01"},
            {"id": "SYN002:week_2", "event_date": "2024-01-15"},
            {"id": "SYN003:week_0", "event_date": "2024-01-01"},
            {"id": "SYN004:week_0", "event_date": "2024-01-01"},
        ],
    )

    original_dir = query_store_module.MOLECULAR_DATA_DIR
    molecular_dir = tmp_path / "molecular"
    molecular_dir.mkdir()
    (molecular_dir / "synthetic_transcriptome_raw_counts.csv").write_text(
        "\n".join(
            [
                "gene_id;SYN001:week_0;SYN001:week_2;SYN002:week_0;SYN002:week_2;SYN003:week_0;SYN004:week_0",
                "ENSG00000111111;100;120;90;110;5;7",
                "ENSG00000122222;6;8;7;9;90;110",
            ]
        ),
        encoding="utf-8",
    )
    query_store_module.MOLECULAR_DATA_DIR = molecular_dir
    try:
        with pytest.raises(RuntimeError, match="one sample per patient"):
            analysis_external_module.run_rscript_analysis(
                "molecular_hallmark_pathway_enrichment",
                prompt="Run Hallmark pathway enrichment between Cohort A and Cohort B for the selected molecular dataset.",
                data_dir=str(tmp_path),
                molecular_dataset_name="synthetic_transcriptome_raw_counts",
                selected_patient_ids="SYN001:week_0,SYN001:week_2",
                compare_selected_patient_ids="SYN002:week_0,SYN002:week_2",
                job_dir=tmp_path / "job-output-pathway-invalid",
                timeout_seconds=60,
            )
    finally:
        query_store_module.MOLECULAR_DATA_DIR = original_dir


def test_analysis_external_snakemake_runner_executes(tmp_path, monkeypatch):
    write_json(
        tmp_path,
        "records.json",
        [
            {"id": "P1:baseline", "patient_id": "P1"},
            {"id": "P2:baseline", "patient_id": "P2"},
        ],
    )

    monkeypatch.setattr(
        analysis_external_module.shutil,
        "which",
        lambda name: "/usr/bin/snakemake" if name == "snakemake" else None,
    )

    def fake_run(command, **kwargs):
        result_arg = next(item for item in command if str(item).startswith("result_json="))
        summary_arg = next(item for item in command if str(item).startswith("summary_txt="))
        result_path = Path(str(result_arg).split("=", 1)[1])
        summary_path = Path(str(summary_arg).split("=", 1)[1])
        result_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(
            json.dumps(
                {
                    "reply": "Snakemake dummy workflow completed for current Analysis scope.",
                    "context": {"mode": "external_snakemake_dummy", "scope_summary": "current Analysis scope"},
                }
            ),
            encoding="utf-8",
        )
        summary_path.write_text("dummy summary\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="snakemake ok\n", stderr="")

    monkeypatch.setattr(analysis_external_module.subprocess, "run", fake_run)

    job_dir = tmp_path / "snakemake-job"
    payload = analysis_external_module.run_snakemake_analysis(
        "dummy_queue_demo",
        prompt="Run the external Snakemake demo for the current Analysis scope.",
        data_dir=str(tmp_path),
        selected_patient_ids="P1",
        job_dir=job_dir,
        timeout_seconds=60,
    )

    assert payload["intent"] == "analysis_external_snakemake"
    assert "Snakemake dummy workflow completed" in payload["reply"]
    assert payload["data"]["runner_type"] == "snakemake"
    assert payload["data"]["runner_ref"] == "dummy_queue_demo"
    assert payload["data"]["context"]["mode"] == "external_snakemake_dummy"
    assert (job_dir / "command.txt").exists()
    assert (job_dir / "stdout.txt").exists()
    assert (job_dir / "stderr.txt").exists()


def test_analysis_external_nextflow_runner_executes(tmp_path, monkeypatch):
    write_json(
        tmp_path,
        "records.json",
        [
            {"id": "P1:baseline", "patient_id": "P1"},
            {"id": "P2:baseline", "patient_id": "P2"},
        ],
    )

    monkeypatch.setattr(
        analysis_external_module.shutil,
        "which",
        lambda name: "/usr/bin/nextflow" if name == "nextflow" else None,
    )
    monkeypatch.delenv("NEXTFLOW_BIN", raising=False)

    def fake_run(command, **kwargs):
        result_index = command.index("--result_json")
        summary_index = command.index("--summary_txt")
        result_path = Path(command[result_index + 1])
        summary_path = Path(command[summary_index + 1])
        result_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(
            json.dumps(
                {
                    "reply": "Nextflow dummy workflow completed for Cohort A vs Cohort B.",
                    "context": {"mode": "external_nextflow_dummy", "scope_summary": "Cohort A vs Cohort B"},
                }
            ),
            encoding="utf-8",
        )
        summary_path.write_text("dummy summary\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="nextflow ok\n", stderr="")

    monkeypatch.setattr(analysis_external_module.subprocess, "run", fake_run)

    job_dir = tmp_path / "nextflow-job"
    payload = analysis_external_module.run_nextflow_analysis(
        "dummy_queue_demo",
        prompt="Run the external Nextflow demo for the current Analysis scope.",
        data_dir=str(tmp_path),
        selected_patient_ids="P1",
        compare_selected_patient_ids="P2",
        job_dir=job_dir,
        timeout_seconds=60,
    )

    assert payload["intent"] == "analysis_external_nextflow"
    assert "Nextflow dummy workflow completed" in payload["reply"]
    assert payload["data"]["runner_type"] == "nextflow"
    assert payload["data"]["runner_ref"] == "dummy_queue_demo"
    assert payload["data"]["context"]["mode"] == "external_nextflow_dummy"
    assert (job_dir / "command.txt").read_text(encoding="utf-8").splitlines()[0].startswith("/usr/bin/nextflow ")
    assert (job_dir / "command.txt").exists()
    assert (job_dir / "stdout.txt").exists()
    assert (job_dir / "stderr.txt").exists()


def test_analysis_external_nextflow_runner_uses_env_override(tmp_path, monkeypatch):
    write_json(
        tmp_path,
        "records.json",
        [
            {"id": "P1:baseline", "patient_id": "P1"},
            {"id": "P2:baseline", "patient_id": "P2"},
        ],
    )

    nextflow_path = tmp_path / "nextflow"
    nextflow_path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    nextflow_path.chmod(0o755)

    monkeypatch.setattr(analysis_external_module.shutil, "which", lambda name: None)
    monkeypatch.setenv("NEXTFLOW_BIN", str(nextflow_path))

    def fake_run(command, **kwargs):
        result_index = command.index("--result_json")
        summary_index = command.index("--summary_txt")
        result_path = Path(command[result_index + 1])
        summary_path = Path(command[summary_index + 1])
        result_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(
            json.dumps(
                {
                    "reply": "Nextflow env override workflow completed for Cohort A vs Cohort B.",
                    "context": {"mode": "external_nextflow_dummy", "scope_summary": "Cohort A vs Cohort B"},
                }
            ),
            encoding="utf-8",
        )
        summary_path.write_text("dummy summary\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="nextflow ok\n", stderr="")

    monkeypatch.setattr(analysis_external_module.subprocess, "run", fake_run)

    job_dir = tmp_path / "nextflow-job-env"
    payload = analysis_external_module.run_nextflow_analysis(
        "dummy_queue_demo",
        prompt="Run the external Nextflow demo for the current Analysis scope.",
        data_dir=str(tmp_path),
        selected_patient_ids="P1",
        compare_selected_patient_ids="P2",
        job_dir=job_dir,
        timeout_seconds=60,
    )

    assert payload["intent"] == "analysis_external_nextflow"
    assert "env override workflow completed" in payload["reply"]
    assert (job_dir / "command.txt").read_text(encoding="utf-8").splitlines()[0].startswith(f"{nextflow_path} ")


def test_analysis_job_submission_creates_user_scoped_record_and_returns_queued_payload(tmp_path, monkeypatch):
    isolate_auth_store(monkeypatch, tmp_path)
    isolate_jobs_store(monkeypatch, tmp_path)
    monkeypatch.setattr(analysis_sessions_module, "USER_STATE_ROOT", tmp_path / "users")
    monkeypatch.setattr(
        analysis_sessions_module,
        "LEGACY_ANALYSIS_SESSIONS_PATH",
        tmp_path / "legacy-analysis-sessions.json",
    )
    monkeypatch.setenv("PN_AUTH_MODE", "local")
    monkeypatch.setenv(
        "PN_LOCAL_USERS_JSON",
        json.dumps(
            [
                {"username": "alice", "password": "secret", "role": "admin", "groups": ["admin"]},
            ]
        ),
    )
    analysis_sessions_module.save_analysis_session(
        {
            "id": "session-1",
            "title": "Scoped analysis",
            "turns": [],
            "history": [],
        },
        user_id="alice",
    )
    monkeypatch.setattr(
        analysis_module,
        "get_analysis_catalog_item",
        lambda item_id: {
            "id": "external-r-clinical-profile",
            "name": "External R clinical scope profile",
            "default_prompt": "Run the external R clinical scope profile for the current Analysis scope.",
            "runner_type": "rscript",
            "runner_ref": "clinical_scope_profile",
            "execution_backend": "job",
            "job_timeout_seconds": 1800,
        },
    )
    monkeypatch.setattr(routes_module, "resolve_dataset_ids", lambda request, dataset_id: ["default"])
    monkeypatch.setattr(routes_module, "resolve_dataset_dir", lambda request, dataset_id: str(tmp_path))
    monkeypatch.setattr(jobs_module, "jobs_enabled", lambda: True)
    monkeypatch.setattr(jobs_module, "analysis_worker_available", lambda: True)
    monkeypatch.setattr(jobs_module, "enqueue_analysis_job", lambda job_id, user_id, timeout_seconds: "rq-job-1")

    client = TestClient(app)
    login = client.post("/auth/login", json={"username": "alice", "password": "secret"})
    assert login.status_code == 200

    response = client.post(
        "/analysis",
        json={
            "prompt": "Run the external R clinical scope profile for the current Analysis scope.",
            "catalog_item_id": "external-r-clinical-profile",
            "analysis_session_id": "session-1",
            "dataset_id": "default",
            "selected_patient_ids": "P1",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["intent"] == "analysis_job"
    assert "Job " in payload["reply"]
    assert payload["data"]["execution"] == "queued"
    assert payload["data"]["job_status"] == "queued"
    assert payload["data"]["analysis_session_title"] == "Scoped analysis"
    job_id = payload["data"]["job_id"]
    assert payload["data"]["job_code"] == f"Job {job_id[:8].upper()}"
    record = jobs_module.load_job_record(job_id, "alice")
    assert record["submitted_by"] == "alice"
    assert record["analysis_session_id"] == "session-1"
    assert record["analysis_session_title"] == "Scoped analysis"
    assert record["run_number"] == 1
    assert record["catalog_item_id"] == "external-r-clinical-profile"
    assert record["status"] == "queued"


def test_analysis_job_submission_requires_live_worker(tmp_path, monkeypatch):
    isolate_auth_store(monkeypatch, tmp_path)
    isolate_jobs_store(monkeypatch, tmp_path)
    monkeypatch.setenv("PN_AUTH_MODE", "local")
    monkeypatch.setenv(
        "PN_LOCAL_USERS_JSON",
        json.dumps(
            [
                {"username": "alice", "password": "secret", "role": "admin", "groups": ["admin"]},
            ]
        ),
    )
    monkeypatch.setattr(
        analysis_module,
        "get_analysis_catalog_item",
        lambda item_id: {
            "id": "external-r-clinical-profile",
            "name": "External R clinical scope profile",
            "default_prompt": "Run the external R clinical scope profile for the current Analysis scope.",
            "runner_type": "rscript",
            "runner_ref": "clinical_scope_profile",
            "execution_backend": "job",
            "job_timeout_seconds": 1800,
        },
    )
    monkeypatch.setattr(routes_module, "resolve_dataset_ids", lambda request, dataset_id: ["default"])
    monkeypatch.setattr(routes_module, "resolve_dataset_dir", lambda request, dataset_id: str(tmp_path))
    monkeypatch.setattr(jobs_module, "jobs_enabled", lambda: True)
    monkeypatch.setattr(jobs_module, "analysis_worker_available", lambda: False)

    client = TestClient(app)
    login = client.post("/auth/login", json={"username": "alice", "password": "secret"})
    assert login.status_code == 200

    response = client.post(
        "/analysis",
        json={
            "prompt": "Run the external R clinical scope profile for the current Analysis scope.",
            "catalog_item_id": "external-r-clinical-profile",
            "analysis_session_id": "session-1",
            "dataset_id": "default",
            "selected_patient_ids": "P1",
        },
    )

    assert response.status_code == 400
    assert "no background worker is running" in response.json()["detail"].lower()
    assert jobs_module.list_job_records("alice") == []


def test_submit_pheno_job_creates_user_scoped_record_and_returns_queued_payload(tmp_path, monkeypatch):
    isolate_jobs_store(monkeypatch, tmp_path)
    monkeypatch.setattr(jobs_module, "jobs_enabled", lambda: True)
    monkeypatch.setattr(jobs_module, "analysis_worker_available", lambda: True)
    monkeypatch.setattr(jobs_module, "enqueue_pheno_job", lambda job_id, user_id, timeout_seconds: "rq-pheno-1")

    payload = jobs_module.submit_pheno_job(
        user_id="alice",
        payload={
            "name": "Pheno-Ranker cohort run",
            "prompt": "Compare the current cohort",
            "dataset_id": "default",
            "data_dir": str(tmp_path),
            "action": "compare",
            "mode": "cohort",
            "selected_patient_ids": "SYN001:week_0,SYN002:week_0",
            "selected_saved_cohort_ids": ["cohort-a"],
            "include_terms": ["fatigue"],
            "exclude_terms": ["asthma"],
            "similarity_metric_cohort": "jaccard",
            "sort_by": "distance",
            "max_out": 25,
            "align": True,
            "render_heatmap": True,
            "render_mds": True,
            "render_graph": True,
            "resolved_sample_count": 1800,
        },
    )

    assert payload["feature"] == "pheno"
    assert payload["status"] == "queued"
    assert payload["job_code"].startswith("Job ")
    record = jobs_module.load_job_record(payload["job_id"], "alice")
    assert record["submitted_by"] == "alice"
    assert record["feature"] == "pheno"
    assert record["dataset_id"] == "default"
    assert record["selected_saved_cohort_ids"] == ["cohort-a"]
    assert record["resolved_sample_count"] == 1800
    assert record["render_graph"] is True
    assert record["rq_job_id"] == "rq-pheno-1"


def test_run_pheno_ranker_route_queues_large_cohort_background_run(tmp_path, monkeypatch):
    request = make_request({"username": "alice"})
    captured = {}

    monkeypatch.setattr(routes_module, "require_authenticated", lambda req: {"username": "alice"})
    monkeypatch.setattr(routes_module, "request_user_id", lambda req: "alice")
    monkeypatch.setattr(routes_module, "resolve_dataset_ids", lambda request, dataset_id: ["default"])
    monkeypatch.setattr(routes_module, "dataset_scope_id", lambda dataset_ids: "default")
    monkeypatch.setattr(routes_module, "effective_query_granularity_ceiling", lambda dataset_ids: "detailed")
    monkeypatch.setattr(routes_module, "effective_ai_provider_access", lambda dataset_ids: "detailed_allowed")
    monkeypatch.setattr(routes_module, "resolve_dataset_dir", lambda request, dataset_id: str(tmp_path))
    monkeypatch.setattr(routes_module, "active_feature_job", lambda user_id, feature: None)
    monkeypatch.setattr(
        routes_module,
        "pheno_run_requires_background_job",
        lambda payload, user_id="": {"resolved_sample_count": 1801, "threshold": 1500, "requires_background_job": True},
    )

    def fake_submit_pheno_job(*, user_id, payload):
        captured["user_id"] = user_id
        captured["payload"] = dict(payload)
        return {"job_id": "abc123def456", "job_code": "Job ABC123DE", "status": "queued"}

    monkeypatch.setattr(routes_module, "submit_pheno_job", fake_submit_pheno_job)

    response = routes_module.run_pheno_ranker_route(
        routes_module.PhenoRankerRequest(
            prompt="Compare the current cohort",
            action="compare",
            mode="cohort",
            dataset_id="default",
            selected_saved_cohort_ids=["cohort-a"],
        ),
        request,
    )

    assert response["intent"] == "pheno_run"
    assert response["data"]["execution"] == "queued"
    assert response["data"]["feature"] == "pheno"
    assert response["job_code"] == "Job ABC123DE"
    assert response["resolved_sample_count"] == 1801
    assert captured["user_id"] == "alice"
    assert captured["payload"]["dataset_id"] == "default"
    assert captured["payload"]["selected_saved_cohort_ids"] == ["cohort-a"]
    assert captured["payload"]["resolved_sample_count"] == 1801


def test_run_pheno_ranker_route_blocks_when_background_job_active(tmp_path, monkeypatch):
    request = make_request({"username": "alice"})

    monkeypatch.setattr(routes_module, "require_authenticated", lambda req: {"username": "alice"})
    monkeypatch.setattr(routes_module, "request_user_id", lambda req: "alice")
    monkeypatch.setattr(routes_module, "resolve_dataset_ids", lambda request, dataset_id: ["default"])
    monkeypatch.setattr(routes_module, "dataset_scope_id", lambda dataset_ids: "default")
    monkeypatch.setattr(routes_module, "effective_query_granularity_ceiling", lambda dataset_ids: "detailed")
    monkeypatch.setattr(routes_module, "effective_ai_provider_access", lambda dataset_ids: "detailed_allowed")
    monkeypatch.setattr(routes_module, "resolve_dataset_dir", lambda request, dataset_id: str(tmp_path))
    monkeypatch.setattr(routes_module, "active_feature_job", lambda user_id, feature: {"job_id": "job-1234", "job_code": "Job ABC12345"})
    monkeypatch.setattr(
        routes_module,
        "pheno_run_requires_background_job",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("background cutoff should not run when a Pheno job is already active")),
    )
    monkeypatch.setattr(
        routes_module,
        "run_pheno_ranker",
        lambda payload: (_ for _ in ()).throw(AssertionError("sync Pheno execution should be blocked while a background Pheno job is active")),
    )

    with pytest.raises(HTTPException) as exc:
        routes_module.run_pheno_ranker_route(
            routes_module.PhenoRankerRequest(
                prompt="Compare the current cohort",
                action="compare",
                mode="cohort",
                dataset_id="default",
                selected_patient_ids="SYN001:week_0",
            ),
            request,
        )

    assert exc.value.status_code == 409
    assert "already in progress" in str(exc.value.detail)
    assert "Job ABC12345" in str(exc.value.detail)


def test_run_pheno_ranker_route_rejects_runs_above_hard_cap(tmp_path, monkeypatch):
    request = make_request({"username": "alice"})

    monkeypatch.setattr(routes_module, "require_authenticated", lambda req: {"username": "alice"})
    monkeypatch.setattr(routes_module, "request_user_id", lambda req: "alice")
    monkeypatch.setattr(routes_module, "resolve_dataset_ids", lambda request, dataset_id: ["default"])
    monkeypatch.setattr(routes_module, "dataset_scope_id", lambda dataset_ids: "default")
    monkeypatch.setattr(routes_module, "effective_query_granularity_ceiling", lambda dataset_ids: "detailed")
    monkeypatch.setattr(routes_module, "effective_ai_provider_access", lambda dataset_ids: "detailed_allowed")
    monkeypatch.setattr(routes_module, "resolve_dataset_dir", lambda request, dataset_id: str(tmp_path))
    monkeypatch.setattr(routes_module, "active_feature_job", lambda user_id, feature: None)
    monkeypatch.setattr(
        routes_module,
        "pheno_run_requires_background_job",
        lambda payload, user_id="": {
            "resolved_sample_count": 5158,
            "threshold": 1500,
            "hard_cap": 2500,
            "exceeds_hard_cap": True,
            "requires_background_job": True,
        },
    )
    monkeypatch.setattr(
        routes_module,
        "submit_pheno_job",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("oversized Pheno runs must not be queued")),
    )
    monkeypatch.setattr(
        routes_module,
        "run_pheno_ranker",
        lambda payload: (_ for _ in ()).throw(AssertionError("oversized Pheno runs must not run synchronously")),
    )

    with pytest.raises(HTTPException) as exc:
        routes_module.run_pheno_ranker_route(
            routes_module.PhenoRankerRequest(
                prompt="compare all",
                action="compare",
                mode="cohort",
                dataset_id="default",
            ),
            request,
        )

    assert exc.value.status_code == 400
    assert "capped at 2500" in str(exc.value.detail).lower()
    assert "5158" in str(exc.value.detail)


def test_run_pheno_job_persists_result_in_shared_job_dir(tmp_path, monkeypatch):
    isolate_jobs_store(monkeypatch, tmp_path)
    record = jobs_module.create_job_record(
        job_type="pheno",
        user_id="alice",
        data={
            "feature": "pheno",
            "name": "Pheno-Ranker cohort run",
            "prompt": "Compare the current cohort",
            "dataset_id": "default",
            "data_dir": str(tmp_path),
            "action": "compare",
            "mode": "cohort",
            "selected_patient_ids": "SYN001:week_0,SYN002:week_0",
            "selected_saved_cohort_ids": [],
            "include_terms": ["fatigue"],
            "exclude_terms": [],
            "similarity_metric_cohort": "jaccard",
            "sort_by": "distance",
            "max_out": 10,
            "align": True,
            "render_heatmap": True,
            "render_mds": True,
            "granularity_ceiling": "detailed",
            "ai_provider_access": "detailed_allowed",
        },
    )

    def fake_run_pheno_ranker(request):
        job_path = Path(request.job_dir_override)
        (job_path / "rank.txt").write_text("id;score\nSYN001:week_0;0.1\n", encoding="utf-8")
        return {
            "intent": "pheno_run",
            "reply": "Finished background cohort run.",
            "job_id": record["job_id"],
            "mode": "cohort",
            "command": "pheno-ranker compare",
            "cwd": str(job_path),
            "stderr": "",
            "files": [
                {
                    "name": "rank.txt",
                    "url": f"/pheno-ranker/results/{record['job_id']}/rank.txt",
                }
            ],
            "plots": [],
        }

    monkeypatch.setattr(pheno_module, "run_pheno_ranker", fake_run_pheno_ranker)

    payload = jobs_module.run_pheno_job(record["job_id"], "alice")

    assert payload["status"] == "completed"
    assert payload["result_payload"]["reply"] == "Finished background cohort run."
    resolved_job_dir = jobs_module.job_dir(record["job_id"], "alice")
    assert pheno_module.resolve_pheno_ranker_job_dir(record["job_id"], user_id="alice") == resolved_job_dir
    assert pheno_module.pheno_ranker_result_file_path(record["job_id"], "rank.txt", user_id="alice").read_text(encoding="utf-8").startswith("id;score")


def test_list_job_records_reconciles_failed_rq_job_to_failed(tmp_path, monkeypatch):
    isolate_jobs_store(monkeypatch, tmp_path)
    record = jobs_module.create_job_record(
        job_type="pheno",
        user_id="alice",
        data={
            "feature": "pheno",
            "name": "Queued Pheno job",
            "dataset_id": "default",
            "rq_job_id": "rq-pheno-1",
        },
    )
    jobs_module.update_job_record(record["job_id"], "alice", status="running", started_at="2026-04-20T10:48:25+00:00")

    class FakeConnection:
        def ping(self):
            return True

    class FakeRqJob:
        exc_info = "Traceback...\nMemoryError: Killed"
        started_at = datetime(2026, 4, 20, 10, 48, 25, tzinfo=timezone.utc)
        ended_at = datetime(2026, 4, 20, 10, 52, 31, tzinfo=timezone.utc)

        def get_status(self, refresh=False):
            assert refresh is True
            return "failed"

    import rq.job

    monkeypatch.setattr(jobs_module, "jobs_enabled", lambda: True)
    monkeypatch.setattr(jobs_module, "_rq_connection", lambda: FakeConnection())
    monkeypatch.setattr(rq.job.Job, "fetch", staticmethod(lambda job_id, connection=None: FakeRqJob()))

    items = jobs_module.list_job_records("alice")

    assert len(items) == 1
    assert items[0]["status"] == "failed"
    assert "memoryerror" in items[0]["error"].lower()
    persisted = jobs_module.load_job_record(record["job_id"], "alice")
    assert persisted["status"] == "failed"


def test_load_job_record_reconciles_finished_rq_job_with_result_to_completed(tmp_path, monkeypatch):
    isolate_jobs_store(monkeypatch, tmp_path)
    record = jobs_module.create_job_record(
        job_type="pheno",
        user_id="alice",
        data={
            "feature": "pheno",
            "name": "Queued Pheno job",
            "dataset_id": "default",
            "rq_job_id": "rq-pheno-2",
        },
    )
    jobs_module.update_job_record(record["job_id"], "alice", status="running", started_at="2026-04-20T10:48:25+00:00")
    jobs_module.save_job_result(
        record["job_id"],
        "alice",
        {"reply": "Finished background cohort run."},
    )

    class FakeConnection:
        def ping(self):
            return True

    class FakeRqJob:
        exc_info = ""
        started_at = datetime(2026, 4, 20, 10, 48, 25, tzinfo=timezone.utc)
        ended_at = datetime(2026, 4, 20, 10, 52, 31, tzinfo=timezone.utc)

        def get_status(self, refresh=False):
            assert refresh is True
            return "finished"

    import rq.job

    monkeypatch.setattr(jobs_module, "jobs_enabled", lambda: True)
    monkeypatch.setattr(jobs_module, "_rq_connection", lambda: FakeConnection())
    monkeypatch.setattr(rq.job.Job, "fetch", staticmethod(lambda job_id, connection=None: FakeRqJob()))

    resolved = jobs_module.load_job_record(record["job_id"], "alice")

    assert resolved["status"] == "completed"
    assert resolved["result_available"] is True
    assert resolved["reply_preview"] == "Finished background cohort run."


def test_jobs_routes_are_user_scoped_and_return_completed_payload(tmp_path, monkeypatch):
    isolate_auth_store(monkeypatch, tmp_path)
    isolate_jobs_store(monkeypatch, tmp_path)
    monkeypatch.setenv("PN_AUTH_MODE", "local")
    monkeypatch.setenv(
        "PN_LOCAL_USERS_JSON",
        json.dumps(
            [
                {"username": "alice", "password": "secret", "role": "admin", "groups": ["admin"]},
                {"username": "bob", "password": "secret", "role": "user", "groups": []},
            ]
        ),
    )

    alice_job = jobs_module.create_job_record(
        job_type="analysis",
        user_id="alice",
        data={"feature": "analysis", "name": "Alice job", "catalog_item_id": "external-r-clinical-profile"},
    )
    alice_dir = jobs_module.job_dir(alice_job["job_id"], "alice")
    (alice_dir / "stdout.txt").write_text("hello", encoding="utf-8")
    jobs_module.save_job_result(
        alice_job["job_id"],
        "alice",
        {"intent": "analysis_external_rscript", "reply": "Finished", "data": {"job_id": alice_job["job_id"]}},
    )
    jobs_module.update_job_record(
        alice_job["job_id"],
        "alice",
        status="completed",
        result_available=True,
        reply_preview="Finished",
    )

    bob_job = jobs_module.create_job_record(
        job_type="analysis",
        user_id="bob",
        data={"feature": "analysis", "name": "Bob job", "catalog_item_id": "other"},
    )

    client = TestClient(app)
    assert client.post("/auth/login", json={"username": "alice", "password": "secret"}).status_code == 200

    listing = client.get("/jobs")
    assert listing.status_code == 200
    jobs = listing.json()["jobs"]
    assert len(jobs) == 1
    assert jobs[0]["job_id"] == alice_job["job_id"]

    detail = client.get(f"/jobs/{alice_job['job_id']}")
    assert detail.status_code == 200
    assert detail.json()["result_payload"]["reply"] == "Finished"

    artifact = client.get(f"/jobs/{alice_job['job_id']}/artifacts/stdout.txt")
    assert artifact.status_code == 200
    assert artifact.text == "hello"

    hidden = client.get(f"/jobs/{bob_job['job_id']}")
    assert hidden.status_code == 404


def test_analysis_session_delete_can_cascade_terminal_job_data(tmp_path, monkeypatch):
    isolate_auth_store(monkeypatch, tmp_path)
    isolate_jobs_store(monkeypatch, tmp_path)
    monkeypatch.setattr(analysis_sessions_module, "USER_STATE_ROOT", tmp_path / "users")
    monkeypatch.setattr(
        analysis_sessions_module,
        "LEGACY_ANALYSIS_SESSIONS_PATH",
        tmp_path / "legacy-analysis-sessions.json",
    )
    monkeypatch.setenv("PN_AUTH_MODE", "local")
    monkeypatch.setenv(
        "PN_LOCAL_USERS_JSON",
        json.dumps(
            [
                {"username": "alice", "password": "secret", "role": "admin", "groups": ["admin"]},
            ]
        ),
    )

    analysis_sessions_module.save_analysis_session(
        {
            "id": "session-1",
            "title": "Session 1",
            "turns": [],
            "history": [],
        },
        user_id="alice",
    )
    job = jobs_module.create_job_record(
        job_type="analysis",
        user_id="alice",
        data={
            "feature": "analysis",
            "name": "Completed job",
            "analysis_session_id": "session-1",
            "catalog_item_id": "external-r-clinical-profile",
        },
    )
    job_path = jobs_module.job_dir(job["job_id"], "alice")
    (job_path / "stdout.txt").write_text("log", encoding="utf-8")
    jobs_module.save_job_result(job["job_id"], "alice", {"reply": "done"})
    jobs_module.update_job_record(job["job_id"], "alice", status="completed", result_available=True)

    client = TestClient(app)
    assert client.post("/auth/login", json={"username": "alice", "password": "secret"}).status_code == 200

    response = client.delete("/analysis-sessions/session-1?delete_generated_data=true")

    assert response.status_code == 200
    payload = response.json()
    assert payload["deleted"] is True
    assert payload["deleted_generated_data"] is True
    assert payload["deleted_job_count"] == 1
    assert not job_path.exists()
    assert analysis_sessions_module.list_analysis_sessions(user_id="alice") == []


def test_analysis_session_delete_with_generated_data_blocks_active_jobs(tmp_path, monkeypatch):
    isolate_auth_store(monkeypatch, tmp_path)
    isolate_jobs_store(monkeypatch, tmp_path)
    monkeypatch.setattr(analysis_sessions_module, "USER_STATE_ROOT", tmp_path / "users")
    monkeypatch.setattr(
        analysis_sessions_module,
        "LEGACY_ANALYSIS_SESSIONS_PATH",
        tmp_path / "legacy-analysis-sessions.json",
    )
    monkeypatch.setenv("PN_AUTH_MODE", "local")
    monkeypatch.setenv(
        "PN_LOCAL_USERS_JSON",
        json.dumps(
            [
                {"username": "alice", "password": "secret", "role": "admin", "groups": ["admin"]},
            ]
        ),
    )

    analysis_sessions_module.save_analysis_session(
        {
            "id": "session-1",
            "title": "Session 1",
            "turns": [],
            "history": [],
        },
        user_id="alice",
    )
    job = jobs_module.create_job_record(
        job_type="analysis",
        user_id="alice",
        data={
            "feature": "analysis",
            "name": "Running job",
            "analysis_session_id": "session-1",
            "catalog_item_id": "external-r-clinical-profile",
        },
    )
    job_path = jobs_module.job_dir(job["job_id"], "alice")
    jobs_module.update_job_record(job["job_id"], "alice", status="running")

    client = TestClient(app)
    assert client.post("/auth/login", json={"username": "alice", "password": "secret"}).status_code == 200

    response = client.delete("/analysis-sessions/session-1?delete_generated_data=true")

    assert response.status_code == 409
    assert "active background jobs" in response.json()["detail"].lower()
    assert job_path.exists()
    assert len(analysis_sessions_module.list_analysis_sessions(user_id="alice")) == 1


def test_run_analysis_job_completes_and_persists_result(tmp_path, monkeypatch):
    isolate_jobs_store(monkeypatch, tmp_path)
    monkeypatch.setattr(
        analysis_catalog_module,
        "get_analysis_catalog_item",
        lambda item_id, path=analysis_catalog_module.ANALYSIS_CATALOG_PATH: {
            "id": "external-r-clinical-profile",
            "name": "External R clinical scope profile",
            "runner_type": "rscript",
            "runner_ref": "clinical_scope_profile",
        },
    )
    monkeypatch.setattr(
        analysis_external_module,
        "run_rscript_analysis",
        lambda runner_ref, **kwargs: {
            "intent": "analysis_external_rscript",
            "reply": "External analysis done.",
            "data": {
                "source": "deterministic",
                "execution": "external_runner",
                "context": {"mode": "external"},
                "runner_type": "rscript",
                "runner_ref": runner_ref,
            },
        },
    )

    record = jobs_module.create_job_record(
        job_type="analysis",
        user_id="alice",
        data={
            "feature": "analysis",
            "name": "Queued external R",
            "prompt": "Run the external R clinical scope profile for the current Analysis scope.",
            "data_dir": str(tmp_path),
            "catalog_item_id": "external-r-clinical-profile",
            "runner_type": "rscript",
            "runner_ref": "clinical_scope_profile",
            "job_timeout_seconds": 120,
        },
    )

    payload = jobs_module.run_analysis_job(record["job_id"], "alice")

    assert payload["status"] == "completed"
    assert payload["result_payload"]["reply"] == "External analysis done."
    stored = jobs_module.load_job_record(record["job_id"], "alice")
    assert stored["status"] == "completed"
    assert stored["result_available"] is True


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


def test_analysis_lists_available_measures_for_current_scope(tmp_path):
    write_json(
        tmp_path,
        "records.json",
        [
            {
                "id": "P1:week0",
                "event_date": "2024-01-01",
                "measures": [
                    {"assayCode": {"label": "CRP"}, "measurementValue": {"quantity": {"value": 10.0, "unit": {"label": "mg/L"}}}},
                    {"assayCode": {"label": "Hemoglobin"}, "measurementValue": {"quantity": {"value": 12.0, "unit": {"label": "g/dL"}}}},
                ],
            },
            {
                "id": "P2:week0",
                "event_date": "2024-01-01",
                "measures": [
                    {"assayCode": {"label": "CRP"}, "measurementValue": {"quantity": {"value": 8.0, "unit": {"label": "mg/L"}}}},
                    {"assayCode": {"label": "Leukocyte Count"}, "measurementValue": {"quantity": {"value": 6.0, "unit": {"label": "10^9/L"}}}},
                ],
            },
        ],
    )

    payload = analysis_module.analysis_llm_reply(
        "What measures are available for this cohort?",
        str(tmp_path),
    )

    assert payload["intent"] == "analysis_measure_inventory"
    context = payload["data"]["context"]
    assert context["mode"] == "measure_inventory"
    assert [item["measure"] for item in context["measures"]] == ["CRP", "Hemoglobin", "Leukocyte Count"]


def test_analysis_lists_available_measures_for_compare_mode(tmp_path):
    write_json(
        tmp_path,
        "records.json",
        [
            {
                "id": "A1:week0",
                "event_date": "2024-01-01",
                "measures": [{"assayCode": {"label": "CRP"}, "measurementValue": {"quantity": {"value": 10.0}}}],
            },
            {
                "id": "A2:week0",
                "event_date": "2024-01-02",
                "measures": [{"assayCode": {"label": "Hemoglobin"}, "measurementValue": {"quantity": {"value": 12.0}}}],
            },
            {
                "id": "B1:week0",
                "event_date": "2024-01-01",
                "measures": [{"assayCode": {"label": "CRP"}, "measurementValue": {"quantity": {"value": 8.0}}}],
            },
            {
                "id": "B2:week0",
                "event_date": "2024-01-02",
                "measures": [{"assayCode": {"label": "Clinical relapse"}, "measurementValue": {"quantity": {"value": 0.0}}}],
            },
        ],
    )

    payload = analysis_module.analysis_llm_reply(
        "Which numeric longitudinal measures can I compare between these cohorts?",
        str(tmp_path),
        selected_patient_ids="A1,A2",
        compare_mode=True,
        compare_selected_patient_ids="B1,B2",
    )

    assert payload["intent"] == "analysis_measure_inventory_compare"
    context = payload["data"]["context"]
    assert context["mode"] == "measure_inventory_compare"
    assert context["measures"] == ["CRP", "Clinical relapse", "Hemoglobin"]


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


def test_analysis_deterministic_only_skips_planner_and_full_llm(tmp_path, monkeypatch):
    write_json(
        tmp_path,
        "records.json",
        [
            {
                "id": "P1:baseline",
                "event_date": "2024-01-01",
                "diseases": [{"diseaseCode": {"label": "Crohn Disease"}}],
                "treatments": [{"treatmentCode": {"label": "Infliximab"}}],
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
        "Summarize the main clinical patterns in this cohort and tell me what stands out.",
        str(tmp_path),
        deterministic_only=True,
    )

    assert payload["intent"] == "analysis_deterministic"
    assert payload["data"]["source"] == "deterministic"
    assert "Deterministic Workspace Summary" in payload["reply"]
    assert calls == []


def test_analysis_ai_provider_blocked_skips_planner_and_llm(tmp_path, monkeypatch):
    write_json(
        tmp_path,
        "records.json",
        [
            {
                "id": "P1:baseline",
                "event_date": "2024-01-01",
                "diseases": [{"diseaseCode": {"label": "Crohn Disease"}}],
                "treatments": [{"treatmentCode": {"label": "Infliximab"}}],
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
        "Summarize the main clinical patterns in this cohort and tell me what stands out.",
        str(tmp_path),
        ai_provider_access="blocked",
    )

    assert payload["intent"] == "analysis_deterministic"
    assert payload["data"]["source"] == "deterministic"
    assert payload["data"]["ai_provider_access"] == "blocked"
    assert payload["data"]["ai_provider_context_granularity"] == "blocked"
    assert calls == []


def test_analysis_ai_provider_restricted_skips_planner_and_sends_no_clinical_context(tmp_path, monkeypatch):
    write_json(
        tmp_path,
        "records.json",
        [
            {
                "id": "P1:baseline",
                "event_date": "2024-01-01",
                "diseases": [{"diseaseCode": {"label": "Crohn Disease"}}],
                "treatments": [{"treatmentCode": {"label": "Infliximab"}}],
            }
        ],
    )

    monkeypatch.setenv("LM_STUDIO_ENABLED", "true")
    monkeypatch.setenv("LM_STUDIO_MODEL", "local-model")

    captured = {}
    calls = []

    def fake_http_json(url, payload=None, log_kind="generic"):
        calls.append(log_kind)
        captured["payload"] = payload
        return {"choices": [{"message": {"content": "I do not have enough permitted context to answer that safely."}}]}

    monkeypatch.setattr(analysis_module, "http_json", fake_http_json)

    payload = analysis_module.analysis_llm_reply(
        "Explain this cohort.",
        str(tmp_path),
        ai_provider_access="safe_summary",
    )

    assert payload["intent"] == "analysis_llm"
    assert payload["reply"] == "I do not have enough permitted context to answer that safely."
    assert payload["data"]["source"] == "llm"
    assert payload["data"]["ai_provider_access"] == "safe_summary"
    assert payload["data"]["ai_provider_context_granularity"] == "safe_summary"
    assert calls == ["analysis_llm"]
    user_message = captured["payload"]["messages"][1]["content"]
    assert "Crohn Disease" not in user_message
    assert "Infliximab" not in user_message
    assert "patient_count" not in user_message


def test_analysis_llm_only_safe_summary_does_not_fall_back_to_deterministic_on_provider_error(tmp_path, monkeypatch):
    write_json(
        tmp_path,
        "records.json",
        [
            {
                "id": "P1:baseline",
                "event_date": "2025-01-10",
                "diseases": [{"diseaseCode": {"label": "Multiple Sclerosis"}}],
                "treatments": [{"treatmentCode": {"label": "Ocrelizumab"}}],
            }
        ],
    )

    monkeypatch.setenv("LM_STUDIO_ENABLED", "true")
    monkeypatch.setenv("LM_STUDIO_MODEL", "local-model")

    def fake_http_json(url, payload=None, log_kind="generic"):
        raise RuntimeError("LM Studio offline")

    monkeypatch.setattr(analysis_module, "http_json", fake_http_json)

    payload = analysis_module.analysis_llm_reply(
        "Write a concise workspace briefing for a clinician, including what stands out and what needs validation.",
        str(tmp_path),
        llm_only=True,
        ai_provider_access="safe_summary",
        granularity_ceiling="summary",
    )

    assert payload["intent"] == "analysis_llm"
    assert payload["data"]["source"] == "provider_unavailable"
    assert payload["data"]["model"] is None
    assert "Deterministic Workspace Summary" not in payload["reply"]
    assert "requires an AI provider" in payload["reply"]


def test_analysis_llm_only_blocked_returns_policy_response(tmp_path):
    write_json(
        tmp_path,
        "records.json",
        [
            {
                "id": "P1:baseline",
                "event_date": "2025-01-10",
                "diseases": [{"diseaseCode": {"label": "Multiple Sclerosis"}}],
                "treatments": [{"treatmentCode": {"label": "Ocrelizumab"}}],
            }
        ],
    )

    payload = analysis_module.analysis_llm_reply(
        "Interpret the disease and medication profiles in this workspace and summarize the main themes.",
        str(tmp_path),
        llm_only=True,
        ai_provider_access="blocked",
        granularity_ceiling="summary",
    )

    assert payload["intent"] == "analysis_llm"
    assert payload["data"]["source"] == "policy"
    assert payload["data"]["model"] is None
    assert "Deterministic Workspace Summary" not in payload["reply"]
    assert "AI provider access is blocked" in payload["reply"]


def test_analysis_summary_ceiling_omits_scope_ids_from_semantic_planner_payload(tmp_path, monkeypatch):
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
                "id": "P2:baseline",
                "event_date": "2024-01-02",
                "treatments": [{"treatmentCode": {"label": "Infliximab"}}],
                "measures": [{"assayCode": {"label": "CRP"}, "measurementValue": {"quantity": {"value": 12.0}}}],
            },
        ],
    )

    monkeypatch.setenv("LM_STUDIO_ENABLED", "true")
    monkeypatch.setenv("LM_STUDIO_MODEL", "local-model")

    captured = {}

    def fake_http_json(url, payload=None, log_kind="generic"):
        if log_kind == "analysis_planner":
            captured["payload"] = payload
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "intent": "analysis_plan",
                                    "analysis_type": "summary",
                                }
                            )
                        }
                    }
                ]
            }
        return {"choices": [{"message": {"content": "Narrative analysis"}}]}

    monkeypatch.setattr(analysis_module, "http_json", fake_http_json)

    payload = analysis_module.analysis_llm_reply(
        "Summarize the main clinical patterns in this cohort and tell me what stands out.",
        str(tmp_path),
        selected_patient_ids="P1,P2",
        granularity_ceiling="summary",
    )

    assert payload["intent"] == "analysis_deterministic"
    assert payload["data"]["execution"] == "deterministic"
    assert payload["data"]["planner"]["provider"] == "lm_studio"
    assert payload["data"]["granularity_applied"] == "summary"
    planner_message = captured["payload"]["messages"][1]["content"]
    assert '"selected_patient_ids": []' in planner_message
    assert '"conversation_history": []' in planner_message
    assert "P1" not in planner_message
    assert "P2" not in planner_message


def test_pheno_explain_llm_ai_provider_restricted_returns_deterministic_metadata(tmp_path, monkeypatch):
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    (job_dir / "rank.txt").write_text(
        "REFERENCE(ID)\tTARGET(ID)\tJACCARD-INDEX\tINTERSECT\n"
        "SYN002:week_0\tSYN001:week_0\t0.85\t4\n",
        encoding="utf-8",
    )

    calls = []

    def fake_http_json(url, payload=None, log_kind="generic"):
        calls.append(log_kind)
        return {"choices": [{"message": {"content": "LLM explanation"}}]}

    monkeypatch.setattr(pheno_module, "http_json", fake_http_json)
    monkeypatch.setattr(pheno_module, "resolve_pheno_ranker_job_dir", lambda job_id, user_id="": job_dir)

    payload = pheno_module.pheno_ranker_explain_llm(
        "job-1",
        top_n=1,
        ai_provider_access="safe_summary",
    )

    assert payload["intent"] == "pheno_explain"
    assert payload["source"] == "deterministic"
    assert payload["data"]["source"] == "deterministic"
    assert payload["data"]["ai_provider_access"] == "safe_summary"
    assert payload["data"]["ai_provider_context_granularity"] == "safe_summary"
    assert calls == []


def test_pheno_run_route_requires_detailed_workspace_access(tmp_path, monkeypatch):
    isolate_auth_store(monkeypatch, tmp_path)
    monkeypatch.setenv("PN_AUTH_MODE", "local")
    monkeypatch.setenv(
        "PN_LOCAL_USERS_JSON",
        json.dumps(
            [
                {"username": "admin", "password": "secret", "role": "admin", "display_name": "Admin"},
                {"username": "maria", "password": "demo", "role": "user", "display_name": "Maria"},
            ]
        ),
    )
    monkeypatch.setattr(datasets_module, "DATASET_REGISTRY_PATH", tmp_path / "state" / "datasets" / "registry.json")
    monkeypatch.setattr(user_state_module, "STATE_ROOT_DIR", tmp_path / "state")

    restricted_root = tmp_path / "restricted"
    restricted_clinical = restricted_root / "clinical"
    restricted_clinical.mkdir(parents=True)
    write_json(
        restricted_clinical,
        "records.json",
        [
            {"id": "M1:week_0", "patient_id": "M1"},
        ],
    )

    registry = [
        {
            "dataset_id": "maria-dataset",
            "name": "Maria dataset",
            "root_path": str(restricted_root),
            "enabled": True,
            "visibility": "restricted",
            "allowed_users": ["maria"],
            "allowed_groups": [],
            "query_granularity_ceiling": "summary",
            "ai_provider_access": "use_thread_mode",
            "created_by": "admin",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        },
    ]
    datasets_module.DATASET_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    datasets_module.DATASET_REGISTRY_PATH.write_text(json.dumps(registry), encoding="utf-8")

    client = TestClient(app)
    login = client.post("/auth/login", json={"username": "maria", "password": "demo"})
    assert login.status_code == 200

    response = client.post(
        "/pheno-ranker/run",
        json={
            "dataset_id": "maria-dataset",
            "action": "compare",
            "mode": "cohort",
            "selected_patient_ids": "M1",
        },
    )

    assert response.status_code == 403
    assert "Detailed in-app access" in response.json()["detail"]


def test_pheno_patient_ids_route_requires_detailed_workspace_access(tmp_path, monkeypatch):
    isolate_auth_store(monkeypatch, tmp_path)
    monkeypatch.setenv("PN_AUTH_MODE", "local")
    monkeypatch.setenv(
        "PN_LOCAL_USERS_JSON",
        json.dumps(
            [
                {"username": "admin", "password": "secret", "role": "admin", "display_name": "Admin"},
                {"username": "maria", "password": "demo", "role": "user", "display_name": "Maria"},
            ]
        ),
    )
    monkeypatch.setattr(datasets_module, "DATASET_REGISTRY_PATH", tmp_path / "state" / "datasets" / "registry.json")
    monkeypatch.setattr(user_state_module, "STATE_ROOT_DIR", tmp_path / "state")

    restricted_root = tmp_path / "restricted"
    restricted_clinical = restricted_root / "clinical"
    restricted_clinical.mkdir(parents=True)
    write_json(
        restricted_clinical,
        "records.json",
        [
            {"id": "M1:week_0", "patient_id": "M1"},
        ],
    )

    registry = [
        {
            "dataset_id": "maria-dataset",
            "name": "Maria dataset",
            "root_path": str(restricted_root),
            "enabled": True,
            "visibility": "restricted",
            "allowed_users": ["maria"],
            "allowed_groups": [],
            "query_granularity_ceiling": "summary",
            "ai_provider_access": "use_thread_mode",
            "created_by": "admin",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        },
    ]
    datasets_module.DATASET_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    datasets_module.DATASET_REGISTRY_PATH.write_text(json.dumps(registry), encoding="utf-8")

    client = TestClient(app)
    login = client.post("/auth/login", json={"username": "maria", "password": "demo"})
    assert login.status_code == 200

    response = client.get("/pheno-ranker/patient-ids", params={"dataset_id": "maria-dataset"})

    assert response.status_code == 403
    assert "Detailed in-app access" in response.json()["detail"]


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
    assert payload["data"]["ai_provider_access"] == "detailed_allowed"


def test_explicit_patient_term_query_stays_deterministic_on_zero_matches(tmp_path, monkeypatch):
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

    calls = []

    def fake_http_json(url, payload=None, log_kind="generic"):
        calls.append((url, log_kind))
        return {"data": [{"id": "local-model"}]}

    monkeypatch.setattr(query_module, "_http_json", fake_http_json)

    payload = answer_query(str(tmp_path), "Which patients have Infliximab?")

    assert payload["intent"] == "term_cohort"
    assert payload["reply"] == "No patients match 'Infliximab' in this workspace."
    assert payload["data"]["patient_count"] == 0
    assert payload["data"]["available_actions"] == {
        "open_in_analysis": False,
        "save_cohort": False,
        "copy_patient_ids": False,
        "use_in_pheno_ranker": False,
    }
    assert calls == []


def test_query_reports_missing_lm_studio_model(tmp_path, monkeypatch):
    write_json(tmp_path, "records.json", [])

    monkeypatch.setenv("LM_STUDIO_ENABLED", "1")
    monkeypatch.delenv("LM_STUDIO_MODEL", raising=False)
    monkeypatch.setattr(query_module, "_http_json", lambda url, payload=None, log_kind="generic": {"data": []})

    payload = answer_query(str(tmp_path), "Explain the cohort")
    assert payload["intent"] == "llm_unavailable"
    assert "no loaded model" in payload["reply"].lower()


def test_query_ai_provider_blocked_skips_lm_studio(tmp_path, monkeypatch):
    write_json(tmp_path, "records.json", [])

    monkeypatch.setenv("LM_STUDIO_ENABLED", "true")

    calls = []

    def fake_http_json(url, payload=None, log_kind="generic"):
        calls.append((url, log_kind))
        return {"data": [{"id": "local-model"}]}

    monkeypatch.setattr(query_module, "_http_json", fake_http_json)

    payload = answer_query(
        str(tmp_path),
        "What evidence supports the main cohort summary?",
        ai_provider_access="blocked",
    )

    assert payload["intent"] == "unsupported"
    assert "LM Studio fallback is currently unavailable" in payload["reply"]
    assert payload["data"]["external_llm_allowed"] is False
    assert payload["data"]["ai_provider_access"] == "blocked"
    assert payload["data"]["ai_provider_context_granularity"] == "blocked"
    assert calls == []


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


def test_query_summary_omits_history_and_patient_ids_from_lm_studio_context(tmp_path, monkeypatch):
    write_json(
        tmp_path,
        "records.json",
        [
            {"id": "107:week_0", "patient_id": "107", "diseases": [{"diseaseCode": {"label": "Crohn Disease"}}]},
            {"id": "208:week_0", "patient_id": "208", "diseases": [{"diseaseCode": {"label": "Ulcerative Colitis"}}]},
        ],
    )

    monkeypatch.setenv("LM_STUDIO_ENABLED", "true")
    monkeypatch.delenv("LM_STUDIO_MODEL", raising=False)

    captured = {}

    def fake_http_json(url, payload=None, log_kind="generic"):
        if url.endswith("/models"):
            return {"data": [{"id": "local-model"}]}
        captured["payload"] = payload
        return {"choices": [{"message": {"content": "Summary-safe answer"}}]}

    monkeypatch.setattr(query_module, "_http_json", fake_http_json)
    monkeypatch.setenv("LM_STUDIO_INCLUDE_PATIENT_NAVIGATOR", "true")

    payload = answer_query(
        str(tmp_path),
        "What changed after that?",
        history=[
            {"role": "user", "content": "Show patient 107"},
            {"role": "assistant", "content": "Patient 107 has 1 visit."},
        ],
        granularity_mode="summary",
    )

    assert payload["intent"] == "llm_fallback"
    user_message = captured["payload"]["messages"][1]["content"]
    assert "conversation_history" not in user_message
    assert '"patient_id"' not in user_message
    assert '"patient_navigator"' not in user_message
    assert "Show patient 107" not in user_message


def test_query_ai_provider_restricted_clamps_detailed_lm_studio_context(tmp_path, monkeypatch):
    write_json(
        tmp_path,
        "records.json",
        [
            {"id": "107:week_0", "patient_id": "107", "diseases": [{"diseaseCode": {"label": "Crohn Disease"}}]},
            {"id": "208:week_0", "patient_id": "208", "diseases": [{"diseaseCode": {"label": "Ulcerative Colitis"}}]},
        ],
    )

    monkeypatch.setenv("LM_STUDIO_ENABLED", "true")
    monkeypatch.delenv("LM_STUDIO_MODEL", raising=False)
    monkeypatch.setenv("LM_STUDIO_INCLUDE_PATIENT_NAVIGATOR", "true")

    captured = {}

    def fake_http_json(url, payload=None, log_kind="generic"):
        if url.endswith("/models"):
            return {"data": [{"id": "local-model"}]}
        captured["payload"] = payload
        return {"choices": [{"message": {"content": "Provider-clamped answer"}}]}

    monkeypatch.setattr(query_module, "_http_json", fake_http_json)

    payload = answer_query(
        str(tmp_path),
        "What changed after that?",
        history=[
            {"role": "user", "content": "Show patient 107"},
            {"role": "assistant", "content": "Patient 107 has 1 visit."},
        ],
        granularity_mode="detailed",
        ai_provider_access="safe_summary",
    )

    assert payload["intent"] == "llm_fallback"
    assert payload["data"]["ai_provider_access"] == "safe_summary"
    assert payload["data"]["ai_provider_context_granularity"] == "safe_summary"
    user_message = captured["payload"]["messages"][1]["content"]
    assert "conversation_history" not in user_message
    assert '"patient_id"' not in user_message
    assert '"patient_navigator"' not in user_message
    assert "Show patient 107" not in user_message
    assert '"patients":' not in user_message
    assert "Crohn Disease" not in user_message
    assert "Ulcerative Colitis" not in user_message


def test_query_ai_provider_restricted_skips_semantic_planner_and_uses_safe_fallback(tmp_path, monkeypatch):
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

    captured = {}
    calls = []

    def fake_http_json(url, payload=None, log_kind="generic"):
        if url.endswith("/models"):
            return {"data": [{"id": "local-model"}]}
        calls.append(log_kind)
        captured["payload"] = payload
        return {"choices": [{"message": {"content": "I don't have enough permitted context to answer that safely."}}]}

    monkeypatch.setattr(query_module, "_http_json", fake_http_json)

    payload = answer_query(
        str(tmp_path),
        "How many patients take biologics?",
        history=[
            {"role": "user", "content": "Show patient P1"},
            {"role": "assistant", "content": "Patient P1 has 1 visit."},
        ],
        granularity_mode="detailed",
        ai_provider_access="safe_summary",
    )

    assert payload["intent"] == "llm_fallback"
    assert payload["data"]["granularity_applied"] == "detailed"
    assert payload["data"]["ai_provider_access"] == "safe_summary"
    assert payload["data"]["ai_provider_context_granularity"] == "safe_summary"
    user_message = captured["payload"]["messages"][1]["content"]
    assert calls == ["query_fallback"]
    assert "Recent conversation history JSON" not in user_message
    assert "Show patient P1" not in user_message
    assert "Infliximab" not in user_message
    assert "Mesalamine" not in user_message
    assert '"patients":' not in user_message


def test_query_ai_provider_restricted_explain_dataset_sends_no_clinical_content(tmp_path, monkeypatch):
    write_json(
        tmp_path,
        "records.json",
        [
            {
                "id": "P1:v1",
                "event_date": "2024-01-01",
                "diseases": [{"diseaseCode": {"label": "Multiple Sclerosis"}}],
                "treatments": [{"treatmentCode": {"label": "Ocrelizumab"}}],
            },
        ],
    )

    monkeypatch.setenv("LM_STUDIO_ENABLED", "true")
    monkeypatch.delenv("LM_STUDIO_MODEL", raising=False)

    captured = {}

    def fake_http_json(url, payload=None, log_kind="generic"):
        if url.endswith("/models"):
            return {"data": [{"id": "local-model"}]}
        captured["payload"] = payload
        return {"choices": [{"message": {"content": "I don't have enough permitted context to describe this dataset safely."}}]}

    monkeypatch.setattr(query_module, "_http_json", fake_http_json)

    payload = answer_query(
        str(tmp_path),
        "Explain this dataset",
        ai_provider_access="safe_summary",
    )

    assert payload["intent"] == "llm_fallback"
    assert payload["data"]["ai_provider_access"] == "safe_summary"
    assert payload["data"]["ai_provider_context_granularity"] == "safe_summary"
    user_message = captured["payload"]["messages"][1]["content"]
    assert "Ocrelizumab" not in user_message
    assert "Multiple Sclerosis" not in user_message
    assert '"patients":1' not in user_message
    assert '"visits":1' not in user_message


def test_query_passes_scoped_subset_into_lm_studio_context(tmp_path, monkeypatch):
    write_json(
        tmp_path,
        "records.json",
        [
            {"id": "P1:v1", "patient_id": "P1", "diseases": [{"diseaseCode": {"label": "Crohn Disease"}}]},
            {"id": "P2:v1", "patient_id": "P2", "diseases": [{"diseaseCode": {"label": "Ulcerative Colitis"}}]},
            {"id": "P3:v1", "patient_id": "P3", "diseases": [{"diseaseCode": {"label": "Crohn Disease"}}]},
        ],
    )

    monkeypatch.setenv("LM_STUDIO_ENABLED", "true")
    monkeypatch.delenv("LM_STUDIO_MODEL", raising=False)

    captured = {}

    def fake_http_json(url, payload=None, log_kind="generic"):
        if url.endswith("/models"):
            return {"data": [{"id": "local-model"}]}
        captured["payload"] = payload
        return {"choices": [{"message": {"content": "Scoped context answer"}}]}

    monkeypatch.setattr(query_module, "_http_json", fake_http_json)

    payload = answer_query(
        str(tmp_path),
        "Can you summarize the main conditions they seem to have?",
        history=[
            {"role": "user", "content": "How many patients have Crohn Disease?"},
            {"role": "assistant", "content": "2 patients match disease query 'Crohn Disease'."},
        ],
        scoped_patient_ids=["P1", "P3"],
    )

    assert payload["intent"] == "llm_fallback"
    user_message = captured["payload"]["messages"][1]["content"]
    assert '"patients":2' in user_message
    assert "P1" in user_message
    assert "P3" in user_message
    assert "P2" not in user_message
    assert "Ulcerative Colitis" not in user_message


def test_query_summary_omits_scoped_patient_ids_from_lm_studio_context(tmp_path, monkeypatch):
    write_json(
        tmp_path,
        "records.json",
        [
            {"id": "P1:v1", "patient_id": "P1", "diseases": [{"diseaseCode": {"label": "Crohn Disease"}}]},
            {"id": "P2:v1", "patient_id": "P2", "diseases": [{"diseaseCode": {"label": "Ulcerative Colitis"}}]},
            {"id": "P3:v1", "patient_id": "P3", "diseases": [{"diseaseCode": {"label": "Crohn Disease"}}]},
        ],
    )

    monkeypatch.setenv("LM_STUDIO_ENABLED", "true")
    monkeypatch.delenv("LM_STUDIO_MODEL", raising=False)

    captured = {}

    def fake_http_json(url, payload=None, log_kind="generic"):
        if url.endswith("/models"):
            return {"data": [{"id": "local-model"}]}
        captured["payload"] = payload
        return {"choices": [{"message": {"content": "Scoped summary-safe answer"}}]}

    monkeypatch.setattr(query_module, "_http_json", fake_http_json)

    payload = answer_query(
        str(tmp_path),
        "Can you summarize the main conditions they seem to have?",
        history=[
            {"role": "user", "content": "How many patients have Crohn Disease?"},
            {"role": "assistant", "content": "2 patients match disease query 'Crohn Disease'."},
        ],
        scoped_patient_ids=["P1", "P3"],
        granularity_mode="summary",
    )

    assert payload["intent"] == "llm_fallback"
    user_message = captured["payload"]["messages"][1]["content"]
    assert '"patients":2' in user_message
    assert "P1" not in user_message
    assert "P3" not in user_message
    assert '"patient_id"' not in user_message


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


def test_query_summary_omits_history_from_semantic_planner_payload(tmp_path, monkeypatch):
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

    payload = answer_query(
        str(tmp_path),
        "select subjects receiving infliximab",
        history=[
            {"role": "user", "content": "Show patient 107"},
            {"role": "assistant", "content": "Patient 107 has 2 visits."},
        ],
        granularity_mode="summary",
    )

    assert payload["intent"] == "semantic_cohort_query"
    planner_message = captured["payload"]["messages"][1]["content"]
    assert "Recent conversation history JSON" not in planner_message
    assert "Show patient 107" not in planner_message



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


def test_query_semantic_planner_respects_how_many_vs_which_wording(tmp_path, monkeypatch):
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
    monkeypatch.setenv("LM_STUDIO_MODEL", "local-model")

    def fake_http_json(url, payload=None, log_kind="generic"):
        if url.endswith("/models"):
            return {"data": [{"id": "local-model"}]}
        if log_kind == "query_semantic_plan":
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "intent": "cohort_query",
                                    "output": "patient_list",
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

    count_payload = answer_query(str(tmp_path), "How many patients take biologics?")
    assert count_payload["intent"] == "semantic_cohort_query"
    assert count_payload["data"]["patient_count"] == 2
    assert count_payload["data"]["semantic_plan"]["output"] == "count"
    assert count_payload["reply"].startswith("2 patients match:")

    list_payload = answer_query(str(tmp_path), "Which patients take biologics?")
    assert list_payload["intent"] == "semantic_cohort_query"
    assert list_payload["data"]["semantic_plan"]["output"] == "patient_list"
    assert "Patients matching" in list_payload["reply"]
    assert "are shown below" in list_payload["reply"]
    assert "P1" not in list_payload["reply"]
    assert "P2" not in list_payload["reply"]


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


def test_query_counts_patients_in_workspace_with_colloquial_prompt(tmp_path):
    write_json(
        tmp_path,
        "individuals.json",
        [
            {"id": "101:week_0_arm_1", "treatments": []},
            {"id": "102:week_0_arm_1", "treatments": []},
            {"id": "103:week_0_arm_1", "treatments": []},
        ],
    )

    payload = answer_query(str(tmp_path), "How many patients we have?")

    assert payload["intent"] == "patient_inventory"
    assert payload["data"]["patient_count"] == 3
    assert payload["data"]["patient_ids"] == [
        "101:week_0_arm_1",
        "102:week_0_arm_1",
        "103:week_0_arm_1",
    ]
    assert payload["reply"] == "This workspace contains 3 patients."


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

    payload = answer_query(str(tmp_path), "Show the timeline for participant 101")
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


def test_query_store_rebuilds_stale_schema_missing_required_tables(tmp_path, monkeypatch):
    if not duckdb_available():
        return

    write_json(
        tmp_path,
        "records.json",
        [
            {
                "id": "SYN001:week_0",
                "event_date": "2024-01-01",
                "diseases": [{"diseaseCode": {"label": "Crohn Disease"}}],
                "treatments": [{"treatmentCode": {"label": "Infliximab"}}],
            }
        ],
    )

    store_dir = tmp_path / "query-store"
    monkeypatch.setattr(query_store_module, "QUERY_STORE_DIR", store_dir)

    db_path, meta_path = query_store_module._store_paths(str(tmp_path))
    con = query_store_module.duckdb.connect(str(db_path))
    try:
        con.execute("CREATE TABLE legacy_only (id TEXT)")
    finally:
        con.close()
    meta_path.write_text(
        json.dumps(query_store_module._source_files_signature(str(tmp_path)), indent=2),
        encoding="utf-8",
    )

    rows = query_module._patient_query_index(str(tmp_path))

    assert [item["patient_id"] for item in rows] == ["SYN001"]


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
                "ENSG00002700028;100;120;140",
            ]
        ),
        encoding="utf-8",
    )
    query_store_module.MOLECULAR_DATA_DIR = molecular_dir
    try:
        payload = analysis_module.analysis_llm_reply(
            "Show expression of ENSG00002700028 in the current Analysis scope.",
            str(tmp_path),
            selected_patient_ids="SYN001,SYN002",
        )
    finally:
        query_store_module.MOLECULAR_DATA_DIR = original_dir

    assert payload["intent"] == "analysis_molecular_expression"
    assert payload["data"]["source"] == "deterministic"
    assert payload["data"]["context"]["mode"] == "molecular_expression"
    assert payload["data"]["context"]["datasets"][0]["scope_a"]["sample_count"] == 2
    assert "ENSG00002700028 was found in 1 molecular dataset." in payload["reply"]
    assert "\n| Dataset | Samples | Patients | Mean | Median | Min | Max |\n" in payload["reply"]
    assert "| synthetic_transcriptome_raw_counts | 2 | 2 | 110 | 110 | 100 | 120 |" in payload["reply"]


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
                "ENSG00002700028;100;120;140",
            ]
        ),
        encoding="utf-8",
    )
    query_store_module.MOLECULAR_DATA_DIR = molecular_dir
    try:
        payload = analysis_module.analysis_llm_reply(
            "Compare expression of ENSG00002700028 between Cohort A and Cohort B.",
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
    assert "\n| Dataset | Scope | Samples | Patients | Mean | Median | Min | Max |\n" in payload["reply"]
    assert "| synthetic_transcriptome_raw_counts | Cohort A | 2 | 2 | 110 | 110 | 100 | 120 |" in payload["reply"]


def test_analysis_supports_deterministic_molecular_medication_comparison(tmp_path):
    write_json(
        tmp_path,
        "records.json",
        [
            {"id": "SYN001:baseline", "event_date": "2024-01-01", "treatments": [{"treatmentCode": {"label": "Infliximab"}}]},
            {"id": "SYN002:baseline", "event_date": "2024-01-01", "treatments": [{"treatmentCode": {"label": "Infliximab"}}]},
            {"id": "SYN006:baseline", "event_date": "2024-01-01", "treatments": [{"treatmentCode": {"label": "Vedolizumab"}}]},
            {"id": "SYN007:baseline", "event_date": "2024-01-01", "treatments": [{"treatmentCode": {"label": "Vedolizumab"}}]},
        ],
    )

    original_dir = query_store_module.MOLECULAR_DATA_DIR
    molecular_dir = tmp_path / "molecular"
    molecular_dir.mkdir()
    (molecular_dir / "synthetic_transcriptome_raw_counts_infliximab.csv").write_text(
        "\n".join(
            [
                "gene_id;SYN001;SYN002",
                "ENSG00000169429;1400;1300",
                "ENSG00000170421;150;160",
            ]
        ),
        encoding="utf-8",
    )
    (molecular_dir / "synthetic_transcriptome_raw_counts_vedolizumab.csv").write_text(
        "\n".join(
            [
                "gene_id;SYN006;SYN007",
                "ENSG00000169429;150;160",
                "ENSG00000170421;1200;1250",
            ]
        ),
        encoding="utf-8",
    )
    query_store_module.MOLECULAR_DATA_DIR = molecular_dir
    try:
        payload = analysis_module.analysis_llm_reply(
            "Explain differences in gene expression according to medication",
            str(tmp_path),
        )
    finally:
        query_store_module.MOLECULAR_DATA_DIR = original_dir

    assert payload["intent"] == "analysis_molecular_medication_compare"
    assert payload["data"]["context"]["mode"] == "molecular_medication_compare"
    assert payload["data"]["context"]["comparisons"][0]["medication_a"] == "Infliximab"
    assert payload["data"]["context"]["comparisons"][0]["medication_b"] == "Vedolizumab"
    assert payload["data"]["context"]["exploratory_note"].startswith("Exploratory transcriptomics comparison")
    assert payload["data"]["context"]["comparisons"][0]["exploratory_volcano_points"]
    volcano_point = payload["data"]["context"]["comparisons"][0]["exploratory_volcano_points"][0]
    assert "gene_id" in volcano_point
    assert "log2_fold_change" in volcano_point
    assert "neg_log10_p" in volcano_point
    assert "largest expression difference is ENSG00000169429" in payload["reply"]
    assert "preliminary and not DESeq2-grade differential expression" in payload["reply"]


def test_analysis_molecular_medication_comparison_respects_scope(tmp_path):
    write_json(
        tmp_path,
        "records.json",
        [
            {"id": "SYN001:baseline", "patient_id": "SYN001", "info": {"event_date": "2024-01-01"}, "treatments": [{"treatmentCode": {"label": "Infliximab"}}]},
            {"id": "SYN002:baseline", "patient_id": "SYN002", "info": {"event_date": "2024-01-01"}, "treatments": [{"treatmentCode": {"label": "Infliximab"}}]},
            {"id": "SYN006:baseline", "patient_id": "SYN006", "info": {"event_date": "2024-01-01"}, "treatments": [{"treatmentCode": {"label": "Vedolizumab"}}]},
            {"id": "SYN007:baseline", "patient_id": "SYN007", "info": {"event_date": "2024-01-01"}, "treatments": [{"treatmentCode": {"label": "Vedolizumab"}}]},
        ],
    )

    original_dir = query_store_module.MOLECULAR_DATA_DIR
    molecular_dir = tmp_path / "molecular"
    molecular_dir.mkdir()
    (molecular_dir / "synthetic_transcriptome_raw_counts_infliximab.csv").write_text(
        "\n".join(
            [
                "gene_id;SYN001;SYN002",
                "ENSG00000169429;1400;400",
                "ENSG00000170421;150;160",
            ]
        ),
        encoding="utf-8",
    )
    (molecular_dir / "synthetic_transcriptome_raw_counts_vedolizumab.csv").write_text(
        "\n".join(
            [
                "gene_id;SYN006;SYN007",
                "ENSG00000169429;150;900",
                "ENSG00000170421;1200;1250",
            ]
        ),
        encoding="utf-8",
    )
    query_store_module.MOLECULAR_DATA_DIR = molecular_dir
    try:
        payload = analysis_module.analysis_llm_reply(
            "Explain differences in gene expression according to medication",
            str(tmp_path),
            selected_patient_ids="SYN001,SYN006",
        )
    finally:
        query_store_module.MOLECULAR_DATA_DIR = original_dir

    assert payload["intent"] == "analysis_molecular_medication_compare"
    context = payload["data"]["context"]
    assert context["scope_patient_count"] == 2
    comparison = context["comparisons"][0]
    assert comparison["scoped_patient_ids_a"] == ["SYN001"]
    assert comparison["scoped_patient_ids_b"] == ["SYN006"]
    volcano_point = comparison["exploratory_volcano_points"][0]
    assert volcano_point["sample_count_a"] == 1
    assert volcano_point["sample_count_b"] == 1


def test_analysis_molecular_medication_comparison_derives_patient_scope_from_sample_ids(tmp_path):
    write_json(
        tmp_path,
        "records.json",
        [
            {"id": "SYN001:week_0", "patient_id": "SYN001", "info": {"event_date": "2024-01-01"}, "treatments": [{"treatmentCode": {"label": "Infliximab"}}]},
            {"id": "SYN002:week_0", "patient_id": "SYN002", "info": {"event_date": "2024-01-01"}, "treatments": [{"treatmentCode": {"label": "Infliximab"}}]},
            {"id": "SYN003:week_0", "patient_id": "SYN003", "info": {"event_date": "2024-01-01"}, "treatments": [{"treatmentCode": {"label": "Infliximab"}}]},
            {"id": "SYN004:week_0", "patient_id": "SYN004", "info": {"event_date": "2024-01-01"}, "treatments": [{"treatmentCode": {"label": "Ustekinumab"}}]},
            {"id": "SYN005:week_0", "patient_id": "SYN005", "info": {"event_date": "2024-01-01"}, "treatments": [{"treatmentCode": {"label": "Ustekinumab"}}]},
        ],
    )

    original_dir = query_store_module.MOLECULAR_DATA_DIR
    molecular_dir = tmp_path / "molecular"
    molecular_dir.mkdir()
    (molecular_dir / "synthetic_transcriptome_raw_counts_infliximab.csv").write_text(
        "\n".join(
            [
                "gene_id;SYN001:week_0;SYN002:week_0;SYN003:week_0",
                "ENSG00000169429;1400;1300;1200",
                "ENSG00000170421;150;160;170",
            ]
        ),
        encoding="utf-8",
    )
    (molecular_dir / "synthetic_transcriptome_raw_counts_ustekinumab.csv").write_text(
        "\n".join(
            [
                "gene_id;SYN004:week_0;SYN005:week_0",
                "ENSG00000169429;150;160",
                "ENSG00000170421;1200;1250",
            ]
        ),
        encoding="utf-8",
    )
    query_store_module.MOLECULAR_DATA_DIR = molecular_dir
    try:
        payload = analysis_module.analysis_llm_reply(
            "Explain differences in gene expression according to medication",
            str(tmp_path),
            selected_patient_ids="SYN001:week_0,SYN002:week_0,SYN003:week_0",
            compare_mode=True,
            compare_selected_patient_ids="SYN004:week_0,SYN005:week_0",
        )
    finally:
        query_store_module.MOLECULAR_DATA_DIR = original_dir

    assert payload["intent"] == "analysis_molecular_medication_compare"
    context = payload["data"]["context"]
    assert context["scope_patient_count"] == 5
    comparison = context["comparisons"][0]
    assert comparison["medication_a"] == "Infliximab"
    assert comparison["medication_b"] == "Ustekinumab"
    assert comparison["scoped_patient_ids_a"] == ["SYN001", "SYN002", "SYN003"]
    assert comparison["scoped_patient_ids_b"] == ["SYN004", "SYN005"]


def test_analysis_compare_follow_up_prompt_does_not_raise_name_error(tmp_path):
    write_json(
        tmp_path,
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
                "event_date": "2024-01-08",
                "diseases": [{"diseaseCode": {"label": "Crohn Disease"}}],
                "treatments": [{"treatmentCode": {"label": "Infliximab"}}],
            },
            {
                "id": "SYN003:week_0",
                "patient_id": "SYN003",
                "event_date": "2024-01-01",
                "diseases": [{"diseaseCode": {"label": "Crohn Disease"}}],
                "treatments": [{"treatmentCode": {"label": "Ustekinumab"}}],
            },
            {
                "id": "SYN004:week_0",
                "patient_id": "SYN004",
                "event_date": "2024-01-08",
                "diseases": [{"diseaseCode": {"label": "Crohn Disease"}}],
                "treatments": [{"treatmentCode": {"label": "Ustekinumab"}}],
            },
        ],
    )

    payload = analysis_module.analysis_llm_reply(
        "Can you explain the plot?",
        str(tmp_path),
        selected_patient_ids="SYN001,SYN002",
        compare_mode=True,
        compare_selected_patient_ids="SYN003,SYN004",
        deterministic_only=True,
        history=[
            {"role": "user", "content": "Compare relapse-free survival between Cohort A and Cohort B."},
            {"role": "assistant", "content": "Kaplan-Meier comparison completed."},
        ],
    )

    assert payload["intent"] == "analysis_compare"
    assert payload["data"]["source"] == "deterministic"
    assert "Deterministic Comparison Summary" in payload["reply"]


def test_routes_index_and_dataset_helpers(monkeypatch, tmp_path):
    class DummyTemplates:
        def TemplateResponse(self, request, name, context):
            return {"template": name, "context": context}

    dataset_root = tmp_path / "dataset-a"
    dataset_root.mkdir()
    source_file = dataset_root / "clinical" / "records.json"
    source_file.parent.mkdir()
    source_file.write_text("[]", encoding="utf-8")

    monkeypatch.setattr(routes_module, "templates", DummyTemplates())
    monkeypatch.setattr(routes_module, "branding_settings", lambda: {"product_name": "PN"})
    monkeypatch.setattr(routes_module, "authorized_datasets_for_user", lambda user: [{"dataset_id": "dataset-a", "name": "Dataset A", "root_path": str(dataset_root)}])
    monkeypatch.setattr(routes_module, "resolve_dataset", lambda request, dataset_id="": {"dataset_id": "dataset-a"})
    monkeypatch.setattr(routes_module, "resolve_dataset_dir", lambda request, key: f"/resolved/{key or 'default'}")
    monkeypatch.setattr(routes_module, "current_dataset_id", lambda user_id="": "current-dataset")
    monkeypatch.setattr(routes_module, "request_user_id", lambda request: "u1")

    monkeypatch.setattr(routes_module, "auth_enabled", lambda: False)
    payload = routes_module.index(make_request())
    assert payload["template"] == "index.html"
    assert payload["context"]["auth_enabled"] is False
    assert payload["context"]["current_dataset_id"] == "dataset-a"

    monkeypatch.setattr(routes_module, "auth_enabled", lambda: True)
    monkeypatch.setattr(routes_module, "session_user", lambda request: {"username": "analyst"})
    payload = routes_module.index(make_request({"username": "analyst"}))
    assert payload["context"]["auth_enabled"] is True
    assert payload["context"]["datasets"][0]["dataset_id"] == "dataset-a"

    provenance = routes_module._dataset_provenance_from_sources(
        make_request({"username": "analyst"}),
        [str(source_file)],
    )
    assert provenance["dataset_ids"] == ["dataset-a"]
    assert provenance["dataset_name"] == "Dataset A"
    assert routes_module._resolve_route_dataset_dir(None, dataset_id="dataset-a") == "/resolved/dataset-a"
    assert routes_module._resolve_route_dataset_dir(make_request(), dataset_id="", data_dir="workspace") == "/resolved/workspace"


def test_dataset_admin_routes_map_value_errors_to_http_400(monkeypatch):
    monkeypatch.setattr(routes_module, "require_admin", lambda request: {"username": "admin"})
    monkeypatch.setattr(routes_module, "register_dataset", lambda **kwargs: (_ for _ in ()).throw(ValueError("bad dataset")))
    monkeypatch.setattr(routes_module, "update_dataset", lambda dataset_id, **kwargs: (_ for _ in ()).throw(ValueError("bad update")))

    create_payload = routes_module.DatasetRegistrationRequest(dataset_id="d1", name="Dataset", root_path="/tmp/data")
    update_payload = routes_module.DatasetUpdateRequest(name="Dataset")

    with pytest.raises(HTTPException) as create_exc:
        routes_module.create_dataset_route(create_payload, make_request({"username": "admin"}))
    with pytest.raises(HTTPException) as update_exc:
        routes_module.update_dataset_route("d1", update_payload, make_request({"username": "admin"}))

    assert create_exc.value.status_code == 400
    assert update_exc.value.status_code == 400


def test_auth_and_saved_cohort_route_wrappers_cover_common_error_paths(monkeypatch):
    monkeypatch.setattr(routes_module, "auth_enabled", lambda: False)
    assert routes_module.login_local(make_request(), routes_module.LoginRequest(username="u", password="p")) == {
        "enabled": False,
        "authenticated": True,
    }

    monkeypatch.setattr(routes_module, "branding_logo_path", lambda: None)
    with pytest.raises(HTTPException) as logo_exc:
        routes_module.get_branding_logo()
    assert logo_exc.value.status_code == 404

    monkeypatch.setattr(routes_module, "reset_local_user_password", lambda username, password: (_ for _ in ()).throw(ValueError("bad password")))
    with pytest.raises(HTTPException) as reset_exc:
        routes_module.reset_auth_user_password("u1", routes_module.AuthPasswordResetRequest(password="secret"), make_request())
    assert reset_exc.value.status_code == 400

    monkeypatch.setattr(routes_module, "delete_local_user", lambda username: (_ for _ in ()).throw(ValueError("User not found.")))
    with pytest.raises(HTTPException) as delete_exc:
        routes_module.delete_auth_user("ghost", make_request())
    assert delete_exc.value.status_code == 404

    monkeypatch.setattr(routes_module, "require_authenticated", lambda request: {"username": "u1"})
    monkeypatch.setattr(routes_module, "request_user_id", lambda request: "u1")
    monkeypatch.setattr(routes_module, "list_sessions_referencing_saved_cohort", lambda cohort_id, user_id="": [{"title": "Session A"}])
    with pytest.raises(HTTPException) as conflict_exc:
        routes_module.remove_saved_cohort("c1", make_request({"username": "u1"}))
    assert conflict_exc.value.status_code == 409

    monkeypatch.setattr(routes_module, "list_sessions_referencing_saved_cohort", lambda cohort_id, user_id="": [])
    monkeypatch.setattr(routes_module, "delete_saved_cohort", lambda cohort_id, user_id="": False)
    with pytest.raises(HTTPException) as missing_exc:
        routes_module.remove_saved_cohort("c1", make_request({"username": "u1"}))
    assert missing_exc.value.status_code == 404


def test_query_analysis_and_dashboard_route_wrappers_map_file_not_found(monkeypatch):
    request = make_request({"username": "u1"})
    monkeypatch.setattr(routes_module, "require_authenticated", lambda req: {"username": "u1"})
    monkeypatch.setattr(routes_module, "resolve_dataset_ids", lambda request, key="": ["default"])
    monkeypatch.setattr(routes_module, "resolve_dataset_dir", lambda request, key: "/resolved/data")
    monkeypatch.setattr(routes_module, "effective_query_granularity_ceiling", lambda dataset_ids: "detailed")
    monkeypatch.setattr(routes_module, "effective_ai_provider_access", lambda dataset_ids: "detailed_allowed")
    monkeypatch.setattr(routes_module, "answer_query", lambda *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError("missing query data")))
    monkeypatch.setattr(routes_module, "analysis_llm_reply", lambda *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError("missing analysis data")))
    monkeypatch.setattr(routes_module, "molecular_dataset_inventory", lambda data_dir: (_ for _ in ()).throw(FileNotFoundError("missing molecular data")))
    monkeypatch.setattr(routes_module, "molecular_gene_inventory", lambda *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError("missing genes")))
    monkeypatch.setattr(routes_module, "molecular_expression_summary", lambda *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError("missing expression")))
    monkeypatch.setattr(routes_module, "dashboard_summary", lambda data_dir: (_ for _ in ()).throw(FileNotFoundError("missing dashboard data")))
    monkeypatch.setattr(routes_module, "_resolve_route_dataset_dir", lambda request, dataset_id="", data_dir="": "/resolved/data")

    query_payload = routes_module.QueryRequest(q="hello")
    analysis_payload = routes_module.AnalysisRequest(prompt="explain")
    expression_payload = routes_module.MolecularExpressionRequest(dataset_name="rna", gene_id="TP53")

    with pytest.raises(HTTPException) as query_exc:
        routes_module.query_app_post(query_payload, request)
    with pytest.raises(HTTPException) as analysis_exc:
        routes_module.analysis_app(analysis_payload, request)
    with pytest.raises(HTTPException) as datasets_exc:
        routes_module.get_molecular_datasets(request)
    with pytest.raises(HTTPException) as genes_exc:
        routes_module.get_molecular_genes("rna", request)
    with pytest.raises(HTTPException) as expression_exc:
        routes_module.get_molecular_expression(expression_payload, request)
    with pytest.raises(HTTPException) as dashboard_exc:
        routes_module.get_dashboard(request)

    assert query_exc.value.status_code == 404
    assert analysis_exc.value.status_code == 404
    assert datasets_exc.value.status_code == 404
    assert genes_exc.value.status_code == 404
    assert expression_exc.value.status_code == 404
    assert dashboard_exc.value.status_code == 404


def test_analysis_session_and_pheno_route_wrappers_enforce_expected_guards(monkeypatch):
    request = make_request({"username": "u1"})
    monkeypatch.setattr(routes_module, "require_authenticated", lambda req: {"username": "u1"})
    monkeypatch.setattr(routes_module, "request_user_id", lambda request: "u1")
    monkeypatch.setattr(routes_module, "save_analysis_session", lambda payload, user_id="": (_ for _ in ()).throw(ValueError("bad session")))
    monkeypatch.setattr(routes_module, "rename_analysis_session", lambda session_id, title, user_id="": None)
    monkeypatch.setattr(routes_module, "delete_analysis_session", lambda session_id, user_id="": False)
    monkeypatch.setattr(routes_module, "resolve_dataset_ids", lambda request, key="": ["summary-dataset"])
    monkeypatch.setattr(routes_module, "effective_query_granularity_ceiling", lambda dataset_ids: "summary")

    session_payload = routes_module.AnalysisSessionRequest(id="s1", title="Test", messages=[])
    rename_payload = routes_module.AnalysisSessionRenameRequest(title="Renamed")
    pheno_payload = routes_module.PhenoRankerRequest(action="compare", mode="cohort", data_dir="/tmp/data")

    with pytest.raises(HTTPException) as save_exc:
        routes_module.create_or_update_analysis_session(session_payload, request)
    with pytest.raises(HTTPException) as rename_exc:
        routes_module.update_analysis_session_title("s1", rename_payload, request)
    with pytest.raises(HTTPException) as remove_exc:
        routes_module.remove_analysis_session("s1", request)
    with pytest.raises(HTTPException) as pheno_run_exc:
        routes_module.run_pheno_ranker_route(pheno_payload, request)
    with pytest.raises(HTTPException) as pheno_ids_exc:
        routes_module.get_pheno_ranker_patient_ids(request)

    assert save_exc.value.status_code == 400
    assert rename_exc.value.status_code == 404
    assert remove_exc.value.status_code == 404
    assert pheno_run_exc.value.status_code == 403
    assert pheno_ids_exc.value.status_code == 403


def test_pheno_helper_normalization_and_matching_utilities(tmp_path):
    write_json(
        tmp_path,
        "records.json",
        [
            {
                "id": "SYN001:week_0",
                "patient_id": "SYN001",
                "diseases": [{"diseaseCode": {"label": "Crohn Disease"}}],
            },
            {
                "id": "SYN002:week_0",
                "patient_id": "SYN002",
                "diseases": [{"diseaseCode": {"label": "Ulcerative Colitis"}}],
            },
        ],
    )

    assert pheno_module._normalize_pheno_ai_provider_access("restricted") == "safe_summary"
    assert pheno_module._normalize_pheno_ai_provider_access("use_thread_mode") == "detailed_allowed"
    assert pheno_module._pheno_ai_provider_context_granularity("blocked") == "blocked"
    assert pheno_module._pheno_ai_provider_context_granularity("safe_summary") == "safe_summary"
    assert pheno_module._pheno_ai_provider_context_granularity("detailed_allowed") == "detailed"

    enriched = pheno_module._pheno_finalize_response(
        {"source": "lm_studio", "data": {}},
        intent="pheno_plan",
        ai_provider_access="summary_only",
        source="lm_studio",
        execution="planning",
        planner={"provider": "lm_studio"},
        provider="lm_studio",
        model="local-model",
    )
    assert enriched["intent"] == "pheno_plan"
    assert enriched["data"]["source"] == "llm"
    assert enriched["data"]["ai_provider_access"] == "safe_summary"
    assert enriched["data"]["model"] == "local-model"

    records = pheno_module.load_pheno_ranker_records(str(tmp_path))
    assert pheno_module.resolve_pheno_ranker_reference_paths(str(tmp_path))[0].name == "records.json"
    assert [item["id"] for item in pheno_module.filter_records_by_disease(records, "crohn")] == ["SYN001:week_0"]
    assert pheno_module.find_target_record(records, "SYN002")["id"] == "SYN002:week_0"
    assert pheno_module.find_target_record(records, "SYN001:week_0")["patient_id"] == "SYN001"
    assert pheno_module.find_target_record(records, "missing") is None

    assert pheno_module.normalize_pheno_term("phenotypes") == "phenotypicFeatures"
    assert pheno_module.normalize_pheno_terms("diseases and measures / treatments only") == ["diseases", "measures", "treatments"]
    assert pheno_module.normalize_pheno_metric("jaccard") == "jaccard"
    assert pheno_module.normalize_pheno_metric("cosine") == ""
    assert pheno_module.available_patient_ids(str(tmp_path)) == ["SYN001", "SYN002"]
    assert pheno_module.available_reference_ids(str(tmp_path)) == ["SYN001:week_0", "SYN002:week_0"]
    assert pheno_module.available_disease_labels(str(tmp_path)) == ["Crohn Disease", "Ulcerative Colitis"]
    assert pheno_module.extract_patient_ids_from_text("Compare SYN001 and syn002", ["SYN001", "SYN002"]) == ["SYN001", "SYN002"]
    assert pheno_module.extract_patient_like_tokens_from_text("Find matches to Beacon 5 and SYN-002") == ["Beacon_5", "SYN_002"]
    assert pheno_module.extract_disease_filter_from_text("Compare by disease Crohn Disease", ["Crohn Disease"]) == "Crohn Disease"
    assert pheno_module.extract_disease_filter_from_text("Compare with disease ulcerative colitis", []) == "ulcerative colitis"
    assert pheno_module.is_non_actionable_pheno_request("hello") is True
    assert pheno_module.is_non_actionable_pheno_request("compare all patients by disease") is False


def test_pheno_scope_expansion_and_deterministic_plan_helpers(tmp_path):
    write_json(
        tmp_path,
        "records.json",
        [
            {
                "id": "SYN001:week_0",
                "patient_id": "SYN001",
                "diseases": [{"diseaseCode": {"label": "Crohn Disease"}}],
            },
            {
                "id": "SYN001:week_2",
                "patient_id": "SYN001",
                "diseases": [{"diseaseCode": {"label": "Crohn Disease"}}],
            },
            {
                "id": "SYN002:week_0",
                "patient_id": "SYN002",
                "diseases": [{"diseaseCode": {"label": "Ulcerative Colitis"}}],
            },
        ],
    )

    records = pheno_module.load_pheno_ranker_records(str(tmp_path))
    expanded = pheno_module.expand_scope_ids_to_record_ids(records, ["SYN001", "SYN002:week_0", "MISSING"])
    assert expanded == {
        "record_ids": ["SYN001:week_0", "SYN001:week_2", "SYN002:week_0"],
        "invalid_ids": ["MISSING"],
        "expanded_patient_ids": ["SYN001"],
        "expanded_record_count": 3,
    }

    patient_plan = pheno_module.plan_pheno_ranker_deterministic(
        "Find closest matches to SYN001 by disease and phenotype",
        str(tmp_path),
    )
    assert patient_plan["plan"]["mode"] == "patient"
    assert patient_plan["plan"]["patient_id"] == "SYN001"
    assert patient_plan["plan"]["align"] is True
    assert patient_plan["plan"]["include_terms"] == ["diseases", "phenotypicFeatures"]

    extract_plan = pheno_module.plan_pheno_ranker_deterministic(
        "Extract patients with disease Crohn Disease",
        str(tmp_path),
        selected_patient_ids="SYN001,SYN002",
    )
    assert extract_plan["plan"]["action"] == "extract"
    assert extract_plan["plan"]["mode"] == "cohort"
    assert extract_plan["plan"]["selected_patient_ids"] == "SYN001,SYN002"
    assert extract_plan["plan"]["render_heatmap"] is False
    assert extract_plan["plan"]["render_mds"] is False
    assert extract_plan["plan"]["render_graph"] is False

    graph_plan = pheno_module.plan_pheno_ranker_deterministic(
        "Compare all patients and render a cytoscape graph network",
        str(tmp_path),
    )
    assert graph_plan["plan"]["render_graph"] is True

    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    with pytest.raises(FileNotFoundError):
        pheno_module.resolve_pheno_ranker_reference_paths(str(empty_dir))


def test_pheno_execution_steps_attach_and_llm_planner(monkeypatch, tmp_path):
    assert pheno_module.pheno_execution_steps({"action": "extract", "selected_patient_ids": "SYN001"}) == [
        "Extract the current scope from the active reference files with jq into one subset JSON."
    ]
    assert pheno_module.pheno_execution_steps({"action": "extract", "selected_patient_ids": ""}) == [
        "Extract requires a non-empty scope."
    ]
    assert pheno_module.pheno_execution_steps({"action": "compare", "mode": "cohort", "selected_patient_ids": "SYN001"}) == [
        "Extract the current scope from the active reference files with jq into one subset JSON.",
        "Run cohort comparison on the extracted subset reference.",
    ]
    assert pheno_module.pheno_execution_steps({"action": "compare", "mode": "cohort", "selected_patient_ids": ""}) == [
        "Run cohort comparison directly on the full reference cohort."
    ]
    assert pheno_module.pheno_execution_steps({"action": "compare", "mode": "patient", "patient_id": "SYN001"}) == [
        "Extract target patient SYN001 from the active reference files with jq.",
        "Run patient-vs-reference ranking with -r -t.",
    ]
    assert pheno_module.pheno_execution_steps({"action": "compare", "mode": "patient", "patient_id": ""}) == [
        "Patient mode requires exactly one target patient from Patient ID or Scope."
    ]
    assert pheno_module.attach_execution_steps({"plan": {"action": "extract", "selected_patient_ids": "SYN001"}})["plan"]["execution_steps"]
    assert pheno_module.attach_execution_steps({"plan": None}) == {"plan": None}

    write_json(
        tmp_path,
        "records.json",
        [
            {"id": "SYN001:week_0", "patient_id": "SYN001", "diseases": [{"diseaseCode": {"label": "Crohn Disease"}}]},
            {"id": "SYN002:week_0", "patient_id": "SYN002", "diseases": [{"diseaseCode": {"label": "Ulcerative Colitis"}}]},
        ],
    )

    monkeypatch.setattr(pheno_module, "lm_studio_enabled", lambda: False)
    assert pheno_module.plan_pheno_ranker_llm("compare cohort", str(tmp_path)) is None
    monkeypatch.setattr(pheno_module, "lm_studio_enabled", lambda: True)
    monkeypatch.setattr(pheno_module, "resolve_lm_studio_model", lambda: "")
    assert pheno_module.plan_pheno_ranker_llm("compare cohort", str(tmp_path)) is None

    monkeypatch.setattr(pheno_module, "resolve_lm_studio_model", lambda: "local-model")
    monkeypatch.setattr(pheno_module, "lm_studio_base_url", lambda: "http://lm")

    def fake_http_json(url, payload=None, log_kind="generic"):
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "action": "compare",
                                "mode": "patient",
                                "patient_id": "SYN001",
                                "include_terms": ["diseases", "phenotypes"],
                                "exclude_terms": ["measures"],
                                "similarity_metric_cohort": "jaccard",
                                "sort_by": "hamming",
                                "align": True,
                                "render_heatmap": True,
                                "render_mds": False,
                                "render_graph": True,
                                "reasoning": "Planned by LM Studio.",
                            }
                        )
                    }
                }
            ]
        }

    monkeypatch.setattr(pheno_module, "http_json", fake_http_json)
    llm_plan = pheno_module.plan_pheno_ranker_llm("compare cohort", str(tmp_path))
    assert llm_plan["source"] == "lm_studio"
    assert llm_plan["plan"]["mode"] == "patient"
    assert llm_plan["plan"]["include_terms"] == ["diseases", "phenotypicFeatures"]
    assert llm_plan["plan"]["exclude_terms"] == ["measures"]
    assert llm_plan["plan"]["render_mds"] is False
    assert llm_plan["plan"]["render_graph"] is False


def test_pheno_rank_and_alignment_helper_stack(tmp_path):
    job_dir = tmp_path / "job1"
    job_dir.mkdir()
    (job_dir / "rank.txt").write_text(
        "REFERENCE(ID)\tTARGET(ID)\tJACCARD-INDEX\tINTERSECT\tTARGET-VARS\tREFERENCE-VARS\tINTERSECT-RATE(%)\tCOMPLETENESS(%)\tHAMMING-DISTANCE\tLENGTH\n"
        "SYN010\tTARGET1\t0.82\t8\t10\t9\t80\t88.89\t2\t11\n"
        "SYN011\tTARGET1\t0.55\t5\t10\t8\t50\t62.5\t4\t12\n",
        encoding="utf-8",
    )
    (job_dir / "alignment.target.csv").write_text(
        "id;json-path;label;indicator;weight;hamming-distance;ref;tar\n"
        "SYN010;diseases.label;Crohn Disease;1;1;0;1;1\n"
        "SYN010;treatments.label;Infliximab;1;1;0;1;0\n"
        "SYN010;phenotypicFeatures.label;Abdominal pain;1;1;0;0;1\n",
        encoding="utf-8",
    )

    headers, rows = pheno_module.read_rank_rows(job_dir)
    assert headers[:2] == ["REFERENCE(ID)", "TARGET(ID)"]
    assert len(rows) == 2
    metric_headers = pheno_module.detect_rank_metric_columns(headers, rows)
    assert "JACCARD-INDEX" in metric_headers
    assert pheno_module.alignment_bucket_from_json_path("interventionsOrProcedures.label") == "procedures"
    assert pheno_module.parse_float("1.25") == 1.25
    assert pheno_module.parse_float("x") is None
    assert pheno_module.describe_jaccard(0.95) == "very high overlap"
    assert pheno_module.describe_jaccard(0.8) == "high overlap"
    assert pheno_module.describe_jaccard(0.6) == "moderate overlap"
    assert pheno_module.describe_jaccard(0.2) == "limited overlap"
    highlights = pheno_module.build_rank_metric_highlights(rows[0])
    assert "Jaccard index 0.820 indicates high overlap." in highlights[0]

    alignment_rows = pheno_module.load_alignment_rows(job_dir)
    summary = pheno_module.summarize_alignment_for_reference(alignment_rows, "SYN010")
    assert summary["shared_count"] == 1
    assert summary["reference_only_count"] == 1
    assert summary["target_only_count"] == 1

    explained = pheno_module.explain_pheno_ranker_results(job_dir, top_n=1)
    assert explained["source"] == "deterministic"
    assert explained["alignment_available"] is True
    assert explained["top_n"] == 1
    assert explained["matches"][0]["alignment"]["shared_bucket_counts"]["diseases"] == 1


def test_pheno_llm_explain_and_wrapper_metadata(monkeypatch, tmp_path):
    deterministic_payload = {
        "job_id": "job1",
        "mode": "patient",
        "target_id": "TARGET1",
        "top_n": 1,
        "alignment_available": True,
        "metric_headers": ["JACCARD-INDEX"],
        "metric_definitions": {"JACCARD-INDEX": "Overlap"},
        "matches": [
            {
                "reference_id": "SYN010",
                "metrics": {"JACCARD-INDEX": "0.82"},
                "metric_highlights": ["Jaccard index 0.820 indicates high overlap."],
                "alignment": {
                    "shared_bucket_counts": {"diseases": 1},
                    "top_shared_items": [{"label": "Crohn Disease", "bucket": "diseases"}],
                    "top_reference_only_items": [{"label": "Infliximab", "bucket": "treatments"}],
                    "top_target_only_items": [{"label": "Abdominal pain", "bucket": "phenotypicFeatures"}],
                },
            }
        ],
        "summary_lines": ["Top 1 matches for TARGET1 from rank.txt."],
        "source": "deterministic",
    }
    monkeypatch.setattr(pheno_module, "explain_pheno_ranker_results", lambda job_dir, top_n=3: deterministic_payload)
    monkeypatch.setattr(pheno_module, "resolve_pheno_ranker_job_dir", lambda job_id, user_id="": tmp_path / job_id)

    monkeypatch.setattr(pheno_module, "lm_studio_enabled", lambda: False)
    unavailable = pheno_module.explain_pheno_ranker_results_llm(tmp_path / "job1")
    assert unavailable["source"] == "llm_unavailable"

    monkeypatch.setattr(pheno_module, "lm_studio_enabled", lambda: True)
    monkeypatch.setattr(pheno_module, "resolve_lm_studio_model", lambda: "")
    no_model = pheno_module.explain_pheno_ranker_results_llm(tmp_path / "job1")
    assert no_model["source"] == "llm_unavailable"

    monkeypatch.setattr(pheno_module, "resolve_lm_studio_model", lambda: "local-model")
    monkeypatch.setattr(pheno_module, "lm_studio_base_url", lambda: "http://lm")
    monkeypatch.setattr(pheno_module, "http_json", lambda *args, **kwargs: {"error": "boom"})
    explicit_error = pheno_module.explain_pheno_ranker_results_llm(tmp_path / "job1")
    assert explicit_error["source"] == "llm_error"

    monkeypatch.setattr(pheno_module, "http_json", lambda *args, **kwargs: {"choices": [{"message": {"content": "  Explanation  "}}]})
    success = pheno_module.explain_pheno_ranker_results_llm(tmp_path / "job1")
    assert success["source"] == "lm_studio"
    assert success["model"] == "local-model"
    assert success["llm_reply"] == "Explanation"

    explain_blocked = pheno_module.pheno_ranker_explain_llm("job1", ai_provider_access="blocked")
    assert explain_blocked["data"]["source"] == "deterministic"
    assert explain_blocked["data"]["ai_provider_access"] == "blocked"

    monkeypatch.setattr(pheno_module, "explain_pheno_ranker_results_llm", lambda job_dir, top_n=3: {"source": "lm_studio", "model": "local-model"})
    explain_allowed = pheno_module.pheno_ranker_explain_llm("job1", ai_provider_access="detailed_allowed")
    assert explain_allowed["data"]["source"] == "llm"
    assert explain_allowed["data"]["provider"] == "lm_studio"


def test_pheno_result_serialization_and_file_helpers(monkeypatch, tmp_path):
    job_dir = tmp_path / "job42"
    job_dir.mkdir()
    (job_dir / "rank.txt").write_text("data", encoding="utf-8")
    (job_dir / "other.txt").write_text("x", encoding="utf-8")

    proc = SimpleNamespace(returncode=0, stdout="ok", stderr="")
    payload = pheno_module.serialize_pheno_result(
        job_dir,
        ["pheno-ranker", "-r", "ref.json"],
        proc,
        "cohort",
        [{"script": "mds_points", "returncode": "0"}],
        similarity_metric_cohort="jaccard",
        pre_commands=["jq ..."],
        scope_expansion_note="expanded scope",
    )
    assert payload["job_id"] == "job42"
    assert payload["plots"][0]["script"] == "mds_points"
    assert payload["files"][0]["url"].startswith("/pheno-ranker/results/job42/")

    monkeypatch.setattr(pheno_module, "PHENO_RANKER_RUNS_DIR", tmp_path)
    assert pheno_module.resolve_pheno_ranker_job_dir("job42") == job_dir
    with pytest.raises(HTTPException):
        pheno_module.resolve_pheno_ranker_job_dir("../escape")
    assert pheno_module.pheno_ranker_result_file_path("job42", "rank.txt") == job_dir / "rank.txt"
    with pytest.raises(HTTPException):
        pheno_module.pheno_ranker_result_file_path("job42", "../secret.txt")

    monkeypatch.setattr(
        pheno_module,
        "load_alignment_rows",
        lambda job_dir: [
            {"reference_id": "SYN010", "bucket": "diseases", "ref_present": True, "target_present": True},
            {"reference_id": "SYN010", "bucket": "treatments", "ref_present": True, "target_present": False},
            {"reference_id": "SYN010", "bucket": "measures", "ref_present": False, "target_present": True},
        ],
    )
    details = pheno_module.pheno_ranker_alignment_details("job42", "SYN010", target_id="TARGET1")
    assert details["shared_bucket_counts"] == {"diseases": 1}
    assert details["reference_only_bucket_counts"] == {"treatments": 1}
    assert details["target_only_bucket_counts"] == {"measures": 1}


def test_query_policy_normalization_and_provider_granularity_helpers():
    assert query_policy_module.normalize_query_granularity_mode("Summary") == "summary"
    assert query_policy_module.normalize_query_granularity_mode("weird") == "detailed"
    assert query_policy_module.normalize_query_granularity_ceiling("summary") == "summary"
    assert query_policy_module.normalize_query_granularity_ceiling("Detailed") == "detailed"

    assert query_policy_module.normalize_ai_provider_access("use_thread_mode") == "detailed_allowed"
    assert query_policy_module.normalize_ai_provider_access("restricted") == "safe_summary"
    assert query_policy_module.normalize_ai_provider_access("blocked") == "blocked"
    assert query_policy_module.normalize_ai_provider_access("unknown") == "detailed_allowed"

    assert query_policy_module.ai_provider_granularity_mode("detailed", "safe_summary") == "summary"
    assert query_policy_module.ai_provider_granularity_mode("detailed", "blocked") == "detailed"
    assert query_policy_module.ai_provider_context_granularity("detailed", "blocked") == "blocked"
    assert query_policy_module.ai_provider_context_granularity("detailed", "safe_summary") == "safe_summary"
    assert query_policy_module.ai_provider_context_granularity("summary", "detailed_allowed") == "summary"


def test_query_policy_action_context_summary_shaping_and_finalization():
    payload = {
        "query": "Which patients have Crohn Disease?",
        "intent": "disease_cohort",
        "reply": "Patients: P1, P2",
        "data": {
            "patient_ids": ["P1", "P2"],
            "sample_ids": ["P1:week_0", "P2:week_0"],
            "patient_count": 2,
            "patients": [
                {"patient_id": "P1", "original_record_ids": ["P1:week_0"]},
                {"patient_id": "P2", "original_record_ids": ["P2:week_0"]},
            ],
            "patient_context": {"foo": "bar"},
            "timeline": [{"x": 1}],
            "visits": [{"visit_id": "v1"}],
        },
    }

    action_context = query_policy_module.query_action_context(payload)
    assert action_context["patient_ids"] == ["P1", "P2"]
    assert action_context["record_ids"] == ["P1:week_0", "P2:week_0"]
    assert action_context["id_type"] == "sample"

    actions = query_policy_module.query_available_actions(payload, "detailed")
    assert actions == {
        "open_in_analysis": True,
        "save_cohort": True,
        "copy_patient_ids": True,
        "use_in_pheno_ranker": True,
    }
    assert query_policy_module.redact_action_context(action_context, "summary") == {
        "patient_ids": [],
        "record_ids": [],
        "id_type": "",
        "analysis_prompt": "",
    }

    shaped = query_policy_module.shape_summary_response(payload)
    assert shaped["reply"] == "2 patients match this query."
    assert shaped["data"]["patient_count"] == 2
    assert "patients" not in shaped["data"]
    assert "patient_context" not in shaped["data"]
    assert "timeline" not in shaped["data"]

    finalized = query_policy_module.finalize_query_response(payload, "detailed", "summary", "restricted")
    assert finalized["data"]["granularity_requested"] == "detailed"
    assert finalized["data"]["granularity_applied"] == "summary"
    assert finalized["data"]["external_llm_allowed"] is True
    assert finalized["data"]["ai_provider_access"] == "safe_summary"
    assert finalized["data"]["ai_provider_context_granularity"] == "safe_summary"
    assert finalized["data"]["available_actions"] == {
        "open_in_analysis": False,
        "save_cohort": False,
        "copy_patient_ids": False,
        "use_in_pheno_ranker": False,
    }
    assert finalized["action_context"]["patient_ids"] == []


def test_query_policy_patient_detail_summary_mode_response():
    payload = {
        "query": "Show patient SYN001",
        "intent": "patient_summary",
        "reply": "Detailed patient view",
        "data": {"patient_id": "SYN001", "patient_context": {"id": "SYN001"}},
    }

    shaped = query_policy_module.shape_summary_response(payload)
    assert shaped["intent"] == "patient_summary"
    assert "not available in Summary mode" in shaped["reply"]
    assert shaped["data"]["patient_id"] == "SYN001"
    assert shaped["data"]["follow_up_suggestions"] == [
        "How many patients are in this workspace?",
        "Which patients have more than 1 medication?",
    ]


def test_query_scope_helpers_cover_inventory_scope_and_buckets(tmp_path):
    write_json(
        tmp_path,
        "records.json",
        [
            {
                "id": "SYN001:week_0",
                "patient_id": "SYN001",
                "diseases": [{"diseaseCode": {"label": "Crohn Disease"}}],
            },
            {
                "id": "SYN001:week_2",
                "patient_id": "SYN001",
                "diseases": [{"diseaseCode": {"label": "Crohn Disease"}}],
            },
            {
                "id": "SYN002:week_0",
                "patient_id": "SYN002",
                "diseases": [{"diseaseCode": {"label": "Ulcerative Colitis"}}],
            },
        ],
    )

    rows = [
        {
            "patient_id": "SYN001",
            "diseases": ["Crohn Disease", "Crohn Disease"],
            "medications": ["Infliximab"],
            "original_record_ids": ["SYN001:week_0", "SYN001:week_2"],
        },
        {
            "patient_id": "SYN002",
            "diseases": ["Ulcerative Colitis"],
            "medications": ["Vedolizumab"],
            "original_record_ids": ["SYN002:week_0"],
        },
    ]

    assert query_scope_module.patient_inventory_from_records(str(tmp_path)) == ["SYN001", "SYN002"]
    assert query_scope_module.patient_inventory_from_records(str(tmp_path), ["SYN001"]) == ["SYN001"]
    assert query_scope_module.sample_inventory_from_records(str(tmp_path)) == ["SYN001:week_0", "SYN001:week_2", "SYN002:week_0"]
    assert query_scope_module.sample_inventory_from_records(str(tmp_path), ["SYN002"]) == ["SYN002:week_0"]

    assert query_scope_module.apply_patient_scope_to_rows(rows, ["SYN002"]) == [rows[1]]
    cohort = {"patients": rows, "patient_count": 2}
    scoped_cohort = query_scope_module.apply_patient_scope_to_cohort(cohort, ["SYN001"])
    assert scoped_cohort["patient_count"] == 1
    assert scoped_cohort["patient_ids"] == ["SYN001"]
    assert scoped_cohort["original_record_ids"] == ["SYN001:week_0", "SYN001:week_2"]

    disease_buckets = query_scope_module.bucket_counts_from_rows(rows, "diseases", "disease")
    medication_buckets = query_scope_module.bucket_counts_from_rows(rows, "medications", "medication")
    assert disease_buckets[0]["disease"] == "Crohn Disease"
    assert disease_buckets[0]["patient_count"] == 2
    assert medication_buckets[0]["medication"] == "Infliximab"

    context = query_scope_module.build_query_scope_context(str(tmp_path), rows, ["SYN001"])
    assert context.patient_ids == ["SYN001"]
    assert context.sample_ids == ["SYN001:week_0", "SYN001:week_2"]
    assert context.disease_counts[0]["disease"] == "Crohn Disease"
    assert context.medication_counts[0]["medication"] == "Infliximab"
