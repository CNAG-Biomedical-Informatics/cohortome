import hashlib
import json
from pathlib import Path
import stat
import threading
import zipfile

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import httpx
import pytest

from app import resource_install as resources


def job():
    return dict(id="test-install", stage="queued", _cancel=threading.Event())


def test_bundled_catalogue_names_match_registry():
    entries = {entry["dataset_id"]: entry for entry in resources.catalogue()}
    seed = json.loads((resources.CONFIG_DIR / "datasets/registry.json").read_text())
    for record in seed:
        if record["dataset_id"] in resources.BUNDLED:
            entry = entries[record["dataset_id"]]
            assert entry["name"] == record["name"]
            assert entry["synthetic"] is True


def package(path):
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in {
            "manifest.json": {"schema_version": 1, "clinical": {"representation": "person"}},
            "clinical/records.json": [{"id": "P1", "sex": {"id": "NCIT:C16576", "label": "female"}}],
            "resource.json": {"manifest_version": 1, "schema_version": 1, "dataset_id": "test-resource", "version": "1"},
        }.items():
            archive.writestr(zipfile.ZipInfo("example/" + name, date_time=(1980, 1, 1, 0, 0, 0)), json.dumps(data))
    return path


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(resources, "ROOT", tmp_path / "resources")
    monkeypatch.setattr(resources.datasets, "DATASET_REGISTRY_PATH", tmp_path / "registry.json")
    monkeypatch.setattr(resources.datasets, "STATE_ROOT_DIR", tmp_path / "state")
    monkeypatch.setattr(resources.query_store, "QUERY_STORE_DIR", tmp_path / "stores")
    (tmp_path / "registry.json").write_text("[]")
    resources._jobs.clear()
    return tmp_path


@pytest.mark.parametrize("name", [
    "../escape", "/absolute", "a/../../escape", "a\\escape", "a/C:escape",
    "a/NUL.txt", "a/file.", "a/file ", "loose.json",
])
def test_rejects_unsafe_paths(tmp_path, name):
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr(name, "{}")
    with pytest.raises(resources.InstallError):
        resources.extract_package(archive, tmp_path / "out", job())
    assert not (tmp_path / "escape").exists()


def test_rejects_symlinks_duplicate_case_and_size(tmp_path, monkeypatch):
    archive = tmp_path / "bad.zip"
    info = zipfile.ZipInfo("a/link")
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr(info, "/outside")
    with pytest.raises(resources.InstallError):
        resources.extract_package(archive, tmp_path / "out", job())
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("a/File", "x")
        bundle.writestr("a/file", "x")
    with pytest.raises(resources.InstallError):
        resources.extract_package(archive, tmp_path / "out", job())
    monkeypatch.setattr(resources, "MAX_EXPANDED", 1)
    with pytest.raises(resources.InstallError):
        resources.extract_package(archive, tmp_path / "out", job())


def test_real_install_safe_permissions_store_and_no_workspace_change(isolated):
    resources.datasets.set_current_datasets("owner", ["default"])
    task = job()
    resources.install(task, "owner", uploaded=package(isolated / "input.zip"))
    assert task["stage"] == "ready", task
    record = resources.datasets.get_dataset(task["dataset_id"])
    assert record["visibility"] == "admin_only"
    assert record["data_classification"] == "private"
    assert record["ai_provider_access"] == "blocked"
    assert record["enabled"]
    assert resources.query_store.dataset_query_store_status(record["dataset_id"])["ready"]
    assert resources.datasets.current_dataset_ids("owner") == ["default"]
    assert not (isolated / "input.zip").exists()
    second = job()
    resources.install(second, "owner", uploaded=package(isolated / "input.zip"))
    assert second["stage"] == "ready"
    assert second["dataset_id"] == task["dataset_id"]
    assert second["already_installed"] is True
    assert "no changes made" in second["message"]


def test_geo_source_uses_existing_installer_and_cleans_staging(isolated, monkeypatch):
    from app import geo_source, geo_gse85034
    calls = []
    def fetch(target, **kw):
        calls.append("fetch")
        target.write_bytes(b"fictional GEO input")
    def build(source, archive, **kw):
        calls.append("build")
        assert source.read_bytes() == b"fictional GEO input"
        with zipfile.ZipFile(archive, "w") as bundle:
            for name, data in {
                "manifest.json": {"schema_version": 1, "clinical": {"representation": "person"}},
                "clinical/records.json": [{"id": "TEST-1"}],
                "resource.json": {"manifest_version": 1, "schema_version": 1,
                                  "dataset_id": "gse85034", "version": "0.1.0-preview"},
            }.items():
                bundle.writestr("gse85034/" + name, json.dumps(data))
    monkeypatch.setattr(geo_source, "fetch_source", fetch)
    monkeypatch.setattr(geo_gse85034, "build_package", build)
    entry = next(e for e in resources.catalogue() if e["dataset_id"] == "gse85034")
    task = job()
    task["_source_review"] = {"acknowledged_by": "owner", "statement": "Reviewed"}
    resources.install(task, "owner", entry=entry, token="must-not-be-forwarded")
    assert task["stage"] == "ready", task
    assert calls == ["fetch", "build"]
    assert resources.query_store.dataset_query_store_status(task["dataset_id"])["ready"]
    assert not list(resources.ROOT.glob(".staging-*"))
    root = Path(resources.datasets.get_dataset(task["dataset_id"])["root_path"])
    receipt = json.loads((root / ".resource-install.json").read_text())
    assert receipt["source_review"] == task["_source_review"]


def test_preparation_failure_rolls_back_and_does_not_expose_errors(isolated, monkeypatch):
    def fail(_):
        raise RuntimeError("secret source path and patient value")
    monkeypatch.setattr(resources.query_store, "prepare_dataset_query_store", fail)
    task = job()
    resources.install(task, "owner", uploaded=package(isolated / "input.zip"))
    assert task["stage"] == "failed"
    assert "secret" not in task["message"]
    assert not list((resources.ROOT / "installed").iterdir())
    assert all(x["name"] != "test-resource" for x in resources.datasets.list_registered_datasets())


def test_user_disabled_install_is_not_deleted_on_retry(isolated):
    first = job()
    resources.install(first, "owner", uploaded=package(isolated / "input.zip"))
    assert first["stage"] == "ready"
    resources.datasets.update_dataset(first["dataset_id"], enabled=False)
    second = job()
    resources.install(second, "owner", uploaded=package(isolated / "input.zip"))
    assert second["stage"] == "failed"
    assert "disabled" in second["message"]
    record = resources.datasets.get_dataset(first["dataset_id"])
    assert record and not record["enabled"] and Path(record["root_path"]).is_dir()


def test_cancellation_and_single_job(isolated):
    task = resources.new_job("first")
    with pytest.raises(HTTPException) as error:
        resources.new_job("second")
    assert error.value.status_code == 409
    task["_cancel"].set()
    resources.install(task, "owner", uploaded=package(isolated / "input.zip"))
    assert task["stage"] == "cancelled"
    assert not (resources.ROOT / "installed").exists()


def test_download_verifies_hash_and_never_redirects_credentials(tmp_path, monkeypatch):
    content = b"zip bytes"
    entry = dict(dataset_id="default", version="1", archive_bytes=len(content),
                 archive_sha256=hashlib.sha256(content).hexdigest())
    seen = []
    def handler(request):
        seen.append(request)
        if "/releases/tags/" in request.url.path:
            return httpx.Response(200, json={"assets": [{"name": "default-1.zip", "id": 7}]})
        if request.url.host == "api.github.com":
            return httpx.Response(302, headers={"location": "https://release-assets.githubusercontent.com/file"})
        return httpx.Response(200, content=content)
    real_client = httpx.Client
    monkeypatch.setattr(resources.httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    resources.download(entry, "private-token", tmp_path / "a.zip", job())
    assert seen[0].headers["authorization"] == "Bearer private-token"
    assert "authorization" not in seen[-1].headers
    entry["archive_sha256"] = "0" * 64
    with pytest.raises(resources.InstallError, match="checksum"):
        resources.download(entry, "", tmp_path / "b.zip", job())


def test_rejects_non_github_redirect(tmp_path, monkeypatch):
    def handler(request):
        if "/tags/" in request.url.path:
            return httpx.Response(200, json={"assets": [{"name": "default-1.zip", "id": 7}]})
        return httpx.Response(302, headers={"location": "http://127.0.0.1/private"})
    real_client = httpx.Client
    monkeypatch.setattr(resources.httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    with pytest.raises(resources.InstallError, match="redirect"):
        resources.download(dict(dataset_id="default", version="1", archive_bytes=10), "", tmp_path / "a.zip", job())


def test_all_routes_admin_only(isolated, monkeypatch):
    def deny(_):
        raise HTTPException(403, "Admin access required.")
    monkeypatch.setattr(resources, "require_admin", deny)
    app = FastAPI()
    app.include_router(resources.router)
    with TestClient(app) as client:
        for path in ("/resources", "/resources/jobs"):
            assert client.get(path).status_code == 403
        assert client.post("/resources/download", json={"dataset_id": "default"}).status_code == 403
        assert client.post("/resources/upload", content=b"zip").status_code == 403
        assert client.post("/resources/jobs/unknown/cancel").status_code == 403
    assert not resources.ROOT.exists()


@pytest.mark.parametrize("dataset_id", sorted(resources.BUNDLED))
def test_bundled_datasets_cannot_be_reinstalled(isolated, monkeypatch, dataset_id):
    monkeypatch.setattr(resources, "require_admin", lambda _: {"username": "owner"})
    app = FastAPI()
    app.include_router(resources.router)
    with TestClient(app) as client:
        entries = client.get("/resources").json()["resources"]
        assert next(x for x in entries if x["dataset_id"] == dataset_id)["included"]
        assert client.post("/resources/download", json={"dataset_id": dataset_id}).status_code == 409
    archive = isolated / "bundled.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("example/resource.json", json.dumps({
            "manifest_version": 1, "schema_version": 1, "dataset_id": dataset_id, "version": "new",
        }))
    task = job()
    resources.install(task, "owner", uploaded=archive)
    assert task["stage"] == "failed"
    assert "already included" in task["message"]
    assert not (resources.ROOT / "installed").exists()
