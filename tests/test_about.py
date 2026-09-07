import subprocess

from fastapi.testclient import TestClient

import app.about as about
from app.main import app


def test_report_allowlist_and_missing_tools(monkeypatch):
    about.version_report.cache_clear()
    monkeypatch.setattr(about, "_command", lambda args: "/private/config secret-value")
    monkeypatch.setattr(about.shutil, "which", lambda name: None)
    monkeypatch.setattr(about.metadata, "version", lambda name: "1.2.3")
    report = about.version_report()
    assert report["components"]["duckdb"] == "1.2.3"
    assert report["components"]["R"] == "Not installed"
    assert report["components"]["Source checkout revision"] == "Unavailable"
    assert "private" not in str(report)
    assert "secret-value" not in str(report)
    assert about.version_report() is report
    about.version_report.cache_clear()


def test_command_failure_is_not_exposed(monkeypatch):
    def timeout(*args, **kwargs):
        assert kwargs["timeout"] == 4
        raise subprocess.TimeoutExpired(args[0], 4, output="secret")
    monkeypatch.setattr(about.subprocess, "run", timeout)
    assert about._command(["example", "--version"]) == ""


def test_about_requires_login(monkeypatch):
    monkeypatch.setenv("COHORTOME_AUTH_MODE", "local")
    assert TestClient(app).get("/about").status_code == 401


def test_about_returns_report(monkeypatch):
    monkeypatch.setenv("COHORTOME_AUTH_MODE", "none")
    monkeypatch.setattr(about, "version_report", lambda: {"components": {"Python": "3.12"}})
    response = TestClient(app).get("/about")
    assert response.status_code == 200
    assert response.json()["components"]["Python"] == "3.12"
