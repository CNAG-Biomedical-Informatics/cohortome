"""Bundled datasets must survive AppImage remounts and registry updates."""
from pathlib import Path

import pytest
from fastapi import HTTPException

from app import datasets, routes, query_store


def test_desktop_registry_survives_import_and_remount(tmp_path, monkeypatch):
    monkeypatch.setenv("COHORTOME_DESKTOP_MODE", "true")
    monkeypatch.setattr(datasets, "DATASET_REGISTRY_PATH", tmp_path / "registry.json")
    monkeypatch.setattr(datasets, "STATE_ROOT_DIR", tmp_path / "state")
    monkeypatch.setattr(query_store, "QUERY_STORE_DIR", tmp_path / "cache")
    old = tmp_path / "mount-old"
    current = tmp_path / "mount-current"
    names = {"default": "synthetic-longitudinal-demo",
             "synthetic-cross-sectional-demo": "synthetic-cross-sectional-demo"}
    for mount in (old, current):
        for name in names.values():
            (mount / "datasets" / name / "clinical").mkdir(parents=True)
            (mount / "datasets" / name / "clinical" / "records.json").write_text('[{"id":"TEST001"}]')
            (mount / "datasets" / name / "manifest.json").write_text('{"clinical":{"representation":"person"}}')
    monkeypatch.setattr(datasets, "BASE_DIR", old)
    monkeypatch.setattr(datasets, "DEFAULT_DATA_DIR", str(old / "datasets" / names["default"]))
    records = [{"dataset_id": key, "root_path": str(old / "datasets" / name),
                "enabled": True, "data_classification": "public",
                "ai_provider_access": "blocked"} for key, name in names.items()]
    datasets._write_registry(records)
    imported = tmp_path / "imported"
    (imported / "clinical").mkdir(parents=True)
    (imported / "clinical" / "records.json").write_text('[{"id":"TEST002"}]')
    (imported / "manifest.json").write_text('{"clinical":{"representation":"person"}}')
    # Importing persists normalized records for existing datasets too.
    datasets.register_dataset(name="external-study", root_path=str(imported), data_classification="public")
    old.rename(tmp_path / "unmounted")
    monkeypatch.setattr(datasets, "BASE_DIR", current)
    monkeypatch.setattr(datasets, "DEFAULT_DATA_DIR", str(current / "datasets" / names["default"]))
    for key, name in names.items():
        record = datasets.get_dataset(key)
        assert Path(record["root_path"]) == current / "datasets" / name
        assert Path(record["root_path"]).is_dir()
        assert record["ai_provider_access"] == "blocked"
    assert datasets.get_dataset("external-study")["root_path"] == str(imported)
    query_store.prepare_dataset_query_store("synthetic-cross-sectional-demo")
    assert query_store.dataset_query_store_status("synthetic-cross-sectional-demo")["ready"]
    scope = Path(datasets.materialize_dataset_scope(["synthetic-cross-sectional-demo", "external-study"]))
    assert len(list((scope / "clinical").glob("*.json"))) == 2
    assert all(path.is_file() for path in (scope / "clinical").glob("*.json"))
    # Another registry save/restart still resolves against the active installation.
    datasets._write_registry(datasets.list_registered_datasets())
    assert Path(datasets.get_dataset("synthetic-cross-sectional-demo")["root_path"]).is_dir()
    monkeypatch.setenv("COHORTOME_DESKTOP_MODE", "false")
    # Web deployments retain their configured path rather than rebasing it.
    monkeypatch.setattr(datasets, "BASE_DIR", old)
    assert datasets.get_dataset("synthetic-cross-sectional-demo")["root_path"] == str(current / "datasets" / names["synthetic-cross-sectional-demo"])


def test_missing_chat_dataset_is_unavailable(monkeypatch):
    monkeypatch.setattr(routes, "resolve_dataset_ids", lambda *args: ["missing"])
    def missing(*args):
        raise FileNotFoundError("private filesystem path")
    monkeypatch.setattr(routes, "resolve_dataset_dir", missing)
    result = routes._analysis_session_workspace_status({"dataset_id": "missing"}, None)
    assert result["state"] == "unavailable"
    assert "private filesystem path" not in result["message"]
    assert "results are kept" in result["message"]


def test_missing_dataset_rebuild_returns_actionable_error(monkeypatch):
    monkeypatch.setattr(routes, "require_admin", lambda *args: None)
    def missing(*args):
        raise FileNotFoundError("private filesystem path")
    monkeypatch.setattr(routes, "prepare_dataset_query_store", missing)
    with pytest.raises(HTTPException) as error:
        routes.prepare_dataset_route("missing", None)
    assert error.value.status_code == 409
    assert "Admin > Data" in error.value.detail
    assert "private filesystem path" not in error.value.detail
