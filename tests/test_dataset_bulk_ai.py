import copy

import pytest
from fastapi import HTTPException

from app import datasets, routes
from app.schemas import DatasetBulkAiRequest


@pytest.fixture
def registry(monkeypatch, tmp_path):
    records = [dict(dataset_id=id, ai_provider_access="blocked", data_classification="private",
                    visibility="admin_only", root_path="unchanged") for id in ("a", "b", "c")]
    writes = []
    monkeypatch.setattr(datasets, "_registry_lock_path", lambda: tmp_path / "lock")
    monkeypatch.setattr(datasets, "_read_registry_unlocked", lambda: copy.deepcopy(records))
    monkeypatch.setattr(datasets, "_write_registry_unlocked", lambda items: writes.append(items))
    return records, writes


def test_bulk_only_updates_selected_ai_permissions(registry):
    records, writes = registry
    assert datasets.update_datasets_ai_access(["a", "b", "a"], "safe_summary") == ["a", "b"]
    assert len(writes) == 1
    assert writes[0][2] == records[2]
    for item in writes[0][:2]:
        assert item["ai_provider_access"] == "safe_summary"
        assert item["data_classification"] == "private"
        assert item["visibility"] == "admin_only"
        assert item["root_path"] == "unchanged"


@pytest.mark.parametrize("ids,access", [(["a", "missing"], "blocked"), ([], "blocked"), (["a"], "invalid")])
def test_invalid_batch_does_not_write(registry, ids, access):
    with pytest.raises(ValueError):
        datasets.update_datasets_ai_access(ids, access)
    assert registry[1] == []


def test_bulk_requires_admin_before_writing(monkeypatch, registry):
    def denied(request):
        raise HTTPException(status_code=403)
    monkeypatch.setattr(routes, "require_admin", denied)
    with pytest.raises(HTTPException) as exc:
        routes.bulk_dataset_ai_route(DatasetBulkAiRequest(dataset_ids=["a"], ai_provider_access="blocked"), None)
    assert exc.value.status_code == 403
    assert registry[1] == []
