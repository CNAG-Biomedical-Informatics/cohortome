import csv
from datetime import datetime, timedelta, timezone
import io
import json
import zipfile
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import cohorts, exports, query_results, routes
from app.main import app
from bff_test_helpers import isolated_registered_dataset


@pytest.fixture
def export_context(monkeypatch, tmp_path):
    monkeypatch.setenv("COHORTOME_AUTH_MODE", "none")
    root = isolated_registered_dataset(monkeypatch, tmp_path)
    monkeypatch.setattr(cohorts, "USER_STATE_ROOT", tmp_path / "state" / "users")
    monkeypatch.setattr(routes, "workspace_fingerprint_for_data_dir", lambda *a, **kw: {"token": "fixture-v1", "private_path": str(root)})
    patients = [{"patient_id": f"P{i:04d}", "sex": "female", "visit_count": 1,
                 "medication_count": 0, "dataset_ids": ["test-study"],
                 "original_record_ids": [f"S{i:04d}"],
                 "clarid": {"human_id": f"ClarID-{i}"}} for i in range(607)]
    monkeypatch.setattr(routes, "get_patients", lambda *a, **kw: patients)
    request = SimpleNamespace(session={}, headers={}, cookies={})
    record = query_results.create_query_result(
        user_id="local", dataset_id="test-study", dataset_ids=["test-study"],
        workspace_fingerprint={"token": "fixture-v1"},
        policy_binding=routes._query_result_policy_binding(["test-study"], request),
        patient_ids=[p["patient_id"] for p in patients], rows=patients, query_text="List all patients",
    )
    cohort = {"id": "cohort_test", "name": "Synthetic cohort", "dataset_id": "test-study",
              "dataset_ids": ["test-study"], "patient_ids": ["P0000"],
              "sample_ids": ["S0000", "unlinked"], "id_type": "patient",
              "data_dir": str(root), "source": {"kind": "query", "prompt": "Example", "secret": "not-exported"}}
    cohorts._write_saved_cohorts([cohort], "local")
    return TestClient(app), record, cohort, patients, root


@pytest.mark.parametrize("format,delimiter", [("tsv", "\t"), ("csv", ",")])
def test_query_exports_all_rows_and_clarids(export_context, format, delimiter):
    client, record, _, _, _ = export_context
    response = client.get(f"/query-results/{record['handle']}/export", params={"format": format})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["content-disposition"].startswith("attachment;")
    rows = list(csv.DictReader(io.StringIO(response.text), delimiter=delimiter))
    assert len(rows) == 607
    assert [row["patient_id"] for row in rows] == [f"P{i:04d}" for i in range(607)]
    assert rows[0]["subject_clarid"] == "ClarID-0"
    assert rows[0]["medication_count"] == "0"
    assert json.loads(rows[0]["dataset_ids"]) == ["test-study"]


def test_export_metadata_omits_internal_state(export_context):
    client, record, _, _, root = export_context
    response = client.get(f"/query-results/{record['handle']}/export?format=json")
    assert response.status_code == 200
    metadata = response.json()
    assert metadata["row_count"] == 607
    assert metadata["query_text"] == "List all patients"
    assert metadata["workspace_fingerprint"] == "fixture-v1"
    assert str(root) not in response.text
    assert record["cursor_secret"] not in response.text
    assert "policy_binding" not in response.text


def test_cohort_bundle_preserves_membership_without_guessing_links(export_context):
    client, _, _, _, root = export_context
    response = client.get("/saved-cohorts/cohort_test/export")
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert set(archive.namelist()) == {"membership.tsv", "metadata.json"}
        rows = list(csv.DictReader(io.StringIO(archive.read("membership.tsv").decode()), delimiter="\t"))
        assert [row["member_type"] for row in rows] == ["patient", "sample", "sample"]
        assert rows[1]["patient_id"] == "P0000"
        assert rows[1]["subject_clarid"] == "ClarID-0"
        assert rows[2]["patient_id"] == ""
        metadata = archive.read("metadata.json").decode()
        assert str(root) not in metadata
        assert "not-exported" not in metadata
        assert json.loads(metadata)["sample_ids"] == ["S0000", "unlinked"]


@pytest.mark.parametrize("kind", ["query", "cohort"])
@pytest.mark.parametrize("failure,status", [("unauthenticated", 401), ("owner", 404), ("summary", 403), ("revoked", 403)])
def test_exports_recheck_access(export_context, monkeypatch, kind, failure, status):
    client, record, _, _, _ = export_context
    if failure == "unauthenticated":
        monkeypatch.setenv("COHORTOME_AUTH_MODE", "local")
    elif failure == "owner":
        monkeypatch.setattr(routes, "request_user_identity", lambda request: "other")
        monkeypatch.setattr(routes, "request_user_id", lambda request: "other")
    elif failure == "summary":
        monkeypatch.setattr(routes, "effective_query_granularity_ceiling", lambda ids: "summary")
    else:
        def deny(*args, **kwargs):
            raise HTTPException(403, "Dataset access denied.")
        monkeypatch.setattr(routes, "resolve_dataset_ids", deny)
    url = f"/query-results/{record['handle']}/export" if kind == "query" else "/saved-cohorts/cohort_test/export"
    response = client.get(url)
    assert response.status_code == status
    assert "content-disposition" not in response.headers


@pytest.mark.parametrize("failure", ["expired", "stale", "policy"])
def test_query_export_rejects_old_results(export_context, monkeypatch, failure):
    client, record, _, _, _ = export_context
    if failure == "expired":
        monkeypatch.setattr(query_results, "_now", lambda: datetime.now(timezone.utc) + timedelta(hours=2))
    elif failure == "stale":
        monkeypatch.setattr(routes, "workspace_fingerprint_for_data_dir", lambda *a, **kw: {"token": "changed"})
    else:
        monkeypatch.setattr(routes, "_query_result_policy_binding", lambda *a: {"changed": True})
    assert client.get(f"/query-results/{record['handle']}/export").status_code == 410


def test_export_quoting_and_bounds(monkeypatch):
    rows = [{"id": '=HYPERLINK("bad")', "value": 'tab\tquote"\nline'}, {"id": "0012", "value": -2}]
    content = exports.table_bytes(rows, ("id", "value"))
    parsed = list(csv.DictReader(io.StringIO(content.decode()), delimiter="\t"))
    assert parsed[0]["id"].startswith("'=")
    assert parsed[0]["value"] == rows[0]["value"]
    assert parsed[1] == {"id": "0012", "value": "-2"}
    monkeypatch.setattr(exports, "MAX_EXPORT_ROWS", 1)
    with pytest.raises(HTTPException) as error:
        exports.table_bytes(rows, ("id",))
    assert error.value.status_code == 413


def test_sample_export_leaves_ambiguous_subject_blank():
    record = {"id_type": "sample", "items": [{"sample_id": "duplicate"}]}
    patients = [{"patient_id": "A", "original_record_ids": ["duplicate"]},
                {"patient_id": "B", "original_record_ids": ["duplicate"]}]
    rows, _ = exports.query_rows(record, patients)
    assert rows[0]["patient_id"] == ""
    assert rows[0]["subject_clarid"] == ""


def test_sort_is_global_numeric_and_matches_export(export_context):
    client, record, _, _, _ = export_context
    # Store a new result whose largest counts are outside the first page.
    record = query_results.create_query_result(
        user_id="local", dataset_id="test-study", dataset_ids=["test-study"],
        workspace_fingerprint=record["workspace_fingerprint"], policy_binding=record["policy_binding"],
        patient_ids=record["patient_ids"],
        rows=[{"patient_id": f"P{i:04d}", "visit_count": i} for i in range(607)])
    url = f"/query-results/{record['handle']}"
    parameters = {"sort_by": "visit_count", "sort_direction": "desc", "limit": 50}
    first = client.get(url, params=parameters)
    assert first.status_code == 200
    assert first.json()["patient_ids"] == [f"P{i:04d}" for i in range(606, 556, -1)]
    cursor = first.json()["next_cursor"]
    second = client.get(url, params={**parameters, "cursor": cursor}).json()
    assert second["patient_ids"][0] == "P0556"
    assert client.get(url, params={**parameters, "sort_direction": "asc", "cursor": cursor}).status_code == 400
    download = client.get(url + "/export", params={"sort_by": "visit_count", "sort_direction": "desc"})
    rows = list(csv.DictReader(io.StringIO(download.text), delimiter="\t"))
    assert len(rows) == 607
    assert [row["patient_id"] for row in rows[:50]] == first.json()["patient_ids"]
    assert rows[-1]["patient_id"] == "P0000"
    assert client.get(url, params={"sort_by": "private_path"}).status_code == 400
    assert client.get(url + "/export", params={"sort_by": "sex", "sort_direction": "invalid"}).status_code == 400


@pytest.mark.parametrize("direction,expected", [("asc", ["B", "C", "A", "D"]), ("desc", ["A", "B", "C", "D"])])
def test_sort_ties_and_missing_values(direction, expected):
    rows = [{"patient_id": "D", "visit_count": None}, {"patient_id": "C", "visit_count": 2},
            {"patient_id": "B", "visit_count": 2}, {"patient_id": "A", "visit_count": 10}]
    record = query_results.sort_query_result({"id_type": "patient"}, rows, "visit_count", direction)
    assert [item["patient_id"] for item in record["items"]] == expected
