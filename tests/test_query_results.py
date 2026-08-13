import json
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

import app.config as config_module
import app.analysis_sessions as analysis_sessions_module
import app.query_results as query_results_module
import app.routes as routes_module
import app.user_state as user_state_module
from app.query_policy import finalize_query_response
from app.query_results import (
    QueryResultExpiredError,
    QueryResultNotFoundError,
    QueryResultStaleError,
    create_query_result,
    load_query_result,
    query_result_membership,
    query_result_page,
    purge_expired_query_results,
    require_query_result_binding,
)


def _policy_binding(*, classification="public", updated_at="2026-01-01T00:00:00+00:00"):
    return {
        "granularity_ceiling": "detailed",
        "data_classification": classification,
        "registry": [{
            "dataset_id": "dataset-a",
            "root_path": "/protected/dataset-a",
            "updated_at": updated_at,
            "data_classification": classification,
        }],
    }


def _isolate_state(monkeypatch, tmp_path):
    monkeypatch.setattr(user_state_module, "STATE_ROOT_DIR", tmp_path / "state")


def _record(monkeypatch, tmp_path, *, user_id="alice", count=607):
    _isolate_state(monkeypatch, tmp_path)
    patient_ids = [f"P{index:04d}" for index in range(count)]
    return create_query_result(
        user_id=user_id,
        dataset_id="dataset-a",
        dataset_ids=["dataset-a"],
        workspace_fingerprint={"token": "fingerprint-a"},
        policy_binding=_policy_binding(),
        patient_ids=patient_ids,
        rows=[
            {
                "patient_id": patient_id,
                "sex": "female",
                "visit_count": 1,
                "medications": ["must-not-be-stored"],
            }
            for patient_id in patient_ids
        ],
    )


def _request():
    return SimpleNamespace(session={"username": "alice"}, headers={}, cookies={})


def _route_context(monkeypatch, *, token="fingerprint-a", ceiling="detailed", classification="public"):
    monkeypatch.setattr(routes_module, "require_authenticated", lambda request: {"username": "alice"})
    monkeypatch.setattr(routes_module, "request_user_id", lambda request: "alice")
    monkeypatch.setattr(routes_module, "request_user_identity", lambda request: "alice")
    monkeypatch.setattr(routes_module, "resolve_dataset_ids", lambda request, dataset_id="": ["dataset-a"])
    monkeypatch.setattr(routes_module, "resolve_dataset_dir", lambda request, dataset_id="": "/protected/dataset-a")
    monkeypatch.setattr(routes_module, "effective_query_granularity_ceiling", lambda dataset_ids: ceiling)
    monkeypatch.setattr(routes_module, "effective_data_classification", lambda dataset_ids: classification)
    monkeypatch.setattr(
        routes_module,
        "_authorized_datasets_for_request",
        lambda request: [{
            "dataset_id": "dataset-a",
            "root_path": "/protected/dataset-a",
            "updated_at": "2026-01-01T00:00:00+00:00",
            "data_classification": classification,
        }],
    )
    monkeypatch.setattr(
        routes_module,
        "workspace_fingerprint_for_data_dir",
        lambda *args, **kwargs: {"token": token},
    )


def test_query_result_pages_600_plus_without_gaps_or_duplicates(monkeypatch, tmp_path):
    record = _record(monkeypatch, tmp_path)
    cursor = ""
    collected = []
    while True:
        page = query_result_page(record, cursor=cursor, limit=50)
        assert len(page["patient_ids"]) <= 50
        assert len(page["sample_ids"]) == 0
        assert len(page["rows"]) <= 50
        collected.extend(page["patient_ids"])
        if not page["has_more"]:
            break
        cursor = page["next_cursor"]

    assert collected == [f"P{index:04d}" for index in range(607)]
    assert len(collected) == len(set(collected)) == 607
    stored = load_query_result("alice", record["handle"])
    assert "must-not-be-stored" not in json.dumps(stored)
    assert (tmp_path / "state" / "users" / "alice" / "query-results").stat().st_mode & 0o777 == 0o700
    assert next((tmp_path / "state" / "users" / "alice" / "query-results").glob("qr_*.json")).stat().st_mode & 0o777 == 0o600


def test_query_request_and_page_dimensions_are_bounded(monkeypatch, tmp_path):
    record = _record(monkeypatch, tmp_path)
    assert query_result_page(record, limit=100)["returned_count"] == 100
    assert query_result_page(record, limit=101)["returned_count"] == 100
    with pytest.raises(ValidationError):
        routes_module.QueryRequest(q="q" * 12001)
    with pytest.raises(ValidationError):
        routes_module.QueryRequest(q="ok", history=[{"role": "user", "content": "x"}] * 17)
    with pytest.raises(ValidationError):
        routes_module.QueryRequest(q="ok", history=[{"role": "assistant", "content": "x" * 4001}])
    with pytest.raises(ValidationError):
        routes_module.QueryRequest(q="ok", scoped_patient_ids=[f"P{index}" for index in range(101)])
    with pytest.raises(ValidationError):
        routes_module.QueryRequest(q="ok", scoped_patient_ids=["x" * 257])
    _route_context(monkeypatch)
    with pytest.raises(HTTPException) as empty_get:
        routes_module.query_app(" ", _request(), dataset_id="dataset-a")
    assert empty_get.value.status_code == 422
    with pytest.raises(HTTPException) as oversized_get:
        routes_module.query_app("q" * 12001, _request(), dataset_id="dataset-a")
    assert oversized_get.value.status_code == 422


def test_query_result_is_user_scoped_and_cursor_is_authenticated(monkeypatch, tmp_path):
    record = _record(monkeypatch, tmp_path)
    with pytest.raises(QueryResultNotFoundError):
        load_query_result("bob", record["handle"])
    with pytest.raises(QueryResultStaleError, match="cursor"):
        query_result_page(record, cursor="tampered", limit=50)
    first = query_result_page(record, limit=50)
    with pytest.raises(QueryResultStaleError, match="cursor"):
        query_result_page(record, cursor=first["next_cursor"], limit=25)


def test_query_result_owner_uses_exact_identity_despite_path_collision(monkeypatch, tmp_path):
    record = _record(monkeypatch, tmp_path, user_id="alice/a")
    assert user_state_module.normalize_user_id("alice/a") == user_state_module.normalize_user_id("alice:a")
    with pytest.raises(QueryResultNotFoundError):
        load_query_result("alice:a", record["handle"])
    assert load_query_result("alice/a", record["handle"])["handle"] == record["handle"]


def test_query_result_dataset_order_is_canonical(monkeypatch, tmp_path):
    _isolate_state(monkeypatch, tmp_path)
    record = create_query_result(
        user_id="alice",
        dataset_id="scope--a--b",
        dataset_ids=["b", "a"],
        workspace_fingerprint={"token": "ordered"},
        policy_binding={"granularity_ceiling": "detailed"},
        patient_ids=["P1"],
    )
    assert record["dataset_ids"] == ["a", "b"]
    require_query_result_binding(
        record,
        dataset_id="scope--a--b",
        dataset_ids=["a", "b"],
        workspace_fingerprint={"token": "ordered"},
        policy_binding={"granularity_ceiling": "detailed"},
    )


def test_query_result_expiry_workspace_and_policy_binding(monkeypatch, tmp_path):
    record = _record(monkeypatch, tmp_path)
    membership = query_result_membership(record)
    assert membership["total_count"] == 607
    require_query_result_binding(
        record,
        dataset_id="dataset-a",
        dataset_ids=["dataset-a"],
        workspace_fingerprint={"token": "fingerprint-a"},
        policy_binding=_policy_binding(),
    )
    with pytest.raises(QueryResultStaleError, match="workspace changed"):
        require_query_result_binding(
            record,
            dataset_id="dataset-a",
            dataset_ids=["dataset-a"],
            workspace_fingerprint={"token": "fingerprint-b"},
            policy_binding=_policy_binding(),
        )
    with pytest.raises(QueryResultStaleError, match="access policy"):
        require_query_result_binding(
            record,
            dataset_id="dataset-a",
            dataset_ids=["dataset-a"],
            workspace_fingerprint={"token": "fingerprint-a"},
            policy_binding={"granularity_ceiling": "summary"},
        )
    with pytest.raises(QueryResultExpiredError):
        load_query_result(
            "alice",
            record["handle"],
            now=datetime.now(timezone.utc) + timedelta(minutes=61),
        )


def test_expired_query_results_are_scavenged_without_direct_access(monkeypatch, tmp_path):
    record = _record(monkeypatch, tmp_path, count=1)
    path = next((tmp_path / "state" / "users" / "alice" / "query-results").glob("qr_*.json"))
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["expires_at"] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert purge_expired_query_results("alice") == 1
    assert not path.exists()
    assert record["handle"] not in [item.stem for item in path.parent.glob("*.json")]


def test_private_query_result_requires_external_protected_runtime(monkeypatch, tmp_path):
    _isolate_state(monkeypatch, tmp_path)
    monkeypatch.setattr(config_module, "private_artifact_runtime_is_safe", lambda: False)
    monkeypatch.setattr(query_results_module, "private_artifact_runtime_is_safe", lambda: False)
    with pytest.raises(RuntimeError, match="Private query-result state requires"):
        create_query_result(
            user_id="alice",
            dataset_id="private-a",
            dataset_ids=["private-a"],
            workspace_fingerprint={"token": "x"},
            policy_binding=_policy_binding(classification="private"),
            patient_ids=["PRIVATE_SENTINEL"],
            private_scope=True,
        )
    assert not (tmp_path / "state" / "users" / "alice" / "query-results").exists()


def test_count_and_summary_responses_recursively_remove_identifiers():
    sentinel = "UNIQUE_PATIENT_SENTINEL"
    unsafe_data = {
        "patient_count": 1,
        "patients": [{"patient_id": sentinel}],
        "nested": {
            "patients": [{"patient_id": sentinel}],
            "record_ids": [sentinel],
            "subject_id": sentinel,
            "subject_ids": [sentinel],
        },
        "conversation_history": [{"role": "assistant", "content": sentinel}],
        "follow_up_suggestions": [f"Show patient {sentinel}"],
        "follow_up_suggestion_metadata": [{"prompt": f"Show patient {sentinel}"}],
    }
    count_payload = {
        "query": "How many patients have treatment X?",
        "intent": "medication_cohort",
        "reply": f"Patient {sentinel} matches.",
        "data": unsafe_data,
    }
    summary_payload = {
        "query": "Which patients have treatment X?",
        "intent": "medication_cohort",
        "reply": f"Patient {sentinel} matches.",
        "data": unsafe_data,
    }
    count = finalize_query_response(count_payload, "detailed", "detailed", "blocked")
    summary = finalize_query_response(summary_payload, "summary", "summary", "blocked")
    assert sentinel not in json.dumps(count)
    assert sentinel not in json.dumps(summary)
    assert "result_handle" not in json.dumps(count)
    assert count["data"]["available_actions"] == {
        "open_in_analysis": False,
        "save_cohort": False,
        "copy_patient_ids": False,
        "use_in_pheno_ranker": False,
    }


def test_route_statuses_for_cross_user_expired_stale_policy_and_revocation(monkeypatch, tmp_path):
    record = _record(monkeypatch, tmp_path)
    request = _request()
    _route_context(monkeypatch)

    monkeypatch.setattr(routes_module, "request_user_identity", lambda request: "bob")
    with pytest.raises(HTTPException) as cross_user:
        routes_module.get_query_result_page(record["handle"], request)
    assert cross_user.value.status_code == 404

    monkeypatch.setattr(routes_module, "request_user_identity", lambda request: "alice")
    monkeypatch.setattr(
        query_results_module,
        "_now",
        lambda: datetime.now(timezone.utc) + timedelta(minutes=61),
    )
    with pytest.raises(HTTPException) as expired:
        routes_module.get_query_result_page(record["handle"], request)
    assert expired.value.status_code == 410

    record = _record(monkeypatch, tmp_path)
    monkeypatch.setattr(query_results_module, "_now", lambda: datetime.now(timezone.utc))
    _route_context(monkeypatch, token="fingerprint-b")
    with pytest.raises(HTTPException) as stale:
        routes_module.get_query_result_page(record["handle"], request)
    assert stale.value.status_code == 410

    _route_context(monkeypatch, ceiling="summary")
    with pytest.raises(HTTPException) as downgraded:
        routes_module.get_query_result_page(record["handle"], request)
    assert downgraded.value.status_code == 403

    _route_context(monkeypatch)
    monkeypatch.setattr(
        routes_module,
        "resolve_dataset_ids",
        lambda *args, **kwargs: (_ for _ in ()).throw(HTTPException(status_code=403, detail="Dataset access denied.")),
    )
    with pytest.raises(HTTPException) as revoked:
        routes_module.get_query_result_page(record["handle"], request)
    assert revoked.value.status_code == 403


def test_reclassification_and_private_runtime_are_rechecked_on_every_use(monkeypatch, tmp_path):
    public_record = _record(monkeypatch, tmp_path, count=1)
    _route_context(monkeypatch, classification="private")
    monkeypatch.setattr(routes_module, "private_artifact_runtime_is_safe", lambda: False)
    with pytest.raises(HTTPException) as unsafe:
        routes_module.get_query_result_page(public_record["handle"], _request())
    assert unsafe.value.status_code == 503

    monkeypatch.setattr(routes_module, "private_artifact_runtime_is_safe", lambda: True)
    with pytest.raises(HTTPException) as reclassified:
        routes_module.get_query_result_page(public_record["handle"], _request())
    assert reclassified.value.status_code == 410


def test_query_result_page_disables_http_caching(monkeypatch, tmp_path):
    record = _record(monkeypatch, tmp_path, count=2)
    _route_context(monkeypatch)
    response = routes_module.get_query_result_page(record["handle"], _request(), cursor="", limit=50)
    assert response.headers["cache-control"] == "no-store"
    payload = json.loads(response.body)
    assert payload["returned_count"] == 2


def test_paging_route_rejects_invalid_cursor(monkeypatch, tmp_path):
    record = _record(monkeypatch, tmp_path)
    _route_context(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        routes_module.get_query_result_page(record["handle"], _request(), cursor="tampered", limit=50)
    assert exc.value.status_code == 400


def test_materialized_long_result_is_bounded_and_patient_detail_is_unchanged(monkeypatch, tmp_path):
    _isolate_state(monkeypatch, tmp_path)
    monkeypatch.setattr(routes_module, "request_user_id", lambda request: "alice")
    monkeypatch.setattr(
        routes_module,
        "workspace_fingerprint_for_data_dir",
        lambda *args, **kwargs: {"token": "fingerprint-a"},
    )
    monkeypatch.setattr(
        routes_module,
        "_authorized_datasets_for_request",
        lambda request: [{"dataset_id": "dataset-a", "data_classification": "public"}],
    )
    patient_ids = [f"LONG{index:04d}" for index in range(607)]
    sentinel = patient_ids[-1]
    payload = {
        "query": "List all patients in the workspace",
        "intent": "patient_inventory",
        "reply": "\n".join(patient_ids),
        "data": {
            "granularity_applied": "detailed",
            "patient_count": len(patient_ids),
            "patient_ids": patient_ids,
            "patients": [{"patient_id": value, "sex": "female"} for value in patient_ids],
            "scope_context": {
                "patient_ids": patient_ids,
                "medication_counts": [{"medication": "Example", "patients": patient_ids}],
            },
            "follow_up_suggestions": [f"Show patient {sentinel}", "How many patients are in this workspace?"],
        },
        "action_context": {"patient_ids": patient_ids},
    }
    shaped = routes_module._materialize_query_response(
        payload,
        _request(),
        selected_ids=["dataset-a"],
        scope_id="dataset-a",
        resolved_dir="/protected/dataset-a",
    )
    assert shaped["data"]["result_page"]["total_count"] == 607
    assert len(shaped["data"]["patient_ids"]) == 50
    assert len(shaped["data"]["patients"]) == 50
    assert sentinel not in json.dumps(shaped)
    assert shaped["action_context"]["patient_ids"] == []
    assert shaped["data"]["available_actions"] == {
        "open_in_analysis": True,
        "save_cohort": True,
        "copy_patient_ids": False,
        "use_in_pheno_ranker": False,
    }

    detail = {
        "query": "Show patient LONG0001",
        "intent": "patient_summary",
        "reply": "Detailed patient reply remains intact.",
        "data": {"granularity_applied": "detailed", "patient_id": "LONG0001"},
    }
    assert routes_module._materialize_query_response(
        detail,
        _request(),
        selected_ids=["dataset-a"],
        scope_id="dataset-a",
        resolved_dir="/protected/dataset-a",
    ) == detail


def test_legacy_get_query_uses_bounded_result_contract(monkeypatch, tmp_path):
    _isolate_state(monkeypatch, tmp_path)
    _route_context(monkeypatch)
    monkeypatch.setattr(routes_module, "selected_lm_provider_id", lambda request: "")
    monkeypatch.setattr(routes_module, "selected_ai_provider_access", lambda request, ids: "blocked")
    monkeypatch.setattr(routes_module, "lm_provider_context", lambda provider_id: nullcontext())
    monkeypatch.setattr(
        routes_module,
        "_authorized_datasets_for_request",
        lambda request: [{"dataset_id": "dataset-a", "data_classification": "public"}],
    )
    patient_ids = [f"GET{index:04d}" for index in range(607)]
    monkeypatch.setattr(
        routes_module,
        "answer_query",
        lambda *args, **kwargs: {
            "query": "List all patients",
            "intent": "patient_inventory",
            "reply": "\n".join(patient_ids),
            "data": {
                "granularity_applied": "detailed",
                "patient_count": len(patient_ids),
                "patient_ids": patient_ids,
                "patients": [{"patient_id": value} for value in patient_ids],
            },
            "action_context": {"patient_ids": patient_ids},
        },
    )
    payload = routes_module.query_app("List all patients", _request(), dataset_id="dataset-a")
    assert payload["data"]["result_page"]["returned_count"] == 50
    assert payload["data"]["result_page"]["total_count"] == 607
    assert patient_ids[-1] not in json.dumps(payload)


def test_private_result_persistence_failure_maps_to_service_unavailable(monkeypatch):
    _route_context(monkeypatch)
    monkeypatch.setattr(routes_module, "selected_lm_provider_id", lambda request: "")
    monkeypatch.setattr(routes_module, "selected_ai_provider_access", lambda request, ids: "blocked")
    monkeypatch.setattr(routes_module, "lm_provider_context", lambda provider_id: nullcontext())
    monkeypatch.setattr(routes_module, "answer_query", lambda *args, **kwargs: {"data": {}})
    monkeypatch.setattr(
        routes_module,
        "_materialize_query_response",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("Private query-result state requires protected storage.")
        ),
    )
    with pytest.raises(HTTPException) as exc:
        routes_module.query_app("List all patients", _request(), dataset_id="dataset-a")
    assert exc.value.status_code == 503


def test_sample_handle_keeps_linked_patients_for_follow_up_and_sanitizes_history(monkeypatch, tmp_path):
    _isolate_state(monkeypatch, tmp_path)
    _route_context(monkeypatch)
    monkeypatch.setattr(
        routes_module,
        "_authorized_datasets_for_request",
        lambda request: [{
            "dataset_id": "dataset-a",
            "name": "Dataset A",
            "root_path": "/protected/dataset-a",
            "updated_at": "2026-01-01T00:00:00+00:00",
            "data_classification": "public",
        }],
    )
    samples = ["P1:T0", "P2:T0", "P3:T0"]
    patients = ["P1", "P2", "P3"]
    record = create_query_result(
        user_id="alice",
        dataset_id="dataset-a",
        dataset_ids=["dataset-a"],
        workspace_fingerprint={"token": "fingerprint-a"},
        policy_binding=_policy_binding(),
        patient_ids=patients,
        sample_ids=samples,
        id_type="sample",
    )
    captured = {}

    def fake_answer(*args, **kwargs):
        captured.update(kwargs)
        return {
            "query": "How many patients are female?",
            "intent": "patient_sex_cohort",
            "reply": "2 patients are female.",
            "data": {
                "patient_count": 2,
                "granularity_requested": "detailed",
                "granularity_applied": "detailed",
                "available_actions": {},
            },
        }

    monkeypatch.setattr(routes_module, "answer_query", fake_answer)
    monkeypatch.setattr(routes_module, "selected_lm_provider_id", lambda request: "")
    monkeypatch.setattr(routes_module, "selected_ai_provider_access", lambda request, ids: "blocked")
    monkeypatch.setattr(routes_module, "lm_provider_context", lambda provider_id: nullcontext())
    sentinel = "PRIOR_EXPANDED_LIST_SENTINEL"
    response = routes_module.query_app_post(
        routes_module.QueryRequest(
            q="How many patients are female?",
            dataset_id="dataset-a",
            scoped_result_handle=record["handle"],
            history=[
                {"role": "user", "content": "List samples"},
                {"role": "assistant", "content": f"{sentinel} {record['handle']}"},
            ],
        ),
        _request(),
    )
    assert captured["scoped_patient_ids"] == patients
    assert sentinel not in json.dumps(captured["history"])
    assert record["handle"] not in json.dumps(captured["history"])
    assert "result_handle" not in response["data"]


def test_save_and_analysis_resolve_full_handle_membership(monkeypatch, tmp_path):
    record = _record(monkeypatch, tmp_path)
    _route_context(monkeypatch)
    captured = {}

    def fake_save_cohort(**kwargs):
        captured["saved"] = kwargs
        return {"id": "cohort-1", "patient_count": len(kwargs["patient_ids"])}

    monkeypatch.setattr(routes_module, "save_cohort", fake_save_cohort)
    saved = routes_module.create_saved_cohort(
        routes_module.SavedCohortRequest(
            name="Long cohort",
            dataset_id="dataset-a",
            result_handle=record["handle"],
            source_kind="query",
        ),
        _request(),
    )
    assert saved["patient_count"] == 607
    assert len(captured["saved"]["patient_ids"]) == 607

    monkeypatch.setattr(routes_module, "selected_lm_provider_id", lambda request: "")
    monkeypatch.setattr(routes_module, "selected_ai_provider_access", lambda request, ids: "blocked")
    monkeypatch.setattr(routes_module, "lm_provider_context", lambda provider_id: nullcontext())

    def fake_analysis(*args, **kwargs):
        captured["analysis"] = kwargs
        return {"intent": "analysis_deterministic", "reply": "ok", "data": {}}

    monkeypatch.setattr(routes_module, "analysis_llm_reply", fake_analysis)
    result = routes_module.analysis_app(
        routes_module.AnalysisRequest(
            prompt="Summarize this cohort",
            dataset_id="dataset-a",
            query_result_handle=record["handle"],
        ),
        _request(),
    )
    assert result["reply"] == "ok"
    assert captured["analysis"]["selected_patient_ids"].split(",") == [f"P{index:04d}" for index in range(607)]

    captured.pop("analysis")
    restored = routes_module.analysis_app(
        routes_module.AnalysisRequest(
            prompt="Continue the restored analysis",
            dataset_id="dataset-a",
            scope_metadata={"query_result_handle": record["handle"], "patient_ids": [], "sample_ids": []},
        ),
        _request(),
    )
    assert restored["reply"] == "ok"
    assert len(captured["analysis"]["selected_patient_ids"].split(",")) == 607

    with pytest.raises(HTTPException) as missing:
        routes_module.analysis_app(
            routes_module.AnalysisRequest(
                prompt="Do not fall back to the full workspace",
                dataset_id="dataset-a",
                scope_metadata={"query_result_handle": "qr_missing_handle"},
            ),
            _request(),
        )
    assert missing.value.status_code == 404


def test_saved_cohort_routes_deny_summary_policy(monkeypatch):
    _route_context(monkeypatch, ceiling="summary")
    with pytest.raises(HTTPException) as listed:
        routes_module.get_saved_cohorts(_request(), dataset_id="dataset-a")
    assert listed.value.status_code == 403
    with pytest.raises(HTTPException) as created:
        routes_module.create_saved_cohort(
            routes_module.SavedCohortRequest(name="Denied", dataset_id="dataset-a", patient_ids=["P1"]),
            _request(),
        )
    assert created.value.status_code == 403
