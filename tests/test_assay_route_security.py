import json

import pytest
from fastapi.testclient import TestClient

import app.auth as auth_module
import app.datasets as datasets_module
import app.query_store as query_store_module
import app.user_state as user_state_module
from app.main import app


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_private_summary_workspace_redacts_inventory_and_blocks_sample_level_assay_routes(tmp_path, monkeypatch):
    if not query_store_module.duckdb_available():
        pytest.skip("duckdb is required for assay route coverage")

    state_root = tmp_path / "state"
    release_root = tmp_path / "private-summary-release"
    clinical_root = release_root / "clinical"
    methylation_root = release_root / "assays" / "methylation"
    imaging_root = release_root / "assays" / "imaging"
    clinical_root.mkdir(parents=True)
    methylation_root.mkdir(parents=True)
    imaging_root.mkdir(parents=True)

    _write_json(
        clinical_root / "records.json",
        [{"id": "PAT001:baseline", "patient_id": "PAT001", "sex": "female"}],
    )
    (methylation_root / "m_values.csv").write_text(
        "feature_id;PAT001:baseline\ncg00000001;0.25\n",
        encoding="utf-8",
    )
    _write_json(
        release_root / "assays" / "manifest.json",
        {
            "version": 1,
            "assays": [
                {
                    "assay_id": "methylation_m_values",
                    "label": "Methylation M-values",
                    "modality": "methylation",
                    "data_type": "m_values",
                    "feature_count": 1,
                    "file": "assays/methylation/m_values.csv",
                }
            ],
        },
    )
    _write_json(
        imaging_root / "dicom_studies.json",
        {
            "version": 1,
            "studies": [
                {
                    "study_id": "study-1",
                    "patient_id": "PAT001",
                    "sample_id": "PAT001:baseline",
                    "study_instance_uid": "1.2.826.0.1.3680043.10.1",
                    "series": [],
                }
            ],
        },
    )

    monkeypatch.setenv("COHORTOME_AUTH_MODE", "local")
    monkeypatch.setenv(
        "COHORTOME_LOCAL_USERS_JSON",
        json.dumps(
            [
                {"username": "admin", "password": "admin-secret", "role": "admin"},
                {"username": "summary-user", "password": "summary-secret", "role": "user"},
            ]
        ),
    )
    monkeypatch.setattr(auth_module, "AUTH_USERS_PATH", state_root / "auth" / "users.json")
    monkeypatch.setattr(
        auth_module,
        "PASSWORD_RESET_TOKENS_PATH",
        state_root / "auth" / "password-reset-tokens.json",
    )
    monkeypatch.setattr(datasets_module, "DATASET_REGISTRY_PATH", state_root / "datasets" / "registry.json")
    monkeypatch.setattr(datasets_module, "STATE_ROOT_DIR", state_root)
    monkeypatch.setattr(user_state_module, "STATE_ROOT_DIR", state_root)
    monkeypatch.setattr(query_store_module, "QUERY_STORE_DIR", state_root / "query-store")

    _write_json(
        datasets_module.DATASET_REGISTRY_PATH,
        [
            {
                "dataset_id": "private-summary",
                "name": "Private summary workspace",
                "root_path": str(release_root),
                "enabled": True,
                "visibility": "restricted",
                "data_classification": "private",
                "allowed_users": ["summary-user"],
                "allowed_groups": [],
                "query_granularity_ceiling": "summary",
                "ai_provider_access": "blocked",
                "created_by": "admin",
                "created_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-01T00:00:00+00:00",
            }
        ],
    )
    query_store_module.prepare_dataset_query_store("private-summary")

    client = TestClient(app)
    login = client.post(
        "/auth/login",
        json={"username": "summary-user", "password": "summary-secret"},
    )
    assert login.status_code == 200

    inventory = client.get("/assays?dataset_id=private-summary")
    assert inventory.status_code == 200
    assay = next(item for item in inventory.json()["datasets"] if item["assay_id"] == "methylation_m_values")
    assert assay["sample_count"] == 1
    assert assay["patient_count"] == 1
    assert "sample_ids" not in assay
    assert "patient_ids" not in assay
    assert "PAT001" not in inventory.text

    blocked_requests = [
        client.get("/assays/readiness?dataset_id=private-summary"),
        client.get("/assays/matrix?dataset_id=private-summary"),
        client.post(
            "/assays/expression",
            json={
                "dataset_id": "private-summary",
                "assay_id": "methylation_m_values",
                "gene_id": "cg00000001",
            },
        ),
        client.get("/dicom/studies?dataset_id=private-summary"),
    ]
    assert [response.status_code for response in blocked_requests] == [403, 403, 403, 403]
    assert all("Detailed" in response.json()["detail"] for response in blocked_requests)
