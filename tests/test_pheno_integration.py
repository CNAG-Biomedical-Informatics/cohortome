import json
import pytest
from fastapi import HTTPException
import app.routes as routes_module
from bff_test_helpers import make_request
from bff_test_helpers import write_json
import app.query_store as query_store_module
from types import SimpleNamespace
import app.pheno as pheno_module
from app.main import app
from fastapi.testclient import TestClient
from bff_test_helpers import isolate_auth_store
import app.datasets as datasets_module
import app.user_state as user_state_module


@pytest.mark.parametrize('prompt', ['Find closest matches by disease', 'Find closest'])
def test_closest_matches_requires_patient_selection(tmp_path, prompt):
    clinical = tmp_path / 'clinical'
    clinical.mkdir()
    write_json(clinical, 'records.json', [{'id': 'SYN001:week_0', 'patient_id': 'SYN001'}])
    result = pheno_module.plan_pheno_ranker(prompt, str(tmp_path))
    assert result['plan']['mode'] == 'patient'
    assert result['plan']['patient_id'] == ''
    assert result['plan']['invalid_patient_id'] == ''


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


def test_pheno_saved_cohort_extracts_fixed_membership_for_job_owner(tmp_path, monkeypatch):
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
        lambda cohort_ids, data_dir, user_id: [
            {
                "id": "cohort_full",
                "name": "Full dataset",
                "sample_ids": ["SYN001:week_0", "SYN002:week_0"],
                "patient_ids": ["SYN001", "SYN002"],
                "is_full_dataset": True,
            }
        ] if user_id == 'alice' else [],
    )

    extraction_calls = []

    def _extract(paths, ids, target):
        extraction_calls.append(ids)
        target.write_text('[]')
        return ['internal:extract-selected-records', 'selection'], SimpleNamespace(returncode=0, stdout='', stderr=''), []

    monkeypatch.setattr(pheno_module, "extract_selected_records", _extract)

    executed_commands = []

    def _fake_run(command, text, check, **kwargs):
        executed_commands.append(command)
        assert kwargs["stdin"] == pheno_module.subprocess.DEVNULL
        assert "--no-color" in command
        kwargs["stdout"].write("ok")
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(pheno_module.subprocess, "run", _fake_run)

    payload = pheno_module.run_pheno_ranker(
        SimpleNamespace(
            user_id='alice',
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

    assert extraction_calls == [["SYN001:week_0", "SYN002:week_0"]]
    assert executed_commands
    assert str(reference_path) not in executed_commands[0]
    assert payload["pre_commands"] == ['internal:extract-selected-records selection']


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
    monkeypatch.setattr(routes_module, "ensure_query_store", lambda data_dir: None)
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
            render_umap=True,
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
    assert captured["payload"]["render_umap"] is True
    assert captured["payload"]["resolved_sample_count"] == 1801


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
    query_store_module.prepare_dataset_query_store("maria-dataset")

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
    assert patient_plan["plan"]["render_graph"] is False
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
        "Compare all patients by disease",
        str(tmp_path),
    )
    assert graph_plan["plan"]["render_graph"] is True
    phenotype_disease_plan = pheno_module.plan_pheno_ranker_deterministic(
        "Compare all patients by phenotypicFeatures and diseases",
        str(tmp_path),
    )
    assert phenotype_disease_plan["plan"]["include_terms"] == ["phenotypicFeatures", "diseases"]
    assert phenotype_disease_plan["plan"]["exclude_terms"] == []
    no_graph_plan = pheno_module.plan_pheno_ranker_deterministic(
        "Compare all patients by disease without graph",
        str(tmp_path),
    )
    assert no_graph_plan["plan"]["render_graph"] is False

    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    with pytest.raises(FileNotFoundError):
        pheno_module.resolve_pheno_ranker_reference_paths(str(empty_dir))


def test_pheno_execution_steps_attach_and_llm_planner(monkeypatch, tmp_path):
    assert pheno_module.pheno_execution_steps({"action": "extract", "selected_patient_ids": "SYN001"}) == [
        "Extract the current scope from the active reference files into one subset JSON."
    ]
    assert pheno_module.pheno_execution_steps({"action": "extract", "selected_patient_ids": ""}) == [
        "Extract requires a non-empty scope."
    ]
    assert pheno_module.pheno_execution_steps({"action": "compare", "mode": "cohort", "selected_patient_ids": "SYN001"}) == [
        "Extract the current scope from the active reference files into one subset JSON.",
        "Run cohort comparison on the extracted subset reference.",
    ]
    assert pheno_module.pheno_execution_steps({"action": "compare", "mode": "cohort", "selected_patient_ids": ""}) == [
        "Run cohort comparison directly on the full reference cohort."
    ]
    assert pheno_module.pheno_execution_steps({"action": "compare", "mode": "patient", "patient_id": "SYN001"}) == [
        "Extract target patient SYN001 from the active reference files.",
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

    def brief_explanation(*args, **kwargs):
        instruction = args[1]['messages'][0]['content']
        assert 'at most 150 words' in instruction
        assert 'exactly three short bullet points' in instruction
        assert 'Do not infer that an unrecorded feature is clinically absent' in instruction
        return {"choices": [{"message": {"content": "  Explanation  "}}]}
    monkeypatch.setattr(pheno_module, "http_json", brief_explanation)
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
        pre_commands=["internal:extract-selected-records ..."],
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
