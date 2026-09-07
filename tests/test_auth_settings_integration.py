import json
import pytest
from fastapi import HTTPException
import app.routes as routes_module
from bff_test_helpers import make_request
from urllib.parse import parse_qs
from urllib.parse import urlparse
import app.auth as auth_module
import app.main as main_module
import app.user_settings as user_settings_module
from app.main import app
from fastapi.testclient import TestClient
from bff_test_helpers import isolate_auth_store
from bff_test_helpers import isolate_user_state


def test_session_secret_is_required_when_local_auth_enabled(monkeypatch):
    monkeypatch.setenv("COHORTOME_AUTH_MODE", "local")
    monkeypatch.delenv("COHORTOME_SESSION_SECRET", raising=False)

    with pytest.raises(RuntimeError, match="COHORTOME_SESSION_SECRET"):
        main_module._session_secret()

    monkeypatch.setenv("COHORTOME_SESSION_SECRET", "test-secret")
    assert main_module._session_secret() == "test-secret"


def test_local_auth_login_logout_cycle(monkeypatch, tmp_path):
    isolate_auth_store(monkeypatch, tmp_path)
    monkeypatch.setenv("COHORTOME_AUTH_MODE", "local")
    monkeypatch.setenv(
        "COHORTOME_LOCAL_USERS_JSON",
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


def test_user_settings_persist_for_local_fallback_user(monkeypatch, tmp_path):
    isolate_user_state(monkeypatch, tmp_path)
    monkeypatch.delenv("COHORTOME_AUTH_MODE", raising=False)
    client = TestClient(app)

    defaults = client.get("/user-settings")
    assert defaults.status_code == 200
    assert defaults.json()["landing_tab"] == "dashboard"
    assert defaults.json()["analysis_auto_open_jobs"] is True
    assert defaults.json()["job_notifications"] is True
    assert defaults.json()["latest_query_details"] is True

    updated = client.patch(
        "/user-settings",
        json={
            "landing_tab": "analysis",
            "query_disclosure_default": "summary",
            "analysis_auto_open_jobs": False,
            "job_notifications": False,
            "latest_query_details": False,
            "run_history_retention_days": 90,
            "pheno_default_metric": "jaccard",
            "pheno_advanced_open": True,
            "dataset_compact_view": True,
            "llm_provider_id": "cnag-120b",
        },
    )
    assert updated.status_code == 200
    payload = updated.json()
    assert payload["landing_tab"] == "analysis"
    assert payload["query_disclosure_default"] == "summary"
    assert payload["analysis_auto_open_jobs"] is False
    assert payload["latest_query_details"] is False
    assert payload["run_history_retention_days"] == 90
    assert payload["pheno_default_metric"] == "jaccard"
    assert payload["pheno_advanced_open"] is True
    assert payload["dataset_compact_view"] is True
    assert payload["llm_provider_id"] == "cnag-120b"
    persisted = user_settings_module.load_user_settings("local")
    assert persisted["landing_tab"] == "analysis"
    assert persisted["job_notifications"] is False
    assert persisted["latest_query_details"] is False
    assert persisted["llm_provider_id"] == "cnag-120b"


def test_user_settings_are_scoped_to_authenticated_user(monkeypatch, tmp_path):
    isolate_auth_store(monkeypatch, tmp_path)
    isolate_user_state(monkeypatch, tmp_path)
    monkeypatch.setenv("COHORTOME_AUTH_MODE", "local")
    monkeypatch.setenv(
        "COHORTOME_LOCAL_USERS_JSON",
        json.dumps(
            [
                {"username": "alice", "password": "secret", "role": "user", "display_name": "Alice"},
                {"username": "bob", "password": "secret", "role": "user", "display_name": "Bob"},
            ]
        ),
    )
    alice = TestClient(app)
    bob = TestClient(app)

    assert alice.post("/auth/login", json={"username": "alice", "password": "secret"}).status_code == 200
    assert bob.post("/auth/login", json={"username": "bob", "password": "secret"}).status_code == 200

    updated = alice.patch("/user-settings", json={"landing_tab": "pheno", "dashboard_assays_open": True})
    assert updated.status_code == 200
    assert updated.json()["landing_tab"] == "pheno"

    assert alice.get("/user-settings").json()["landing_tab"] == "pheno"
    bob_settings = bob.get("/user-settings").json()
    assert bob_settings["landing_tab"] == "dashboard"
    assert bob_settings["dashboard_assays_open"] is False


def test_user_settings_reject_invalid_values(monkeypatch, tmp_path):
    isolate_user_state(monkeypatch, tmp_path)
    monkeypatch.delenv("COHORTOME_AUTH_MODE", raising=False)
    client = TestClient(app)

    response = client.patch("/user-settings", json={"landing_tab": "admin"})

    assert response.status_code == 422


def test_auth_enabled_protects_workspace_routes(monkeypatch, tmp_path):
    isolate_auth_store(monkeypatch, tmp_path)
    monkeypatch.setenv("COHORTOME_AUTH_MODE", "local")
    monkeypatch.setenv(
        "COHORTOME_LOCAL_USERS_JSON",
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
    monkeypatch.setenv("COHORTOME_AUTH_MODE", "local")
    monkeypatch.setenv(
        "COHORTOME_LOCAL_USERS_JSON",
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


def test_auth_debug_requires_admin_when_auth_enabled(monkeypatch, tmp_path):
    isolate_auth_store(monkeypatch, tmp_path)
    monkeypatch.setenv("COHORTOME_AUTH_MODE", "local")
    monkeypatch.setenv(
        "COHORTOME_LOCAL_USERS_JSON",
        json.dumps(
            [
                {"username": "admin", "password": "secret", "role": "admin", "display_name": "Admin User"},
                {"username": "maria", "password": "demo", "role": "user", "display_name": "Maria"},
            ]
        ),
    )
    client = TestClient(app)

    assert client.get("/auth/debug").status_code == 403

    login_user = client.post("/auth/login", json={"username": "maria", "password": "demo"})
    assert login_user.status_code == 200
    assert client.get("/auth/debug").status_code == 403

    client.post("/auth/logout")
    login_admin = client.post("/auth/login", json={"username": "admin", "password": "secret"})
    assert login_admin.status_code == 200
    response = client.get("/auth/debug")
    assert response.status_code == 200
    assert response.json()["user_count"] == 2


def test_auth_admin_can_create_update_reset_and_delete_local_users(monkeypatch, tmp_path):
    isolate_auth_store(monkeypatch, tmp_path)
    monkeypatch.setenv("COHORTOME_AUTH_MODE", "local")
    monkeypatch.setenv(
        "COHORTOME_LOCAL_USERS_JSON",
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
    deleted_payload = deleted.json()
    assert deleted_payload["deleted"] is True
    assert deleted_payload["id"] == "alice"
    assert deleted_payload["deleted_generated_data"] is False
    assert deleted_payload["deleted_job_count"] == 0
    assert deleted_payload["related_job_count"] == 0
    assert deleted_payload["deleted_count"] == 0
    assert deleted_payload["skipped_active_count"] == 0
    assert deleted_payload["kept_job_count"] == 0
    listing = client.get("/auth/users")
    assert listing.status_code == 200
    assert [item["username"] for item in listing.json()["users"]] == ["admin"]


def test_auth_admin_can_create_and_update_user_email(monkeypatch, tmp_path):
    isolate_auth_store(monkeypatch, tmp_path)
    monkeypatch.setenv("COHORTOME_AUTH_MODE", "local")
    monkeypatch.setenv(
        "COHORTOME_LOCAL_USERS_JSON",
        json.dumps([{"username": "admin", "password": "secret", "role": "admin", "display_name": "Admin User"}]),
    )
    client = TestClient(app)

    assert client.post("/auth/login", json={"username": "admin", "password": "secret"}).status_code == 200
    created = client.post(
        "/auth/users",
        json={
            "username": "alice",
            "password": "first-secret",
            "display_name": "Alice Example",
            "email": "alice@example.org",
            "role": "user",
            "groups": [],
            "enabled": True,
        },
    )
    assert created.status_code == 200
    assert created.json()["email"] == "alice@example.org"

    updated = client.patch("/auth/users/alice", json={"email": "alice.updated@example.org"})
    assert updated.status_code == 200
    assert updated.json()["email"] == "alice.updated@example.org"

    listing = client.get("/auth/users")
    assert listing.status_code == 200
    alice = next(item for item in listing.json()["users"] if item["username"] == "alice")
    assert alice["email"] == "alice.updated@example.org"


def test_password_reset_reports_disabled_without_smtp(monkeypatch, tmp_path):
    isolate_auth_store(monkeypatch, tmp_path)
    monkeypatch.setenv("COHORTOME_AUTH_MODE", "local")
    monkeypatch.delenv("COHORTOME_SMTP_HOST", raising=False)
    monkeypatch.delenv("COHORTOME_SMTP_FROM", raising=False)
    monkeypatch.setenv(
        "COHORTOME_LOCAL_USERS_JSON",
        json.dumps([{"username": "alice", "password": "secret", "role": "user", "email": "alice@example.org"}]),
    )
    client = TestClient(app)

    status = client.get("/auth/me")
    assert status.status_code == 200
    assert status.json()["password_reset_enabled"] is False

    response = client.post("/auth/password-reset/request", json={"identifier": "alice"})
    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert "not configured" in response.json()["message"]
    assert not auth_module.PASSWORD_RESET_TOKENS_PATH.exists()


def test_password_reset_request_is_non_enumerating_and_confirms_once(monkeypatch, tmp_path):
    isolate_auth_store(monkeypatch, tmp_path)
    monkeypatch.setenv("COHORTOME_AUTH_MODE", "local")
    monkeypatch.setenv("COHORTOME_SMTP_HOST", "smtp.example.org")
    monkeypatch.setenv("COHORTOME_SMTP_FROM", "patient_workspace@example.org")
    monkeypatch.setenv("COHORTOME_PUBLIC_BASE_URL", "https://patient_workspace.example.org")
    monkeypatch.setenv(
        "COHORTOME_LOCAL_USERS_JSON",
        json.dumps(
            [
                {
                    "username": "alice",
                    "password": "old-secret",
                    "role": "user",
                    "display_name": "Alice",
                    "email": "alice@example.org",
                }
            ]
        ),
    )
    sent_messages = []

    def fake_send_password_reset_email(user, reset_url):
        sent_messages.append({"user": user["username"], "reset_url": reset_url})

    monkeypatch.setattr(auth_module, "send_password_reset_email", fake_send_password_reset_email)
    client = TestClient(app)

    unknown = client.post("/auth/password-reset/request", json={"identifier": "missing@example.org"})
    assert unknown.status_code == 200
    assert unknown.json()["message"] == "If an account exists, reset instructions were sent."
    assert sent_messages == []

    requested = client.post("/auth/password-reset/request", json={"identifier": "alice@example.org"})
    assert requested.status_code == 200
    assert requested.json()["message"] == "If an account exists, reset instructions were sent."
    assert len(sent_messages) == 1
    token = parse_qs(urlparse(sent_messages[0]["reset_url"]).query)["password_reset_token"][0]
    stored = json.loads(auth_module.PASSWORD_RESET_TOKENS_PATH.read_text(encoding="utf-8"))
    assert stored["tokens"][0]["username"] == "alice"
    assert stored["tokens"][0]["token_hash"] != token

    confirm = client.post("/auth/password-reset/confirm", json={"token": token, "password": "new-secret"})
    assert confirm.status_code == 200
    assert client.post("/auth/login", json={"username": "alice", "password": "old-secret"}).status_code == 401
    assert client.post("/auth/login", json={"username": "alice", "password": "new-secret"}).status_code == 200

    reused = client.post("/auth/password-reset/confirm", json={"token": token, "password": "third-secret"})
    assert reused.status_code == 400


def test_oidc_login_maps_verified_email_to_local_user(monkeypatch, tmp_path):
    isolate_auth_store(monkeypatch, tmp_path)
    monkeypatch.setenv("COHORTOME_AUTH_MODE", "oidc")
    monkeypatch.setenv("COHORTOME_OIDC_PROVIDER_NAME", "Dex")
    monkeypatch.setenv("COHORTOME_OIDC_ISSUER", "http://127.0.0.1:5556/dex")
    monkeypatch.setenv("COHORTOME_OIDC_CLIENT_ID", "cohortome")
    monkeypatch.setenv("COHORTOME_OIDC_CLIENT_SECRET", "cohortome-secret")
    monkeypatch.setenv("COHORTOME_OIDC_REDIRECT_URI", "http://127.0.0.1:8000/auth/oidc/callback")
    monkeypatch.setenv(
        "COHORTOME_LOCAL_USERS_JSON",
        json.dumps(
            [
                {
                    "username": "mrueda",
                    "password": "local-secret",
                    "role": "admin",
                    "display_name": "Manuel Rueda",
                    "email": "manuel.rueda@cnag.eu",
                    "groups": ["cnag"],
                }
            ]
        ),
    )

    def fake_oidc_authorization_url(state, nonce):
        return f"https://dex.example.test/auth?state={state}&nonce={nonce}"

    def fake_oidc_userinfo_from_code(code):
        assert code == "valid-code"
        return {
            "sub": "cohortome-dev-mrueda",
            "email": "manuel.rueda@cnag.eu",
            "email_verified": True,
            "name": "Manuel Rueda",
        }

    monkeypatch.setattr(routes_module, "oidc_authorization_url", fake_oidc_authorization_url)
    monkeypatch.setattr(routes_module, "oidc_userinfo_from_code", fake_oidc_userinfo_from_code)
    client = TestClient(app)

    me_before = client.get("/auth/me")
    assert me_before.status_code == 200
    assert me_before.json()["mode"] == "oidc"
    assert me_before.json()["provider"] == "Dex"
    assert me_before.json()["authenticated"] is False

    start = client.get("/auth/login", follow_redirects=False)
    assert start.status_code == 303
    location = start.headers["location"]
    state = parse_qs(urlparse(location).query)["state"][0]

    callback = client.get(f"/auth/oidc/callback?code=valid-code&state={state}", follow_redirects=False)
    assert callback.status_code == 303
    assert callback.headers["location"] == "/"

    me_after = client.get("/auth/me")
    assert me_after.status_code == 200
    assert me_after.json()["authenticated"] is True
    assert me_after.json()["user"]["username"] == "mrueda"
    assert me_after.json()["user"]["role"] == "admin"
    assert me_after.json()["user"]["groups"] == ["cnag"]
    assert me_after.json()["user"]["login_method"] == "oidc"


def test_oidc_callback_rejects_unmapped_user(monkeypatch, tmp_path):
    isolate_auth_store(monkeypatch, tmp_path)
    monkeypatch.setenv("COHORTOME_AUTH_MODE", "oidc")
    monkeypatch.setenv("COHORTOME_OIDC_PROVIDER_NAME", "Dex")
    monkeypatch.setenv("COHORTOME_OIDC_ISSUER", "http://127.0.0.1:5556/dex")
    monkeypatch.setenv("COHORTOME_OIDC_CLIENT_ID", "cohortome")
    monkeypatch.setenv("COHORTOME_OIDC_CLIENT_SECRET", "cohortome-secret")
    monkeypatch.setenv("COHORTOME_OIDC_REDIRECT_URI", "http://127.0.0.1:8000/auth/oidc/callback")
    monkeypatch.setenv(
        "COHORTOME_LOCAL_USERS_JSON",
        json.dumps([{"username": "admin", "password": "secret", "role": "admin", "email": "admin@example.org"}]),
    )
    monkeypatch.setattr(
        routes_module,
        "oidc_authorization_url",
        lambda state, nonce: f"https://dex.example.test/auth?state={state}&nonce={nonce}",
    )
    monkeypatch.setattr(
        routes_module,
        "oidc_userinfo_from_code",
        lambda code: {"sub": "unknown", "email": "unknown@example.org", "email_verified": True},
    )
    client = TestClient(app)

    start = client.get("/auth/login", follow_redirects=False)
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    callback = client.get(f"/auth/oidc/callback?code=valid-code&state={state}", follow_redirects=False)

    assert callback.status_code == 403
    assert client.get("/auth/me").json()["authenticated"] is False


def test_oidc_mode_can_enable_local_password_fallback(monkeypatch, tmp_path):
    isolate_auth_store(monkeypatch, tmp_path)
    monkeypatch.setenv("COHORTOME_AUTH_MODE", "oidc")
    monkeypatch.setenv("COHORTOME_AUTH_LOCAL_FALLBACK", "true")
    monkeypatch.setenv("COHORTOME_OIDC_PROVIDER_NAME", "Dex")
    monkeypatch.setenv("COHORTOME_OIDC_ISSUER", "http://127.0.0.1:5556/dex")
    monkeypatch.setenv("COHORTOME_OIDC_CLIENT_ID", "cohortome")
    monkeypatch.setenv("COHORTOME_OIDC_CLIENT_SECRET", "cohortome-secret")
    monkeypatch.setenv("COHORTOME_OIDC_REDIRECT_URI", "http://127.0.0.1:8000/auth/oidc/callback")
    monkeypatch.setenv(
        "COHORTOME_LOCAL_USERS_JSON",
        json.dumps([{"username": "admin", "password": "secret", "role": "admin", "email": "admin@example.org"}]),
    )
    client = TestClient(app)

    status = client.get("/auth/me")
    assert status.status_code == 200
    assert status.json()["mode"] == "oidc"
    assert status.json()["local_login_enabled"] is True

    login = client.post("/auth/login", json={"username": "admin", "password": "secret"})
    assert login.status_code == 200
    assert login.json()["authenticated"] is True
    assert login.json()["local_login_enabled"] is True
    assert login.json()["user"]["username"] == "admin"
    assert login.json()["user"]["login_method"] == "local"
    assert client.get("/auth/me").json()["user"]["login_method"] == "local"


def test_auth_admin_cannot_delete_last_enabled_admin(monkeypatch, tmp_path):
    isolate_auth_store(monkeypatch, tmp_path)
    monkeypatch.setenv("COHORTOME_AUTH_MODE", "local")
    monkeypatch.setenv(
        "COHORTOME_LOCAL_USERS_JSON",
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
    monkeypatch.setenv("COHORTOME_AUTH_MODE", "local")
    monkeypatch.setenv(
        "COHORTOME_LOCAL_USERS_JSON",
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
    monkeypatch.setenv("COHORTOME_AUTH_MODE", "local")
    monkeypatch.setenv(
        "COHORTOME_LOCAL_USERS_JSON",
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


def test_auth_and_saved_cohort_route_wrappers_cover_common_error_paths(monkeypatch):
    monkeypatch.setattr(routes_module, "auth_enabled", lambda: False)
    login_payload = routes_module.login_local(make_request(), routes_module.LoginRequest(username="u", password="p"))
    assert login_payload["enabled"] is False
    assert login_payload["authenticated"] is True
    assert login_payload["mode"] == "none"
    assert login_payload["provider"] == "none"
    assert login_payload["local_login_enabled"] is False
    assert login_payload["password_reset_enabled"] is False

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
