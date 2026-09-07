import json
import pytest
from fastapi import HTTPException
import app.routes as routes_module
from bff_test_helpers import make_request
from bff_test_helpers import write_json
import app.query_store as query_store_module
from app.main import app
from fastapi.testclient import TestClient
from bff_test_helpers import isolate_auth_store
from contextlib import nullcontext
import app.datasets as datasets_module
import app.user_state as user_state_module
import app.query as query_module
import app.query_scope as query_scope_module
from app.query import answer_query


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
    assert "patient_ids" not in payload["data"]
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
    assert "patient_ids" not in payload["data"]
    assert payload["data"]["patient_count"] == 2
    assert payload["reply"] == "2 patients match this query."


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
    assert "patient_ids" not in payload["data"]
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
    assert "patient_ids" not in payload["data"]
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
    assert "patient_ids" not in payload["data"]
    assert payload["data"]["patient_count"] == 2


def test_deterministic_patient_inventory_prefers_patient_ids_over_sample_ids(tmp_path):
    clinical_dir = tmp_path / "clinical"
    clinical_dir.mkdir()
    write_json(
        clinical_dir,
        "records.json",
        [
            {
                "id": "SYN001:week_0",
                "patient_id": "SYN001",
                "patient": {"sex": "female"},
                "treatments": [{"treatmentCode": {"label": "Example treatment"}}],
            },
            {"id": "SYN001:week_2", "patient_id": "SYN001", "patient": {"sex": "female"}},
            {"id": "SYN002:week_0", "patient_id": "SYN002", "patient": {"sex": "male"}},
        ],
    )

    payload = answer_query(str(tmp_path), "Tell me the list of patients on the cohort")

    assert payload["intent"] == "patient_inventory"
    assert payload["data"]["patient_ids"] == ["SYN001", "SYN002"]
    assert payload["data"]["patients"] == [
        {
            "patient_id": "SYN001",
            "sex": "female",
            "visit_count": 2,
            "medication_count": 1,
            "disease_count": 0,
        },
        {
            "patient_id": "SYN002",
            "sex": "male",
            "visit_count": 1,
            "medication_count": 0,
            "disease_count": 0,
        },
    ]
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


def test_query_post_accepts_granularity_mode_summary(tmp_path, monkeypatch):
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

    monkeypatch.setattr(routes_module, "resolve_dataset_ids", lambda request, key="": ["test-dataset"])
    monkeypatch.setattr(routes_module, "resolve_dataset_dir", lambda request, key: str(tmp_path))
    monkeypatch.setattr(
        routes_module,
        "_authorized_datasets_for_request",
        lambda request: [{"dataset_id": "test-dataset", "name": "Test dataset"}],
    )
    client = TestClient(app)
    response = client.post(
        "/query",
        json={
            "q": "Tell me the list of patients on the cohort",
            "dataset_id": "test-dataset",
            "granularity_mode": "summary",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["granularity_requested"] == "summary"
    assert payload["data"]["granularity_applied"] == "summary"
    assert payload["data"]["dataset_id"] == "test-dataset"
    assert payload["data"]["dataset_name"] == "Test dataset"


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
    assert "101" not in payload["reply"]
    assert "timeline" not in payload["data"]
    assert "patient_id" not in payload["data"]
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
    assert payload["reply"] == "Found 3 samples in this workspace. Browse the bounded result below."
    assert "SYN001:week_0" not in payload["reply"]


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


def test_query_route_respects_dataset_query_granularity_ceiling(tmp_path, monkeypatch):
    isolate_auth_store(monkeypatch, tmp_path)
    monkeypatch.setenv("COHORTOME_AUTH_MODE", "local")
    monkeypatch.setenv(
        "COHORTOME_LOCAL_USERS_JSON",
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
    query_store_module.prepare_dataset_query_store("maria-dataset")

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


def test_query_needs_clarification_for_short_prompt(tmp_path):
    write_json(tmp_path, "records.json", [])

    payload = answer_query(str(tmp_path), "why")
    assert payload["intent"] == "needs_clarification"
    assert "too short" in payload["reply"].lower()
    assert payload["data"]["follow_up_suggestions"]
    assert len(payload["data"]["follow_up_suggestion_metadata"]) == len(payload["data"]["follow_up_suggestions"])
    assert {item["execution_mode"] for item in payload["data"]["follow_up_suggestion_metadata"]} <= {
        "deterministic_only",
        "planner_only",
    }


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


def test_follow_up_metadata_discloses_and_pins_query_execution_mode():
    metadata = query_module._follow_up_suggestion_metadata(
        [
            "How many patients take Infliximab?",
            "How many patients take biologics?",
            "What evidence supports the main cohort summary?",
        ]
    )

    assert metadata == [
        {
            "prompt": "How many patients take Infliximab?",
            "execution_kind": "deterministic",
            "execution_mode": "deterministic_only",
            "label": "Deterministic",
        },
        {
            "prompt": "How many patients take biologics?",
            "execution_kind": "planner",
            "execution_mode": "planner_only",
            "label": "LLM-planned",
        },
        {
            "prompt": "What evidence supports the main cohort summary?",
            "execution_kind": "planner",
            "execution_mode": "planner_only",
            "label": "LLM-planned",
        },
    ]


def test_query_deterministic_only_does_not_call_ai_fallback(tmp_path, monkeypatch):
    write_json(tmp_path, "records.json", [])

    monkeypatch.setattr(
        query_module,
        "_semantic_query_plan",
        lambda *_args, **_kwargs: pytest.fail("deterministic-only query called the semantic planner"),
    )
    monkeypatch.setattr(
        query_module,
        "_lm_studio_reply",
        lambda *_args, **_kwargs: pytest.fail("deterministic-only query called the LLM fallback"),
    )

    payload = answer_query(str(tmp_path), "Explain the hidden pattern", query_mode="deterministic_only")

    assert payload["intent"] == "unsupported"
    assert payload["data"]["source"] == "deterministic"
    assert "deterministic router" in payload["reply"].lower()


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
    assert "patients" not in payload["data"]
    assert payload["reply"] == "1 patient match this query."


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
    assert "patient_ids" not in payload["data"]
    assert "sample_ids" not in payload["data"]
    assert "result_handle" not in payload["data"]
    assert payload["data"]["available_actions"] == {
        "open_in_analysis": False,
        "save_cohort": False,
        "copy_patient_ids": False,
        "use_in_pheno_ranker": False,
    }
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
    assert payload["reply"] == "2 patients match this query."
    assert payload["data"]["count_only"] is True
    assert "patient_ids" not in payload["data"]


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
    assert "patient_ids" not in payload["data"]
    assert payload["reply"] == "1 patient match this query."


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
    assert "patient_ids" not in payload["data"]
    assert payload["reply"] == "1 patient match this query."


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
    assert "patient_ids" not in payload["data"]
    assert payload["reply"] == "1 patient match this query."


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
    assert "patient_ids" not in payload["data"]
    assert payload["reply"] == "1 patient match this query."


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


def test_query_post_uses_active_workspace_and_returns_dataset_provenance(monkeypatch):
    request = make_request({"username": "admin"})
    captured = {}

    monkeypatch.setattr(routes_module, "require_authenticated", lambda req: {"username": "admin"})
    monkeypatch.setattr(routes_module, "request_user_id", lambda req: "admin")
    monkeypatch.setattr(routes_module, "current_dataset_ids", lambda user_id: ["private-v2"])

    def fake_resolve_dataset_ids(req, key=""):
        captured["dataset_key"] = key
        return ["private-v2"]

    def fake_resolve_dataset_dir(req, key):
        captured["resolved_key"] = key
        return "/protected/release"

    def fake_answer_query(data_dir, *args, **kwargs):
        captured["data_dir"] = data_dir
        return {"intent": "disease_cohort", "reply": "No matching patients.", "data": {"patient_count": 0}}

    monkeypatch.setattr(routes_module, "resolve_dataset_ids", fake_resolve_dataset_ids)
    monkeypatch.setattr(routes_module, "resolve_dataset_dir", fake_resolve_dataset_dir)
    monkeypatch.setattr(routes_module, "effective_query_granularity_ceiling", lambda dataset_ids: "detailed")
    monkeypatch.setattr(routes_module, "effective_ai_provider_access", lambda dataset_ids: "blocked")
    monkeypatch.setattr(routes_module, "selected_lm_provider_id", lambda req: "")
    monkeypatch.setattr(routes_module, "lm_provider_context", lambda provider_id: nullcontext())
    monkeypatch.setattr(routes_module, "answer_query", fake_answer_query)
    monkeypatch.setattr(
        routes_module,
        "_authorized_datasets_for_request",
        lambda req: [{"dataset_id": "private-v2", "name": "Private cross-sectional v2"}],
    )

    payload = routes_module.query_app_post(
        routes_module.QueryRequest(q="Which patients have COPD?", data_dir="default_dataset"),
        request,
    )

    assert captured == {
        "dataset_key": "private-v2",
        "resolved_key": "private-v2",
        "data_dir": "/protected/release",
    }
    assert payload["data"]["dataset_id"] == "private-v2"
    assert payload["data"]["dataset_ids"] == ["private-v2"]
    assert payload["data"]["dataset_name"] == "Private cross-sectional v2"
    assert payload["data"]["dataset_names"] == ["Private cross-sectional v2"]


def test_query_post_rejects_missing_active_workspace(monkeypatch):
    request = make_request({"username": "admin"})
    monkeypatch.setattr(routes_module, "require_authenticated", lambda req: {"username": "admin"})
    monkeypatch.setattr(routes_module, "request_user_id", lambda req: "admin")
    monkeypatch.setattr(routes_module, "current_dataset_ids", lambda user_id: [])

    with pytest.raises(HTTPException, match="No active workspace") as exc:
        routes_module.query_app_post(routes_module.QueryRequest(q="Which patients have COPD?"), request)

    assert exc.value.status_code == 409


def test_query_analysis_and_dashboard_route_wrappers_map_file_not_found(monkeypatch):
    request = make_request({"username": "u1"})
    monkeypatch.setattr(routes_module, "require_authenticated", lambda req: {"username": "u1"})
    monkeypatch.setattr(routes_module, "current_dataset_ids", lambda user_id: ["default"])
    monkeypatch.setattr(routes_module, "resolve_dataset_ids", lambda request, key="": ["default"])
    monkeypatch.setattr(routes_module, "resolve_dataset_dir", lambda request, key: "/resolved/data")
    monkeypatch.setattr(routes_module, "effective_query_granularity_ceiling", lambda dataset_ids: "detailed")
    monkeypatch.setattr(routes_module, "effective_ai_provider_access", lambda dataset_ids: "detailed_allowed")
    monkeypatch.setattr(routes_module, "answer_query", lambda *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError("missing query data")))
    monkeypatch.setattr(routes_module, "analysis_llm_reply", lambda *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError("missing analysis data")))
    monkeypatch.setattr(routes_module, "assay_dataset_inventory", lambda data_dir: (_ for _ in ()).throw(FileNotFoundError("missing assay data")))
    monkeypatch.setattr(routes_module, "assay_feature_inventory", lambda *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError("missing genes")))
    monkeypatch.setattr(routes_module, "assay_expression_summary", lambda *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError("missing expression")))
    monkeypatch.setattr(routes_module, "dashboard_summary", lambda data_dir: (_ for _ in ()).throw(FileNotFoundError("missing dashboard data")))
    monkeypatch.setattr(routes_module, "_resolve_route_dataset_dir", lambda request, dataset_id="", data_dir="": "/resolved/data")

    query_payload = routes_module.QueryRequest(q="hello", dataset_id="default")
    analysis_payload = routes_module.AnalysisRequest(prompt="explain")
    expression_payload = routes_module.AssayExpressionRequest(assay_id="rna", gene_id="TP53")

    with pytest.raises(HTTPException) as query_exc:
        routes_module.query_app_post(query_payload, request)
    with pytest.raises(HTTPException) as analysis_exc:
        routes_module.analysis_app(analysis_payload, request)
    with pytest.raises(HTTPException) as datasets_exc:
        routes_module.get_assay_datasets(request)
    with pytest.raises(HTTPException) as genes_exc:
        routes_module.get_assay_features("rna", request)
    with pytest.raises(HTTPException) as expression_exc:
        routes_module.get_assay_expression(expression_payload, request)
    with pytest.raises(HTTPException) as dashboard_exc:
        routes_module.get_dashboard(request)

    assert query_exc.value.status_code == 404
    assert analysis_exc.value.status_code == 404
    assert datasets_exc.value.status_code == 404
    assert genes_exc.value.status_code == 404
    assert expression_exc.value.status_code == 404
    assert dashboard_exc.value.status_code == 404


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
