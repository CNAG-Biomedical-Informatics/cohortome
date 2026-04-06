import json
from pathlib import Path
from types import SimpleNamespace

from fastapi import HTTPException

import app.analysis as analysis_module
import app.analysis_sessions as analysis_sessions_module
import app.cohorts as cohorts_module
import app.datasets as datasets_module
import app.pheno as pheno_module
import app.query as query_module
import app.query_store as query_store_module
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


def test_deterministic_patient_inventory_supports_subject_and_individual_synonyms(tmp_path):
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

    assert payload_subject["intent"] == "patient_inventory"
    assert payload_subject["data"]["patient_ids"] == ["SYN001", "SYN002"]
    assert payload_individual["intent"] == "patient_inventory"
    assert payload_individual["data"]["patient_ids"] == ["SYN001", "SYN002"]


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


def test_local_auth_login_logout_cycle(monkeypatch):
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


def test_auth_enabled_protects_workspace_routes(monkeypatch):
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


def test_auth_users_requires_admin(monkeypatch):
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


def test_dataset_registry_filters_by_user_and_persists_current_selection(tmp_path, monkeypatch):
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
