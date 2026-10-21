import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app import export_settings as settings, exports, molecular_exports


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "SETTINGS_PATH", tmp_path / "state/export-settings.json")
    monkeypatch.setattr(settings, "require_admin", lambda _: {"role": "admin"})
    app = FastAPI()
    app.include_router(settings.router)
    with TestClient(app) as client:
        yield client


def test_defaults_persistence_and_enforcement(client, tmp_path):
    defaults = {"source_mib": 512, "total_source_mib": 1024, "output_mib": 256}
    assert client.get("/export-settings").json() == defaults
    assert exports.output_limit() == 256 * settings.MIB
    values = {"source_mib": 1, "total_source_mib": 2, "output_mib": 1}
    assert client.put("/export-settings", json=values).status_code == 200
    assert client.get("/export-settings").json() == values
    assert exports.output_limit() == settings.MIB
    with pytest.raises(HTTPException):
        exports.bounded_bytes(b"x" * (settings.MIB + 1))
    (tmp_path / "matrix").write_bytes(b"x" * (settings.MIB + 1))
    with pytest.raises(ValueError, match="1 MiB"):
        molecular_exports._inside(tmp_path, "matrix")


@pytest.mark.parametrize("values", [
    {"source_mib": 0}, {"source_mib": 2049}, {"output_mib": 1025},
    {"total_source_mib": 4097}, {"source_mib": 1.5}, {"source_mib": True},
    {"source_mib": 512, "total_source_mib": 1}, {"unknown": 1},
])
def test_invalid_settings_are_not_persisted(client, values):
    assert client.put("/export-settings", json=values).status_code == 422
    assert not settings.SETTINGS_PATH.exists()


def test_admin_required_for_read_and_write(client, monkeypatch):
    def denied(_):
        raise HTTPException(403, "Admin access required.")
    monkeypatch.setattr(settings, "require_admin", denied)
    assert client.get("/export-settings").status_code == 403
    assert client.put("/export-settings", json={}).status_code == 403
    assert not settings.SETTINGS_PATH.exists()


def test_bad_saved_settings_fail_closed_and_can_be_repaired(client):
    settings.SETTINGS_PATH.parent.mkdir(parents=True)
    settings.SETTINGS_PATH.write_text('{"output_mib": -1}')
    with pytest.raises(HTTPException) as error:
        exports.output_limit()
    assert error.value.status_code == 503
    assert client.put("/export-settings", json={}).status_code == 200
    assert exports.output_limit() == 256 * settings.MIB
