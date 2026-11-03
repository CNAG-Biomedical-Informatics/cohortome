import copy
import json

import httpx
import pytest

from app import resource_catalogue as catalogue
from app import resource_install
from fastapi import HTTPException


@pytest.fixture
def payload(tmp_path, monkeypatch):
    monkeypatch.setattr(catalogue, "CACHE", tmp_path / "catalogue.json")
    return {"catalogue_version": 1, "dataset_schema_version": 1, "datasets": catalogue.bundled()}


def mock_response(monkeypatch, payload, status=200):
    client = httpx.Client
    transport = httpx.MockTransport(lambda request: httpx.Response(status, json=payload))
    monkeypatch.setattr(catalogue.httpx, "Client", lambda **kwargs: client(transport=transport, **kwargs))


def test_refresh_and_offline_cache(payload, monkeypatch):
    assert catalogue.read()[1] == "bundled"
    mock_response(monkeypatch, payload)
    assert "refreshed" in catalogue.refresh()
    assert catalogue.read() == (payload["datasets"], "cached")


def test_failed_refresh_keeps_cache(payload, monkeypatch):
    catalogue.CACHE.write_text(json.dumps(payload))
    original = catalogue.CACHE.read_bytes()
    mock_response(monkeypatch, {}, 503)
    assert "Could not refresh" in catalogue.refresh()
    assert catalogue.CACHE.read_bytes() == original


@pytest.mark.parametrize("change", [
    lambda p: p.update(catalogue_version=2),
    lambda p: p["datasets"].append(copy.deepcopy(p["datasets"][0])),
    lambda p: p["datasets"][0].update(source_page="javascript:alert(1)"),
    lambda p: p["datasets"][0].update(command="execute something"),
    lambda p: p["datasets"][1].update(install_mode="archive", archive_sha256="invalid"),
    lambda p: p["datasets"][1].update(install_mode="unknown"),
    lambda p: p["datasets"][0].update(modality_keys="not a list"),
])
def test_invalid_remote_preserves_fallback(payload, monkeypatch, change):
    change(payload)
    mock_response(monkeypatch, payload)
    assert "Could not refresh" in catalogue.refresh()
    assert not catalogue.CACHE.exists()
    assert catalogue.read()[1] == "bundled"


def test_recipe_and_schema_compatibility(payload):
    entry = payload["datasets"][0]
    assert catalogue.compatible(entry)
    entry["recipe_version"] += 1
    assert not catalogue.compatible(entry)
    entry["dataset_id"] = "unknown-recipe"
    assert not catalogue.compatible(entry)
    archive = payload["datasets"][1]
    archive['install_mode'] = 'archive'
    archive["dataset_id"] = "new-prepared-dataset"
    assert catalogue.compatible(archive)
    archive["dataset_schema_version"] = 2
    assert not catalogue.compatible(archive)


def test_unsupported_recipe_rejected_before_job(payload, monkeypatch):
    entry = payload["datasets"][0]
    entry["recipe_version"] += 1
    monkeypatch.setattr(resource_install, "require_admin", lambda request: {"username": "local"})
    monkeypatch.setattr(resource_install, "catalogue", lambda: [entry])
    with pytest.raises(HTTPException) as error:
        resource_install.start_download(resource_install.DownloadRequest(dataset_id=entry["dataset_id"]), None)
    assert error.value.status_code == 409


def test_oversized_remote_rejected(payload, monkeypatch):
    monkeypatch.setattr(catalogue, "MAX_BYTES", 10)
    mock_response(monkeypatch, payload)
    assert "Could not refresh" in catalogue.refresh()
    assert not catalogue.CACHE.exists()


def test_refresh_requires_admin(monkeypatch):
    def denied(request):
        raise HTTPException(403, "Denied")
    monkeypatch.setattr(resource_install, "require_admin", denied)
    with pytest.raises(HTTPException) as error:
        resource_install.refresh_resources(None)
    assert error.value.status_code == 403


def test_installation_types_and_unknown_bundled_entry(payload, monkeypatch):
    included = next(e for e in payload['datasets'] if e.get('install_mode') == 'included')
    included.pop('archive_bytes', None)
    included.pop('archive_sha256', None)
    catalogue.validate(payload)
    assert catalogue.compatible(included)
    included['dataset_id'] = 'not-shipped'
    assert not catalogue.compatible(included)
    monkeypatch.setattr(resource_install, 'require_admin', lambda _: {'username': 'local'})
    monkeypatch.setattr(resource_install, 'catalogue', lambda: [included])
    with pytest.raises(HTTPException) as error:
        resource_install.start_download(resource_install.DownloadRequest(dataset_id='not-shipped'), None)
    assert error.value.status_code == 409
