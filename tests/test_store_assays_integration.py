import json
from pathlib import Path
import pytest
import app.routes as routes_module
from app.main import get_patients
from app.query_store import duckdb_available
from bff_test_helpers import isolate_query_store
from bff_test_helpers import make_request
from bff_test_helpers import write_json
import app.analysis as analysis_module
import app.analysis_catalog as analysis_catalog_module
import app.analysis_external as analysis_external_module
import app.query_store as query_store_module
from bff_test_helpers import _write_synthetic_methylation_runner_fixture
from bff_test_helpers import _write_synthetic_quantitative_assay_runner_fixture
import app.datasets as datasets_module
from app.query_store import assay_dataset_inventory as store_assay_dataset_inventory
from app.query_store import patient_inventory as store_patient_inventory
import app.query as query_module
from app.query import answer_query
from app.query_store import cohort_over_time_summary as store_cohort_over_time_summary
from app.query_store import medication_counts as store_medication_counts
from app.query_store import assay_expression_summary as store_assay_expression_summary
from app.query_store import assay_feature_inventory as store_assay_feature_inventory
from app.query_store import patient_visit_count_cohort as store_patient_visit_count_cohort


def test_multimodal_feature_matrix_joins_clinical_assays_and_dicom(tmp_path, monkeypatch):
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
                "sex": "female",
                "diseases": [{"diseaseCode": {"label": "Multiple Sclerosis"}}],
                "treatments": [{"treatmentCode": {"label": "Ocrelizumab"}}],
                "info": {"event_date": "2024-01-01"},
            },
            {
                "id": "SYN012:week_0",
                "patient_id": "SYN012",
                "sex": "male",
                "diseases": [{"diseaseCode": {"label": "Multiple Sclerosis"}}],
                "info": {"event_date": "2024-01-08"},
            },
        ],
    )
    transcriptomics_dir = tmp_path / "assays" / "transcriptomics"
    transcriptomics_dir.mkdir(parents=True)
    (transcriptomics_dir / "synthetic_transcriptome_raw_counts.csv").write_text(
        "\n".join(
            [
                "gene_id;SYN011:week_0;SYN012:week_0",
                "ENSG00000111111;10;20",
                "ENSG00000222222;5;4",
            ]
        ),
        encoding="utf-8",
    )
    imaging_dir = tmp_path / "assays" / "imaging"
    imaging_dir.mkdir(parents=True)
    (imaging_dir / "synthetic_imaging_derived_features.csv").write_text(
        "\n".join(
            [
                "feature_id;SYN011:week_0;SYN012:week_0",
                "lesion_volume_ml;1.2;0.8",
                "brain_volume_ml;1450;1420",
            ]
        ),
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
                        "study_instance_uid": "1.2.826.0.1.3680043.10.54321.200.1",
                        "series": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    proteomics_dir = tmp_path / "assays" / "proteomics"
    proteomics_dir.mkdir(parents=True)
    (proteomics_dir / "synthetic_proteomics.csv").write_text(
        "\n".join(["protein_id;SYN011:plasma", "CXCL13;3.4"]),
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
                    },
                    {
                        "assay_id": "synthetic_proteomics",
                        "label": "synthetic proteomics",
                        "modality": "proteomics",
                        "data_type": "feature_matrix",
                        "file": "assays/proteomics/synthetic_proteomics.csv",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    payload = routes_module.get_assay_feature_matrix(
        make_request({"user": {"username": "maria"}}),
        data_dir=str(tmp_path),
        max_features_per_dataset=2,
        max_rows=10,
    )

    column_keys = {item["key"] for item in payload["columns"]}
    assert payload["metadata"]["join_level"] == "sample"
    assert payload["metadata"]["row_count"] == 2
    assert "clinical.sex" in column_keys
    assert "synthetic_transcriptome_raw_counts.ENSG00000111111" in column_keys
    assert "synthetic_imaging_derived_features.lesion_volume_ml" in column_keys
    assert "dicom.study_count" in column_keys
    row = next(item for item in payload["rows"] if item["sample_id"] == "SYN011:week_0")
    assert row["values"]["clinical.sex"] == "female"
    assert row["values"]["clinical.diseases"] == "Multiple Sclerosis"
    assert row["values"]["synthetic_transcriptome_raw_counts.ENSG00000111111"] == 10
    assert row["values"]["synthetic_imaging_derived_features.lesion_volume_ml"] == 1.2
    assert row["values"]["dicom.study_count"] == 1
    assert any(item["dataset_name"] == "synthetic_imaging_derived_features" for item in payload["feature_groups"])
    assert any(item["kind"] == "patient_overlap_without_exact_sample_match" for item in payload["warnings"])


def test_dataset_api_record_redacts_query_store_error_details():
    payload = routes_module._dataset_record_for_user(
        {
            "dataset_id": "private-demo",
            "root_path": "/protected/release",
            "query_store_status": {
                "status": "failed",
                "ready": False,
                "last_error": "Unable to read /protected/release/private-source.csv",
            },
        },
        {"username": "researcher", "role": "user"},
    )

    assert payload["root_path"] == ""
    assert payload["query_store_status"]["last_error"] == (
        "Store preparation failed. Review server logs for technical details."
    )
    assert "/protected" not in json.dumps(payload)


def test_methylation_limma_rejects_incomplete_declared_covariates_before_r(tmp_path, monkeypatch):
    _write_synthetic_methylation_runner_fixture(tmp_path)
    metadata_path = tmp_path / "assays" / "methylation" / "sample_metadata.csv"
    metadata_path.write_text(
        metadata_path.read_text(encoding="utf-8").replace("METH003;METH003;53;101", "METH003;METH003;;101"),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        analysis_external_module.shutil,
        "which",
        lambda name: "/usr/bin/Rscript" if name == "Rscript" else None,
    )

    with pytest.raises(RuntimeError, match="complete declared covariates"):
        analysis_external_module.run_rscript_analysis(
            "methylation_limma_differential_methylation",
            prompt="Run limma differential methylation.",
            data_dir=str(tmp_path),
            assay_id="synthetic_methylation_m_values",
            selected_patient_ids="METH001,METH002,METH003",
            compare_selected_patient_ids="METH004,METH005,METH006",
            job_dir=tmp_path / "methylation-invalid-job",
            timeout_seconds=60,
        )


def test_quantitative_assay_matrix_read_error_redacts_protected_path(tmp_path, monkeypatch):
    isolate_query_store(monkeypatch, tmp_path)
    matrix_path = _write_synthetic_quantitative_assay_runner_fixture(tmp_path)
    original_open = Path.open

    def fail_protected_matrix_open(path, *args, **kwargs):
        if path == matrix_path:
            raise OSError(f"cannot read protected source {path}")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_protected_matrix_open)

    with pytest.raises(RuntimeError, match="matrix header cannot be read") as caught:
        analysis_external_module._prepare_quantitative_assay_comparison_bundle(
            str(tmp_path),
            prompt="Compare the cohorts.",
            assay_id="synthetic_quantitative_serology",
            selected_patient_ids="SYN001,SYN002,SYN003",
            compare_selected_patient_ids="SYN004,SYN005,SYN006",
            output_dir=tmp_path / "failed-quantitative-assay-job",
        )

    assert str(matrix_path) not in str(caught.value)
    assert caught.value.__cause__ is None


def test_quantitative_assay_catalog_rejects_multi_dataset_scope_before_queue(monkeypatch):
    monkeypatch.setattr(
        analysis_module,
        "get_analysis_catalog_item",
        lambda _item_id: {
            "id": "compact-assay",
            "name": "Compact assay",
            "default_prompt": "Run compact assay.",
            "runner_type": "rscript",
            "runner_ref": "quantitative_assay_wilcoxon_comparison",
            "execution_backend": "job",
            "requires_single_dataset_workspace": True,
        },
    )
    monkeypatch.setattr(
        analysis_module,
        "store_workspace_dataset_ids",
        lambda _data_dir: ["dataset-a", "dataset-b"],
    )
    submitted = {"value": False}
    monkeypatch.setattr(
        analysis_module,
        "submit_analysis_job",
        lambda **_kwargs: submitted.__setitem__("value", True),
    )

    with pytest.raises(RuntimeError, match="exactly one dataset"):
        analysis_module._analysis_catalog_dispatch(
            "Run compact assay.",
            catalog_item_id="compact-assay",
            data_dir="scope--dataset-a--dataset-b",
        )

    assert submitted["value"] is False


def test_quantitative_assay_comparison_rejects_repeated_patient_samples(tmp_path, monkeypatch):
    isolate_query_store(monkeypatch, tmp_path)
    _write_synthetic_quantitative_assay_runner_fixture(tmp_path)
    metadata_path = tmp_path / "assays" / "serology" / "sample_metadata.tsv"
    metadata_path.write_text(
        "sample_id\tpatient_id\n"
        "SYN001\tSYN001\nSYN002\tSYN001\nSYN003\tSYN003\n"
        "SYN004\tSYN004\nSYN005\tSYN005\nSYN006\tSYN006\n",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="one independent sample per patient"):
        analysis_external_module._prepare_quantitative_assay_comparison_bundle(
            str(tmp_path),
            prompt="Compare the cohorts.",
            assay_id="synthetic_quantitative_serology",
            selected_patient_ids="SYN001,SYN002,SYN003",
            compare_selected_patient_ids="SYN004,SYN005,SYN006",
            output_dir=tmp_path / "invalid-quantitative-assay-job",
        )


def test_duckdb_query_store_indexes_multiple_files(tmp_path):
    if not duckdb_available():
        return

    write_json(
        tmp_path,
        "individuals.json",
        [
            {
                "id": "Beacon_1",
                "diseases": [{"diseaseCode": {"label": "Crohn Disease"}}],
                "treatments": [{"treatmentCode": {"label": "Infliximab"}}],
            },
            {
                "id": "Beacon_2",
                "diseases": [{"diseaseCode": {"label": "Ulcerative Colitis"}}],
                "treatments": [{"treatmentCode": {"label": "Mesalamine"}}],
            },
        ],
    )
    write_json(
        tmp_path,
        "omop-cdm.json",
        [
            {
                "id": "101:week_0",
                "treatments": [{"_visit": {"id": "week_0"}, "treatmentCode": {"label": "Infliximab"}}],
            }
        ],
    )

    assert store_patient_inventory(str(tmp_path)) == ["101", "Beacon_1", "Beacon_2"]
    meds = store_medication_counts(str(tmp_path))
    assert meds[0]["medication"] == "Infliximab"
    assert meds[0]["patient_count"] == 2
    assert meds[0]["patients"] == ["101", "Beacon_1"]


def test_query_store_ingests_and_resolves_precomputed_subject_clarids(tmp_path, monkeypatch):
    if not duckdb_available():
        return
    isolate_query_store(monkeypatch, tmp_path)
    write_json(
        tmp_path,
        "individuals.json",
        [
            {
                "id": "SYN001",
                "sex": "female",
                "diseases": [{"diseaseCode": {"label": "Crohn Disease"}}],
            },
            {
                "id": "SYN002",
                "sex": "male",
                "diseases": [{"diseaseCode": {"label": "Healthy control"}}],
            },
        ],
    )
    identifiers_dir = tmp_path / "identifiers"
    identifiers_dir.mkdir()
    (identifiers_dir / "clarid_subjects.csv").write_text(
        "\n".join(
            [
                "unique_id,subject_id,study,type,condition,sex,age_group,clar_id,stub_id",
                "SYN001,1,SyntheticStudy,Case,K50.9,Female,Age40to49,SyntheticStudy-00001-Case-K50.9-Female-A40_49,SyntheticStudy00001CASE",
                "SYN002,2,SyntheticStudy,Control,Z00.00,Male,Age50to59,SyntheticStudy-00002-Control-Z00.00-Male-A50_59,SyntheticStudy00002CTRL",
            ]
        ),
        encoding="utf-8",
    )
    write_json(
        tmp_path,
        "manifest.json",
        {
            "schema_version": 1,
            "clinical": {"representation": "person"},
            "identifiers": {
                "clarid_subjects": {
                    "entity": "subject",
                    "file": "identifiers/clarid_subjects.csv",
                    "codebook_version": "0.04",
                    "tools_version": "0.04",
                }
            },
        },
    )

    clarids = query_store_module.patient_clarid_inventory(str(tmp_path))
    assert clarids["SYN001"] == {
        "subject_id": 1,
        "human_id": "SyntheticStudy-00001-Case-K50.9-Female-A40_49",
        "stub_id": "SyntheticStudy00001CASE",
        "study": "SyntheticStudy",
        "type": "Case",
        "condition": "K50.9",
        "sex": "Female",
        "age_group": "Age40to49",
        "codebook_version": "0.04",
        "tools_version": "0.04",
    }
    resolved = query_store_module.resolve_patient_identifier(
        str(tmp_path), "syntheticstudy-00001-case-k50.9-female-a40_49"
    )
    assert resolved == {"patient_id": "SYN001", "clarid": clarids["SYN001"]}

    patient_payload = get_patients(data_dir=str(tmp_path))
    assert patient_payload[0]["clarid"]["stub_id"] == "SyntheticStudy00001CASE"
    query_payload = answer_query(
        str(tmp_path),
        "Show patient SyntheticStudy-00001-Case-K50.9-Female-A40_49",
        query_mode="deterministic_only",
    )
    assert query_payload["intent"] == "patient_summary"
    assert query_payload["data"]["patient_id"] == "SYN001"
    assert query_payload["data"]["clarid"]["subject_id"] == 1
    assert query_payload["reply"].startswith("ClarID recognized as patient SYN001.")

    stub_payload = answer_query(
        str(tmp_path),
        "ClarID SyntheticStudy00001CASE",
        query_mode="deterministic_only",
    )
    assert stub_payload["intent"] == "patient_summary"
    assert stub_payload["data"]["patient_id"] == "SYN001"
    assert stub_payload["reply"].startswith("ClarID recognized as patient SYN001.")

    summary_payload = answer_query(
        str(tmp_path),
        "Show patient SyntheticStudy-00001-Case-K50.9-Female-A40_49",
        query_mode="deterministic_only",
        granularity_mode="summary",
    )
    assert summary_payload["reply"] == "Detailed patient-level answers are not available in Summary mode."
    assert "clarid" not in json.dumps(summary_payload).lower()


def test_query_store_rejects_incomplete_subject_clarid_coverage(tmp_path, monkeypatch):
    if not duckdb_available():
        return
    isolate_query_store(monkeypatch, tmp_path)
    write_json(tmp_path, "individuals.json", [{"id": "SYN001"}, {"id": "SYN002"}])
    identifiers_dir = tmp_path / "identifiers"
    identifiers_dir.mkdir()
    (identifiers_dir / "clarid_subjects.csv").write_text(
        "\n".join(
            [
                "unique_id,subject_id,study,type,condition,sex,age_group,clar_id,stub_id",
                "SYN001,1,SyntheticStudy,Case,K50.9,Female,Age40to49,SyntheticStudy-00001-Case-K50.9-Female-A40_49,SyntheticStudy00001CASE",
            ]
        ),
        encoding="utf-8",
    )
    write_json(
        tmp_path,
        "manifest.json",
        {
            "schema_version": 1,
            "clinical": {"representation": "person"},
            "identifiers": {
                "clarid_subjects": {
                    "file": "identifiers/clarid_subjects.csv",
                    "codebook_version": "0.04",
                    "tools_version": "0.04",
                }
            },
        },
    )

    with pytest.raises(ValueError, match="coverage must exactly match"):
        query_store_module.patient_clarid_inventory(str(tmp_path))


def test_default_fixture_exposes_precomputed_subject_clarids(tmp_path, monkeypatch):
    if not duckdb_available():
        return
    isolate_query_store(monkeypatch, tmp_path)
    monkeypatch.setattr(query_store_module, "list_registered_datasets", lambda: [])
    fixture_root = str(Path("default_dataset").resolve())

    clarids = query_store_module.patient_clarid_inventory(fixture_root)

    assert len(clarids) == 38
    assert clarids["SYN001"] == {
        "subject_id": 1,
        "human_id": "CNAG_Test-00001-Case-K50.9-Female-A20_29",
        "stub_id": "CT001C3ad01FA2",
        "study": "CNAG-Test",
        "type": "Case",
        "condition": "K50.9",
        "condition_name": "Crohn's disease, unspecified",
        "sex": "Female",
        "age_group": "Age20to29",
        "codebook_version": "0.04",
        "tools_version": "0.04",
    }
    assert query_store_module.resolve_patient_identifier(
        fixture_root, "CT001C3ad01FA2"
    )["patient_id"] == "SYN001"


def test_query_store_supports_longitudinal_helpers(tmp_path):
    if not duckdb_available():
        return

    write_json(
        tmp_path,
        "individuals.json",
        [
            {
                "id": "700:baseline",
                "event_date": "2024-01-01",
                "treatments": [{"_visit": {"id": "baseline"}, "treatmentCode": {"label": "Azathioprine"}}],
            },
            {
                "id": "700:month_3",
                "event_date": "2024-03-01",
                "treatments": [{"_visit": {"id": "month_3"}, "treatmentCode": {"label": "Azathioprine"}}],
            },
            {
                "id": "800:baseline",
                "event_date": "2024-03-15",
            },
        ],
    )

    summary = store_cohort_over_time_summary(str(tmp_path))
    assert summary["timepoint_count"] == 3
    assert summary["periods"][0]["period"] == "2024-01"

    cohort = store_patient_visit_count_cohort(str(tmp_path), "gt", 1)
    assert [item["patient_id"] for item in cohort["patients"]] == ["700"]


def test_query_store_rebuilds_stale_schema_missing_required_tables(tmp_path, monkeypatch):
    if not duckdb_available():
        return

    write_json(
        tmp_path,
        "records.json",
        [
            {
                "id": "SYN001:week_0",
                "event_date": "2024-01-01",
                "diseases": [{"diseaseCode": {"label": "Crohn Disease"}}],
                "treatments": [{"treatmentCode": {"label": "Infliximab"}}],
            }
        ],
    )

    store_dir = tmp_path / "query-store"
    monkeypatch.setattr(query_store_module, "QUERY_STORE_DIR", store_dir)

    db_path, meta_path = query_store_module._store_paths(str(tmp_path))
    con = query_store_module.duckdb.connect(str(db_path))
    try:
        con.execute("CREATE TABLE stale_schema_only (id TEXT)")
    finally:
        con.close()
    meta_path.write_text(
        json.dumps(query_store_module._source_files_signature(str(tmp_path)), indent=2),
        encoding="utf-8",
    )

    rows = query_module._patient_query_index(str(tmp_path))

    assert [item["patient_id"] for item in rows] == ["SYN001"]


def test_query_store_ingests_assay_count_matrices(tmp_path):
    if not duckdb_available():
        return

    write_json(
        tmp_path,
        "records.json",
        [
            {"id": "SYN001:baseline", "event_date": "2024-01-01"},
            {"id": "SYN002:baseline", "event_date": "2024-01-01"},
        ],
    )

    original_dir = query_store_module.ASSAY_DATA_DIR
    transcriptomics_dir = tmp_path / "assays" / "transcriptomics"
    transcriptomics_dir.mkdir(parents=True)
    (transcriptomics_dir / "synthetic_transcriptome_raw_counts.csv").write_text(
        "\n".join(
            [
                "gene_id;SYN001;SYN002",
                "ENSG00000111111;10;20",
                "ENSG00000122222;30;40",
            ]
        ),
        encoding="utf-8",
    )
    imaging_dir = tmp_path / "assays" / "imaging"
    imaging_dir.mkdir(parents=True)
    (imaging_dir / "synthetic_imaging_derived_features.csv").write_text(
        "\n".join(
            [
                "feature_id;SYN001;SYN002",
                "DICOM:0018,0087_MagneticFieldStrength;3.0;1.5",
                "DICOM:0028,1050_WindowCenter;450;520",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "assays" / "manifest.json").write_text(
        json.dumps(
            {
                "version": 1,
                "assays": [
                    {
                        "assay_id": "synthetic_transcriptome_raw_counts",
                        "label": "synthetic transcriptome raw counts",
                        "modality": "transcriptomics",
                        "data_type": "raw_counts",
                        "file": "assays/transcriptomics/synthetic_transcriptome_raw_counts.csv",
                    },
                    {
                        "assay_id": "synthetic_imaging_derived_features",
                        "label": "synthetic imaging derived features",
                        "modality": "imaging",
                        "data_type": "dicom_derived_measurements",
                        "file": "assays/imaging/synthetic_imaging_derived_features.csv",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    query_store_module.ASSAY_DATA_DIR = transcriptomics_dir
    try:
        inventory = store_assay_dataset_inventory(str(tmp_path))
    finally:
        query_store_module.ASSAY_DATA_DIR = original_dir

    assert len(inventory) == 2
    item = next(item for item in inventory if item["dataset_name"] == "synthetic_transcriptome_raw_counts")
    assert item["dataset_name"] == "synthetic_transcriptome_raw_counts"
    assert item["modality"] == "transcriptomics"
    assert item["data_type"] == "raw_counts"
    assert item["sample_count"] == 2
    assert item["patient_count"] == 2
    assert item["gene_count"] == 2
    assert item["clinical_overlap_patient_count"] == 2
    assert item["sample_ids"] == ["SYN001", "SYN002"]
    assert item["patient_ids"] == ["SYN001", "SYN002"]
    assert len(item["top_genes"]) == 2
    imaging = next(item for item in inventory if item["dataset_name"] == "synthetic_imaging_derived_features")
    assert imaging["modality"] == "imaging"
    assert imaging["data_type"] == "dicom_derived_measurements"
    assert imaging["feature_id_type"] == "dicom_standard_tag"
    assert imaging["feature_count"] == 2
    assert imaging["sample_count"] == 2
    assert imaging["clinical_overlap_patient_count"] == 2


def test_manifest_assay_stats_stream_header_and_use_declared_feature_count(tmp_path, monkeypatch):
    assay_dir = tmp_path / "assays" / "methylation"
    assay_dir.mkdir(parents=True)
    matrix_path = assay_dir / "matrix.csv"
    matrix_path.write_text(
        "feature_id;SYN001;SYN002\nCpG001;0.1;0.2\nCpG002;0.3;0.4\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        Path,
        "read_text",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("matrix must be streamed")),
    )
    stats = query_store_module._assay_matrix_stats(
        tmp_path,
        {
            "file": "assays/methylation/matrix.csv",
            "feature_count": 368_607,
        },
    )

    assert stats is not None
    assert stats["sample_ids"] == ["SYN001", "SYN002"]
    assert stats["feature_count"] == 368_607


def test_manifest_assay_stats_uses_explicit_metadata_linkage_for_tsv_matrix(tmp_path):
    assay_dir = tmp_path / "assays" / "methylation"
    assay_dir.mkdir(parents=True)
    (assay_dir / "matrix.tsv").write_text(
        "feature_id\tARRAY_A\tARRAY_B\n"
        "cg00000001\t0.1\t0.2\n",
        encoding="utf-8",
    )
    (assay_dir / "samples.tsv").write_text(
        "sample_id\tpatient_id\n"
        "ARRAY_A\tPATIENT_1\n"
        "ARRAY_B\tPATIENT_2\n",
        encoding="utf-8",
    )

    stats = query_store_module._assay_matrix_stats(
        tmp_path,
        {
            "file": "assays/methylation/matrix.tsv",
            "sample_metadata_file": "assays/methylation/samples.tsv",
        },
    )

    assert stats is not None
    assert stats["sample_ids"] == ["ARRAY_A", "ARRAY_B"]
    assert stats["patient_ids"] == ["PATIENT_1", "PATIENT_2"]
    assert stats["linkage_source"] == "sample_metadata_file"
    assert stats["linked_sample_count"] == 2
    assert stats["unlinked_sample_count"] == 0


def test_manifest_assay_inventory_honors_exact_sample_id_with_technical_metadata(tmp_path, monkeypatch):
    if not duckdb_available():
        return

    isolate_query_store(monkeypatch, tmp_path)
    write_json(
        tmp_path,
        "records.json",
        [{"id": "SYN001"}, {"id": "SYN002"}],
    )
    assay_dir = tmp_path / "assays" / "transcriptomics"
    assay_dir.mkdir(parents=True)
    (assay_dir / "matrix.csv").write_text(
        "feature_id;SYN001;SYN002\n"
        "ENSG00000141510;10.5;12.25\n",
        encoding="utf-8",
    )
    (assay_dir / "technical.csv").write_text(
        "sample_id;batch\n"
        "SYN001;A\n"
        "SYN002;B\n",
        encoding="utf-8",
    )
    (tmp_path / "assays" / "manifest.json").write_text(
        json.dumps(
            {
                "version": 1,
                "assays": [
                    {
                        "assay_id": "synthetic_rsem_expected_counts",
                        "modality": "transcriptomics",
                        "data_type": "rsem_expected_counts",
                        "file": "assays/transcriptomics/matrix.csv",
                        "sample_metadata_file": "assays/transcriptomics/technical.csv",
                        "patient_linkage": "exact_sample_id",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    inventory = store_assay_dataset_inventory(str(tmp_path))

    assert len(inventory) == 1
    item = inventory[0]
    assert item["dataset_name"] == "synthetic_rsem_expected_counts"
    assert item["sample_ids"] == ["SYN001", "SYN002"]
    assert item["patient_ids"] == ["SYN001", "SYN002"]
    assert item["clinical_overlap_patient_count"] == 2
    assert item["linkage_source"] == "exact_sample_id"
    assert item["linked_sample_count"] == 2
    assert item["unlinked_sample_count"] == 0
    assert item["supports_expression_summary"] is False

    catalog = analysis_catalog_module.analysis_catalog_payload(str(tmp_path))
    catalog_items = {value["id"]: value for value in catalog["items"]}
    for item_id in (
        "transcriptomics-expression",
        "transcriptomics-medication-compare",
    ):
        assert catalog_items[item_id]["available"] is False
        assert "raw_counts" in catalog_items[item_id]["unavailable_reason"]

    expression_context = analysis_module.transcriptomics_expression_context(
        str(tmp_path),
        "ENSG00000141510",
    )
    medication_context = analysis_module.transcriptomics_expression_by_medication_context(str(tmp_path))
    assert expression_context["datasets"] == []
    assert "No raw-count transcriptomics assays" in expression_context["error"]
    assert medication_context["comparisons"] == []
    assert "raw-count transcriptomics assays" in medication_context["error"]

    with pytest.raises(RuntimeError, match="compatible assay"):
        analysis_module.analysis_llm_reply(
            "Show expression of ENSG00000141510 in the current Analysis scope.",
            str(tmp_path),
            catalog_item_id="transcriptomics-expression",
            assay_id="synthetic_rsem_expected_counts",
            deterministic_only=True,
        )

    with pytest.raises(RuntimeError, match="compatible assay"):
        analysis_module.analysis_llm_reply(
            "Explain differences in gene expression according to medication.",
            str(tmp_path),
            catalog_item_id="transcriptomics-medication-compare",
            assay_id="synthetic_rsem_expected_counts",
            deterministic_only=True,
        )


def test_methylation_manifest_is_registered_without_materializing_values(tmp_path, monkeypatch):
    if not duckdb_available():
        return

    isolate_query_store(monkeypatch, tmp_path)
    write_json(
        tmp_path,
        "records.json",
        [
            {"id": "SYN001", "diseases": [{"diseaseCode": {"label": "Rheumatoid Arthritis"}}]},
            {"id": "SYN002", "diseases": [{"diseaseCode": {"label": "Healthy Control"}}]},
        ],
    )
    assay_dir = tmp_path / "assays" / "methylation"
    assay_dir.mkdir(parents=True)
    matrix_path = assay_dir / "synthetic_m_values.csv"
    matrix_path.write_text(
        "feature_id;SYN001;SYN002\n"
        "cg00000029;-1.42;-1.10\n"
        "cg00000108;0.34;0.55\n"
        "cg00000165;2.10;1.92\n",
        encoding="utf-8",
    )
    (tmp_path / "assays" / "manifest.json").write_text(
        json.dumps(
            {
                "version": 1,
                "assays": [
                    {
                        "assay_id": "synthetic_m_values",
                        "label": "Synthetic methylation M-values",
                        "modality": "methylation",
                        "data_type": "m_values",
                        "feature_namespace": "illumina_cpg_probe_id",
                        "feature_label": "CpG probes",
                        "value_kind": "m_values",
                        "file": "assays/methylation/synthetic_m_values.csv",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    assert query_store_module._assay_matrix_files(str(tmp_path)) == []
    inventory = store_assay_dataset_inventory(str(tmp_path))
    item = next(value for value in inventory if value["dataset_name"] == "synthetic_m_values")
    searchable_features = store_assay_feature_inventory(str(tmp_path), "synthetic_m_values")
    preview = query_store_module.assay_dataset_matrix_preview(
        str(tmp_path),
        "synthetic_m_values",
        feature_limit=2,
    )
    con = query_store_module._connect(str(tmp_path))
    try:
        materialized_value_count = con.execute("SELECT count(*) FROM transcript_counts").fetchone()[0]
    finally:
        con.close()

    assert item["modality"] == "methylation"
    assert item["data_type"] == "m_values"
    assert item["feature_id_type"] == "illumina_cpg_probe_id"
    assert item["feature_label"] == "CpG probes"
    assert item["value_kind"] == "m_values"
    assert item["feature_count"] == 3
    assert item["sample_count"] == 2
    assert item["clinical_overlap_patient_count"] == 2
    assert item["supports_expression_summary"] is False
    assert item["supports_differential_expression"] is False
    # Feature discovery reads the compact external matrix without importing values.
    assert searchable_features == ["cg00000029", "cg00000108", "cg00000165"]
    assert preview is not None
    assert preview["features"] == [
        {"feature_id": "cg00000029", "label": "cg00000029"},
        {"feature_id": "cg00000108", "label": "cg00000108"},
    ]
    assert preview["sample_values"]["SYN001"]["cg00000029"] == -1.42
    assert materialized_value_count == 0


def test_flow_cytometry_and_serology_manifests_are_first_class_external_assays(tmp_path, monkeypatch):
    if not duckdb_available():
        return

    isolate_query_store(monkeypatch, tmp_path)
    write_json(
        tmp_path,
        "records.json",
        [
            {"id": "SYN001", "diseases": [{"diseaseCode": {"label": "Condition A"}}]},
            {"id": "SYN002", "diseases": [{"diseaseCode": {"label": "Healthy Control"}}]},
        ],
    )
    assays_dir = tmp_path / "assays"
    immune_dir = assays_dir / "flow_cytometry"
    serology_dir = assays_dir / "serology"
    immune_dir.mkdir(parents=True)
    serology_dir.mkdir(parents=True)
    (immune_dir / "immune_cells.csv").write_text(
        "feature_id,SYN001,SYN002\nCD4_T_cells,0.31,0.28\nMonocytes,0.12,0.09\n",
        encoding="utf-8",
    )
    (serology_dir / "markers.csv").write_text(
        "feature_id,SYN001,SYN002\nMarker_A,4.2,3.8\nMarker_B,11.0,9.5\n",
        encoding="utf-8",
    )
    (assays_dir / "manifest.json").write_text(
        json.dumps(
            {
                "version": 1,
                "assays": [
                    {
                        "assay_id": "immune_cells",
                        "label": "Immune-cell abundance",
                        "modality": "flow_cytometry",
                        "data_type": "cell_population_abundance",
                        "patient_linkage": "exact_sample_id",
                        "file": "assays/flow_cytometry/immune_cells.csv",
                    },
                    {
                        "assay_id": "quantitative_serology",
                        "label": "Quantitative serology",
                        "modality": "serology",
                        "data_type": "quantitative_measurement",
                        "patient_linkage": "exact_sample_id",
                        "file": "assays/serology/markers.csv",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    assert query_store_module._assay_matrix_files(str(tmp_path)) == []
    inventory = {item["dataset_name"]: item for item in store_assay_dataset_inventory(str(tmp_path))}

    immune = inventory["immune_cells"]
    assert immune["feature_id_type"] == "immune_cell_population"
    assert immune["feature_label"] == "immune-cell populations"
    assert immune["value_kind"] == "cell_population_abundance"
    assert immune["sample_count"] == 2
    assert immune["clinical_overlap_patient_count"] == 2

    serology = inventory["quantitative_serology"]
    assert serology["feature_id_type"] == "serology_marker"
    assert serology["feature_label"] == "serology markers"
    assert serology["value_kind"] == "quantitative_measurement"
    assert serology["sample_count"] == 2
    assert serology["clinical_overlap_patient_count"] == 2

    con = query_store_module._connect(str(tmp_path))
    try:
        assert con.execute("SELECT count(*) FROM transcript_counts").fetchone()[0] == 0
    finally:
        con.close()


def test_query_reads_compact_external_assays_deterministically_without_duckdb_values(tmp_path, monkeypatch):
    if not duckdb_available():
        return

    isolate_query_store(monkeypatch, tmp_path)
    write_json(
        tmp_path,
        "records.json",
        [
            {"id": "SYN001", "diseases": [{"diseaseCode": {"label": "Condition A"}}]},
            {"id": "SYN002", "diseases": [{"diseaseCode": {"label": "Condition A"}}]},
            {"id": "SYN003", "diseases": [{"diseaseCode": {"label": "Healthy Control"}}]},
            {"id": "SYN004", "diseases": [{"diseaseCode": {"label": "Healthy Control"}}]},
        ],
    )
    assays_dir = tmp_path / "assays"
    immune_dir = assays_dir / "flow_cytometry"
    serology_dir = assays_dir / "serology"
    immune_dir.mkdir(parents=True)
    serology_dir.mkdir(parents=True)
    (immune_dir / "immune.tsv").write_text(
        "feature_id\tSYN001\tSYN002\tSYN003\tSYN004\n"
        "CD4_T_cells\t0.30\t0.34\t0.21\t0.25\n"
        "Monocytes\t0.12\t0.16\t0.08\t0.10\n",
        encoding="utf-8",
    )
    (serology_dir / "serology.tsv").write_text(
        "feature_id\tSYN001\tSYN002\tSYN003\tSYN004\n"
        "Marker_A\t4\t6\t2\t4\n"
        "Marker_B\t8\tNA\t3\t5\n",
        encoding="utf-8",
    )
    (assays_dir / "manifest.json").write_text(
        json.dumps(
            {
                "version": 1,
                "assays": [
                    {
                        "assay_id": "immune_cells",
                        "label": "Immune-cell abundance",
                        "modality": "flow_cytometry",
                        "data_type": "cell_population_abundance",
                        "patient_linkage": "exact_sample_id",
                        "feature_count": 2,
                        "file": "assays/flow_cytometry/immune.tsv",
                    },
                    {
                        "assay_id": "quantitative_serology",
                        "label": "Quantitative serology",
                        "modality": "serology",
                        "data_type": "quantitative_measurement",
                        "patient_linkage": "exact_sample_id",
                        "feature_count": 2,
                        "file": "assays/serology/serology.tsv",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    inventory = answer_query(str(tmp_path), "List the available serology markers", query_mode="deterministic_only")
    assert inventory["intent"] == "external_assay_inventory"
    assert inventory["data"]["feature_count"] == 2
    assert [row["feature_id"] for row in inventory["data"]["assay_results"]] == ["Marker_A", "Marker_B"]

    summary = answer_query(
        str(tmp_path),
        "Summarize Marker_A in serology for this cohort",
        query_mode="deterministic_only",
        history=[{"role": "assistant", "content": "A prior query selected this cohort."}],
        scoped_patient_ids=["SYN001", "SYN003"],
    )
    assert summary["intent"] == "external_assay_summary"
    assert summary["data"]["scope_sample_count"] == 2
    assert summary["data"]["assay_results"][0]["mean"] == 3.0
    assert all(patient_id not in json.dumps(summary) for patient_id in ("SYN001", "SYN002", "SYN003", "SYN004"))

    comparison = answer_query(
        str(tmp_path),
        "Compare Marker_A in serology between Condition A and Healthy Control",
        query_mode="deterministic_only",
    )
    assert comparison["intent"] == "external_assay_comparison"
    result = comparison["data"]["assay_results"][0]
    assert result["cohort_a"]["mean"] == 5.0
    assert result["cohort_b"]["mean"] == 3.0
    assert result["mean_difference_a_minus_b"] == 2.0
    assert all(patient_id not in json.dumps(comparison) for patient_id in ("SYN001", "SYN002", "SYN003", "SYN004"))

    con = query_store_module._connect(str(tmp_path))
    try:
        assert con.execute("SELECT count(*) FROM transcript_counts").fetchone()[0] == 0
    finally:
        con.close()


def test_semantic_planner_can_select_a_validated_external_assay_operation(tmp_path, monkeypatch):
    if not duckdb_available():
        return

    isolate_query_store(monkeypatch, tmp_path)
    write_json(tmp_path, "records.json", [{"id": "SYN001"}, {"id": "SYN002"}])
    assay_dir = tmp_path / "assays" / "serology"
    assay_dir.mkdir(parents=True)
    (assay_dir / "serology.tsv").write_text(
        "feature_id\tSYN001\tSYN002\nMarker_A\t4\t2\n",
        encoding="utf-8",
    )
    (tmp_path / "assays" / "manifest.json").write_text(
        json.dumps(
            {
                "version": 1,
                "assays": [
                    {
                        "assay_id": "quantitative_serology",
                        "label": "Quantitative serology",
                        "modality": "serology",
                        "data_type": "quantitative_measurement",
                        "patient_linkage": "exact_sample_id",
                        "feature_count": 1,
                        "file": "assays/serology/serology.tsv",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(query_module, "_lm_studio_enabled", lambda: True)
    monkeypatch.setattr(query_module, "_resolve_lm_studio_model", lambda: "synthetic-model")
    monkeypatch.setattr(
        query_module,
        "_http_json",
        lambda *_args, **_kwargs: {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "intent": "assay_query",
                                "operation": "summary",
                                "modality": "serology",
                                "feature": "Marker_A",
                            }
                        )
                    }
                }
            ]
        },
    )

    payload = answer_query(
        str(tmp_path),
        "Give me a compact overview of the first serological marker",
        query_mode="planner_only",
        ai_provider_access="detailed_allowed",
    )

    assert payload["intent"] == "external_assay_summary"
    assert payload["data"]["planner"]["provider"] == "lm_studio"
    assert payload["data"]["semantic_plan"]["intent"] == "assay_query"
    assert payload["data"]["assay_results"][0]["mean"] == 3.0


def test_synthetic_methylation_fixture_uses_processed_m_value_contract():
    matrices = []
    for dataset_root in (Path("default_dataset"), Path("dataset-large")):
        manifest = json.loads((dataset_root / "assays" / "manifest.json").read_text(encoding="utf-8"))
        item = next(
            value
            for value in manifest["assays"]
            if value.get("assay_id") == "synthetic_methylation_m_values"
        )
        matrix_path = dataset_root / item["file"]

        assert item["modality"] == "methylation"
        assert item["data_type"] == "m_values"
        assert item["feature_namespace"] == "illumina_cpg_probe_id"
        assert item["feature_label"] == "CpG probes"
        assert item["value_kind"] == "m_values"
        assert item["sample_metadata_file"] == "assays/methylation/synthetic_methylation_sample_metadata.tsv"
        assert matrix_path.is_file()
        metadata_path = dataset_root / item["sample_metadata_file"]
        assert metadata_path.is_file()
        assert metadata_path.read_text(encoding="utf-8").splitlines()[0] == "sample_id\tpatient_id"
        matrices.append(matrix_path.read_text(encoding="utf-8"))

    assert matrices[0] == matrices[1]
    assert matrices[0].splitlines()[1].startswith("cg00000029;")


def test_synthetic_compact_assay_fixtures_have_complete_analysis_ready_linkage():
    expected = {
        "synthetic_immune_cell_abundance": {
            "modality": "flow_cytometry",
            "data_type": "cell_population_abundance",
            "feature_namespace": "immune_cell_population",
            "feature_label": "immune-cell populations",
            "feature_count": 5,
            "metadata_file": "assays/flow_cytometry/synthetic_immune_cell_sample_metadata.tsv",
        },
        "synthetic_quantitative_serology": {
            "modality": "serology",
            "data_type": "quantitative_measurement",
            "feature_namespace": "serology_marker",
            "feature_label": "serology markers",
            "feature_count": 6,
            "metadata_file": "assays/serology/synthetic_serology_sample_metadata.tsv",
        },
    }
    generated_payloads = {}

    for dataset_root in (Path("default_dataset"), Path("dataset-large")):
        manifest = json.loads((dataset_root / "assays" / "manifest.json").read_text(encoding="utf-8"))
        items = {value.get("assay_id"): value for value in manifest["assays"]}
        clinical_records = json.loads(
            (dataset_root / "clinical" / "synthetic_longitudinal.json").read_text(encoding="utf-8")
        )
        baseline_disease_by_patient = {
            str(record.get("patient_id") or ""): str(
                ((record.get("diseases") or [{}])[0].get("diseaseCode") or {}).get("label") or ""
            )
            for record in clinical_records
            if str(record.get("id") or "").endswith(":week_0")
        }

        for assay_id, contract in expected.items():
            item = items[assay_id]
            matrix_path = dataset_root / item["file"]
            metadata_path = dataset_root / item["sample_metadata_file"]
            matrix_lines = matrix_path.read_text(encoding="utf-8").splitlines()
            metadata_lines = metadata_path.read_text(encoding="utf-8").splitlines()
            sample_ids = matrix_lines[0].split(";")[1:]
            metadata_rows = [line.split("\t") for line in metadata_lines[1:]]
            links = dict(metadata_rows)

            assert item["modality"] == contract["modality"]
            assert item["data_type"] == contract["data_type"]
            assert item["feature_namespace"] == contract["feature_namespace"]
            assert item["feature_label"] == contract["feature_label"]
            assert item["value_kind"] == contract["data_type"]
            assert item["level"] == "sample"
            assert item["patient_linkage"] == "sample_metadata_file"
            assert item["patient_id_column"] == "patient_id"
            assert item["sample_metadata_file"] == contract["metadata_file"]
            assert len(matrix_lines) - 1 == contract["feature_count"]
            assert metadata_lines[0] == "sample_id\tpatient_id"
            assert sample_ids == list(links)
            assert len(sample_ids) == len(set(sample_ids)) == 8
            assert len(set(links.values())) == 8
            assert all(links[sample_id] in baseline_disease_by_patient for sample_id in sample_ids)

            disease_counts = {
                disease: sum(
                    baseline_disease_by_patient[patient_id] == disease
                    for patient_id in links.values()
                )
                for disease in (
                    "Systemic Lupus Erythematosus",
                    "Rheumatoid Arthritis",
                )
            }
            assert disease_counts == {
                "Systemic Lupus Erythematosus": 4,
                "Rheumatoid Arthritis": 4,
            }

            stats = query_store_module._assay_matrix_stats(dataset_root.resolve(), item)
            assert stats is not None
            assert stats["sample_count"] == 8
            assert stats["patient_count"] == 8
            assert stats["feature_count"] == contract["feature_count"]
            assert stats["linked_sample_count"] == 8
            assert stats["unlinked_sample_count"] == 0
            assert stats["linkage_source"] == "sample_metadata_file"

            payload = (matrix_path.read_text(encoding="utf-8"), metadata_path.read_text(encoding="utf-8"))
            if assay_id in generated_payloads:
                assert generated_payloads[assay_id] == payload
            else:
                generated_payloads[assay_id] = payload


def test_assay_inventory_metadata_honors_manifest_capability_overrides():
    metadata = query_store_module._assay_inventory_metadata(
        "transcriptomics",
        "expression_values",
        {
            "feature_namespace": "ensembl_gene_id",
            "feature_label": "genes",
            "value_kind": "preprocessing_unresolved_expression_values",
            "patient_linkage": "exact_sample_id",
            "supports_expression_summary": False,
            "supports_differential_expression": False,
            "compatible_analysis_levels": ["patient"],
        },
    )

    assert metadata["feature_id_type"] == "ensembl_gene_id"
    assert metadata["value_kind"] == "preprocessing_unresolved_expression_values"
    assert metadata["patient_linkage"] == "exact_sample_id"
    assert metadata["supports_expression_summary"] is False
    assert metadata["supports_differential_expression"] is False
    assert metadata["compatible_analysis_levels"] == ["patient"]


def test_manifest_expression_values_are_not_coerced_into_raw_counts(tmp_path):
    transcriptomics_dir = tmp_path / "assays" / "transcriptomics"
    transcriptomics_dir.mkdir(parents=True)
    raw_counts = transcriptomics_dir / "raw_counts.csv"
    expression_values = transcriptomics_dir / "expression_values.csv"
    sample_metadata = transcriptomics_dir / "sample_metadata.csv"
    raw_counts.write_text("gene_id;SYN001\nENSG00000141510;10\n", encoding="utf-8")
    expression_values.write_text("gene_id;SYN001\nENSG00000141510;10.75\n", encoding="utf-8")
    sample_metadata.write_text("sample_id;batch\nSYN001;A\n", encoding="utf-8")
    (tmp_path / "assays" / "manifest.json").write_text(
        json.dumps(
            {
                "version": 1,
                "assays": [
                    {
                        "assay_id": "raw_counts",
                        "modality": "transcriptomics",
                        "data_type": "raw_counts",
                        "file": "assays/transcriptomics/raw_counts.csv",
                    },
                    {
                        "assay_id": "expression_values",
                        "modality": "transcriptomics",
                        "data_type": "expression_values",
                        "file": "assays/transcriptomics/expression_values.csv",
                        "sample_metadata_file": "assays/transcriptomics/sample_metadata.csv",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    assert query_store_module._assay_matrix_files(str(tmp_path)) == [raw_counts]
    assert datasets_module.dataset_content_metadata(str(tmp_path))["assay_file_count"] == 2


def test_query_store_summarizes_transcriptomics_expression_by_scope(tmp_path):
    if not duckdb_available():
        return

    write_json(
        tmp_path,
        "records.json",
        [
            {"id": "SYN001:baseline", "event_date": "2024-01-01"},
            {"id": "SYN002:baseline", "event_date": "2024-01-01"},
            {"id": "SYN003:baseline", "event_date": "2024-01-01"},
        ],
    )

    original_dir = query_store_module.ASSAY_DATA_DIR
    transcriptomics_dir = tmp_path / "assays" / "transcriptomics"
    transcriptomics_dir.mkdir(parents=True)
    (transcriptomics_dir / "synthetic_transcriptome_raw_counts.csv").write_text(
        "\n".join(
            [
                "gene_id;SYN001;SYN002;SYN003",
                "ENSG00000141510;10;20;30",
                "ENSG00000122222;7;8;9",
            ]
        ),
        encoding="utf-8",
    )
    query_store_module.ASSAY_DATA_DIR = transcriptomics_dir
    try:
        inventory = store_assay_dataset_inventory(str(tmp_path))
        genes = store_assay_feature_inventory(str(tmp_path), "synthetic_transcriptome_raw_counts", search="tp53")
        payload = store_assay_expression_summary(
            str(tmp_path),
            "synthetic_transcriptome_raw_counts",
            "ENSG00000141510",
            selected_patient_ids="SYN001,SYN002",
            compare_selected_patient_ids="SYN003",
        )
    finally:
        query_store_module.ASSAY_DATA_DIR = original_dir

    assert genes == ["ENSG00000141510"]
    assert inventory[0]["clinical_overlap_patient_count"] == 3
    assert inventory[0]["mean_total_counts_per_sample"] == 28
    assert inventory[0]["mean_detected_genes_per_sample"] == 2
    assert inventory[0]["top_genes"][0]["gene_symbol"] == "TP53"
    assert inventory[0]["top_genes"][0]["ensembl_url"].endswith("ENSG00000141510")
    assert payload["gene_symbol"] == "TP53"
    assert payload["ensembl_url"].endswith("ENSG00000141510")
    assert payload["scope_a"]["sample_count"] == 2
    assert payload["scope_a"]["mean"] == 15
    assert payload["scope_b"]["sample_count"] == 1
    assert payload["scope_b"]["max"] == 30
