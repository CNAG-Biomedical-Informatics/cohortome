import json
import app.lm as lm_module
import app.routes as routes_module
from bff_test_helpers import write_json
import app.query_store as query_store_module
from app.main import app
from fastapi.testclient import TestClient
from bff_test_helpers import isolate_auth_store
from bff_test_helpers import isolate_user_state
import app.datasets as datasets_module
import app.user_state as user_state_module
import app.query as query_module
from app.query import answer_query
import app.query_policy as query_policy_module


def test_query_route_uses_authenticated_user_llm_provider_context(monkeypatch, tmp_path):
    isolate_auth_store(monkeypatch, tmp_path)
    isolate_user_state(monkeypatch, tmp_path)
    monkeypatch.setenv("COHORTOME_AUTH_MODE", "local")
    monkeypatch.setenv(
        "COHORTOME_LOCAL_USERS_JSON",
        json.dumps([{"username": "alice", "password": "secret", "role": "user", "display_name": "Alice"}]),
    )
    monkeypatch.setenv("LM_STUDIO_ENABLED", "false")
    monkeypatch.setenv(
        "COHORTOME_LLM_PROVIDERS_JSON",
        json.dumps(
            [
                {
                    "id": "cnag-route",
                    "label": "CNAG Route",
                    "base_url": "http://cnag-route:1234/v1",
                    "model": "route-model",
                    "enabled": True,
                }
            ]
        ),
    )
    observed = {}

    def fake_answer_query(*_args, **_kwargs):
        observed["base_url"] = lm_module.lm_studio_base_url()
        observed["model"] = lm_module.resolve_lm_studio_model()
        return {"intent": "test", "reply": "ok", "data": {}}

    monkeypatch.setattr(routes_module, "resolve_dataset_ids", lambda *_args, **_kwargs: ["default"])
    monkeypatch.setattr(routes_module, "resolve_dataset_dir", lambda *_args, **_kwargs: "default_dataset")
    monkeypatch.setattr(routes_module, "effective_query_granularity_ceiling", lambda *_args, **_kwargs: "detailed")
    monkeypatch.setattr(routes_module, "effective_ai_provider_access", lambda *_args, **_kwargs: "detailed_allowed")
    monkeypatch.setattr(routes_module, "answer_query", fake_answer_query)
    client = TestClient(app)

    assert client.post("/auth/login", json={"username": "alice", "password": "secret"}).status_code == 200
    assert client.patch("/user-settings", json={"llm_provider_id": "cnag-route"}).status_code == 200
    response = client.post("/query", json={"q": "Use an LLM", "dataset_id": "default"})

    assert response.status_code == 200
    assert observed == {"base_url": "http://cnag-route:1234/v1", "model": "route-model"}


def test_query_route_respects_dataset_ai_provider_access(tmp_path, monkeypatch):
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
    query_store_module.prepare_dataset_query_store("maria-dataset")

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
    assert "AI provider access is blocked for this dataset" in payload["reply"]
    assert "LM Studio fallback is currently unavailable" not in payload["reply"]
    assert payload["data"]["external_llm_allowed"] is False
    assert payload["data"]["ai_provider_access"] == "blocked"
    assert payload["data"]["ai_provider_context_granularity"] == "blocked"
    assert calls == []


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
    monkeypatch.setenv("LM_STUDIO_INCLUDE_PATIENT_WORKSPACE", "true")

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
    assert '"patient_workspace"' not in user_message
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
    monkeypatch.setenv("LM_STUDIO_INCLUDE_PATIENT_WORKSPACE", "true")

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
    assert '"patient_workspace"' not in user_message
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
    assert count_payload["reply"] == "2 patients match this query."

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
    assert "SYN001" not in shaped["reply"]
    assert "patient_id" not in shaped["data"]
    assert shaped["data"]["follow_up_suggestions"] == [
        "How many patients are in this workspace?",
        "Which patients have more than 1 medication?",
    ]
