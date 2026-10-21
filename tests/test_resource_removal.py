import json

import pytest
from fastapi import HTTPException

from app import resource_install as resources


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(resources, "require_admin", lambda request: {"username": "admin"})
    monkeypatch.setattr(resources, "ROOT", tmp_path / "resources")
    monkeypatch.setattr(resources, "STATE_ROOT_DIR", tmp_path)
    monkeypatch.setattr(resources.datasets, "DATASET_REGISTRY_PATH", tmp_path / "registry.json")
    monkeypatch.setattr(resources.query_store, "QUERY_STORE_DIR", tmp_path / "stores")
    resources._jobs.clear()
    root = tmp_path / "resources/installed" / ("a" * 32)
    root.mkdir(parents=True)
    (root / ".resource-install.json").write_text(json.dumps({"complete": True, "dataset_id": "ibdmdb"}))
    (tmp_path / "registry.json").write_text(json.dumps([
        {"dataset_id": "test", "root_path": str(root), "enabled": True}]))
    return tmp_path, root


def test_remove_registration_retains_files(setup):
    tmp, root = setup
    result = resources.remove_dataset("test", resources.RemoveRequest(confirmation="test"), None)
    assert result["removed"] and not result["files_removed"]
    assert root.exists()
    assert not any(r["dataset_id"] == "test" for r in json.loads((tmp / "registry.json").read_text()))


def test_managed_files_recoverable(setup):
    tmp, root = setup
    result = resources.remove_dataset("test", resources.RemoveRequest(confirmation="test", remove_files=True), None)
    assert result["files_removed"] and not root.exists()
    assert len(list((tmp / "resources/removed").glob("*/.resource-install.json"))) == 1


@pytest.mark.parametrize("case", ["active", "bundled", "confirmation", "unmanaged"])
def test_removal_rejected_without_mutation(setup, case):
    tmp, root = setup
    dataset_id, confirmation = "test", "test"
    remove_files = False
    if case == "active":
        job = tmp / "users/other/jobs/run/job.json"
        job.parent.mkdir(parents=True)
        job.write_text('{"status": "running"}')
    elif case == "bundled":
        dataset_id = confirmation = "default"
    elif case == "confirmation":
        confirmation = "wrong"
    else:
        (root / ".resource-install.json").unlink()
        remove_files = True
    with pytest.raises(HTTPException):
        resources.remove_dataset(dataset_id, resources.RemoveRequest(
            confirmation=confirmation, remove_files=remove_files), None)
    assert root.exists()
    records = json.loads((tmp / "registry.json").read_text())
    assert next(r for r in records if r["dataset_id"] == "test")["enabled"]


def test_admin_required(setup, monkeypatch):
    def deny(request):
        raise HTTPException(403, "Admin required")
    monkeypatch.setattr(resources, "require_admin", deny)
    with pytest.raises(HTTPException) as exc:
        resources.remove_dataset("test", resources.RemoveRequest(confirmation="test"), None)
    assert exc.value.status_code == 403
