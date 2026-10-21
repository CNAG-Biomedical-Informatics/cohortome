import json
from pathlib import Path
import pytest
from fastapi import HTTPException
import app.routes as routes_module
from app.query_store import duckdb_available
from bff_test_helpers import isolate_query_store
from bff_test_helpers import make_request
from bff_test_helpers import write_json
import app.query_store as query_store_module
from types import SimpleNamespace
from app.main import app
from fastapi.testclient import TestClient
from bff_test_helpers import isolate_auth_store
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import app.datasets as datasets_module
import app.dicom as dicom_module
import app.user_state as user_state_module
import scripts.register_dataset as register_dataset_script
from app.bff import build_patient_workspace
from app.main import get_patient_workspace
from app.query_store import assay_dataset_inventory as store_assay_dataset_inventory
from app.query_store import patient_inventory as store_patient_inventory


def test_multimodal_readiness_reports_overlap_and_linkage_issues(tmp_path, monkeypatch):
    if not duckdb_available():
        return

    isolate_query_store(monkeypatch, tmp_path)
    monkeypatch.setattr(routes_module, "_resolve_route_dataset_dir", lambda _request, _dataset_id, data_dir: data_dir)
    monkeypatch.setattr(routes_module, "resolve_dataset_ids", lambda _request, _dataset_id="": ["synthetic"])
    monkeypatch.setattr(routes_module, "effective_query_granularity_ceiling", lambda _dataset_ids: "detailed")
    write_json(
        tmp_path,
        "records.json",
        [
            {
                "id": "SYN011:week_0",
                "patient_id": "SYN011",
                "diseases": [{"diseaseCode": {"label": "Multiple Sclerosis"}}],
                "info": {"event_date": "2024-01-01"},
            },
            {
                "id": "SYN012:week_0",
                "patient_id": "SYN012",
                "diseases": [{"diseaseCode": {"label": "Crohn Disease"}}],
                "info": {"event_date": "2024-01-01"},
            },
            {
                "id": "SYN013:week_0",
                "patient_id": "SYN013",
                "diseases": [{"diseaseCode": {"label": "Multiple Sclerosis"}}],
                "info": {"event_date": "2024-01-01"},
            },
        ],
    )
    transcriptomics_dir = tmp_path / "assays" / "transcriptomics"
    transcriptomics_dir.mkdir(parents=True)
    (transcriptomics_dir / "synthetic_transcriptome_raw_counts.csv").write_text(
        "\n".join(["gene_id;SYN011:week_0;SYN012:week_0", "ENSG00000111111;10;20"]),
        encoding="utf-8",
    )
    imaging_dir = tmp_path / "assays" / "imaging"
    imaging_dir.mkdir(parents=True)
    (imaging_dir / "synthetic_imaging_derived_features.csv").write_text(
        "\n".join(["feature_id;SYN011:week_0;SYN013:week_0", "lesion_volume_ml;1.2;0.4"]),
        encoding="utf-8",
    )
    (imaging_dir / "dicom_studies.json").write_text(
        json.dumps(
            {
                "version": 1,
                "studies": [
                    {
                        "study_id": "ms-syn011",
                        "label": "Synthetic MS brain MRI SYN011",
                        "patient_id": "SYN011",
                        "sample_id": "SYN011:week_0",
                        "study_instance_uid": "1.2.826.0.1.3680043.10.54321.100.1",
                        "series": [],
                    },
                    {
                        "study_id": "bad-ms-syn012",
                        "label": "Synthetic MS brain MRI SYN012",
                        "patient_id": "SYN012",
                        "sample_id": "SYN012:missing",
                        "study_instance_uid": "1.2.826.0.1.3680043.10.54321.100.2",
                        "series": [],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "assays" / "manifest.json").write_text(
        json.dumps(
            {
                "version": 1,
                "assays": [
                    {
                        "assay_id": "synthetic_imaging_derived_features",
                        "label": "synthetic imaging derived features",
                        "modality": "imaging",
                        "data_type": "dicom_derived_measurements",
                        "file": "assays/imaging/synthetic_imaging_derived_features.csv",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    payload = routes_module.get_assay_readiness(make_request({"user": {"username": "maria"}}), data_dir=str(tmp_path))

    modalities = {item["key"]: item for item in payload["modalities"]}
    assert payload["workspace"]["patient_count"] == 3
    assert modalities["transcriptomics"]["patient_count"] == 2
    assert modalities["imaging"]["patient_count"] == 2
    assert modalities["dicom"]["study_count"] == 2
    assert any(
        item["left"] == "imaging" and item["right"] == "transcriptomics" and item["patient_overlap_count"] == 1
        for item in payload["pairwise_overlaps"]
    )
    issue_kinds = {item["kind"] for item in payload["issues"]}
    assert "dicom_sample_without_clinical_timepoint" in issue_kinds
    assert "ms_dicom_without_ms_diagnosis" in issue_kinds
    suggestions = {item["key"]: item for item in payload["suggestions"]}
    assert suggestions["dicom_review"]["enabled"] is True
    assert suggestions["patient_level_cross_modal"]["enabled"] is True


def test_dataset_content_metadata_reports_patients_timepoints_and_matrices(tmp_path):
    dataset_root = tmp_path / "synthetic-large"
    clinical_root = dataset_root / "clinical"
    transcriptomics_root = dataset_root / "assays" / "transcriptomics"
    clinical_root.mkdir(parents=True)
    transcriptomics_root.mkdir(parents=True)
    write_json(dataset_root, "manifest.json", {"schema_version": 1, "clinical": {"representation": "snapshot"}})
    write_json(
        clinical_root,
        "records.json",
        [
            {"id": "P1:baseline", "patient_id": "P1"},
            {"id": "P1:week_4", "patient_id": "P1"},
            {"id": "P2:baseline", "patient_id": "P2"},
        ],
    )
    (transcriptomics_root / "counts_a.csv").write_text("gene_id,P1:baseline\nENSG00000141510,10\n", encoding="utf-8")
    (transcriptomics_root / "counts_b.csv").write_text("gene_id,P2:baseline\nENSG00000171862,11\n", encoding="utf-8")

    metadata = datasets_module.dataset_content_metadata(str(dataset_root))

    assert metadata["patient_count"] == 2
    assert metadata["clinical_record_count"] == 3
    assert metadata["clinical_representation"] == "snapshot"
    assert metadata["assay_file_count"] == 2
    assert metadata["content_tags"] == ["2 patients", "3 timepoints", "2 matrices", "large transcriptome"]
    assert metadata["content_summary"] == ""


def test_dataset_content_metadata_labels_person_representation_without_visits(tmp_path):
    dataset_root = tmp_path / "cross-sectional"
    clinical_root = dataset_root / "clinical"
    clinical_root.mkdir(parents=True)
    write_json(dataset_root, "manifest.json", {"schema_version": 1, "clinical": {"representation": "person"}})
    write_json(
        clinical_root,
        "individuals.json",
        [
            {"id": "P1", "patient_id": "P1"},
            {"id": "P2", "patient_id": "P2"},
        ],
    )

    metadata = datasets_module.dataset_content_metadata(str(dataset_root))

    assert metadata["patient_count"] == 2
    assert metadata["clinical_record_count"] == 2
    assert metadata["clinical_representation"] == "person"
    assert metadata["content_tags"] == ["2 patients", "2 person records"]
    assert all("visit" not in tag and "timepoint" not in tag for tag in metadata["content_tags"])


def test_dataset_registry_filters_by_user_and_persists_current_selection(tmp_path, monkeypatch):
    isolate_auth_store(monkeypatch, tmp_path)
    isolate_query_store(monkeypatch, tmp_path)
    monkeypatch.setenv("COHORTOME_AUTH_MODE", "local")
    monkeypatch.setenv(
        "COHORTOME_LOCAL_USERS_JSON",
        json.dumps(
            [
                {"username": "admin", "password": "secret", "role": "admin", "display_name": "Admin"},
                {"username": "maria", "password": "demo", "role": "user", "display_name": "Maria"},
            ]
        ),
    )
    monkeypatch.setattr(datasets_module, "DATASET_REGISTRY_PATH", tmp_path / "state" / "datasets" / "registry.json")
    monkeypatch.setattr(datasets_module, "STATE_ROOT_DIR", tmp_path / "state")
    monkeypatch.setattr(user_state_module, "STATE_ROOT_DIR", tmp_path / "state")

    restricted_root = tmp_path / "restricted"
    restricted_clinical = restricted_root / "clinical"
    restricted_clinical.mkdir(parents=True)
    write_json(restricted_root, "manifest.json", {"schema_version": 1, "clinical": {"representation": "person"}})
    write_json(restricted_clinical, "records.json", [{"id": "M1:week_0", "patient_id": "M1"}])

    admin_root = tmp_path / "admin-only"
    admin_clinical = admin_root / "clinical"
    admin_clinical.mkdir(parents=True)
    write_json(admin_clinical, "records.json", [{"id": "A1:week_0", "patient_id": "A1"}])

    registry = [
        {
            "dataset_id": "default",
            "name": "Synthetic longitudinal demo",
            "root_path": str(admin_root),
            "enabled": True,
            "visibility": "admin_only",
            "allowed_users": [],
            "created_by": "system",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        },
        {
            "dataset_id": "maria-dataset",
            "name": "Maria dataset",
            "root_path": str(restricted_root),
            "enabled": True,
            "visibility": "restricted",
            "allowed_users": ["maria"],
            "created_by": "admin",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        },
    ]
    datasets_module.DATASET_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    datasets_module.DATASET_REGISTRY_PATH.write_text(json.dumps(registry), encoding="utf-8")
    query_store_module.prepare_dataset_query_store("maria-dataset")

    client = TestClient(app)
    login = client.post("/auth/login", json={"username": "maria", "password": "demo"})
    assert login.status_code == 200

    listed = client.get("/datasets")
    assert listed.status_code == 200
    assert [item["dataset_id"] for item in listed.json()["datasets"]] == ["maria-dataset"]
    assert listed.json()["current_dataset_id"] == ""
    assert listed.json()["current_dataset_ids"] == []
    assert listed.json()["datasets"][0]["root_path"] == ""
    assert listed.json()["datasets"][0]["clinical_representation"] == "person"

    denied = client.get("/patients?dataset_id=default")
    assert denied.status_code == 403

    invalid = client.post("/datasets/select", json={"dataset_ids": [""]})
    assert invalid.status_code == 400
    assert client.get("/datasets").json()["current_dataset_ids"] == []

    selected = client.post("/datasets/select", json={"dataset_id": "maria-dataset"})
    assert selected.status_code == 200
    assert selected.json()["current_dataset_id"] == "maria-dataset"

    invalid = client.post("/datasets/select", json={"dataset_ids": [""]})
    assert invalid.status_code == 400
    assert client.get("/datasets").json()["current_dataset_ids"] == ["maria-dataset"]

    patients = client.get("/patients")
    assert patients.status_code == 200
    assert patients.json()[0]["patient_id"] == "M1"
    assert patients.json()[0]["clinical_representation"] == "person"
    assert patients.json()[0]["source_files"] == ["maria-dataset:clinical/records.json"]
    assert str(tmp_path) not in json.dumps(patients.json())

    unloaded = client.post("/datasets/select", json={"dataset_ids": []})
    assert unloaded.status_code == 200
    assert unloaded.json()["selected"] is False
    assert unloaded.json()["current_dataset_ids"] == []
    assert client.get("/datasets").json()["current_dataset_ids"] == []
    assert client.get("/patients").status_code == 409


def test_dicom_studies_route_lists_authorized_dataset_manifest(tmp_path, monkeypatch):
    monkeypatch.setenv("COHORTOME_DICOM_ENABLED", "true")
    monkeypatch.setenv("COHORTOME_OHIF_PUBLIC_URL", "http://ohif.example")
    monkeypatch.setattr(dicom_module, "orthanc_health", lambda: {"checked": False, "reachable": False, "message": "mocked"})
    monkeypatch.setattr(routes_module, "require_authenticated", lambda request: {"username": "maria"})

    dataset_root = tmp_path / "dicom-dataset"
    (dataset_root / "clinical").mkdir(parents=True)
    write_json(dataset_root / "clinical", "records.json", [{"id": "M1:week_0", "patient_id": "M1"}])
    imaging_dir = dataset_root / "assays" / "imaging"
    imaging_dir.mkdir(parents=True)
    (imaging_dir / "dicom_studies.json").write_text(
        json.dumps(
            {
                "version": 1,
                "studies": [
                    {
                        "study_id": "m1-mri",
                        "label": "M1 MRI",
                        "patient_id": "M1",
                        "sample_id": "M1:week_0",
                        "timepoint": "week_0",
                        "modality": "MR",
                        "study_instance_uid": "1.2.826.0.1.1",
                        "series": [{"series_instance_uid": "1.2.826.0.1.1.1", "instance_count": 2}],
                    },
                    {"study_instance_uid": "../invalid"},
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(routes_module, "_resolve_route_dataset_dir", lambda request, dataset_id, data_dir: str(dataset_root))
    monkeypatch.setattr(routes_module, "resolve_dataset_ids", lambda request, dataset_id="": ["dicom-dataset"])
    monkeypatch.setattr(routes_module, "effective_query_granularity_ceiling", lambda dataset_ids: "detailed")

    payload = routes_module.get_dicom_studies(make_request({"user": {"username": "maria"}}), dataset_id="dicom-dataset")

    assert payload["enabled"] is True
    assert payload["ohif_public_url"] == "http://ohif.example"
    assert len(payload["studies"]) == 1
    study = payload["studies"][0]
    assert study["study_instance_uid"] == "1.2.826.0.1.1"
    assert study["ohif_url"] == "http://ohif.example/viewer?StudyInstanceUIDs=1.2.826.0.1.1"
    assert study["series"][0]["instance_count"] == 2
    status = routes_module.get_dicom_status(make_request({"user": {"username": "maria"}}), dataset_id="dicom-dataset")
    assert status["manifest_found"] is True
    assert status["manifest_count"] == 1
    assert "manifest_paths" not in status
    assert "COHORTOME_ORTHANC_PASSWORD" not in json.dumps(status)


def test_dicom_studies_route_enforces_dataset_access(tmp_path, monkeypatch):
    monkeypatch.setattr(routes_module, "require_authenticated", lambda request: {"username": "maria"})

    def deny_dataset(_request, _dataset_id, _data_dir):
        raise HTTPException(status_code=403, detail="Dataset access denied.")

    monkeypatch.setattr(routes_module, "_resolve_route_dataset_dir", deny_dataset)

    with pytest.raises(HTTPException) as exc:
        routes_module.get_dicom_studies(make_request({"user": {"username": "maria"}}), dataset_id="admin-only")

    assert exc.value.status_code == 403


def test_synthetic_dicom_fixtures_use_visible_mr_pixel_data():
    import hashlib

    pydicom = pytest.importorskip("pydicom")
    from pydicom.uid import MRImageStorage

    manifest_path = Path("datasets/synthetic-longitudinal-demo/assays/imaging/dicom_studies.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    studies = manifest.get("studies", [])
    study_profiles = {study["study_id"]: study.get("synthetic_profile") for study in studies}
    study_patients = {study["study_id"]: study.get("patient_id") for study in studies}
    assert study_profiles["synthetic-mri-syn001-week0"] == "smoke_test"
    assert sum(1 for profile in study_profiles.values() if str(profile).startswith("ms_brain")) >= 2

    clinical_records = json.loads(Path("datasets/synthetic-longitudinal-demo/clinical/synthetic_longitudinal.json").read_text(encoding="utf-8"))
    patient_diseases: dict[str, set[str]] = {}
    for record in clinical_records:
        patient_id = str(record.get("patient_id") or "")
        for disease in record.get("diseases") or []:
            code = disease.get("diseaseCode") if isinstance(disease, dict) else {}
            patient_diseases.setdefault(patient_id, set()).add(str(code.get("label") or ""))
    for study_id, profile in study_profiles.items():
        if str(profile).startswith("ms_brain"):
            assert "Multiple Sclerosis" in patient_diseases.get(str(study_patients.get(study_id) or ""), set())

    paths = sorted(Path("datasets/synthetic-longitudinal-demo/assays/imaging/dicom").glob("*.dcm"))
    assert paths
    pixel_hashes = set()
    for path in paths:
        ds = pydicom.dcmread(str(path))
        pixels = ds.pixel_array
        study_id = path.name.split("__", 1)[0]

        assert str(ds.SOPClassUID) == MRImageStorage
        assert str(ds.PhotometricInterpretation) == "MONOCHROME2"
        assert int(ds.BitsAllocated) == 16
        assert int(ds.BitsStored) == 16
        assert float(ds.WindowCenter) > 0
        assert float(ds.WindowWidth) > 0
        assert int(pixels.max()) - int(pixels.min()) > 1000
        assert float(pixels.std()) > 100
        assert "pydicom MR_small.dcm" in str(ds.DerivationDescription)
        if str(study_profiles.get(study_id, "")).startswith("ms_brain"):
            assert str(ds.BodyPartExamined) == "BRAIN"
            assert "profile=ms_brain" in str(ds.DerivationDescription)
        pixel_hashes.add(hashlib.sha256(ds.PixelData).hexdigest())
    assert len(pixel_hashes) >= 2


def test_dataset_registry_allows_group_based_access(tmp_path, monkeypatch):
    isolate_auth_store(monkeypatch, tmp_path)
    isolate_query_store(monkeypatch, tmp_path)
    monkeypatch.setenv("COHORTOME_AUTH_MODE", "local")
    monkeypatch.setenv(
        "COHORTOME_LOCAL_USERS_JSON",
        json.dumps(
            [
                {"username": "admin", "password": "secret", "role": "admin", "display_name": "Admin"},
                {"username": "mrueda", "password": "demo", "role": "user", "display_name": "mrueda", "groups": ["cnag"]},
                {"username": "outsider", "password": "demo", "role": "user", "display_name": "outsider", "groups": ["other"]},
            ]
        ),
    )
    monkeypatch.setattr(datasets_module, "DATASET_REGISTRY_PATH", tmp_path / "state" / "datasets" / "registry.json")
    monkeypatch.setattr(datasets_module, "STATE_ROOT_DIR", tmp_path / "state")
    monkeypatch.setattr(user_state_module, "STATE_ROOT_DIR", tmp_path / "state")

    shared_root = tmp_path / "shared"
    shared_clinical = shared_root / "clinical"
    shared_clinical.mkdir(parents=True)
    write_json(shared_clinical, "records.json", [{"id": "CNAG1:week_0", "patient_id": "CNAG1"}])

    registry = [
        {
            "dataset_id": "cnag-dataset",
            "name": "CNAG dataset",
            "root_path": str(shared_root),
            "enabled": True,
            "visibility": "restricted",
            "allowed_users": [],
            "allowed_groups": ["cnag"],
            "created_by": "admin",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        },
    ]
    datasets_module.DATASET_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    datasets_module.DATASET_REGISTRY_PATH.write_text(json.dumps(registry), encoding="utf-8")
    query_store_module.prepare_dataset_query_store("cnag-dataset")

    client = TestClient(app)

    login = client.post("/auth/login", json={"username": "mrueda", "password": "demo"})
    assert login.status_code == 200
    listed = client.get("/datasets")
    assert listed.status_code == 200
    assert "cnag-dataset" in [item["dataset_id"] for item in listed.json()["datasets"]]
    selected = client.post("/datasets/select", json={"dataset_id": "cnag-dataset"})
    assert selected.status_code == 200
    patients = client.get("/patients")
    assert patients.status_code == 200
    assert patients.json()[0]["patient_id"] == "CNAG1"

    client.post("/auth/logout")
    login_outsider = client.post("/auth/login", json={"username": "outsider", "password": "demo"})
    assert login_outsider.status_code == 200
    outsider_listed = client.get("/datasets")
    assert outsider_listed.status_code == 200
    assert "cnag-dataset" not in [item["dataset_id"] for item in outsider_listed.json()["datasets"]]


def test_dataset_prepare_store_route_builds_ready_store(tmp_path, monkeypatch):
    isolate_auth_store(monkeypatch, tmp_path)
    isolate_query_store(monkeypatch, tmp_path)
    monkeypatch.setenv("COHORTOME_AUTH_MODE", "local")
    monkeypatch.setenv(
        "COHORTOME_LOCAL_USERS_JSON",
        json.dumps([{"username": "admin", "password": "secret", "role": "admin", "display_name": "Admin"}]),
    )
    monkeypatch.setattr(datasets_module, "DATASET_REGISTRY_PATH", tmp_path / "state" / "datasets" / "registry.json")
    monkeypatch.setattr(datasets_module, "STATE_ROOT_DIR", tmp_path / "state")
    monkeypatch.setattr(user_state_module, "STATE_ROOT_DIR", tmp_path / "state")

    dataset_root = tmp_path / "default"
    clinical_dir = dataset_root / "clinical"
    clinical_dir.mkdir(parents=True)
    write_json(clinical_dir, "records.json", [{"id": "D1:baseline", "patient_id": "D1"}])

    datasets_module.DATASET_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    datasets_module.DATASET_REGISTRY_PATH.write_text(
        json.dumps(
            [
                {
                    "dataset_id": "default",
                    "name": "Synthetic longitudinal demo",
                    "root_path": str(dataset_root),
                    "enabled": True,
                    "visibility": "all_authenticated",
                    "created_by": "admin",
                    "created_at": "2026-01-01T00:00:00+00:00",
                    "updated_at": "2026-01-01T00:00:00+00:00",
                }
            ]
        ),
        encoding="utf-8",
    )

    client = TestClient(app)
    assert client.post("/auth/login", json={"username": "admin", "password": "secret"}).status_code == 200
    selected = client.post("/datasets/select", json={"dataset_id": "default"})
    assert selected.status_code == 409

    listed = client.get("/datasets")
    assert listed.status_code == 200
    assert listed.json()["datasets"][0]["query_store_status"]["status"] == "not_built"
    assert listed.json()["current_dataset_ids"] == []

    prepared = client.post("/datasets/default/prepare-store")
    assert prepared.status_code == 200
    assert prepared.json()["query_store_status"]["status"] == "ready"
    assert prepared.json()["query_store_status"]["ready"] is True

    selected = client.post("/datasets/select", json={"dataset_id": "default"})
    assert selected.status_code == 200

    patients = client.get("/patients", params={"dataset_id": "default"})
    assert patients.status_code == 200
    assert patients.json()


def test_dataset_routes_block_until_dataset_store_is_prepared(tmp_path, monkeypatch):
    isolate_auth_store(monkeypatch, tmp_path)
    isolate_query_store(monkeypatch, tmp_path)
    monkeypatch.setenv("COHORTOME_AUTH_MODE", "local")
    monkeypatch.setenv(
        "COHORTOME_LOCAL_USERS_JSON",
        json.dumps([{"username": "maria", "password": "demo", "role": "user", "display_name": "Maria"}]),
    )
    monkeypatch.setattr(datasets_module, "DATASET_REGISTRY_PATH", tmp_path / "state" / "datasets" / "registry.json")
    monkeypatch.setattr(datasets_module, "STATE_ROOT_DIR", tmp_path / "state")
    monkeypatch.setattr(user_state_module, "STATE_ROOT_DIR", tmp_path / "state")

    dataset_root = tmp_path / "maria-dataset"
    clinical_dir = dataset_root / "clinical"
    clinical_dir.mkdir(parents=True)
    write_json(clinical_dir, "records.json", [{"id": "M1:baseline", "patient_id": "M1"}])

    datasets_module.DATASET_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    datasets_module.DATASET_REGISTRY_PATH.write_text(
        json.dumps(
            [
                {
                    "dataset_id": "maria-dataset",
                    "name": "Maria dataset",
                    "root_path": str(dataset_root),
                    "enabled": True,
                    "visibility": "restricted",
                    "allowed_users": ["maria"],
                    "created_by": "admin",
                    "created_at": "2026-01-01T00:00:00+00:00",
                    "updated_at": "2026-01-01T00:00:00+00:00",
                }
            ]
        ),
        encoding="utf-8",
    )

    client = TestClient(app)
    assert client.post("/auth/login", json={"username": "maria", "password": "demo"}).status_code == 200
    selected = client.post("/datasets/select", json={"dataset_id": "maria-dataset"})
    assert selected.status_code == 409
    assert client.get("/datasets").json()["current_dataset_ids"] == []

    blocked = client.get("/patients", params={"dataset_id": "maria-dataset"})
    assert blocked.status_code == 409
    assert "not ready" in blocked.json()["detail"].lower()

    query_store_module.prepare_dataset_query_store("maria-dataset")

    selected = client.post("/datasets/select", json={"dataset_id": "maria-dataset"})
    assert selected.status_code == 200

    patients = client.get("/patients")
    assert patients.status_code == 200
    assert patients.json()[0]["patient_id"] == "M1"


def test_failed_dataset_switch_preserves_active_workspace_and_stale_selection_is_cleared(tmp_path, monkeypatch):
    isolate_auth_store(monkeypatch, tmp_path)
    isolate_query_store(monkeypatch, tmp_path)
    monkeypatch.setenv("COHORTOME_AUTH_MODE", "local")
    monkeypatch.setenv(
        "COHORTOME_LOCAL_USERS_JSON",
        json.dumps([{"username": "maria", "password": "demo", "role": "user", "display_name": "Maria"}]),
    )
    monkeypatch.setattr(datasets_module, "DATASET_REGISTRY_PATH", tmp_path / "state" / "datasets" / "registry.json")
    monkeypatch.setattr(datasets_module, "STATE_ROOT_DIR", tmp_path / "state")
    monkeypatch.setattr(user_state_module, "STATE_ROOT_DIR", tmp_path / "state")

    ready_root = tmp_path / "ready-dataset"
    unready_root = tmp_path / "unready-dataset"
    for root, patient_id in ((ready_root, "R1"), (unready_root, "U1")):
        clinical_dir = root / "clinical"
        clinical_dir.mkdir(parents=True)
        write_json(clinical_dir, "records.json", [{"id": f"{patient_id}:baseline", "patient_id": patient_id}])

    records = [
        {
            "dataset_id": "default",
            "name": "Admin dataset",
            "root_path": str(ready_root),
            "enabled": True,
            "visibility": "admin_only",
        },
    ]
    for dataset_id, root in (("ready-dataset", ready_root), ("unready-dataset", unready_root)):
        records.append(
            {
                "dataset_id": dataset_id,
                "name": dataset_id,
                "root_path": str(root),
                "enabled": True,
                "visibility": "restricted",
                "allowed_users": ["maria"],
                "created_by": "admin",
                "created_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-01T00:00:00+00:00",
            }
        )
    datasets_module.DATASET_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    datasets_module.DATASET_REGISTRY_PATH.write_text(json.dumps(records), encoding="utf-8")
    query_store_module.prepare_dataset_query_store("ready-dataset")

    client = TestClient(app)
    assert client.post("/auth/login", json={"username": "maria", "password": "demo"}).status_code == 200
    assert client.post("/datasets/select", json={"dataset_id": "ready-dataset"}).status_code == 200

    failed_switch = client.post("/datasets/select", json={"dataset_id": "unready-dataset"})
    assert failed_switch.status_code == 409
    assert client.get("/datasets").json()["current_dataset_ids"] == ["ready-dataset"]
    patients = client.get("/patients")
    assert patients.status_code == 200
    assert [item["patient_id"] for item in patients.json()] == ["R1"]

    datasets_module.update_dataset("ready-dataset", enabled=False)
    assert client.get("/datasets").json()["current_dataset_ids"] == []
    assert datasets_module.current_dataset_ids("maria") == []

    datasets_module.update_dataset("unready-dataset", enabled=False)
    listed = client.get("/datasets")
    assert listed.status_code == 200
    assert listed.json()["datasets"] == []
    assert listed.json()["current_dataset_ids"] == []


def test_invalid_dataset_registry_is_not_silently_replaced(tmp_path, monkeypatch):
    registry_path = tmp_path / "state" / "datasets" / "registry.json"
    monkeypatch.setattr(datasets_module, "DATASET_REGISTRY_PATH", registry_path)
    registry_path.parent.mkdir(parents=True)
    registry_path.write_text('{"truncated":', encoding="utf-8")
    original = registry_path.read_bytes()

    with pytest.raises(RuntimeError, match="registry is invalid"):
        datasets_module.list_registered_datasets()

    assert registry_path.read_bytes() == original


def test_prepared_dataset_store_supports_concurrent_readers(tmp_path, monkeypatch):
    if not duckdb_available():
        return

    isolate_query_store(monkeypatch, tmp_path)
    monkeypatch.setattr(datasets_module, "DATASET_REGISTRY_PATH", tmp_path / "state" / "datasets" / "registry.json")
    monkeypatch.setattr(datasets_module, "STATE_ROOT_DIR", tmp_path / "state")

    dataset_root = tmp_path / "concurrent-dataset"
    clinical_dir = dataset_root / "clinical"
    clinical_dir.mkdir(parents=True)
    write_json(clinical_dir, "records.json", [{"id": "C1:baseline", "patient_id": "C1"}])

    datasets_module.DATASET_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    datasets_module.DATASET_REGISTRY_PATH.write_text(
        json.dumps(
            [
                {
                    "dataset_id": "concurrent-dataset",
                    "name": "Concurrent dataset",
                    "root_path": str(dataset_root),
                    "enabled": True,
                    "visibility": "all_authenticated",
                    "created_by": "admin",
                    "created_at": "2026-01-01T00:00:00+00:00",
                    "updated_at": "2026-01-01T00:00:00+00:00",
                }
            ]
        ),
        encoding="utf-8",
    )
    query_store_module.prepare_dataset_query_store("concurrent-dataset")

    reader_count = 8
    start = Barrier(reader_count)

    def read_patients():
        start.wait()
        return query_store_module.patient_inventory(str(dataset_root))

    with ThreadPoolExecutor(max_workers=reader_count) as executor:
        results = list(executor.map(lambda _index: read_patients(), range(reader_count)))

    assert results == [["C1"]] * reader_count


def test_dataset_store_supports_concurrent_rebuild_requests(tmp_path, monkeypatch):
    if not duckdb_available():
        return

    isolate_query_store(monkeypatch, tmp_path)
    monkeypatch.setattr(datasets_module, "DATASET_REGISTRY_PATH", tmp_path / "state" / "datasets" / "registry.json")
    monkeypatch.setattr(datasets_module, "STATE_ROOT_DIR", tmp_path / "state")

    dataset_root = tmp_path / "concurrent-rebuild-dataset"
    clinical_dir = dataset_root / "clinical"
    clinical_dir.mkdir(parents=True)
    write_json(clinical_dir, "records.json", [{"id": "C1:baseline", "patient_id": "C1"}])
    datasets_module.DATASET_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    datasets_module.DATASET_REGISTRY_PATH.write_text(
        json.dumps(
            [
                {
                    "dataset_id": "default",
                    "name": "Synthetic longitudinal demo",
                    "root_path": str(dataset_root),
                    "enabled": True,
                    "visibility": "all_authenticated",
                    "created_by": "admin",
                    "created_at": "2026-01-01T00:00:00+00:00",
                    "updated_at": "2026-01-01T00:00:00+00:00",
                },
                {
                    "dataset_id": "concurrent-rebuild-dataset",
                    "name": "Concurrent rebuild dataset",
                    "root_path": str(dataset_root),
                    "enabled": True,
                    "visibility": "all_authenticated",
                    "created_by": "admin",
                    "created_at": "2026-01-01T00:00:00+00:00",
                    "updated_at": "2026-01-01T00:00:00+00:00",
                }
            ]
        ),
        encoding="utf-8",
    )

    builder_count = 2
    start = Barrier(builder_count)

    def rebuild_store():
        start.wait()
        return query_store_module.prepare_dataset_query_store("concurrent-rebuild-dataset")

    with ThreadPoolExecutor(max_workers=builder_count) as executor:
        results = list(executor.map(lambda _index: rebuild_store(), range(builder_count)))

    assert all(result["ready"] is True for result in results)
    assert query_store_module.patient_inventory(str(dataset_root)) == ["C1"]


def test_multi_dataset_scope_refreshes_when_source_file_inventory_changes(tmp_path, monkeypatch):
    monkeypatch.setattr(datasets_module, "DATASET_REGISTRY_PATH", tmp_path / "state" / "datasets" / "registry.json")
    monkeypatch.setattr(datasets_module, "STATE_ROOT_DIR", tmp_path / "state")

    dataset_a = tmp_path / "dataset-a"
    dataset_b = tmp_path / "dataset-b"
    (dataset_a / "clinical").mkdir(parents=True)
    (dataset_a / "assays" / "transcriptomics").mkdir(parents=True)
    (dataset_b / "clinical").mkdir(parents=True)
    (dataset_b / "assays" / "transcriptomics").mkdir(parents=True)
    write_json(dataset_a / "clinical", "a_records.json", [{"id": "A1:baseline", "patient_id": "A1"}])
    write_json(dataset_b / "clinical", "b_records.json", [{"id": "B1:baseline", "patient_id": "B1"}])

    registry = [
        {
            "dataset_id": "dataset-a",
            "name": "Dataset A",
            "root_path": str(dataset_a),
            "enabled": True,
            "visibility": "all_authenticated",
            "data_classification": "public",
            "created_by": "admin",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        },
        {
            "dataset_id": "dataset-b",
            "name": "Dataset B",
            "root_path": str(dataset_b),
            "enabled": True,
            "visibility": "all_authenticated",
            "data_classification": "public",
            "created_by": "admin",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        },
    ]
    datasets_module.DATASET_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    datasets_module.DATASET_REGISTRY_PATH.write_text(json.dumps(registry), encoding="utf-8")

    scope_root = Path(datasets_module.materialize_dataset_scope(["dataset-a", "dataset-b"]))
    assert (scope_root / "clinical" / "dataset-a__a_records.json").exists()
    assert (scope_root / "clinical" / "dataset-b__b_records.json").exists()

    write_json(dataset_b / "clinical", "b_new_records.json", [{"id": "B2:baseline", "patient_id": "B2"}])

    refreshed_root = Path(datasets_module.materialize_dataset_scope(["dataset-a", "dataset-b"]))
    assert refreshed_root == scope_root
    assert (refreshed_root / "clinical" / "dataset-b__b_new_records.json").exists()
    manifest = json.loads((refreshed_root / "manifest.json").read_text(encoding="utf-8"))
    assert "dataset-b__b_new_records.json" in [item["target"] for item in manifest["clinical_files"]]


def test_multi_dataset_scope_build_failure_preserves_previous_scope(tmp_path, monkeypatch):
    monkeypatch.setattr(datasets_module, "DATASET_REGISTRY_PATH", tmp_path / "state" / "datasets" / "registry.json")
    monkeypatch.setattr(datasets_module, "STATE_ROOT_DIR", tmp_path / "state")

    registry = []
    for dataset_id, patient_id in (("dataset-a", "A1"), ("dataset-b", "B1")):
        root = tmp_path / dataset_id
        (root / "clinical").mkdir(parents=True)
        (root / "assays").mkdir()
        write_json(root / "clinical", "records.json", [{"id": f"{patient_id}:baseline", "patient_id": patient_id}])
        registry.append(
            {
                "dataset_id": dataset_id,
                "name": dataset_id,
                "root_path": str(root),
                "enabled": True,
                "visibility": "all_authenticated",
                "data_classification": "public",
                "created_by": "admin",
                "created_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-01T00:00:00+00:00",
            }
        )
    datasets_module.DATASET_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    datasets_module.DATASET_REGISTRY_PATH.write_text(json.dumps(registry), encoding="utf-8")

    scope_root = Path(datasets_module.materialize_dataset_scope(["dataset-a", "dataset-b"]))
    original_manifest = (scope_root / "manifest.json").read_text(encoding="utf-8")
    new_source = write_json(
        tmp_path / "dataset-b" / "clinical",
        "new_records.json",
        [{"id": "B2:baseline", "patient_id": "B2"}],
    )
    original_symlink_to = Path.symlink_to

    def fail_new_link(path, target, *args, **kwargs):
        if Path(target) == new_source.resolve():
            raise OSError("simulated scope publication failure")
        return original_symlink_to(path, target, *args, **kwargs)

    monkeypatch.setattr(Path, "symlink_to", fail_new_link)
    with pytest.raises(OSError, match="simulated scope publication failure"):
        datasets_module.materialize_dataset_scope(["dataset-a", "dataset-b"])

    assert (scope_root / "manifest.json").read_text(encoding="utf-8") == original_manifest
    assert (scope_root / "clinical" / "dataset-a__records.json").exists()
    assert (scope_root / "clinical" / "dataset-b__records.json").exists()
    assert not (scope_root / "clinical" / "dataset-b__new_records.json").exists()


def test_multi_dataset_scope_supports_concurrent_materialization(tmp_path, monkeypatch):
    monkeypatch.setattr(datasets_module, "DATASET_REGISTRY_PATH", tmp_path / "state" / "datasets" / "registry.json")
    monkeypatch.setattr(datasets_module, "STATE_ROOT_DIR", tmp_path / "state")

    registry = []
    for dataset_id, patient_id in (("dataset-a", "A1"), ("dataset-b", "B1")):
        root = tmp_path / dataset_id
        (root / "clinical").mkdir(parents=True)
        (root / "assays").mkdir()
        write_json(root / "clinical", "records.json", [{"id": f"{patient_id}:baseline", "patient_id": patient_id}])
        registry.append(
            {
                "dataset_id": dataset_id,
                "name": dataset_id,
                "root_path": str(root),
                "enabled": True,
                "visibility": "all_authenticated",
                "data_classification": "public",
                "created_by": "admin",
                "created_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-01T00:00:00+00:00",
            }
        )
    datasets_module.DATASET_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    datasets_module.DATASET_REGISTRY_PATH.write_text(json.dumps(registry), encoding="utf-8")

    builder_count = 4
    start = Barrier(builder_count)

    def materialize_scope():
        start.wait()
        return datasets_module.materialize_dataset_scope(["dataset-a", "dataset-b"])

    with ThreadPoolExecutor(max_workers=builder_count) as executor:
        roots = list(executor.map(lambda _index: materialize_scope(), range(builder_count)))

    assert len(set(roots)) == 1
    scope_root = Path(roots[0])
    manifest = json.loads((scope_root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["dataset_ids"] == ["dataset-a", "dataset-b"]
    assert sorted(path.name for path in (scope_root / "clinical").glob("*.json")) == [
        "dataset-a__records.json",
        "dataset-b__records.json",
    ]


def test_federated_workspace_uses_prepared_dataset_stores_without_building_combined_db(tmp_path, monkeypatch):
    if not duckdb_available():
        return

    isolate_query_store(monkeypatch, tmp_path)
    monkeypatch.setattr(datasets_module, "DATASET_REGISTRY_PATH", tmp_path / "state" / "datasets" / "registry.json")
    monkeypatch.setattr(datasets_module, "STATE_ROOT_DIR", tmp_path / "state")

    dataset_a = tmp_path / "dataset-a"
    dataset_b = tmp_path / "dataset-b"
    for root, patient_id, raw_a, raw_b in (
        (dataset_a, "A1", 10, 20),
        (dataset_b, "B1", 30, 40),
    ):
        clinical_dir = root / "clinical"
        transcriptomics_dir = root / "assays" / "transcriptomics"
        clinical_dir.mkdir(parents=True)
        transcriptomics_dir.mkdir(parents=True)
        write_json(clinical_dir, "records.json", [{"id": f"{patient_id}:baseline", "patient_id": patient_id}])
        (transcriptomics_dir / "counts.csv").write_text(
            "\n".join(
                [
                    f"gene_id;{patient_id}",
                    f"GENE1;{raw_a}",
                    f"GENE2;{raw_b}",
                ]
            ),
            encoding="utf-8",
        )

    datasets_module.DATASET_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    datasets_module.DATASET_REGISTRY_PATH.write_text(
        json.dumps(
            [
                {
                    "dataset_id": "dataset-a",
                    "name": "Dataset A",
                    "root_path": str(dataset_a),
                    "enabled": True,
                    "visibility": "all_authenticated",
                    "data_classification": "public",
                    "created_by": "admin",
                    "created_at": "2026-01-01T00:00:00+00:00",
                    "updated_at": "2026-01-01T00:00:00+00:00",
                },
                {
                    "dataset_id": "dataset-b",
                    "name": "Dataset B",
                    "root_path": str(dataset_b),
                    "enabled": True,
                    "visibility": "all_authenticated",
                    "data_classification": "public",
                    "created_by": "admin",
                    "created_at": "2026-01-01T00:00:00+00:00",
                    "updated_at": "2026-01-01T00:00:00+00:00",
                },
            ]
        ),
        encoding="utf-8",
    )

    query_store_module.prepare_dataset_query_store("dataset-a")
    query_store_module.prepare_dataset_query_store("dataset-b")

    scope_root = Path(datasets_module.materialize_dataset_scope(["dataset-a", "dataset-b"]))
    combined_db_path, combined_meta_path = query_store_module._store_paths(str(scope_root))
    assert not combined_db_path.exists()
    assert not combined_meta_path.exists()

    assert store_patient_inventory(str(scope_root)) == ["A1", "B1"]
    inventory = store_assay_dataset_inventory(str(scope_root))

    assert [item["dataset_name"] for item in inventory] == ["dataset-a__counts", "dataset-b__counts"]
    assert [item["patient_ids"] for item in inventory] == [["A1"], ["B1"]]
    assert not combined_db_path.exists()
    assert not combined_meta_path.exists()


def test_private_dataset_preserves_detailed_access_for_local_providers_only(tmp_path, monkeypatch):
    monkeypatch.setattr(datasets_module, "DATASET_REGISTRY_PATH", tmp_path / "state" / "datasets" / "registry.json")
    dataset_root = tmp_path / "restricted-dataset"
    (dataset_root / "clinical").mkdir(parents=True)
    write_json(dataset_root / "clinical", "records.json", [{"id": "P1:v1", "patient_id": "P1"}])
    write_json(dataset_root, "manifest.json", {"schema_version": 1, "clinical": {"representation": "snapshot"}})

    item = datasets_module.register_dataset(
        name="Restricted dataset",
        root_path=str(dataset_root),
        visibility="restricted",
        data_classification="private",
        ai_provider_access="detailed_allowed",
        created_by="admin",
    )

    assert item["visibility"] == "restricted"
    assert item["data_classification"] == "private"
    assert item["ai_provider_access"] == "detailed_allowed"

    stored = datasets_module.get_dataset(item["dataset_id"])
    assert stored is not None
    assert stored["ai_provider_access"] == "detailed_allowed"
    assert datasets_module.constrain_ai_provider_access(
        [item["dataset_id"]],
        stored["ai_provider_access"],
        "local",
    ) == "detailed_allowed"
    assert datasets_module.constrain_ai_provider_access(
        [item["dataset_id"]],
        stored["ai_provider_access"],
        "external",
    ) == "blocked"


def test_public_dataset_allows_configured_external_provider_access(tmp_path, monkeypatch):
    monkeypatch.setattr(datasets_module, "DATASET_REGISTRY_PATH", tmp_path / "state" / "datasets" / "registry.json")
    dataset_root = tmp_path / "public-dataset"
    (dataset_root / "clinical").mkdir(parents=True)
    write_json(dataset_root / "clinical", "records.json", [{"id": "P1:v1", "patient_id": "P1"}])
    write_json(dataset_root, "manifest.json", {"schema_version": 1, "clinical": {"representation": "snapshot"}})

    item = datasets_module.register_dataset(
        name="Public dataset",
        root_path=str(dataset_root),
        data_classification="public",
        ai_provider_access="detailed_allowed",
    )

    assert datasets_module.constrain_ai_provider_access(
        [item["dataset_id"]],
        item["ai_provider_access"],
        "external",
    ) == "detailed_allowed"


def test_dataset_registration_requires_explicit_clinical_representation(tmp_path, monkeypatch):
    monkeypatch.setattr(datasets_module, "DATASET_REGISTRY_PATH", tmp_path / "state" / "datasets" / "registry.json")
    dataset_root = tmp_path / "ambiguous-dataset"
    (dataset_root / "clinical").mkdir(parents=True)
    write_json(dataset_root / "clinical", "records.json", [{"id": "P1", "patient_id": "P1"}])

    with pytest.raises(ValueError, match="clinical.representation"):
        datasets_module.register_dataset(name="Ambiguous", root_path=str(dataset_root))


def test_register_dataset_script_enables_dataset_only_after_store_is_ready(monkeypatch, capsys):
    calls = []
    args = SimpleNamespace(
        name="Private dataset",
        root="/private/release",
        description="",
        visibility="restricted",
        data_classification="private",
        allowed_user=["maria"],
        allowed_group=[],
        query_detail="detailed",
        ai_provider_access="blocked",
        created_by="admin",
        prepare_store=True,
    )
    monkeypatch.setattr(register_dataset_script, "_parser", lambda: SimpleNamespace(parse_args=lambda: args))

    def fake_register_dataset(**kwargs):
        calls.append(("register", kwargs["enabled"]))
        return {
            "dataset_id": "private-dataset",
            "visibility": "restricted",
            "data_classification": "private",
            "query_granularity_ceiling": "detailed",
            "ai_provider_access": "blocked",
        }

    monkeypatch.setattr(register_dataset_script, "register_dataset", fake_register_dataset)
    monkeypatch.setattr(
        register_dataset_script,
        "prepare_dataset_query_store",
        lambda dataset_id: calls.append(("prepare", dataset_id)) or {"status": "ready", "ready": True},
    )
    monkeypatch.setattr(
        register_dataset_script,
        "update_dataset",
        lambda dataset_id, enabled: calls.append(("enable", dataset_id, enabled))
        or {
            "dataset_id": dataset_id,
            "visibility": "restricted",
            "data_classification": "private",
            "query_granularity_ceiling": "detailed",
            "ai_provider_access": "blocked",
        },
    )

    assert register_dataset_script.main() == 0
    assert calls == [
        ("register", False),
        ("prepare", "private-dataset"),
        ("enable", "private-dataset", True),
    ]
    assert json.loads(capsys.readouterr().out)["query_store"] == {"status": "ready", "ready": True}


def test_register_dataset_script_rolls_back_failed_store_preparation(monkeypatch):
    calls = []
    args = SimpleNamespace(
        name="Private dataset",
        root="/private/release",
        description="",
        visibility="restricted",
        data_classification="private",
        allowed_user=["maria"],
        allowed_group=[],
        query_detail="detailed",
        ai_provider_access="blocked",
        created_by="admin",
        prepare_store=True,
    )
    monkeypatch.setattr(register_dataset_script, "_parser", lambda: SimpleNamespace(parse_args=lambda: args))
    monkeypatch.setattr(
        register_dataset_script,
        "register_dataset",
        lambda **kwargs: calls.append(("register", kwargs["enabled"]))
        or {
            "dataset_id": "private-dataset",
            "visibility": "restricted",
            "data_classification": "private",
            "query_granularity_ceiling": "detailed",
            "ai_provider_access": "blocked",
        },
    )

    def fail_prepare(dataset_id):
        calls.append(("prepare", dataset_id))
        raise RuntimeError("simulated store failure")

    monkeypatch.setattr(register_dataset_script, "prepare_dataset_query_store", fail_prepare)
    monkeypatch.setattr(
        register_dataset_script,
        "remove_dataset_query_store",
        lambda dataset_id: calls.append(("remove_store", dataset_id)),
    )
    monkeypatch.setattr(
        register_dataset_script,
        "unregister_dataset",
        lambda dataset_id: calls.append(("unregister", dataset_id)),
    )
    monkeypatch.setattr(
        register_dataset_script,
        "update_dataset",
        lambda *args, **kwargs: pytest.fail("A failed store must not enable the dataset."),
    )

    with pytest.raises(RuntimeError, match="simulated store failure"):
        register_dataset_script.main()
    assert calls == [
        ("register", False),
        ("prepare", "private-dataset"),
        ("remove_store", "private-dataset"),
        ("unregister", "private-dataset"),
    ]


def test_patient_workspace_precomputes_fragment_pointers(tmp_path):
    write_json(
        tmp_path,
        "individuals.json",
        [
            {
                "id": "900:week_0_arm_1",
                "sex": {"label": "Female"},
                "diseases": [
                    {
                        "_visit": {"id": "week_0_arm_1"},
                        "diseaseCode": {"label": "Ulcerative Colitis"},
                    }
                ],
                "measures": [
                    {
                        "_visit": {"id": "week_0_arm_1"},
                        "assayCode": {"label": "C-Reactive Protein Measurement"},
                    }
                ],
                "treatments": [
                    {
                        "_visit": {"id": "week_0_arm_1"},
                        "treatmentCode": {"label": "Infliximab"},
                    }
                ],
            }
        ],
    )

    patient_workspace = build_patient_workspace(str(tmp_path), "900")
    assert patient_workspace is not None
    assert patient_workspace.summary.patient_id == "900"
    assert patient_workspace.evidence.diseases.count == 1
    assert patient_workspace.visits[0].key_fragments[0].path == "diseases[0]"
    assert patient_workspace.visits[0].key_fragments[0].label == "Ulcerative Colitis"
    assert patient_workspace.visits[0].key_fragments[1].path == "measures[0]"
    assert patient_workspace.key_fragments[2].label == "Infliximab"

    workspace_payload = get_patient_workspace("900", data_dir=str(tmp_path))
    assert workspace_payload["patient_id"] == "900"
    assert workspace_payload["visits"][0]["key_fragments"][0]["category"] == "disease"


def test_routes_index_and_dataset_helpers(monkeypatch, tmp_path):
    class DummyTemplates:
        def TemplateResponse(self, request, name, context):
            return {"template": name, "context": context}

    dataset_root = tmp_path / "dataset-a"
    dataset_root.mkdir()
    source_file = dataset_root / "clinical" / "records.json"
    source_file.parent.mkdir()
    source_file.write_text("[]", encoding="utf-8")

    monkeypatch.setattr(routes_module, "templates", DummyTemplates())
    monkeypatch.setattr(routes_module, "branding_settings", lambda: {"product_name": "PN"})
    monkeypatch.setattr(routes_module, "authorized_datasets_for_user", lambda user: [{"dataset_id": "dataset-a", "name": "Dataset A", "root_path": str(dataset_root)}])
    monkeypatch.setattr(routes_module, "resolve_dataset", lambda request, dataset_id="": {"dataset_id": "dataset-a"})
    monkeypatch.setattr(routes_module, "resolve_dataset_dir", lambda request, key: f"/resolved/{key or 'default'}")
    monkeypatch.setattr(routes_module, "current_dataset_id", lambda user_id="": "current-dataset")
    monkeypatch.setattr(routes_module, "request_user_id", lambda request: "u1")

    monkeypatch.setattr(routes_module, "auth_enabled", lambda: False)
    payload = routes_module.index(make_request())
    assert payload["template"] == "index.html"
    assert payload["context"]["auth_enabled"] is False
    assert payload["context"]["current_dataset_id"] == "dataset-a"

    monkeypatch.setattr(routes_module, "auth_enabled", lambda: True)
    monkeypatch.setattr(routes_module, "session_user", lambda request: {"username": "analyst"})
    payload = routes_module.index(make_request({"username": "analyst"}))
    assert payload["context"]["auth_enabled"] is True
    assert payload["context"]["datasets"][0]["dataset_id"] == "dataset-a"

    provenance = routes_module._dataset_provenance_from_sources(
        make_request({"username": "analyst"}),
        [str(source_file)],
    )
    assert provenance["dataset_ids"] == ["dataset-a"]
    assert provenance["dataset_name"] == "Dataset A"
    sanitized = routes_module._sanitize_response_paths(
        {
            "source_file": str(source_file),
            "source_files": [str(source_file)],
            "unrelated_absolute_path": str(tmp_path / "outside" / "secret.txt"),
        },
        make_request({"username": "analyst"}),
    )
    assert sanitized["source_file"] == "dataset-a:clinical/records.json"
    assert sanitized["source_files"] == ["dataset-a:clinical/records.json"]
    assert sanitized["unrelated_absolute_path"] == "[filesystem path redacted]"
    assert routes_module._safe_source_path(make_request({"username": "analyst"}), "~unknown-user/value") == "~unknown-user/value"
    assert routes_module._resolve_route_dataset_dir(None, dataset_id="dataset-a") == "/resolved/dataset-a"
    assert routes_module._resolve_route_dataset_dir(make_request(), dataset_id="", data_dir="workspace") == "/resolved/workspace"


def test_dataset_admin_routes_map_value_errors_to_http_400(monkeypatch):
    monkeypatch.setattr(routes_module, "require_admin", lambda request: {"username": "admin"})
    monkeypatch.setattr(routes_module, "register_dataset", lambda **kwargs: (_ for _ in ()).throw(ValueError("bad dataset")))
    monkeypatch.setattr(routes_module, "update_dataset", lambda dataset_id, **kwargs: (_ for _ in ()).throw(ValueError("bad update")))

    create_payload = routes_module.DatasetRegistrationRequest(dataset_id="d1", name="Dataset", root_path="/tmp/data")
    update_payload = routes_module.DatasetUpdateRequest(name="Dataset")

    with pytest.raises(HTTPException) as create_exc:
        routes_module.create_dataset_route(create_payload, make_request({"username": "admin"}))
    with pytest.raises(HTTPException) as update_exc:
        routes_module.update_dataset_route("d1", update_payload, make_request({"username": "admin"}))

    assert create_exc.value.status_code == 400
    assert update_exc.value.status_code == 400
