from app.identities import identity_key
import json
import pytest
from fastapi import HTTPException
import app.routes as routes_module
from bff_test_helpers import make_request
from bff_test_helpers import write_json
from app.main import app
from fastapi.testclient import TestClient
from bff_test_helpers import isolate_auth_store
import app.analysis_sessions as analysis_sessions_module
import app.cohorts as cohorts_module


def test_saved_cohorts_persist_and_filter_by_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(cohorts_module, "USER_STATE_ROOT", tmp_path / "users")

    saved = cohorts_module.save_cohort(
        name="Crohn cohort",
        data_dir="/data/a",
        members=[dict(dataset_id="a", patient_id=p) for p in ["P1", "P2"]],
        id_type="patient",
        source_kind="query",
        source_prompt="Which patients have Crohn Disease?",
    )
    assert saved["name"] == "Crohn cohort"
    assert saved["patient_ids"] == [identity_key("a", "patient", p) for p in ["P1", "P2"]]

    other = cohorts_module.save_cohort(
        name="Other cohort",
        data_dir="/data/b",
        members=[dict(dataset_id="b", patient_id="X1", sample_id="X1")],
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
    monkeypatch.setattr(analysis_sessions_module, "USER_STATE_ROOT", tmp_path / "users")

    saved = cohorts_module.save_cohort(
        name="Crohn cohort",
        data_dir="/data/a",
        members=[dict(dataset_id="a", patient_id=p, sample_id=p + ":week_0") for p in ["SYN001", "SYN002"]],
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


def test_analysis_session_persists_scope_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr(analysis_sessions_module, "USER_STATE_ROOT", tmp_path / "users")

    saved = analysis_sessions_module.save_analysis_session({
        "id": "session-metadata",
        "data_dir": "/data/a",
        "scope": "SYN001:week_0,SYN002:week_0",
        "scope_metadata": {
            "sample_ids": ["SYN001:week_0", "SYN002:week_0"],
            "patient_ids": ["SYN001", "SYN002"],
            "id_type": "sample",
            "source": {"kind": "dashboard_timeline", "prompt": "Timeline selection"},
        },
        "compare_mode": False,
        "context_mode": "general",
    })

    assert saved["scope_metadata"]["sample_count"] == 2
    assert saved["scope_metadata"]["patient_count"] == 2
    assert saved["scope_metadata"]["source"]["kind"] == "dashboard_timeline"
    assert saved["context_mode"] == "general"
    assert analysis_sessions_module.get_analysis_session("session-metadata")["scope_metadata"]["sample_ids"] == ["SYN001:week_0", "SYN002:week_0"]


def test_analysis_session_preserves_handle_only_scope_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr(analysis_sessions_module, "USER_STATE_ROOT", tmp_path / "users")

    saved = analysis_sessions_module.save_analysis_session({
        "id": "session-handle-scope",
        "data_dir": "/data/a",
        "scope": "",
        "scope_metadata": {
            "query_result_handle": "qr_handle_only_scope",
            "id_type": "patient",
            "source": {"kind": "query", "prompt": "List all patients"},
        },
    })

    assert saved["scope_metadata"]["query_result_handle"] == "qr_handle_only_scope"
    assert saved["scope_metadata"]["patient_ids"] == []
    assert analysis_sessions_module.get_analysis_session("session-handle-scope")["scope_metadata"]["query_result_handle"] == "qr_handle_only_scope"


def test_saved_cohort_retains_fixed_membership_even_when_all_records_selected(tmp_path, monkeypatch):
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

    saved = cohorts_module.save_cohort(
        name="Full dataset cohort",
        data_dir=str(tmp_path),
        members=[dict(dataset_id="a", patient_id=s.split(":")[0], sample_id=s) for s in ["SYN001:week_0", "SYN001:week_2", "SYN002:week_0"]],
        patient_ids=["SYN001", "SYN002"],
        id_type="sample",
        source_kind="query",
    )

    assert saved["is_full_dataset"] is False
    assert saved["sample_count"] == 3


def test_saved_cohorts_are_user_scoped(tmp_path, monkeypatch):
    monkeypatch.setattr(cohorts_module, "USER_STATE_ROOT", tmp_path / "users")

    cohorts_module.save_cohort(
        name="Local cohort",
        data_dir="/data/a",
        members=[dict(dataset_id="a", patient_id="P1")],
        id_type="patient",
        source_kind="query",
        user_id="local",
    )
    cohorts_module.save_cohort(
        name="Alice cohort",
        data_dir="/data/a",
        members=[dict(dataset_id="a", patient_id="P2")],
        id_type="patient",
        source_kind="query",
        user_id="alice",
    )

    assert [item["name"] for item in cohorts_module.list_saved_cohorts("/data/a", user_id="local")] == ["Local cohort"]
    assert [item["name"] for item in cohorts_module.list_saved_cohorts("/data/a", user_id="alice")] == ["Alice cohort"]


def test_saved_cohorts_auto_suffix_duplicate_names(tmp_path, monkeypatch):
    monkeypatch.setattr(cohorts_module, "USER_STATE_ROOT", tmp_path / "users")

    first = cohorts_module.save_cohort(
        name="Crohn cohort",
        data_dir="/data/a",
        members=[dict(dataset_id="a", patient_id="P1")],
        id_type="patient",
        source_kind="query",
        source_prompt="First Crohn cohort",
    )
    second = cohorts_module.save_cohort(
        name="Crohn cohort",
        data_dir="/data/a",
        members=[dict(dataset_id="a", patient_id="P2")],
        id_type="patient",
        source_kind="query",
        source_prompt="Second Crohn cohort",
    )
    third_other_dir = cohorts_module.save_cohort(
        name="Crohn cohort",
        data_dir="/data/b",
        members=[dict(dataset_id="b", patient_id="X1", sample_id="X1")],
        id_type="patient",
        source_kind="query",
        source_prompt="Crohn cohort in another dataset",
    )

    assert first["name"] == "Crohn cohort"
    assert second["name"] == "Crohn cohort (2)"
    assert third_other_dir["name"] == "Crohn cohort"


def test_analysis_sessions_are_user_scoped(tmp_path, monkeypatch):
    monkeypatch.setattr(analysis_sessions_module, "USER_STATE_ROOT", tmp_path / "users")

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


def test_user_data_analysis_sessions_bulk_delete_is_user_scoped(tmp_path, monkeypatch):
    isolate_auth_store(monkeypatch, tmp_path)
    monkeypatch.setattr(analysis_sessions_module, "USER_STATE_ROOT", tmp_path / "users")
    monkeypatch.setenv("COHORTOME_AUTH_MODE", "local")
    monkeypatch.setenv(
        "COHORTOME_LOCAL_USERS_JSON",
        json.dumps(
            [
                {"username": "alice", "password": "secret", "role": "admin", "groups": ["admin"]},
                {"username": "bob", "password": "secret", "role": "user", "groups": ["research"]},
            ]
        ),
    )

    analysis_sessions_module.save_analysis_session({"id": "alice-1", "title": "Alice 1", "turns": []}, user_id="alice")
    analysis_sessions_module.save_analysis_session({"id": "alice-2", "title": "Alice 2", "turns": []}, user_id="alice")
    analysis_sessions_module.save_analysis_session({"id": "bob-1", "title": "Bob 1", "turns": []}, user_id="bob")

    client = TestClient(app)
    assert client.post("/auth/login", json={"username": "alice", "password": "secret"}).status_code == 200

    response = client.delete("/user-data/analysis-sessions")

    assert response.status_code == 200
    assert response.json()["deleted_count"] == 2
    assert analysis_sessions_module.list_analysis_sessions(user_id="alice") == []
    assert [item["id"] for item in analysis_sessions_module.list_analysis_sessions(user_id="bob")] == ["bob-1"]


def test_analysis_session_and_pheno_route_wrappers_enforce_expected_guards(monkeypatch):
    request = make_request({"username": "u1"})
    monkeypatch.setattr(routes_module, "require_authenticated", lambda req: {"username": "u1"})
    monkeypatch.setattr(routes_module, "request_user_id", lambda request: "u1")
    monkeypatch.setattr(routes_module, "save_analysis_session", lambda payload, user_id="": (_ for _ in ()).throw(ValueError("bad session")))
    monkeypatch.setattr(routes_module, "rename_analysis_session", lambda session_id, title, user_id="": None)
    monkeypatch.setattr(routes_module, "delete_analysis_session", lambda session_id, user_id="": False)
    monkeypatch.setattr(routes_module, "resolve_dataset_ids", lambda request, key="": ["summary-dataset"])
    monkeypatch.setattr(routes_module, "resolve_dataset_dir", lambda request, key="": "/tmp/data")
    monkeypatch.setattr(routes_module, "workspace_fingerprint_for_data_dir", lambda *args, **kwargs: {})
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
