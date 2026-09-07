import json
from pathlib import Path
import pytest
from fastapi import HTTPException
import app.routes as routes_module
from bff_test_helpers import make_request
import app.analysis as analysis_module
import app.analysis_catalog as analysis_catalog_module
import app.analysis_external as analysis_external_module
import app.jobs as jobs_module
import app.pheno as pheno_module
from bff_test_helpers import isolate_jobs_store
import app.user_settings as user_settings_module
from app.main import app
from fastapi.testclient import TestClient
from bff_test_helpers import isolate_auth_store
from bff_test_helpers import isolate_user_state
import app.analysis_sessions as analysis_sessions_module
from datetime import datetime
from datetime import timezone


def test_run_analysis_job_supports_curated_workflow_runner(tmp_path, monkeypatch):
    isolate_jobs_store(monkeypatch, tmp_path)
    monkeypatch.setattr(
        analysis_catalog_module,
        "get_analysis_catalog_item",
        lambda item_id, path=analysis_catalog_module.ANALYSIS_CATALOG_PATH: {
            "id": "transcriptomics-signature-workflow",
            "name": "Assay signature workflow",
            "runner_type": "workflow",
            "runner_ref": "transcriptomics_signature",
        },
    )
    monkeypatch.setattr(
        analysis_external_module,
        "run_workflow_analysis",
        lambda runner_ref, **kwargs: {
            "intent": "analysis_workflow",
            "reply": "Workflow done.",
            "data": {
                "source": "deterministic",
                "execution": "external_runner",
                "context": {"mode": "workflow_transcriptomics_signature"},
                "runner_type": "workflow",
                "runner_ref": runner_ref,
            },
        },
    )

    record = jobs_module.create_job_record(
        job_type="analysis",
        user_id="alice",
        data={
            "feature": "analysis",
            "name": "Queued workflow",
            "prompt": "Run the assay signature workflow between Cohort A and Cohort B for the selected assay.",
            "dataset_id": "default",
            "data_dir": str(tmp_path),
            "catalog_item_id": "transcriptomics-signature-workflow",
            "runner_type": "workflow",
            "runner_ref": "transcriptomics_signature",
            "job_timeout_seconds": 120,
        },
    )

    payload = jobs_module.run_analysis_job(record["job_id"], "alice")

    assert payload["status"] == "completed"
    assert payload["result_payload"]["intent"] == "analysis_workflow"
    assert payload["result_payload"]["data"]["runner_type"] == "workflow"


def test_analysis_job_submission_creates_user_scoped_record_and_returns_queued_payload(tmp_path, monkeypatch):
    isolate_auth_store(monkeypatch, tmp_path)
    isolate_jobs_store(monkeypatch, tmp_path)
    monkeypatch.setattr(analysis_sessions_module, "USER_STATE_ROOT", tmp_path / "users")
    monkeypatch.setenv("COHORTOME_AUTH_MODE", "local")
    monkeypatch.setenv(
        "COHORTOME_LOCAL_USERS_JSON",
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
            "prompt": "Run the clinical scope profile and retain this reviewer note.",
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
    assert record["prompt"] == "Run the clinical scope profile and retain this reviewer note."
    assert record["status"] == "queued"


def test_analysis_job_submission_requires_live_worker(tmp_path, monkeypatch):
    isolate_auth_store(monkeypatch, tmp_path)
    isolate_jobs_store(monkeypatch, tmp_path)
    monkeypatch.setenv("COHORTOME_AUTH_MODE", "local")
    monkeypatch.setenv(
        "COHORTOME_LOCAL_USERS_JSON",
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


@pytest.mark.parametrize(
    ("worker_states", "expected_activity", "expected_busy"),
    [
        (["idle"], "idle", 0),
        (["busy", "idle"], "working", 1),
    ],
)
def test_analysis_worker_status_distinguishes_online_from_working(
    monkeypatch,
    worker_states,
    expected_activity,
    expected_busy,
):
    class FakeConnection:
        def ping(self):
            return True

    class FakeWorker:
        def __init__(self, state):
            self._state = state

        def queue_names(self):
            return ["analysis"]

        def get_state(self):
            return self._state

        @classmethod
        def all(cls, connection):
            assert isinstance(connection, FakeConnection)
            return [cls(state) for state in worker_states]

    import rq

    monkeypatch.setattr(jobs_module, "jobs_enabled", lambda: True)
    monkeypatch.setattr(jobs_module, "jobs_queue_name", lambda: "analysis")
    monkeypatch.setattr(jobs_module, "_rq_connection", lambda: FakeConnection())
    monkeypatch.setattr(rq, "Worker", FakeWorker)

    status = jobs_module.analysis_worker_status()

    assert status["available"] is True
    assert status["redis_available"] is True
    assert status["worker_count"] == len(worker_states)
    assert status["busy_worker_count"] == expected_busy
    assert status["activity"] == expected_activity


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


def test_run_pheno_ranker_route_persists_inline_run_as_managed_job(tmp_path, monkeypatch):
    isolate_jobs_store(monkeypatch, tmp_path)
    request = make_request({"username": "alice"})

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
        lambda payload, user_id="": {"resolved_sample_count": 2, "threshold": 1500, "requires_background_job": False},
    )

    def fake_run_pheno_ranker(payload):
        job_path = Path(payload.job_dir_override)
        (job_path / "matrix.txt").write_text("\tP1\tP2\nP1\t0\t1\nP2\t1\t0\n", encoding="utf-8")
        return {
            "intent": "pheno_run",
            "reply": "Completed inline cohort run.",
            "job_id": job_path.name,
            "mode": "cohort",
            "command": "pheno-ranker -r ref.json",
            "files": [
                {
                    "name": "matrix.txt",
                    "url": f"/pheno-ranker/results/{job_path.name}/matrix.txt",
                    "size": 16,
                }
            ],
            "plots": [],
            "data": {"source": "deterministic"},
        }

    monkeypatch.setattr(routes_module, "run_pheno_ranker", fake_run_pheno_ranker)

    payload = routes_module.run_pheno_ranker_route(
        routes_module.PhenoRankerRequest(
            prompt="Compare the current cohort",
            action="compare",
            mode="cohort",
            dataset_id="default",
        ),
        request,
    )

    job_id = payload["job_id"]
    assert payload["data"]["job_id"] == job_id
    assert payload["data"]["job_status"] == "completed"
    record = jobs_module.load_job_record(job_id, "alice")
    assert record["status"] == "completed"
    assert record["feature"] == "pheno"
    assert record["execution_backend"] == "inline"
    assert record["result_available"] is True
    assert (jobs_module.job_dir(job_id, "alice") / "matrix.txt").exists()
    assert pheno_module.pheno_ranker_result_file_path(job_id, "matrix.txt", user_id="alice").read_text(encoding="utf-8").startswith("\tP1")


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
    monkeypatch.setenv("COHORTOME_AUTH_MODE", "local")
    monkeypatch.setenv(
        "COHORTOME_LOCAL_USERS_JSON",
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
        data={
            "feature": "analysis",
            "name": "Alice job",
            "dataset_id": "default",
            "catalog_item_id": "external-r-clinical-profile",
            "execution_backend": "job",
        },
    )
    alice_dir = jobs_module.job_dir(alice_job["job_id"], "alice")
    (alice_dir / "stdout.txt").write_text("hello", encoding="utf-8")
    nested_dir = alice_dir / "workflow" / "01-deseq2"
    nested_dir.mkdir(parents=True)
    (nested_dir / "de_results.tsv").write_text("gene\tlog2FoldChange\nG1\t1.2\n", encoding="utf-8")
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
        data={
            "feature": "analysis",
            "name": "Bob job",
            "dataset_id": "default",
            "catalog_item_id": "other",
            "execution_backend": "job",
        },
    )

    client = TestClient(app)
    assert client.post("/auth/login", json={"username": "alice", "password": "secret"}).status_code == 200

    listing = client.get("/jobs")
    assert listing.status_code == 200
    jobs = listing.json()["jobs"]
    assert len(jobs) == 1
    assert jobs[0]["job_id"] == alice_job["job_id"]
    assert "workflow/01-deseq2/de_results.tsv" in [item["name"] for item in jobs[0]["artifacts"]]

    detail = client.get(f"/jobs/{alice_job['job_id']}")
    assert detail.status_code == 200
    assert detail.json()["result_payload"]["reply"] == "Finished"

    artifact = client.get(f"/jobs/{alice_job['job_id']}/artifacts/stdout.txt")
    assert artifact.status_code == 200
    assert artifact.text == "hello"
    nested_artifact = client.get(f"/jobs/{alice_job['job_id']}/artifacts/workflow/01-deseq2/de_results.tsv")
    assert nested_artifact.status_code == 200
    assert nested_artifact.text.startswith("gene\tlog2FoldChange")

    hidden = client.get(f"/jobs/{bob_job['job_id']}")
    assert hidden.status_code == 404


def test_run_history_lists_inline_runs_without_polluting_jobs_drawer(tmp_path, monkeypatch):
    isolate_auth_store(monkeypatch, tmp_path)
    isolate_jobs_store(monkeypatch, tmp_path)
    monkeypatch.setenv("COHORTOME_AUTH_MODE", "local")
    monkeypatch.setenv(
        "COHORTOME_LOCAL_USERS_JSON",
        json.dumps([{"username": "alice", "password": "secret", "role": "admin", "groups": ["admin"]}]),
    )

    inline_job = jobs_module.create_job_record(
        job_type="pheno",
        user_id="alice",
        data={"feature": "pheno", "name": "Inline Pheno", "dataset_id": "default", "execution_backend": "inline"},
    )
    jobs_module.save_job_result(inline_job["job_id"], "alice", {"reply": "Inline finished"})
    jobs_module.update_job_record(inline_job["job_id"], "alice", status="completed", result_available=True)
    background_job = jobs_module.create_job_record(
        job_type="analysis",
        user_id="alice",
        data={"feature": "analysis", "name": "Queued workflow", "dataset_id": "default", "execution_backend": "job"},
    )
    jobs_module.update_job_record(background_job["job_id"], "alice", status="running")

    client = TestClient(app)
    assert client.post("/auth/login", json={"username": "alice", "password": "secret"}).status_code == 200

    jobs_payload = client.get("/jobs").json()
    assert [item["job_id"] for item in jobs_payload["jobs"]] == [background_job["job_id"]]

    history_payload = client.get("/run-history").json()
    history_ids = {item["job_id"] for item in history_payload["runs"]}
    assert inline_job["job_id"] in history_ids
    assert background_job["job_id"] in history_ids


def test_run_history_delete_removes_terminal_runs_and_skips_active(tmp_path, monkeypatch):
    isolate_auth_store(monkeypatch, tmp_path)
    isolate_jobs_store(monkeypatch, tmp_path)
    monkeypatch.setenv("COHORTOME_AUTH_MODE", "local")
    monkeypatch.setenv(
        "COHORTOME_LOCAL_USERS_JSON",
        json.dumps([{"username": "alice", "password": "secret", "role": "admin", "groups": ["admin"]}]),
    )

    terminal_job = jobs_module.create_job_record(
        job_type="pheno",
        user_id="alice",
        data={"feature": "pheno", "name": "Completed inline", "dataset_id": "default", "execution_backend": "inline"},
    )
    terminal_path = jobs_module.job_dir(terminal_job["job_id"], "alice")
    (terminal_path / "matrix.txt").write_text("ok\n", encoding="utf-8")
    jobs_module.update_job_record(terminal_job["job_id"], "alice", status="completed", result_available=True)
    active_job = jobs_module.create_job_record(
        job_type="analysis",
        user_id="alice",
        data={"feature": "analysis", "name": "Running queued", "dataset_id": "default", "execution_backend": "job"},
    )
    active_path = jobs_module.job_dir(active_job["job_id"], "alice")
    jobs_module.update_job_record(active_job["job_id"], "alice", status="running")

    client = TestClient(app)
    assert client.post("/auth/login", json={"username": "alice", "password": "secret"}).status_code == 200

    response = client.delete("/run-history")

    assert response.status_code == 200
    payload = response.json()
    assert payload["deleted_count"] == 1
    assert payload["skipped_active_count"] == 1
    assert not terminal_path.exists()
    assert active_path.exists()


def test_run_history_applies_user_retention_to_terminal_runs(tmp_path, monkeypatch):
    isolate_auth_store(monkeypatch, tmp_path)
    isolate_user_state(monkeypatch, tmp_path)
    isolate_jobs_store(monkeypatch, tmp_path)
    monkeypatch.setenv("COHORTOME_AUTH_MODE", "local")
    monkeypatch.setenv(
        "COHORTOME_LOCAL_USERS_JSON",
        json.dumps([{"username": "alice", "password": "secret", "role": "admin", "groups": ["admin"]}]),
    )
    user_settings_module.save_user_settings({"run_history_retention_days": 7}, "alice")

    old_timestamp = "2024-01-01T00:00:00+00:00"
    fresh_timestamp = datetime.now(timezone.utc).isoformat()
    old_job = jobs_module.create_job_record(
        job_type="pheno",
        user_id="alice",
        data={"feature": "pheno", "name": "Old direct", "dataset_id": "default", "execution_backend": "inline"},
    )
    old_path = jobs_module.job_dir(old_job["job_id"], "alice")
    jobs_module.update_job_record(old_job["job_id"], "alice", status="completed", completed_at=old_timestamp, result_available=True)
    fresh_job = jobs_module.create_job_record(
        job_type="pheno",
        user_id="alice",
        data={"feature": "pheno", "name": "Fresh direct", "dataset_id": "default", "execution_backend": "inline"},
    )
    fresh_path = jobs_module.job_dir(fresh_job["job_id"], "alice")
    jobs_module.update_job_record(fresh_job["job_id"], "alice", status="completed", completed_at=fresh_timestamp, result_available=True)
    active_job = jobs_module.create_job_record(
        job_type="analysis",
        user_id="alice",
        data={"feature": "analysis", "name": "Old active", "dataset_id": "default", "execution_backend": "job"},
    )
    active_path = jobs_module.job_dir(active_job["job_id"], "alice")
    jobs_module.update_job_record(active_job["job_id"], "alice", status="running", submitted_at=old_timestamp)

    client = TestClient(app)
    assert client.post("/auth/login", json={"username": "alice", "password": "secret"}).status_code == 200

    response = client.get("/run-history")

    assert response.status_code == 200
    payload = response.json()
    assert payload["expired_deleted_count"] == 1
    assert payload["retention_days"] == 7
    run_ids = {item["job_id"] for item in payload["runs"]}
    assert old_job["job_id"] not in run_ids
    assert fresh_job["job_id"] in run_ids
    assert active_job["job_id"] in run_ids
    assert not old_path.exists()
    assert fresh_path.exists()
    assert active_path.exists()


def test_analysis_session_delete_can_cascade_terminal_job_data(tmp_path, monkeypatch):
    isolate_auth_store(monkeypatch, tmp_path)
    isolate_jobs_store(monkeypatch, tmp_path)
    monkeypatch.setattr(analysis_sessions_module, "USER_STATE_ROOT", tmp_path / "users")
    monkeypatch.setenv("COHORTOME_AUTH_MODE", "local")
    monkeypatch.setenv(
        "COHORTOME_LOCAL_USERS_JSON",
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
    monkeypatch.setenv("COHORTOME_AUTH_MODE", "local")
    monkeypatch.setenv(
        "COHORTOME_LOCAL_USERS_JSON",
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
            "dataset_id": "default",
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
