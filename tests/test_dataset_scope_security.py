import json
from pathlib import Path

import pytest

import app.datasets as datasets_module


def _write_registry(records: list[dict]) -> None:
    path = datasets_module.DATASET_REGISTRY_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records), encoding="utf-8")


def _dataset_record(dataset_id: str, root: Path, classification: str) -> dict:
    return {
        "dataset_id": dataset_id,
        "name": dataset_id,
        "root_path": str(root),
        "enabled": True,
        "visibility": "all_authenticated",
        "data_classification": classification,
        "allowed_users": [],
        "allowed_groups": [],
    }


def _write_dataset(root: Path, patient_id: str) -> None:
    clinical = root / "clinical"
    assay = root / "assays" / "transcriptomics"
    clinical.mkdir(parents=True)
    assay.mkdir(parents=True)
    (clinical / "records.json").write_text(
        json.dumps([{"id": f"{patient_id}:baseline", "patient_id": patient_id}]),
        encoding="utf-8",
    )
    (assay / "counts.csv").write_text(
        f"gene_id;{patient_id}\nGENE1;1\n",
        encoding="utf-8",
    )


def test_private_multi_dataset_scope_fails_before_scope_storage_is_created(tmp_path, monkeypatch):
    state_root = tmp_path / "state"
    monkeypatch.setattr(datasets_module, "DATASET_REGISTRY_PATH", state_root / "datasets" / "registry.json")
    monkeypatch.setattr(datasets_module, "STATE_ROOT_DIR", state_root)
    monkeypatch.setattr(datasets_module, "private_artifact_runtime_is_safe", lambda: False)

    private_root = tmp_path / "private-release"
    public_root = tmp_path / "public-release"
    _write_dataset(private_root, "PRIVATE1")
    _write_dataset(public_root, "PUBLIC1")
    _write_registry(
        [
            _dataset_record("private-study", private_root, "private"),
            _dataset_record("public-study", public_root, "public"),
        ],
    )

    with pytest.raises(RuntimeError, match="Private multi-dataset workspaces require COHORTOME_RUNTIME_ROOT"):
        datasets_module.materialize_dataset_scope(["private-study", "public-study"])

    assert not (state_root / "datasets" / "scopes").exists()


def test_external_private_scope_links_only_clinical_files(tmp_path, monkeypatch):
    state_root = tmp_path / "protected-runtime" / "state"
    monkeypatch.setattr(datasets_module, "DATASET_REGISTRY_PATH", state_root / "datasets" / "registry.json")
    monkeypatch.setattr(datasets_module, "STATE_ROOT_DIR", state_root)
    monkeypatch.setattr(datasets_module, "private_artifact_runtime_is_safe", lambda: True)

    private_root = tmp_path / "private-release"
    public_root = tmp_path / "public-release"
    _write_dataset(private_root, "PRIVATE1")
    _write_dataset(public_root, "PUBLIC1")
    _write_registry(
        [
            _dataset_record("private-study", private_root, "private"),
            _dataset_record("public-study", public_root, "public"),
        ],
    )

    scope_root = Path(datasets_module.materialize_dataset_scope(["private-study", "public-study"]))
    manifest = json.loads((scope_root / "manifest.json").read_text(encoding="utf-8"))

    assert sorted(path.name for path in (scope_root / "clinical").iterdir()) == [
        "private-study__records.json",
        "public-study__records.json",
    ]
    assert all(path.is_symlink() for path in (scope_root / "clinical").iterdir())
    assert (scope_root / "assays").is_dir()
    assert list((scope_root / "assays").rglob("*")) == []
    assert manifest["assay_files"] == []


def test_compose_runtime_uses_named_volume_outside_the_checkout() -> None:
    compose = Path("docker/docker-compose.yml").read_text(encoding="utf-8")

    assert "../runtime:/var/lib/cohortome" not in compose
    assert compose.count("cohortome-runtime:/var/lib/cohortome") == 2
    assert "  cohortome-runtime:\n" in compose
