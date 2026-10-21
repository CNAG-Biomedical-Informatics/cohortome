import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest

from app import resource_storage as storage, resource_install as installer
from test_resource_install import package, job


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "SETTINGS", tmp_path / "state/storage.json")
    monkeypatch.setattr(storage, "DEFAULT", tmp_path / "default")
    monkeypatch.setattr(storage, "require_admin", lambda _: {"username": "admin"})
    app = FastAPI()
    app.include_router(storage.router)
    with TestClient(app) as client:
        yield client


def test_storage_persistence_validation_and_missing_disk(client, tmp_path):
    assert client.get("/resource-storage").json()["directory"] == str(tmp_path / "default")
    assert client.put("/resource-storage", json={"directory": "relative"}).status_code == 400
    assert client.put("/resource-storage", json={"directory": str(tmp_path / "missing")}).status_code == 400
    folder = tmp_path / "external"
    folder.mkdir()
    response = client.put("/resource-storage", json={"directory": str(folder)})
    assert response.status_code == 200 and response.json()["free_bytes"] > 0
    assert storage.import_root() == folder
    folder.rmdir()
    assert client.get("/resource-storage").status_code == 503
    assert not folder.exists()


def test_storage_admin_only(client, monkeypatch):
    def denied(_):
        raise HTTPException(403)
    monkeypatch.setattr(storage, "require_admin", denied)
    assert client.get("/resource-storage").status_code == 403
    assert client.put("/resource-storage", json={"directory": "/tmp"}).status_code == 403


def test_new_folder_does_not_move_old_install_and_duplicate_stays_detected(client, tmp_path, monkeypatch):
    monkeypatch.setattr(installer, "ROOT", tmp_path / "default")
    monkeypatch.setattr(installer.datasets, "DATASET_REGISTRY_PATH", tmp_path / "registry.json")
    monkeypatch.setattr(installer.query_store, "QUERY_STORE_DIR", tmp_path / "stores")
    (tmp_path / "registry.json").write_text("[]")
    first = job()
    installer.install(first, "admin", uploaded=package(tmp_path / "package.zip"))
    assert first["stage"] == "ready"
    original = installer.datasets.get_dataset(first["dataset_id"])["root_path"]
    folder = tmp_path / "external"
    folder.mkdir()
    assert client.put("/resource-storage", json={"directory": str(folder)}).status_code == 200
    second = job()
    installer.install(second, "admin", uploaded=package(tmp_path / "package.zip"))
    assert second["dataset_id"] == first["dataset_id"]
    assert installer.datasets.get_dataset(first["dataset_id"])["root_path"] == original
    assert Path(original).is_dir()
    assert not (folder / "installed").exists()
