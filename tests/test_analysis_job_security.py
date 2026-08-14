import json
import stat
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import app.analysis_catalog as analysis_catalog_module
import app.analysis_external as analysis_external_module
import app.auth as auth_module
import app.config as config_module
import app.datasets as datasets_module
import app.jobs as jobs_module
import app.routes as routes_module
import app.user_state as user_state_module


def _request(session=None):
    return SimpleNamespace(session=session or {})


def _isolate_runtime(monkeypatch, tmp_path):
    monkeypatch.setattr(
        jobs_module,
        "user_state_dir",
        lambda user_id=None: tmp_path / "state" / "users" / user_state_module.normalize_user_id(user_id),
    )
    monkeypatch.setattr(auth_module, "AUTH_USERS_PATH", tmp_path / "state" / "auth" / "users.json")
    monkeypatch.setattr(
        auth_module,
        "PASSWORD_RESET_TOKENS_PATH",
        tmp_path / "state" / "auth" / "password-reset-tokens.json",
    )
    monkeypatch.setattr(
        datasets_module,
        "DATASET_REGISTRY_PATH",
        tmp_path / "state" / "datasets" / "registry.json",
    )
    monkeypatch.setattr(datasets_module, "STATE_ROOT_DIR", tmp_path / "state")


def _write_registry(tmp_path, records):
    path = tmp_path / "state" / "datasets" / "registry.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records), encoding="utf-8")


def _dataset_record(dataset_id, root, **overrides):
    record = {
        "dataset_id": dataset_id,
        "name": dataset_id,
        "root_path": str(root),
        "enabled": True,
        "visibility": "all_authenticated",
        "data_classification": "public",
        "allowed_users": [],
        "allowed_groups": [],
    }
    record.update(overrides)
    return record


def _catalog_item(runner_ref="clinical_scope_profile"):
    return {
        "id": "security-test-analysis",
        "name": "Security test analysis",
        "runner_type": "rscript",
        "runner_ref": runner_ref,
        "execution_backend": "job",
        "job_timeout_seconds": 120,
    }


def test_analysis_ignores_forged_data_dir_and_uses_active_authorized_workspace(monkeypatch):
    request = _request({"username": "alice"})
    captured = {}
    monkeypatch.setattr(routes_module, "require_authenticated", lambda raw_request: {"username": "alice"})
    monkeypatch.setattr(routes_module, "request_user_id", lambda raw_request: "alice")
    monkeypatch.setattr(routes_module, "current_dataset_ids", lambda user_id: ["dataset-b", "dataset-a"])

    def resolve_ids(raw_request, dataset_id):
        captured["requested_scope"] = dataset_id
        return ["dataset-a", "dataset-b"]

    def resolve_dir(raw_request, dataset_id):
        captured["resolved_scope"] = dataset_id
        return "/authorized/materialized-scope"

    def analysis_reply(prompt, data_dir, **kwargs):
        captured["data_dir"] = data_dir
        captured["analysis_dataset_id"] = kwargs["dataset_id"]
        return {"intent": "analysis_context", "reply": "ok", "data": {}}

    monkeypatch.setattr(routes_module, "resolve_dataset_ids", resolve_ids)
    monkeypatch.setattr(routes_module, "resolve_dataset_dir", resolve_dir)
    monkeypatch.setattr(routes_module, "analysis_llm_reply", analysis_reply)
    monkeypatch.setattr(routes_module, "effective_query_granularity_ceiling", lambda dataset_ids: "detailed")
    monkeypatch.setattr(routes_module, "selected_ai_provider_access", lambda raw_request, dataset_ids: "blocked")
    monkeypatch.setattr(routes_module, "selected_lm_provider_id", lambda raw_request: "")
    monkeypatch.setattr(routes_module, "lm_provider_context", lambda provider_id: nullcontext())

    payload = routes_module.analysis_app(
        routes_module.AnalysisRequest(prompt="Summarize", data_dir="/forged/private/release"),
        request,
    )

    assert payload["reply"] == "ok"
    assert captured == {
        "requested_scope": "scope--dataset-a--dataset-b",
        "resolved_scope": "scope--dataset-a--dataset-b",
        "data_dir": "/authorized/materialized-scope",
        "analysis_dataset_id": "scope--dataset-a--dataset-b",
    }


@pytest.mark.parametrize("dataset_id", ["not-authorized", "../../forged-release"])
def test_analysis_rejects_explicit_unauthorized_or_forged_dataset_id(monkeypatch, dataset_id):
    request = _request({"username": "alice"})
    called = {"analysis": False}
    monkeypatch.setattr(routes_module, "require_authenticated", lambda raw_request: {"username": "alice"})

    def reject_dataset(raw_request, requested_id):
        raise HTTPException(status_code=403, detail="Dataset access denied.")

    def analysis_reply(*args, **kwargs):
        called["analysis"] = True
        return {}

    monkeypatch.setattr(routes_module, "resolve_dataset_ids", reject_dataset)
    monkeypatch.setattr(routes_module, "analysis_llm_reply", analysis_reply)

    with pytest.raises(HTTPException) as exc:
        routes_module.analysis_app(
            routes_module.AnalysisRequest(
                prompt="Run analysis",
                dataset_id=dataset_id,
                data_dir="/forged/private/release",
            ),
            request,
        )

    assert exc.value.status_code == 403
    assert called["analysis"] is False


def test_analysis_worker_resolves_fresh_dataset_root_and_ignores_stored_data_dir(tmp_path, monkeypatch):
    _isolate_runtime(monkeypatch, tmp_path)
    monkeypatch.setenv("COHORTOME_AUTH_MODE", "none")
    dataset_root = tmp_path / "current-release"
    dataset_root.mkdir()
    _write_registry(tmp_path, [_dataset_record("study", dataset_root)])
    captured = {}
    monkeypatch.setattr(analysis_catalog_module, "get_analysis_catalog_item", lambda item_id: _catalog_item())

    def run_external(runner_type, runner_ref, **kwargs):
        captured["data_dir"] = kwargs["data_dir"]
        return {"intent": "analysis_external_rscript", "reply": "done", "data": {}}

    monkeypatch.setattr(analysis_external_module, "run_external_analysis", run_external)
    record = jobs_module.create_job_record(
        job_type="analysis",
        user_id="local",
        data={
            "feature": "analysis",
            "dataset_id": "study",
            "data_dir": "/stale/forged/release",
            "catalog_item_id": "security-test-analysis",
            "job_timeout_seconds": 120,
        },
    )

    payload = jobs_module.run_analysis_job(record["job_id"], "local")

    assert payload["status"] == "completed"
    assert captured["data_dir"] == str(dataset_root.resolve())
    job_path = jobs_module.job_dir(record["job_id"], "local")
    assert stat.S_IMODE(job_path.stat().st_mode) == 0o700
    assert stat.S_IMODE((job_path / "job.json").stat().st_mode) == 0o600
    assert stat.S_IMODE((job_path / "result.json").stat().st_mode) == 0o600


def test_analysis_worker_fails_after_dataset_access_is_revoked(tmp_path, monkeypatch):
    _isolate_runtime(monkeypatch, tmp_path)
    monkeypatch.setenv("COHORTOME_AUTH_MODE", "local")
    monkeypatch.setenv(
        "COHORTOME_LOCAL_USERS_JSON",
        json.dumps(
            [
                {"username": "admin", "password": "secret", "role": "admin"},
                {"username": "alice", "password": "secret", "role": "user"},
            ]
        ),
    )
    dataset_root = tmp_path / "restricted-release"
    dataset_root.mkdir()
    allowed = _dataset_record(
        "restricted-study",
        dataset_root,
        visibility="restricted",
        allowed_users=["alice"],
    )
    _write_registry(tmp_path, [allowed])
    assert jobs_module._authorize_analysis_scope("alice", "restricted-study")["dataset_id"] == "restricted-study"
    record = jobs_module.create_job_record(
        job_type="analysis",
        user_id="alice",
        data={"dataset_id": "restricted-study", "catalog_item_id": "security-test-analysis"},
    )
    _write_registry(tmp_path, [{**allowed, "allowed_users": []}])
    called = {"external": False}
    monkeypatch.setattr(analysis_catalog_module, "get_analysis_catalog_item", lambda item_id: _catalog_item())
    monkeypatch.setattr(
        analysis_external_module,
        "run_external_analysis",
        lambda *args, **kwargs: called.__setitem__("external", True),
    )

    payload = jobs_module.run_analysis_job(record["job_id"], "alice")

    assert payload["status"] == "failed"
    assert "access was revoked" in payload["error"].lower()
    assert called["external"] is False


def test_analysis_worker_fails_when_submitting_user_is_disabled(tmp_path, monkeypatch):
    _isolate_runtime(monkeypatch, tmp_path)
    monkeypatch.setenv("COHORTOME_AUTH_MODE", "local")
    monkeypatch.setenv(
        "COHORTOME_LOCAL_USERS_JSON",
        json.dumps(
            [
                {"username": "admin", "password": "secret", "role": "admin"},
                {"username": "alice", "password": "secret", "role": "user"},
            ]
        ),
    )
    dataset_root = tmp_path / "restricted-release"
    dataset_root.mkdir()
    _write_registry(
        tmp_path,
        [
            _dataset_record(
                "restricted-study",
                dataset_root,
                visibility="restricted",
                allowed_users=["alice"],
            )
        ],
    )
    assert jobs_module._authorize_analysis_scope("alice", "restricted-study")["dataset_id"] == "restricted-study"
    record = jobs_module.create_job_record(
        job_type="analysis",
        user_id="alice",
        data={"dataset_id": "restricted-study", "catalog_item_id": "security-test-analysis"},
    )
    auth_module.update_local_user("alice", enabled=False)
    called = {"external": False}
    monkeypatch.setattr(analysis_catalog_module, "get_analysis_catalog_item", lambda item_id: _catalog_item())
    monkeypatch.setattr(
        analysis_external_module,
        "run_external_analysis",
        lambda *args, **kwargs: called.__setitem__("external", True),
    )

    payload = jobs_module.run_analysis_job(record["job_id"], "alice")

    assert payload["status"] == "failed"
    assert "authorization is no longer valid" in payload["error"].lower()
    assert called["external"] is False


def test_analysis_worker_user_lookup_supports_oidc_usernames_normalized_for_state(tmp_path, monkeypatch):
    _isolate_runtime(monkeypatch, tmp_path)
    monkeypatch.setenv("COHORTOME_AUTH_MODE", "oidc")
    monkeypatch.setenv(
        "COHORTOME_LOCAL_USERS_JSON",
        json.dumps(
            [
                {
                    "username": "researcher@example.org",
                    "role": "user",
                    "auth_source": "oidc",
                    "external_subject": "oidc-subject-1",
                    "enabled": True,
                }
            ]
        ),
    )

    user = jobs_module._analysis_job_user("researcher_example.org")

    assert user["username"] == "researcher@example.org"
    assert user["auth_source"] == "oidc"


@pytest.mark.parametrize(
    "runner_ref",
    ["methylation_qc_pca", "quantitative_assay_wilcoxon_comparison"],
)
def test_private_external_matrix_submission_requires_explicit_external_runtime(tmp_path, monkeypatch, runner_ref):
    _isolate_runtime(monkeypatch, tmp_path)
    monkeypatch.setenv("COHORTOME_AUTH_MODE", "none")
    monkeypatch.delenv("COHORTOME_RUNTIME_ROOT", raising=False)
    dataset_root = tmp_path / "private-release"
    dataset_root.mkdir()
    _write_registry(
        tmp_path,
        [_dataset_record("private-study", dataset_root, data_classification="private")],
    )
    monkeypatch.setattr(jobs_module, "jobs_enabled", lambda: True)
    monkeypatch.setattr(jobs_module, "analysis_worker_available", lambda: True)

    with pytest.raises(RuntimeError, match="absolute path.*outside the Git checkout"):
        jobs_module.submit_analysis_job(
            user_id="local",
            analysis_session_id="",
            prompt="Run an external-matrix analysis",
            data_dir=str(dataset_root),
            dataset_id="private-study",
            assay_id="external-assay",
            catalog_item=_catalog_item(runner_ref),
        )

    assert jobs_module.list_job_records("local") == []


@pytest.mark.parametrize(
    "runner_ref",
    ["methylation_qc_pca", "quantitative_assay_wilcoxon_comparison"],
)
def test_private_external_matrix_worker_rechecks_runtime_before_execution(tmp_path, monkeypatch, runner_ref):
    _isolate_runtime(monkeypatch, tmp_path)
    monkeypatch.setenv("COHORTOME_AUTH_MODE", "none")
    monkeypatch.delenv("COHORTOME_RUNTIME_ROOT", raising=False)
    dataset_root = tmp_path / "private-release"
    dataset_root.mkdir()
    _write_registry(
        tmp_path,
        [_dataset_record("private-study", dataset_root, data_classification="private")],
    )
    record = jobs_module.create_job_record(
        job_type="analysis",
        user_id="local",
        data={"dataset_id": "private-study", "catalog_item_id": "private-methylation"},
    )
    called = {"external": False}
    monkeypatch.setattr(
        analysis_catalog_module,
        "get_analysis_catalog_item",
        lambda item_id: _catalog_item(runner_ref),
    )
    monkeypatch.setattr(
        analysis_external_module,
        "run_external_analysis",
        lambda *args, **kwargs: called.__setitem__("external", True),
    )

    payload = jobs_module.run_analysis_job(record["job_id"], "local")

    assert payload["status"] == "failed"
    assert "cohortome_runtime_root" in payload["error"].lower()
    assert called["external"] is False


def test_internal_analysis_inputs_are_not_downloadable_job_artifacts(tmp_path, monkeypatch):
    _isolate_runtime(monkeypatch, tmp_path)
    root = jobs_module.job_dir("private-input-job", "local", create=True)
    internal = root / ".analysis-private"
    internal.mkdir()
    (internal / "sample_table.tsv").write_text("sample_id\tpatient_id\nS1\tP1\n", encoding="utf-8")
    (root / "summary.json").write_text("{}\n", encoding="utf-8")

    assert [item["name"] for item in jobs_module._artifact_inventory(root)] == ["summary.json"]
    with pytest.raises(HTTPException, match="Job artifact not found"):
        jobs_module.resolve_job_artifact_path(
            "private-input-job",
            "local",
            ".analysis-private/sample_table.tsv",
        )


def test_private_artifact_runtime_requires_matching_absolute_external_root(tmp_path, monkeypatch):
    external_root = tmp_path / "protected-runtime"
    monkeypatch.setenv("COHORTOME_RUNTIME_ROOT", str(external_root.resolve()))
    monkeypatch.setattr(config_module, "RUNTIME_ROOT_DIR", external_root.resolve())
    assert config_module.private_artifact_runtime_is_safe() is True

    monkeypatch.setenv("COHORTOME_RUNTIME_ROOT", "relative-runtime")
    assert config_module.private_artifact_runtime_is_safe() is False

    monkeypatch.setenv("COHORTOME_RUNTIME_ROOT", str((config_module.BASE_DIR / "runtime").resolve()))
    monkeypatch.setattr(config_module, "RUNTIME_ROOT_DIR", (config_module.BASE_DIR / "runtime").resolve())
    assert config_module.private_artifact_runtime_is_safe() is False


def test_job_detail_and_artifact_fail_after_dataset_access_is_revoked(tmp_path, monkeypatch):
    _isolate_runtime(monkeypatch, tmp_path)
    monkeypatch.setenv("COHORTOME_AUTH_MODE", "local")
    monkeypatch.setenv(
        "COHORTOME_LOCAL_USERS_JSON",
        json.dumps(
            [
                {"username": "admin", "password": "secret", "role": "admin"},
                {"username": "alice", "password": "secret", "role": "user"},
            ]
        ),
    )
    dataset_root = tmp_path / "restricted-release"
    dataset_root.mkdir()
    allowed = _dataset_record(
        "restricted-study",
        dataset_root,
        visibility="restricted",
        allowed_users=["alice"],
    )
    _write_registry(tmp_path, [allowed])
    record = jobs_module.create_job_record(
        job_type="analysis",
        user_id="alice",
        data={
            "dataset_id": "restricted-study",
            "catalog_item_id": "security-test-analysis",
            "status": "completed",
            "result_available": True,
        },
    )
    artifact = jobs_module.job_dir(record["job_id"], "alice") / "sample_qc.tsv"
    artifact.write_text("sample_id\tmissing\nS1\t0\n", encoding="utf-8")
    _write_registry(tmp_path, [{**allowed, "allowed_users": []}])
    request = _request({"username": "alice", "role": "user"})

    with pytest.raises(HTTPException) as detail_exc:
        routes_module.get_job(record["job_id"], request)
    with pytest.raises(HTTPException) as artifact_exc:
        routes_module.get_job_artifact(record["job_id"], "sample_qc.tsv", request)

    assert detail_exc.value.status_code == 403
    assert artifact_exc.value.status_code == 403


def test_pheno_result_routes_fail_after_dataset_access_is_revoked(tmp_path, monkeypatch):
    _isolate_runtime(monkeypatch, tmp_path)
    monkeypatch.setenv("COHORTOME_AUTH_MODE", "local")
    monkeypatch.setenv(
        "COHORTOME_LOCAL_USERS_JSON",
        json.dumps(
            [
                {"username": "admin", "password": "secret", "role": "admin"},
                {"username": "alice", "password": "secret", "role": "user"},
            ]
        ),
    )
    dataset_root = tmp_path / "restricted-release"
    dataset_root.mkdir()
    allowed = _dataset_record(
        "restricted-study",
        dataset_root,
        visibility="restricted",
        allowed_users=["alice"],
    )
    _write_registry(tmp_path, [allowed])
    record = jobs_module.create_job_record(
        job_type="pheno",
        user_id="alice",
        data={
            "feature": "pheno",
            "dataset_id": "restricted-study",
            "status": "completed",
            "result_available": True,
        },
    )
    _write_registry(tmp_path, [{**allowed, "allowed_users": []}])
    request = _request({"username": "alice", "role": "user"})

    calls = (
        lambda: routes_module.get_pheno_ranker_result(record["job_id"], "rank.txt", request),
        lambda: routes_module.get_pheno_ranker_alignment(record["job_id"], "reference", request),
        lambda: routes_module.explain_pheno_ranker_results(record["job_id"], request),
        lambda: routes_module.explain_pheno_ranker_results_llm(record["job_id"], request),
    )
    for call in calls:
        with pytest.raises(HTTPException) as exc:
            call()
        assert exc.value.status_code == 403


def test_job_visibility_is_removed_when_detailed_access_is_downgraded_to_summary(tmp_path, monkeypatch):
    _isolate_runtime(monkeypatch, tmp_path)
    monkeypatch.setenv("COHORTOME_AUTH_MODE", "local")
    monkeypatch.setenv(
        "COHORTOME_LOCAL_USERS_JSON",
        json.dumps(
            [
                {"username": "admin", "password": "secret", "role": "admin"},
                {"username": "alice", "password": "secret", "role": "user"},
            ]
        ),
    )
    monkeypatch.setattr(routes_module, "load_user_settings", lambda user_id: {"run_history_retention_days": 0})
    dataset_root = tmp_path / "restricted-release"
    dataset_root.mkdir()
    detailed = _dataset_record(
        "restricted-study",
        dataset_root,
        visibility="restricted",
        allowed_users=["alice"],
        query_granularity_ceiling="detailed",
    )
    _write_registry(tmp_path, [detailed])
    record = jobs_module.create_job_record(
        job_type="analysis",
        user_id="alice",
        data={
            "feature": "analysis",
            "dataset_id": "restricted-study",
            "execution_backend": "job",
            "status": "completed",
            "result_available": True,
        },
    )
    jobs_module.save_job_result(record["job_id"], "alice", {"data": {"sample_count": 1}})
    artifact = jobs_module.job_dir(record["job_id"], "alice") / "sample_qc.tsv"
    artifact.write_text("sample_id\tmissing\nS1\t0\n", encoding="utf-8")
    request = _request({"username": "alice", "role": "user"})

    assert [item["job_id"] for item in routes_module.get_jobs(request)["jobs"]] == [record["job_id"]]
    assert [item["job_id"] for item in routes_module.get_run_history(request)["runs"]] == [record["job_id"]]

    _write_registry(tmp_path, [{**detailed, "query_granularity_ceiling": "summary"}])

    assert routes_module.get_jobs(request) == {"jobs": []}
    assert routes_module.get_run_history(request)["runs"] == []
    for call in (
        lambda: routes_module.get_job(record["job_id"], request),
        lambda: routes_module.get_job_artifact(record["job_id"], "sample_qc.tsv", request),
    ):
        with pytest.raises(HTTPException) as exc:
            call()
        assert exc.value.status_code == 403
        assert "detailed" in str(exc.value.detail).lower()


def test_pheno_retrieval_is_denied_after_detailed_access_is_downgraded_to_summary(tmp_path, monkeypatch):
    _isolate_runtime(monkeypatch, tmp_path)
    monkeypatch.setenv("COHORTOME_AUTH_MODE", "local")
    monkeypatch.setenv(
        "COHORTOME_LOCAL_USERS_JSON",
        json.dumps(
            [
                {"username": "admin", "password": "secret", "role": "admin"},
                {"username": "alice", "password": "secret", "role": "user"},
            ]
        ),
    )
    dataset_root = tmp_path / "restricted-release"
    dataset_root.mkdir()
    _write_registry(
        tmp_path,
        [
            _dataset_record(
                "restricted-study",
                dataset_root,
                visibility="restricted",
                allowed_users=["alice"],
                query_granularity_ceiling="summary",
            )
        ],
    )
    record = jobs_module.create_job_record(
        job_type="pheno",
        user_id="alice",
        data={
            "feature": "pheno",
            "dataset_id": "restricted-study",
            "status": "completed",
            "result_available": True,
        },
    )
    request = _request({"username": "alice", "role": "user"})

    calls = (
        lambda: routes_module.get_pheno_ranker_result(record["job_id"], "rank.txt", request),
        lambda: routes_module.get_pheno_ranker_alignment(record["job_id"], "reference", request),
        lambda: routes_module.explain_pheno_ranker_results(record["job_id"], request),
        lambda: routes_module.explain_pheno_ranker_results_llm(record["job_id"], request),
    )
    for call in calls:
        with pytest.raises(HTTPException) as exc:
            call()
        assert exc.value.status_code == 403
        assert "detailed" in str(exc.value.detail).lower()


def test_legacy_jobs_without_dataset_scope_are_hidden_and_results_fail_closed(tmp_path, monkeypatch):
    _isolate_runtime(monkeypatch, tmp_path)
    monkeypatch.setenv("COHORTOME_AUTH_MODE", "local")
    monkeypatch.setenv(
        "COHORTOME_LOCAL_USERS_JSON",
        json.dumps([{"username": "alice", "password": "secret", "role": "admin"}]),
    )
    monkeypatch.setattr(routes_module, "load_user_settings", lambda user_id: {"run_history_retention_days": 0})
    analysis_record = jobs_module.create_job_record(
        job_type="analysis",
        user_id="alice",
        data={
            "feature": "analysis",
            "execution_backend": "job",
            "status": "completed",
            "result_available": True,
        },
    )
    artifact = jobs_module.job_dir(analysis_record["job_id"], "alice") / "sample_qc.tsv"
    artifact.write_text("sample_id\tmissing\nS1\t0\n", encoding="utf-8")
    pheno_record = jobs_module.create_job_record(
        job_type="pheno",
        user_id="alice",
        data={"feature": "pheno", "status": "completed", "result_available": True},
    )
    request = _request({"username": "alice", "role": "admin"})

    assert routes_module.get_jobs(request) == {"jobs": []}
    assert routes_module.get_run_history(request)["runs"] == []
    calls = (
        lambda: routes_module.get_job(analysis_record["job_id"], request),
        lambda: routes_module.get_job_artifact(analysis_record["job_id"], "sample_qc.tsv", request),
        lambda: routes_module.get_pheno_ranker_result(pheno_record["job_id"], "rank.txt", request),
        lambda: routes_module.get_pheno_ranker_alignment(pheno_record["job_id"], "reference", request),
        lambda: routes_module.explain_pheno_ranker_results(pheno_record["job_id"], request),
        lambda: routes_module.explain_pheno_ranker_results_llm(pheno_record["job_id"], request),
    )
    for call in calls:
        with pytest.raises(HTTPException) as exc:
            call()
        assert exc.value.status_code == 403
        assert "scope" in str(exc.value.detail).lower()
