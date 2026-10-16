import json

import pytest

from app import lm


@pytest.fixture
def registry(monkeypatch, tmp_path):
    monkeypatch.setattr(lm, "LLM_PROVIDER_REGISTRY_PATH", tmp_path / "providers.json")
    monkeypatch.delenv("COHORTOME_LLM_PROVIDERS_JSON", raising=False)
    monkeypatch.delenv("COHORTOME_LLM_PROVIDERS_FILE", raising=False)
    monkeypatch.setenv("COHORTOME_DESKTOP_MODE", "true")
    return lm.LLM_PROVIDER_REGISTRY_PATH


def test_desktop_default_is_editable_persistent_and_key_is_write_only(registry):
    lm.initialize_desktop_default_provider()
    default = lm.public_llm_provider(lm.resolve_lm_provider())
    assert default["managed"] and not default["enabled"]
    assert default["data_boundary"] == "external"
    lm.update_managed_lm_provider("system-default", {
        "base_url": "http://localhost:1234/v1", "data_boundary": "local",
        "enabled": True, "model": "test-model", "api_key": "test-secret",
        "timeout_seconds": 120,
    })
    lm.initialize_desktop_default_provider()  # The next desktop launch.
    saved = lm.resolve_lm_provider()
    assert saved["enabled"] and saved["model"] == "test-model"
    assert saved["data_boundary"] == "local" and saved["timeout"] == 120
    assert "test-secret" not in json.dumps(lm.public_llm_provider(saved))
    lm.update_managed_lm_provider("system-default", {"api_key": "", "enabled": False})
    assert lm.resolve_lm_provider()["api_key"] == "test-secret"
    assert len(lm.llm_providers()) == 1
    with pytest.raises(ValueError, match="Disable it"):
        lm.delete_managed_lm_provider("system-default")


def test_web_default_remains_read_only(registry, monkeypatch):
    monkeypatch.delenv("COHORTOME_DESKTOP_MODE")
    assert not lm.public_llm_provider(lm.resolve_lm_provider())["managed"]
    with pytest.raises(ValueError, match="read-only"):
        lm.update_managed_lm_provider("system-default", {"enabled": True})
    with pytest.raises(ValueError, match="environment configuration"):
        lm.create_managed_lm_provider({"id": "system-default", "base_url": "http://localhost/v1"})
    with pytest.raises(RuntimeError, match="desktop mode"):
        lm.initialize_desktop_default_provider()


def test_seed_preserves_other_providers_and_invalid_registry(registry):
    lm.create_managed_lm_provider({"id": "other", "base_url": "http://localhost/v1"})
    lm.initialize_desktop_default_provider()
    assert {item["id"] for item in lm.llm_providers()} == {"system-default", "other"}
    registry.write_text("not JSON")
    with pytest.raises(RuntimeError, match="invalid"):
        lm.initialize_desktop_default_provider()
    assert registry.read_text() == "not JSON"
