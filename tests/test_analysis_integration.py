import json
from pathlib import Path
import pytest
import app.routes as routes_module
from bff_test_helpers import write_json
import shutil
import subprocess
from starlette.requests import Request
import app.analysis as analysis_module
import app.analysis_catalog as analysis_catalog_module
import app.analysis_external as analysis_external_module
import app.query_store as query_store_module
from bff_test_helpers import _write_synthetic_methylation_runner_fixture


def test_analysis_survival_kaplan_meier_for_measure_threshold(tmp_path):
    write_json(
        tmp_path,
        "records.json",
        [
            {
                "id": "P1:week0",
                "event_date": "2024-01-01",
                "measures": [
                    {
                        "assayCode": {"label": "Leukocyte Count"},
                        "measurementValue": {"quantity": {"value": 8.0, "unit": {"label": "Cells per Microliter"}}},
                    }
                ],
            },
            {
                "id": "P1:week4",
                "event_date": "2024-01-15",
                "measures": [
                    {
                        "assayCode": {"label": "Leukocyte Count"},
                        "measurementValue": {"quantity": {"value": 11.2, "unit": {"label": "Cells per Microliter"}}},
                    }
                ],
            },
            {
                "id": "P2:week0",
                "event_date": "2024-01-03",
                "measures": [
                    {
                        "assayCode": {"label": "Leukocyte Count"},
                        "measurementValue": {"quantity": {"value": 7.1, "unit": {"label": "Cells per Microliter"}}},
                    }
                ],
            },
            {
                "id": "P2:week4",
                "event_date": "2024-01-21",
                "measures": [
                    {
                        "assayCode": {"label": "Leukocyte Count"},
                        "measurementValue": {"quantity": {"value": 8.4, "unit": {"label": "Cells per Microliter"}}},
                    }
                ],
            },
        ],
    )

    payload = analysis_module.analysis_llm_reply(
        "Show a Kaplan-Meier curve for time to Leukocyte Count > 10",
        str(tmp_path),
    )

    assert payload["intent"] == "analysis_survival"
    context = payload["data"]["context"]
    assert context["mode"] == "survival"
    assert context["measure"] == "Leukocyte Count"
    assert context["patient_count"] == 2
    assert context["event_count"] == 1
    assert context["censored_count"] == 1
    assert context["median_survival_days"] == 14
    assert context["curve_points"][0]["survival_probability"] == 1.0
    assert context["curve_points"][1]["time_days"] == 14
    assert context["curve_points"][1]["survival_probability"] == 0.5


def test_analysis_catalog_loader_normalizes_yaml_entries(tmp_path):
    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text(
        """
items:
  - id: clinical-summary
    name: Clinical cohort summary
    description: Summarize the active cohort.
    default_prompt: Summarize the active cohort.
    execution_mode: deterministic
    tags: [clinical, summary]
""".strip(),
        encoding="utf-8",
    )

    items = analysis_catalog_module.load_analysis_catalog(catalog_path)

    assert len(items) == 1
    assert items[0]["id"] == "clinical-summary"
    assert items[0]["category"] == "General"
    assert items[0]["execution_mode"] == "deterministic"
    assert items[0]["runner_type"] == "builtin"
    assert items[0]["runner_ref"] == "clinical-summary"
    assert items[0]["tags"] == ["clinical", "summary"]


def test_analysis_catalog_loader_accepts_curated_workflow_metadata(tmp_path):
    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text(
        """
items:
  - id: transcriptomics-signature-workflow
    name: Assay signature workflow
    description: Run the project workflow.
    default_prompt: Run the assay signature workflow.
    runner_type: workflow
    runner_ref: transcriptomics_signature
    execution_backend: job
    steps:
      - transcriptomics-deseq2-differential-expression
      - transcriptomics-hallmark-pathway-enrichment
""".strip(),
        encoding="utf-8",
    )

    items = analysis_catalog_module.load_analysis_catalog(catalog_path)

    assert items[0]["runner_type"] == "workflow"
    assert items[0]["runner_ref"] == "transcriptomics_signature"
    assert items[0]["execution_backend"] == "job"
    assert items[0]["steps"] == [
        "transcriptomics-deseq2-differential-expression",
        "transcriptomics-hallmark-pathway-enrichment",
    ]


def test_analysis_catalog_declares_two_governed_quantitative_assay_comparisons():
    items = {
        item["id"]: item
        for item in analysis_catalog_module.load_analysis_catalog()
        if item["id"] in {
            "flow-cytometry-wilcoxon-cohort-comparison",
            "serology-wilcoxon-cohort-comparison",
        }
    }

    assert set(items) == {
        "flow-cytometry-wilcoxon-cohort-comparison",
        "serology-wilcoxon-cohort-comparison",
    }
    expected_contracts = {
        "flow-cytometry-wilcoxon-cohort-comparison": ("flow_cytometry", "cell_population_abundance"),
        "serology-wilcoxon-cohort-comparison": ("serology", "quantitative_measurement"),
    }
    for item_id, (modality, data_type) in expected_contracts.items():
        item = items[item_id]
        assert item["runner_type"] == "rscript"
        assert item["runner_ref"] == "quantitative_assay_wilcoxon_comparison"
        assert item["execution_backend"] == "job"
        assert item["default_compare_mode"] is True
        assert item["minimum_samples_per_cohort"] == 3
        assert item["requires_detailed_access"] is True
        assert item["requires_single_dataset_workspace"] is True
        assert item["required_modalities"] == [modality]
        assert item["required_data_types"] == [data_type]


def test_analysis_catalog_restricts_builtin_transcript_count_analyses_to_raw_counts():
    items = {
        item["id"]: item
        for item in analysis_catalog_module.load_analysis_catalog()
        if item["id"] in {
            "transcriptomics-expression",
            "transcriptomics-medication-compare",
        }
    }

    assert set(items) == {
        "transcriptomics-expression",
        "transcriptomics-medication-compare",
    }
    for item in items.values():
        assert item["runner_type"] == "builtin"
        assert item["required_modalities"] == ["transcriptomics"]
        assert item["required_data_types"] == ["raw_counts"]


def test_analysis_catalog_loader_preserves_debug_only_flag(tmp_path):
    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text(
        """
items:
  - id: external-debug-demo
    name: External debug demo
    description: Demo.
    default_prompt: Run it.
    runner_type: rscript
    runner_ref: dummy_scope_snapshot
    debug_only: true
""".strip(),
        encoding="utf-8",
    )

    items = analysis_catalog_module.load_analysis_catalog(catalog_path)

    assert items[0]["debug_only"] is True


def test_analysis_catalog_payload_hides_debug_only_items_by_default(tmp_path, monkeypatch):
    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text(
        """
items:
  - id: visible-analysis
    name: Visible analysis
    description: Demo.
    default_prompt: Run visible.
  - id: debug-analysis
    name: Debug analysis
    description: Demo.
    default_prompt: Run debug.
    debug_only: true
""".strip(),
        encoding="utf-8",
    )
    write_json(tmp_path, "records.json", [{"id": "P1:baseline", "patient_id": "P1"}])
    monkeypatch.delenv("COHORTOME_ANALYSIS_CATALOG_DEBUG", raising=False)

    payload = analysis_catalog_module.analysis_catalog_payload(str(tmp_path), path=catalog_path)

    assert [item["id"] for item in payload["items"]] == ["visible-analysis"]


def test_analysis_catalog_payload_can_include_debug_only_items_with_server_flag(tmp_path, monkeypatch):
    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text(
        """
items:
  - id: visible-analysis
    name: Visible analysis
    description: Demo.
    default_prompt: Run visible.
  - id: debug-analysis
    name: Debug analysis
    description: Demo.
    default_prompt: Run debug.
    debug_only: true
""".strip(),
        encoding="utf-8",
    )
    write_json(tmp_path, "records.json", [{"id": "P1:baseline", "patient_id": "P1"}])
    monkeypatch.setenv("COHORTOME_ANALYSIS_CATALOG_DEBUG", "true")

    payload = analysis_catalog_module.analysis_catalog_payload(str(tmp_path), path=catalog_path)

    assert [item["id"] for item in payload["items"]] == ["visible-analysis", "debug-analysis"]


def test_analysis_catalog_nextflow_availability_accepts_env_override(tmp_path, monkeypatch):
    catalog_item = {
        "id": "nextflow-demo",
        "name": "Nextflow demo",
        "description": "Demo.",
        "default_prompt": "Run it.",
        "runner_type": "nextflow",
        "runner_ref": "dummy_queue_demo",
        "execution_backend": "job",
    }
    nextflow_path = tmp_path / "nextflow"
    nextflow_path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    nextflow_path.chmod(0o755)

    monkeypatch.setattr(analysis_catalog_module.shutil, "which", lambda name: None)
    monkeypatch.setenv("NEXTFLOW_BIN", str(nextflow_path))

    availability = analysis_catalog_module._availability_for_item(
        catalog_item,
        granularity_ceiling="detailed",
        has_assays=True,
    )

    assert availability["available"] is True
    assert availability["unavailable_reason"] == ""


def test_analysis_catalog_blocks_longitudinal_item_for_person_representation():
    availability = analysis_catalog_module._availability_for_item(
        {
            "id": "trajectory-single",
            "runner_type": "builtin",
            "required_clinical_representation": "snapshot",
        },
        granularity_ceiling="detailed",
        has_assays=False,
        clinical_record_representation="person",
    )

    assert availability["available"] is False
    assert "longitudinal visit or timepoint records" in availability["unavailable_reason"]


def test_analysis_prompt_without_catalog_selection_uses_normal_routing(tmp_path):
    write_json(
        tmp_path,
        "records.json",
        [
            {
                "id": "P1:baseline",
                "event_date": "2025-01-10",
                "diseases": [{"diseaseCode": {"label": "Multiple Sclerosis"}}],
                "treatments": [{"treatmentCode": {"label": "Ocrelizumab"}}],
            }
        ],
    )

    payload = analysis_module.analysis_llm_reply(
        "Summarize the main clinical patterns in this workspace and tell me what stands out.",
        str(tmp_path),
        catalog_item_id="",
        deterministic_only=True,
    )

    assert payload["intent"] == "analysis_deterministic"
    assert payload["data"]["source"] == "deterministic"
    assert "Deterministic Workspace Summary" in payload["reply"]


def test_analysis_debug_catalog_item_is_rejected_without_server_flag(tmp_path, monkeypatch):
    write_json(tmp_path, "records.json", [{"id": "P1:baseline", "patient_id": "P1"}])
    monkeypatch.delenv("COHORTOME_ANALYSIS_CATALOG_DEBUG", raising=False)

    with pytest.raises(RuntimeError, match="not available"):
        analysis_module.analysis_llm_reply(
            "Run the external R cohort snapshot analysis for the current Analysis scope.",
            str(tmp_path),
            catalog_item_id="external-r-scope-snapshot",
            deterministic_only=True,
        )


def test_analysis_catalog_item_requires_detailed_access_on_backend(tmp_path):
    write_json(tmp_path, "records.json", [{"id": "P1:baseline", "patient_id": "P1"}])

    with pytest.raises(RuntimeError, match="Detailed in-app access"):
        analysis_module.analysis_llm_reply(
            "Run the external R clinical scope profile for the current Analysis scope.",
            str(tmp_path),
            catalog_item_id="external-r-clinical-profile",
            deterministic_only=True,
            granularity_ceiling="summary",
        )


def test_analysis_catalog_payload_marks_unavailable_items_for_workspace_limits(tmp_path):
    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text(
        """
items:
  - id: detailed-only
    name: Detailed analysis
    description: Needs detailed access.
    default_prompt: Show the detailed analysis.
    requires_detailed_access: true
  - id: assay-only
    name: Assay analysis
    description: Needs assay data.
    default_prompt: Show the assay analysis.
    requires_assays: true
  - id: single-dataset-only
    name: Single dataset analysis
    description: Needs one dataset.
    default_prompt: Run the single dataset analysis.
    requires_single_dataset_workspace: true
""".strip(),
        encoding="utf-8",
    )
    write_json(tmp_path, "records.json", [{"id": "P1:baseline", "patient_id": "P1"}])

    payload = analysis_catalog_module.analysis_catalog_payload(
        str(tmp_path),
        granularity_ceiling="summary",
        ai_provider_access="safe_summary",
        workspace_dataset_count=2,
        path=catalog_path,
    )

    assert payload["workspace"]["granularity_ceiling"] == "summary"
    assert payload["workspace"]["ai_provider_access"] == "safe_summary"
    items = {item["id"]: item for item in payload["items"]}
    assert items["detailed-only"]["available"] is False
    assert "Detailed" in items["detailed-only"]["unavailable_reason"]
    assert items["assay-only"]["available"] is False
    assert "assays" in items["assay-only"]["unavailable_reason"]
    assert items["single-dataset-only"]["available"] is False
    assert "exactly one dataset" in items["single-dataset-only"]["unavailable_reason"]


def test_analysis_catalog_route_uses_workspace_policy(tmp_path, monkeypatch):
    captured = {}

    monkeypatch.setattr(routes_module, "require_authenticated", lambda request: None)
    monkeypatch.setattr(routes_module, "resolve_dataset_ids", lambda request, dataset_id="": ["default"])
    monkeypatch.setattr(routes_module, "resolve_dataset_dir", lambda request, dataset_id="": str(tmp_path))
    monkeypatch.setattr(routes_module, "effective_query_granularity_ceiling", lambda dataset_ids: "summary")
    monkeypatch.setattr(routes_module, "effective_ai_provider_access", lambda dataset_ids: "safe_summary")
    monkeypatch.setattr(routes_module, "lm_provider_data_boundary", lambda provider_id=None: "local")

    def fake_catalog_payload(
        data_dir,
        *,
        granularity_ceiling="detailed",
        ai_provider_access="detailed_allowed",
        workspace_dataset_count=1,
        path=None,
    ):
        captured["data_dir"] = data_dir
        captured["granularity_ceiling"] = granularity_ceiling
        captured["ai_provider_access"] = ai_provider_access
        captured["workspace_dataset_count"] = workspace_dataset_count
        return {"items": [], "workspace": {"granularity_ceiling": granularity_ceiling}}

    monkeypatch.setattr(routes_module, "analysis_catalog_payload", fake_catalog_payload)

    request = Request({"type": "http", "headers": []})
    payload = routes_module.get_analysis_catalog(request, dataset_id="default")

    assert captured == {
        "data_dir": str(tmp_path),
        "granularity_ceiling": "summary",
        "ai_provider_access": "safe_summary",
        "workspace_dataset_count": 1,
    }
    assert payload["workspace"]["granularity_ceiling"] == "summary"


def test_analysis_external_methylation_qc_reads_manifest_matrix_without_copying_it(tmp_path):
    if shutil.which("Rscript") is None:
        pytest.skip("Rscript is not available")
    matrix_path = _write_synthetic_methylation_runner_fixture(tmp_path)
    job_dir = tmp_path / "methylation-qc-job"

    payload = analysis_external_module.run_rscript_analysis(
        "methylation_qc_pca",
        prompt="Run methylation QC and PCA for the selected assay.",
        data_dir=str(tmp_path),
        assay_id="synthetic_methylation_m_values",
        selected_patient_ids="METH001,METH002,METH003",
        compare_selected_patient_ids="METH004,METH005,METH006",
        job_dir=job_dir,
        timeout_seconds=60,
    )

    assert payload["data"]["context"]["mode"] == "external_rscript_methylation_qc_pca"
    assert payload["data"]["context"]["observed_feature_count"] == 6
    assert payload["data"]["context"]["pca_feature_count"] == 6
    assert payload["data"]["context"]["sample_count"] == 6
    assert payload["data"]["context"]["association_scope"] == "exploratory_one_covariate_at_a_time_bh_adjusted"
    assert "strongest_covariate_adj_p_value" in payload["data"]["context"]
    assert payload["data"]["context"]["r_version"].startswith("R version")
    association_header = (job_dir / "pca_covariate_associations.tsv").read_text(encoding="utf-8").splitlines()[0]
    assert association_header.endswith("\tadj_p_value")
    assert payload["data"]["context"]["source_matrix_materialized_in_duckdb"] is False
    assert (job_dir / "sample_qc.tsv").is_file()
    assert (job_dir / "pca_scores.tsv").is_file()
    assert (job_dir / "pca_variance.tsv").is_file()
    assert (job_dir / "pca_covariate_associations.tsv").is_file()
    assert (job_dir / "pca_plot.png").is_file()
    assert not (job_dir / "m_values.tsv").exists()
    assert not (job_dir / matrix_path.name).exists()
    command_text = (job_dir / "command.txt").read_text(encoding="utf-8")
    assert "[protected assay matrix]" in command_text
    assert str(matrix_path) not in command_text
    assert str(job_dir) not in command_text
    assert str(matrix_path) not in json.dumps(payload)
    assert str(job_dir) not in json.dumps(payload["data"]["runner_command"])


def test_analysis_external_methylation_qc_accepts_quoted_semicolon_header(tmp_path):
    if shutil.which("Rscript") is None:
        pytest.skip("Rscript is not available")
    matrix_path = _write_synthetic_methylation_runner_fixture(tmp_path)
    lines = matrix_path.read_text(encoding="utf-8").splitlines()
    header_values = lines[0].split(";")
    lines[0] = ";".join(['"feature;identifier"', *[f'"{value}"' for value in header_values[1:]]])
    matrix_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    payload = analysis_external_module.run_rscript_analysis(
        "methylation_qc_pca",
        prompt="Run methylation QC and PCA for the quoted-header assay.",
        data_dir=str(tmp_path),
        assay_id="synthetic_methylation_m_values",
        job_dir=tmp_path / "quoted-methylation-qc-job",
        timeout_seconds=60,
    )

    assert payload["data"]["context"]["observed_feature_count"] == 6
    assert payload["data"]["context"]["sample_count"] == 6


def test_analysis_external_methylation_limma_uses_declared_covariates(tmp_path):
    if shutil.which("Rscript") is None:
        pytest.skip("Rscript is not available")
    try:
        has_limma = subprocess.run(
            ["Rscript", "-e", "quit(status=ifelse(requireNamespace('limma', quietly=TRUE), 0, 1))"],
            check=False,
            capture_output=True,
            timeout=20,
        ).returncode == 0
    except (OSError, subprocess.SubprocessError):
        has_limma = False
    if not has_limma:
        pytest.skip("limma is not available")
    matrix_path = _write_synthetic_methylation_runner_fixture(tmp_path)
    job_dir = tmp_path / "methylation-limma-job"

    payload = analysis_external_module.run_rscript_analysis(
        "methylation_limma_differential_methylation",
        prompt="Run limma differential methylation between Cohort A and Cohort B.",
        data_dir=str(tmp_path),
        assay_id="synthetic_methylation_m_values",
        selected_patient_ids="METH001,METH002,METH003",
        compare_selected_patient_ids="METH004,METH005,METH006",
        job_dir=job_dir,
        timeout_seconds=60,
    )

    context = payload["data"]["context"]
    assert context["mode"] == "external_rscript_methylation_limma_differential_methylation"
    assert context["observed_feature_count"] == 6
    assert context["analyzed_feature_count"] == 6
    assert context["plotted_point_count"] == 6
    assert context["volcano_point_limit"] == 50_000
    assert context["covariates_used"] == ["age", "plate"]
    assert context["analysis_covariate_types"] == {"age": "numeric", "plate": "categorical"}
    assert "age" in context["design_columns"]
    assert "plate102" in context["design_columns"]
    assert context["contrast"] == "Cohort A - Cohort B"
    assert context["source_matrix_materialized_in_duckdb"] is False
    assert context["adjustment_status"] == "covariate_adjusted"
    assert context["r_version"].startswith("R version")
    assert context["limma_version"]
    assert context["clinical_linkage_status"] == "complete_selected_scope"
    assert (job_dir / "dm_results.tsv").is_file()
    assert (job_dir / "volcano_points.tsv").is_file()
    assert (job_dir / "volcano_plot.png").is_file()
    assert str(matrix_path) not in (job_dir / "command.txt").read_text(encoding="utf-8")
    assert str(job_dir) not in (job_dir / "command.txt").read_text(encoding="utf-8")
    assert str(matrix_path) not in json.dumps(payload)


def test_analysis_external_methylation_limma_marks_unadjusted_run_exploratory(tmp_path):
    if shutil.which("Rscript") is None:
        pytest.skip("Rscript is not available")
    try:
        has_limma = subprocess.run(
            ["Rscript", "-e", "quit(status=ifelse(requireNamespace('limma', quietly=TRUE), 0, 1))"],
            check=False,
            capture_output=True,
            timeout=20,
        ).returncode == 0
    except (OSError, subprocess.SubprocessError):
        has_limma = False
    if not has_limma:
        pytest.skip("limma is not available")
    _write_synthetic_methylation_runner_fixture(tmp_path)
    manifest_path = tmp_path / "assays" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["assays"][0]["analysis_covariates"] = []
    manifest["assays"][0]["analysis_covariate_types"] = {}
    manifest["assays"][0]["sha256"] = "synthetic-declared-fingerprint"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    payload = analysis_external_module.run_rscript_analysis(
        "methylation_limma_differential_methylation",
        prompt="Run exploratory limma differential methylation.",
        data_dir=str(tmp_path),
        assay_id="synthetic_methylation_m_values",
        selected_patient_ids="METH001,METH002,METH003",
        compare_selected_patient_ids="METH004,METH005,METH006",
        job_dir=tmp_path / "methylation-unadjusted-job",
        timeout_seconds=60,
    )

    context = payload["data"]["context"]
    assert context["adjustment_status"] == "unadjusted_exploratory"
    assert "unadjusted and exploratory" in payload["reply"]
    assert context["source_fingerprint_status"] == "declared_not_recomputed"
    assert context["source_fingerprint_verified_for_run"] is False
    assert context["source_sha256"] == "synthetic-declared-fingerprint"
    params = (tmp_path / "methylation-unadjusted-job" / "params.yaml").read_text(encoding="utf-8")
    assert "adjustment_status: unadjusted_exploratory" in params
    assert "source_fingerprint_status: declared_not_recomputed" in params


def test_analysis_external_snakemake_sync_reads_result_before_tempdir_cleanup(tmp_path, monkeypatch):
    write_json(tmp_path, "records.json", [{"id": "P1:baseline", "patient_id": "P1"}])
    monkeypatch.setattr(
        analysis_external_module.shutil,
        "which",
        lambda name: "/usr/bin/snakemake" if name == "snakemake" else None,
    )

    def fake_run(command, **kwargs):
        result_arg = next(item for item in command if str(item).startswith("result_json="))
        summary_arg = next(item for item in command if str(item).startswith("summary_txt="))
        result_path = Path(str(result_arg).split("=", 1)[1])
        summary_path = Path(str(summary_arg).split("=", 1)[1])
        result_path.write_text(
            json.dumps(
                {
                    "reply": "Snakemake sync workflow completed.",
                    "context": {"mode": "external_snakemake_dummy"},
                }
            ),
            encoding="utf-8",
        )
        summary_path.write_text("dummy summary\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="snakemake ok\n", stderr="")

    monkeypatch.setattr(analysis_external_module.subprocess, "run", fake_run)

    payload = analysis_external_module.run_snakemake_analysis(
        "dummy_queue_demo",
        prompt="Run the external Snakemake demo for the current Analysis scope.",
        data_dir=str(tmp_path),
        selected_patient_ids="P1",
        timeout_seconds=60,
    )

    assert payload["reply"] == "Snakemake sync workflow completed."
    assert payload["data"]["runner_type"] == "snakemake"


def test_analysis_survival_compare_kaplan_meier(tmp_path):
    write_json(
        tmp_path,
        "records.json",
        [
            {
                "id": "A1:week0",
                "event_date": "2024-01-01",
                "measures": [{"assayCode": {"label": "Hemoglobin"}, "measurementValue": {"quantity": {"value": 12.0}}}],
            },
            {
                "id": "A1:week2",
                "event_date": "2024-01-10",
                "measures": [{"assayCode": {"label": "Hemoglobin"}, "measurementValue": {"quantity": {"value": 10.4}}}],
            },
            {
                "id": "A2:week0",
                "event_date": "2024-01-02",
                "measures": [{"assayCode": {"label": "Hemoglobin"}, "measurementValue": {"quantity": {"value": 12.8}}}],
            },
            {
                "id": "A2:week2",
                "event_date": "2024-01-12",
                "measures": [{"assayCode": {"label": "Hemoglobin"}, "measurementValue": {"quantity": {"value": 12.1}}}],
            },
            {
                "id": "B1:week0",
                "event_date": "2024-01-01",
                "measures": [{"assayCode": {"label": "Hemoglobin"}, "measurementValue": {"quantity": {"value": 12.5}}}],
            },
            {
                "id": "B1:week2",
                "event_date": "2024-01-10",
                "measures": [{"assayCode": {"label": "Hemoglobin"}, "measurementValue": {"quantity": {"value": 12.1}}}],
            },
            {
                "id": "B2:week0",
                "event_date": "2024-01-03",
                "measures": [{"assayCode": {"label": "Hemoglobin"}, "measurementValue": {"quantity": {"value": 12.7}}}],
            },
            {
                "id": "B2:week2",
                "event_date": "2024-01-11",
                "measures": [{"assayCode": {"label": "Hemoglobin"}, "measurementValue": {"quantity": {"value": 12.0}}}],
            },
        ],
    )

    payload = analysis_module.analysis_llm_reply(
        "Compare Cohort A and Cohort B with Kaplan-Meier for time to Hemoglobin < 11",
        str(tmp_path),
        selected_patient_ids="A1,A2",
        compare_mode=True,
        compare_selected_patient_ids="B1,B2",
    )

    assert payload["intent"] == "analysis_survival_compare"
    context = payload["data"]["context"]
    assert context["mode"] == "survival_compare"
    assert context["cohort_a"]["event_count"] == 1
    assert context["cohort_b"]["event_count"] == 0


def test_analysis_survival_reports_unavailable_when_insufficient_dated_measure_data(tmp_path):
    write_json(
        tmp_path,
        "records.json",
        [
            {
                "id": "P1:week0",
                "event_date": "2024-01-01",
                "measures": [{"assayCode": {"label": "CRP"}, "measurementValue": {"quantity": {"value": 8.0}}}],
            },
            {
                "id": "P2:week0",
                "event_date": "1900-01-01",
                "measures": [{"assayCode": {"label": "CRP"}, "measurementValue": {"quantity": {"value": 11.0}}}],
            },
        ],
    )

    payload = analysis_module.analysis_llm_reply(
        "Show a Kaplan-Meier curve for time to CRP > 10",
        str(tmp_path),
    )

    assert payload["intent"] == "analysis_survival"
    context = payload["data"]["context"]
    assert context["mode"] == "survival"
    assert "Kaplan-Meier is unavailable" in context["error"]
    assert context["patient_count"] == 1


def test_analysis_trajectory_for_measure_over_time(tmp_path):
    write_json(
        tmp_path,
        "records.json",
        [
            {
                "id": "P1:week0",
                "event_date": "2024-01-01",
                "measures": [{"assayCode": {"label": "CRP"}, "measurementValue": {"quantity": {"value": 10.0}}}],
            },
            {
                "id": "P1:week2",
                "event_date": "2024-01-10",
                "measures": [{"assayCode": {"label": "CRP"}, "measurementValue": {"quantity": {"value": 6.0}}}],
            },
            {
                "id": "P2:week0",
                "event_date": "2024-01-01",
                "measures": [{"assayCode": {"label": "CRP"}, "measurementValue": {"quantity": {"value": 8.0}}}],
            },
            {
                "id": "P2:week2",
                "event_date": "2024-01-10",
                "measures": [{"assayCode": {"label": "CRP"}, "measurementValue": {"quantity": {"value": 4.0}}}],
            },
        ],
    )

    payload = analysis_module.analysis_llm_reply(
        "Show the trajectory of CRP over time",
        str(tmp_path),
    )

    assert payload["intent"] == "analysis_trajectory"
    context = payload["data"]["context"]
    assert context["mode"] == "trajectory"
    assert context["measure"] == "CRP"
    assert context["patient_count"] == 2
    assert len(context["summary_points"]) == 2


def test_analysis_lists_available_measures_for_current_scope(tmp_path):
    write_json(
        tmp_path,
        "records.json",
        [
            {
                "id": "P1:week0",
                "event_date": "2024-01-01",
                "measures": [
                    {"assayCode": {"label": "CRP"}, "measurementValue": {"quantity": {"value": 10.0, "unit": {"label": "mg/L"}}}},
                    {"assayCode": {"label": "Hemoglobin"}, "measurementValue": {"quantity": {"value": 12.0, "unit": {"label": "g/dL"}}}},
                ],
            },
            {
                "id": "P2:week0",
                "event_date": "2024-01-01",
                "measures": [
                    {"assayCode": {"label": "CRP"}, "measurementValue": {"quantity": {"value": 8.0, "unit": {"label": "mg/L"}}}},
                    {"assayCode": {"label": "Leukocyte Count"}, "measurementValue": {"quantity": {"value": 6.0, "unit": {"label": "10^9/L"}}}},
                ],
            },
        ],
    )

    payload = analysis_module.analysis_llm_reply(
        "What measures are available for this cohort?",
        str(tmp_path),
    )

    assert payload["intent"] == "analysis_measure_inventory"
    context = payload["data"]["context"]
    assert context["mode"] == "measure_inventory"
    assert [item["measure"] for item in context["measures"]] == ["CRP", "Hemoglobin", "Leukocyte Count"]


def test_analysis_lists_available_measures_for_compare_mode(tmp_path):
    write_json(
        tmp_path,
        "records.json",
        [
            {
                "id": "A1:week0",
                "event_date": "2024-01-01",
                "measures": [{"assayCode": {"label": "CRP"}, "measurementValue": {"quantity": {"value": 10.0}}}],
            },
            {
                "id": "A2:week0",
                "event_date": "2024-01-02",
                "measures": [{"assayCode": {"label": "Hemoglobin"}, "measurementValue": {"quantity": {"value": 12.0}}}],
            },
            {
                "id": "B1:week0",
                "event_date": "2024-01-01",
                "measures": [{"assayCode": {"label": "CRP"}, "measurementValue": {"quantity": {"value": 8.0}}}],
            },
            {
                "id": "B2:week0",
                "event_date": "2024-01-02",
                "measures": [{"assayCode": {"label": "Clinical relapse"}, "measurementValue": {"quantity": {"value": 0.0}}}],
            },
        ],
    )

    payload = analysis_module.analysis_llm_reply(
        "Which numeric longitudinal measures can I compare between these cohorts?",
        str(tmp_path),
        selected_patient_ids="A1,A2",
        compare_mode=True,
        compare_selected_patient_ids="B1,B2",
    )

    assert payload["intent"] == "analysis_measure_inventory_compare"
    context = payload["data"]["context"]
    assert context["mode"] == "measure_inventory_compare"
    assert context["measures"] == ["CRP", "Clinical relapse", "Hemoglobin"]


def test_analysis_treatment_response_trajectory(tmp_path):
    write_json(
        tmp_path,
        "records.json",
        [
            {
                "id": "P1:baseline",
                "event_date": "2024-01-01",
                "measures": [{"assayCode": {"label": "CRP"}, "measurementValue": {"quantity": {"value": 12.0}}}],
            },
            {
                "id": "P1:treat",
                "event_date": "2024-01-05",
                "treatments": [{"treatmentCode": {"label": "Infliximab"}}],
                "measures": [{"assayCode": {"label": "CRP"}, "measurementValue": {"quantity": {"value": 11.0}}}],
            },
            {
                "id": "P1:followup",
                "event_date": "2024-01-15",
                "measures": [{"assayCode": {"label": "CRP"}, "measurementValue": {"quantity": {"value": 5.0}}}],
            },
            {
                "id": "P2:baseline",
                "event_date": "2024-01-02",
                "measures": [{"assayCode": {"label": "CRP"}, "measurementValue": {"quantity": {"value": 14.0}}}],
            },
            {
                "id": "P2:treat",
                "event_date": "2024-01-06",
                "treatments": [{"treatmentCode": {"label": "Infliximab"}}],
                "measures": [{"assayCode": {"label": "CRP"}, "measurementValue": {"quantity": {"value": 13.0}}}],
            },
            {
                "id": "P2:followup",
                "event_date": "2024-01-16",
                "measures": [{"assayCode": {"label": "CRP"}, "measurementValue": {"quantity": {"value": 7.0}}}],
            },
        ],
    )

    payload = analysis_module.analysis_llm_reply(
        "Show response to Infliximab using CRP",
        str(tmp_path),
    )

    assert payload["intent"] == "analysis_trajectory"
    context = payload["data"]["context"]
    assert context["mode"] == "trajectory_response"
    assert context["treatment"] == "Infliximab"
    assert context["measure"] == "CRP"
    assert context["patient_count"] == 2


def test_analysis_treatment_response_trajectory_uses_requested_treatment(tmp_path):
    write_json(
        tmp_path,
        "records.json",
        [
            {
                "id": "P1:adalimumab",
                "event_date": "2024-01-03",
                "treatments": [{"treatmentCode": {"label": "Adalimumab"}}],
                "measures": [{"assayCode": {"label": "CRP"}, "measurementValue": {"quantity": {"value": 12.0}}}],
            },
            {
                "id": "P1:infliximab",
                "event_date": "2024-01-10",
                "treatments": [{"treatmentCode": {"label": "Infliximab"}}],
                "measures": [{"assayCode": {"label": "CRP"}, "measurementValue": {"quantity": {"value": 9.0}}}],
            },
            {
                "id": "P1:followup",
                "event_date": "2024-01-20",
                "measures": [{"assayCode": {"label": "CRP"}, "measurementValue": {"quantity": {"value": 4.0}}}],
            },
            {
                "id": "P2:adalimumab",
                "event_date": "2024-01-04",
                "treatments": [{"treatmentCode": {"label": "Adalimumab"}}],
                "measures": [{"assayCode": {"label": "CRP"}, "measurementValue": {"quantity": {"value": 10.0}}}],
            },
            {
                "id": "P2:infliximab",
                "event_date": "2024-01-12",
                "treatments": [{"treatmentCode": {"label": "Infliximab"}}],
                "measures": [{"assayCode": {"label": "CRP"}, "measurementValue": {"quantity": {"value": 8.0}}}],
            },
            {
                "id": "P2:followup",
                "event_date": "2024-01-22",
                "measures": [{"assayCode": {"label": "CRP"}, "measurementValue": {"quantity": {"value": 5.0}}}],
            },
        ],
    )

    payload = analysis_module.analysis_llm_reply(
        "Show response to Infliximab using CRP",
        str(tmp_path),
    )

    assert payload["intent"] == "analysis_trajectory"
    context = payload["data"]["context"]
    assert context["mode"] == "trajectory_response"
    assert context["treatment"] == "Infliximab"
    assert context["summary_points"][0]["x"] == 0
    assert context["summary_points"][-1]["x"] == 10


def test_analysis_compare_trajectory(tmp_path):
    write_json(
        tmp_path,
        "records.json",
        [
            {
                "id": "A1:week0",
                "event_date": "2024-01-01",
                "measures": [{"assayCode": {"label": "Leukocyte Count"}, "measurementValue": {"quantity": {"value": 12.0}}}],
            },
            {
                "id": "A1:week2",
                "event_date": "2024-01-15",
                "measures": [{"assayCode": {"label": "Leukocyte Count"}, "measurementValue": {"quantity": {"value": 8.0}}}],
            },
            {
                "id": "A2:week0",
                "event_date": "2024-01-02",
                "measures": [{"assayCode": {"label": "Leukocyte Count"}, "measurementValue": {"quantity": {"value": 11.0}}}],
            },
            {
                "id": "A2:week2",
                "event_date": "2024-01-16",
                "measures": [{"assayCode": {"label": "Leukocyte Count"}, "measurementValue": {"quantity": {"value": 7.0}}}],
            },
            {
                "id": "B1:week0",
                "event_date": "2024-01-01",
                "measures": [{"assayCode": {"label": "Leukocyte Count"}, "measurementValue": {"quantity": {"value": 9.0}}}],
            },
            {
                "id": "B1:week2",
                "event_date": "2024-01-15",
                "measures": [{"assayCode": {"label": "Leukocyte Count"}, "measurementValue": {"quantity": {"value": 10.0}}}],
            },
            {
                "id": "B2:week0",
                "event_date": "2024-01-02",
                "measures": [{"assayCode": {"label": "Leukocyte Count"}, "measurementValue": {"quantity": {"value": 8.0}}}],
            },
            {
                "id": "B2:week2",
                "event_date": "2024-01-16",
                "measures": [{"assayCode": {"label": "Leukocyte Count"}, "measurementValue": {"quantity": {"value": 9.0}}}],
            },
        ],
    )

    payload = analysis_module.analysis_llm_reply(
        "Compare Cohort A and Cohort B by Leukocyte Count trajectories",
        str(tmp_path),
        selected_patient_ids="A1,A2",
        compare_mode=True,
        compare_selected_patient_ids="B1,B2",
    )

    assert payload["intent"] == "analysis_trajectory_compare"
    context = payload["data"]["context"]
    assert context["mode"] == "trajectory_compare"
    assert context["measure"] == "Leukocyte Count"
    assert context["cohort_a"]["patient_count"] == 2
    assert context["cohort_b"]["patient_count"] == 2


def test_analysis_uses_semantic_planner_for_broad_trajectory_prompt(tmp_path, monkeypatch):
    write_json(
        tmp_path,
        "records.json",
        [
            {
                "id": "P1:baseline",
                "event_date": "2024-01-01",
                "treatments": [{"treatmentCode": {"label": "Infliximab"}}],
                "measures": [{"assayCode": {"label": "CRP"}, "measurementValue": {"quantity": {"value": 10.0}}}],
            },
            {
                "id": "P1:followup",
                "event_date": "2024-01-15",
                "measures": [{"assayCode": {"label": "CRP"}, "measurementValue": {"quantity": {"value": 5.0}}}],
            },
            {
                "id": "P2:baseline",
                "event_date": "2024-01-02",
                "treatments": [{"treatmentCode": {"label": "Infliximab"}}],
                "measures": [{"assayCode": {"label": "CRP"}, "measurementValue": {"quantity": {"value": 12.0}}}],
            },
            {
                "id": "P2:followup",
                "event_date": "2024-01-16",
                "measures": [{"assayCode": {"label": "CRP"}, "measurementValue": {"quantity": {"value": 7.0}}}],
            },
        ],
    )

    monkeypatch.setenv("LM_STUDIO_ENABLED", "true")
    monkeypatch.setenv("LM_STUDIO_MODEL", "local-model")

    calls = []

    def fake_http_json(url, payload=None, log_kind="generic"):
        if url.endswith("/models"):
            return {"data": [{"id": "local-model"}]}
        calls.append(log_kind)
        if log_kind == "analysis_planner":
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "intent": "analysis_plan",
                                    "analysis_type": "trajectory",
                                    "measure_query": "CRP",
                                    "treatment_query": "Infliximab",
                                }
                            )
                        }
                    }
                ]
            }
        return {"choices": [{"message": {"content": "Narrative analysis"}}]}

    monkeypatch.setattr(analysis_module, "http_json", fake_http_json)

    payload = analysis_module.analysis_llm_reply(
        "Analyze CRP response after infliximab",
        str(tmp_path),
    )

    assert payload["intent"] == "analysis_trajectory"
    assert payload["data"]["execution"] == "deterministic"
    assert payload["data"]["planner"]["model"] == "local-model"
    assert payload["data"]["context"]["mode"] == "trajectory_response"
    assert calls == ["analysis_planner"]


def test_analysis_falls_back_to_llm_narrative_when_planner_is_unsupported(tmp_path, monkeypatch):
    write_json(
        tmp_path,
        "records.json",
        [
            {
                "id": "P1:baseline",
                "event_date": "2024-01-01",
                "measures": [{"assayCode": {"label": "CRP"}, "measurementValue": {"quantity": {"value": 10.0}}}],
            }
        ],
    )

    monkeypatch.setenv("LM_STUDIO_ENABLED", "true")
    monkeypatch.setenv("LM_STUDIO_MODEL", "local-model")

    calls = []

    def fake_http_json(url, payload=None, log_kind="generic"):
        if url.endswith("/models"):
            return {"data": [{"id": "local-model"}]}
        calls.append(log_kind)
        if log_kind == "analysis_planner":
            return {"choices": [{"message": {"content": "{\"intent\":\"unsupported\"}"}}]}
        return {"choices": [{"message": {"content": "Narrative analysis"}}]}

    monkeypatch.setattr(analysis_module, "http_json", fake_http_json)

    payload = analysis_module.analysis_llm_reply(
        "What should I inspect next in this cohort?",
        str(tmp_path),
    )

    assert payload["intent"] == "analysis_llm"
    assert payload["reply"] == "Narrative analysis"
    assert calls == ["analysis_planner", "analysis_llm"]


def test_analysis_llm_only_skips_planner(tmp_path, monkeypatch):
    write_json(
        tmp_path,
        "records.json",
        [
            {
                "id": "P1:baseline",
                "event_date": "2024-01-01",
                "measures": [{"assayCode": {"label": "CRP"}, "measurementValue": {"quantity": {"value": 10.0}}}],
            }
        ],
    )

    monkeypatch.setenv("LM_STUDIO_ENABLED", "true")
    monkeypatch.setenv("LM_STUDIO_MODEL", "local-model")

    calls = []

    def fake_http_json(url, payload=None, log_kind="generic"):
        calls.append(log_kind)
        return {"choices": [{"message": {"content": "Narrative analysis"}}]}

    monkeypatch.setattr(analysis_module, "http_json", fake_http_json)

    payload = analysis_module.analysis_llm_reply(
        "Compare Cohort A and Cohort B like a clinical reviewer and summarize the main similarities, differences, and uncertainties.",
        str(tmp_path),
        llm_only=True,
    )

    assert payload["intent"] == "analysis_llm"
    assert payload["reply"] == "Narrative analysis"
    assert calls == ["analysis_llm"]


def test_analysis_llm_only_skips_matching_deterministic_router(tmp_path, monkeypatch):
    write_json(
        tmp_path,
        "records.json",
        [
            {
                "id": "P1:baseline",
                "event_date": "2024-01-01",
                "measures": [{"assayCode": {"label": "CRP"}, "measurementValue": {"quantity": {"value": 10.0}}}],
            }
        ],
    )

    monkeypatch.setenv("LM_STUDIO_ENABLED", "true")
    monkeypatch.setenv("LM_STUDIO_MODEL", "local-model")
    calls = []

    def fake_http_json(url, payload=None, log_kind="generic"):
        calls.append(log_kind)
        return {"choices": [{"message": {"content": "LLM interpretation"}}]}

    monkeypatch.setattr(analysis_module, "http_json", fake_http_json)

    payload = analysis_module.analysis_llm_reply(
        "Show response to Infliximab using CRP",
        str(tmp_path),
        llm_only=True,
    )

    assert payload["intent"] == "analysis_llm"
    assert payload["reply"] == "LLM interpretation"
    assert payload["data"]["source"] == "llm"
    assert calls == ["analysis_llm"]


def test_analysis_deterministic_only_skips_planner_and_full_llm(tmp_path, monkeypatch):
    write_json(
        tmp_path,
        "records.json",
        [
            {
                "id": "P1:baseline",
                "event_date": "2024-01-01",
                "diseases": [{"diseaseCode": {"label": "Crohn Disease"}}],
                "treatments": [{"treatmentCode": {"label": "Infliximab"}}],
            }
        ],
    )

    monkeypatch.setenv("LM_STUDIO_ENABLED", "true")
    monkeypatch.setenv("LM_STUDIO_MODEL", "local-model")

    calls = []

    def fake_http_json(url, payload=None, log_kind="generic"):
        calls.append(log_kind)
        return {"choices": [{"message": {"content": "Narrative analysis"}}]}

    monkeypatch.setattr(analysis_module, "http_json", fake_http_json)

    payload = analysis_module.analysis_llm_reply(
        "Summarize the main clinical patterns in this cohort and tell me what stands out.",
        str(tmp_path),
        deterministic_only=True,
    )

    assert payload["intent"] == "analysis_deterministic"
    assert payload["data"]["source"] == "deterministic"
    assert "Deterministic Workspace Summary" in payload["reply"]
    assert calls == []


def test_analysis_ai_provider_blocked_skips_planner_and_llm(tmp_path, monkeypatch):
    write_json(
        tmp_path,
        "records.json",
        [
            {
                "id": "P1:baseline",
                "event_date": "2024-01-01",
                "diseases": [{"diseaseCode": {"label": "Crohn Disease"}}],
                "treatments": [{"treatmentCode": {"label": "Infliximab"}}],
            }
        ],
    )

    monkeypatch.setenv("LM_STUDIO_ENABLED", "true")
    monkeypatch.setenv("LM_STUDIO_MODEL", "local-model")

    calls = []

    def fake_http_json(url, payload=None, log_kind="generic"):
        calls.append(log_kind)
        return {"choices": [{"message": {"content": "Narrative analysis"}}]}

    monkeypatch.setattr(analysis_module, "http_json", fake_http_json)

    payload = analysis_module.analysis_llm_reply(
        "Summarize the main clinical patterns in this cohort and tell me what stands out.",
        str(tmp_path),
        ai_provider_access="blocked",
    )

    assert payload["intent"] == "analysis_deterministic"
    assert payload["data"]["source"] == "deterministic"
    assert payload["data"]["ai_provider_access"] == "blocked"
    assert payload["data"]["ai_provider_context_granularity"] == "blocked"
    assert calls == []


def test_analysis_ai_provider_restricted_skips_planner_and_sends_no_clinical_context(tmp_path, monkeypatch):
    write_json(
        tmp_path,
        "records.json",
        [
            {
                "id": "P1:baseline",
                "event_date": "2024-01-01",
                "diseases": [{"diseaseCode": {"label": "Crohn Disease"}}],
                "treatments": [{"treatmentCode": {"label": "Infliximab"}}],
            }
        ],
    )

    monkeypatch.setenv("LM_STUDIO_ENABLED", "true")
    monkeypatch.setenv("LM_STUDIO_MODEL", "local-model")

    captured = {}
    calls = []

    def fake_http_json(url, payload=None, log_kind="generic"):
        calls.append(log_kind)
        captured["payload"] = payload
        return {"choices": [{"message": {"content": "I do not have enough permitted context to answer that safely."}}]}

    monkeypatch.setattr(analysis_module, "http_json", fake_http_json)

    payload = analysis_module.analysis_llm_reply(
        "Explain this cohort.",
        str(tmp_path),
        ai_provider_access="safe_summary",
    )

    assert payload["intent"] == "analysis_llm"
    assert payload["reply"] == "I do not have enough permitted context to answer that safely."
    assert payload["data"]["source"] == "llm"
    assert payload["data"]["ai_provider_access"] == "safe_summary"
    assert payload["data"]["ai_provider_context_granularity"] == "safe_summary"
    assert calls == ["analysis_llm"]
    user_message = captured["payload"]["messages"][1]["content"]
    assert "Crohn Disease" not in user_message
    assert "Infliximab" not in user_message
    assert "patient_count" not in user_message


def test_analysis_llm_only_safe_summary_does_not_fall_back_to_deterministic_on_provider_error(tmp_path, monkeypatch):
    write_json(
        tmp_path,
        "records.json",
        [
            {
                "id": "P1:baseline",
                "event_date": "2025-01-10",
                "diseases": [{"diseaseCode": {"label": "Multiple Sclerosis"}}],
                "treatments": [{"treatmentCode": {"label": "Ocrelizumab"}}],
            }
        ],
    )

    monkeypatch.setenv("LM_STUDIO_ENABLED", "true")
    monkeypatch.setenv("LM_STUDIO_MODEL", "local-model")

    def fake_http_json(url, payload=None, log_kind="generic"):
        raise RuntimeError("LM Studio offline")

    monkeypatch.setattr(analysis_module, "http_json", fake_http_json)

    payload = analysis_module.analysis_llm_reply(
        "Write a concise workspace briefing for a clinician, including what stands out and what needs validation.",
        str(tmp_path),
        llm_only=True,
        ai_provider_access="safe_summary",
        granularity_ceiling="summary",
    )

    assert payload["intent"] == "analysis_llm"
    assert payload["data"]["source"] == "provider_unavailable"
    assert payload["data"]["model"] is None
    assert "Deterministic Workspace Summary" not in payload["reply"]
    assert "requires an AI provider" in payload["reply"]


def test_analysis_llm_only_blocked_returns_policy_response(tmp_path):
    write_json(
        tmp_path,
        "records.json",
        [
            {
                "id": "P1:baseline",
                "event_date": "2025-01-10",
                "diseases": [{"diseaseCode": {"label": "Multiple Sclerosis"}}],
                "treatments": [{"treatmentCode": {"label": "Ocrelizumab"}}],
            }
        ],
    )

    payload = analysis_module.analysis_llm_reply(
        "Interpret the disease and medication profiles in this workspace and summarize the main themes.",
        str(tmp_path),
        llm_only=True,
        ai_provider_access="blocked",
        granularity_ceiling="summary",
    )

    assert payload["intent"] == "analysis_llm"
    assert payload["data"]["source"] == "policy"
    assert payload["data"]["model"] is None
    assert "Deterministic Workspace Summary" not in payload["reply"]
    assert "AI provider access is blocked" in payload["reply"]


def test_analysis_summary_ceiling_omits_scope_ids_from_semantic_planner_payload(tmp_path, monkeypatch):
    write_json(
        tmp_path,
        "records.json",
        [
            {
                "id": "P1:baseline",
                "event_date": "2024-01-01",
                "treatments": [{"treatmentCode": {"label": "Infliximab"}}],
                "measures": [{"assayCode": {"label": "CRP"}, "measurementValue": {"quantity": {"value": 10.0}}}],
            },
            {
                "id": "P2:baseline",
                "event_date": "2024-01-02",
                "treatments": [{"treatmentCode": {"label": "Infliximab"}}],
                "measures": [{"assayCode": {"label": "CRP"}, "measurementValue": {"quantity": {"value": 12.0}}}],
            },
        ],
    )

    monkeypatch.setenv("LM_STUDIO_ENABLED", "true")
    monkeypatch.setenv("LM_STUDIO_MODEL", "local-model")

    captured = {}

    def fake_http_json(url, payload=None, log_kind="generic"):
        if log_kind == "analysis_planner":
            captured["payload"] = payload
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "intent": "analysis_plan",
                                    "analysis_type": "summary",
                                }
                            )
                        }
                    }
                ]
            }
        return {"choices": [{"message": {"content": "Narrative analysis"}}]}

    monkeypatch.setattr(analysis_module, "http_json", fake_http_json)

    payload = analysis_module.analysis_llm_reply(
        "Summarize the main clinical patterns in this cohort and tell me what stands out.",
        str(tmp_path),
        selected_patient_ids="P1,P2",
        granularity_ceiling="summary",
    )

    assert payload["intent"] == "analysis_deterministic"
    assert payload["data"]["execution"] == "deterministic"
    assert payload["data"]["planner"]["provider"] == "lm_studio"
    assert payload["data"]["granularity_applied"] == "summary"
    planner_message = captured["payload"]["messages"][1]["content"]
    assert '"selected_patient_ids": []' in planner_message
    assert '"conversation_history": []' in planner_message
    assert "P1" not in planner_message
    assert "P2" not in planner_message


def test_analysis_supports_deterministic_transcriptomics_expression_prompt(tmp_path):
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
                "ENSG00002700028;100;120;140",
            ]
        ),
        encoding="utf-8",
    )
    query_store_module.ASSAY_DATA_DIR = transcriptomics_dir
    try:
        payload = analysis_module.analysis_llm_reply(
            "Show expression of ENSG00002700028 in the current Analysis scope.",
            str(tmp_path),
            selected_patient_ids="SYN001,SYN002",
        )
    finally:
        query_store_module.ASSAY_DATA_DIR = original_dir

    assert payload["intent"] == "analysis_transcriptomics_expression"
    assert payload["data"]["source"] == "deterministic"
    assert payload["data"]["context"]["mode"] == "transcriptomics_expression"
    assert payload["data"]["context"]["datasets"][0]["scope_a"]["sample_count"] == 2
    assert "ENSG00002700028 was found in 1 assay." in payload["reply"]
    assert "\n| Dataset | Samples | Patients | Mean | Median | Min | Max |\n" in payload["reply"]
    assert "| synthetic_transcriptome_raw_counts | 2 | 2 | 110 | 110 | 100 | 120 |" in payload["reply"]


def test_analysis_supports_deterministic_transcriptomics_expression_compare_prompt(tmp_path):
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
                "ENSG00002700028;100;120;140",
            ]
        ),
        encoding="utf-8",
    )
    query_store_module.ASSAY_DATA_DIR = transcriptomics_dir
    try:
        payload = analysis_module.analysis_llm_reply(
            "Compare expression of ENSG00002700028 between Cohort A and Cohort B.",
            str(tmp_path),
            selected_patient_ids="SYN001,SYN002",
            compare_mode=True,
            compare_selected_patient_ids="SYN003",
        )
    finally:
        query_store_module.ASSAY_DATA_DIR = original_dir

    assert payload["intent"] == "analysis_transcriptomics_expression"
    assert payload["data"]["context"]["compare_mode"] is True
    assert payload["data"]["context"]["datasets"][0]["scope_b"]["sample_count"] == 1
    assert "\n| Dataset | Scope | Samples | Patients | Mean | Median | Min | Max |\n" in payload["reply"]
    assert "| synthetic_transcriptome_raw_counts | Cohort A | 2 | 2 | 110 | 110 | 100 | 120 |" in payload["reply"]


def test_analysis_supports_deterministic_assay_medication_comparison(tmp_path):
    write_json(
        tmp_path,
        "records.json",
        [
            {"id": "SYN001:baseline", "event_date": "2024-01-01", "treatments": [{"treatmentCode": {"label": "Infliximab"}}]},
            {"id": "SYN002:baseline", "event_date": "2024-01-01", "treatments": [{"treatmentCode": {"label": "Infliximab"}}]},
            {"id": "SYN006:baseline", "event_date": "2024-01-01", "treatments": [{"treatmentCode": {"label": "Vedolizumab"}}]},
            {"id": "SYN007:baseline", "event_date": "2024-01-01", "treatments": [{"treatmentCode": {"label": "Vedolizumab"}}]},
        ],
    )

    original_dir = query_store_module.ASSAY_DATA_DIR
    transcriptomics_dir = tmp_path / "assays" / "transcriptomics"
    transcriptomics_dir.mkdir(parents=True)
    (transcriptomics_dir / "synthetic_transcriptome_raw_counts_infliximab.csv").write_text(
        "\n".join(
            [
                "gene_id;SYN001;SYN002",
                "ENSG00000169429;1400;1300",
                "ENSG00000170421;150;160",
            ]
        ),
        encoding="utf-8",
    )
    (transcriptomics_dir / "synthetic_transcriptome_raw_counts_vedolizumab.csv").write_text(
        "\n".join(
            [
                "gene_id;SYN006;SYN007",
                "ENSG00000169429;150;160",
                "ENSG00000170421;1200;1250",
            ]
        ),
        encoding="utf-8",
    )
    query_store_module.ASSAY_DATA_DIR = transcriptomics_dir
    try:
        payload = analysis_module.analysis_llm_reply(
            "Explain differences in gene expression according to medication",
            str(tmp_path),
        )
    finally:
        query_store_module.ASSAY_DATA_DIR = original_dir

    assert payload["intent"] == "analysis_transcriptomics_medication_compare"
    assert payload["data"]["context"]["mode"] == "transcriptomics_medication_compare"
    assert payload["data"]["context"]["comparisons"][0]["medication_a"] == "Infliximab"
    assert payload["data"]["context"]["comparisons"][0]["medication_b"] == "Vedolizumab"
    assert payload["data"]["context"]["exploratory_note"].startswith("Exploratory transcriptomics comparison")
    assert payload["data"]["context"]["comparisons"][0]["exploratory_volcano_points"]
    volcano_point = payload["data"]["context"]["comparisons"][0]["exploratory_volcano_points"][0]
    assert "gene_id" in volcano_point
    assert "log2_fold_change" in volcano_point
    assert "neg_log10_p" in volcano_point
    assert "largest expression difference is ENSG00000169429" in payload["reply"]
    assert "preliminary and not DESeq2-grade differential expression" in payload["reply"]


def test_analysis_assay_medication_comparison_respects_scope(tmp_path):
    write_json(
        tmp_path,
        "records.json",
        [
            {"id": "SYN001:baseline", "patient_id": "SYN001", "info": {"event_date": "2024-01-01"}, "treatments": [{"treatmentCode": {"label": "Infliximab"}}]},
            {"id": "SYN002:baseline", "patient_id": "SYN002", "info": {"event_date": "2024-01-01"}, "treatments": [{"treatmentCode": {"label": "Infliximab"}}]},
            {"id": "SYN006:baseline", "patient_id": "SYN006", "info": {"event_date": "2024-01-01"}, "treatments": [{"treatmentCode": {"label": "Vedolizumab"}}]},
            {"id": "SYN007:baseline", "patient_id": "SYN007", "info": {"event_date": "2024-01-01"}, "treatments": [{"treatmentCode": {"label": "Vedolizumab"}}]},
        ],
    )

    original_dir = query_store_module.ASSAY_DATA_DIR
    transcriptomics_dir = tmp_path / "assays" / "transcriptomics"
    transcriptomics_dir.mkdir(parents=True)
    (transcriptomics_dir / "synthetic_transcriptome_raw_counts_infliximab.csv").write_text(
        "\n".join(
            [
                "gene_id;SYN001;SYN002",
                "ENSG00000169429;1400;400",
                "ENSG00000170421;150;160",
            ]
        ),
        encoding="utf-8",
    )
    (transcriptomics_dir / "synthetic_transcriptome_raw_counts_vedolizumab.csv").write_text(
        "\n".join(
            [
                "gene_id;SYN006;SYN007",
                "ENSG00000169429;150;900",
                "ENSG00000170421;1200;1250",
            ]
        ),
        encoding="utf-8",
    )
    query_store_module.ASSAY_DATA_DIR = transcriptomics_dir
    try:
        payload = analysis_module.analysis_llm_reply(
            "Explain differences in gene expression according to medication",
            str(tmp_path),
            selected_patient_ids="SYN001,SYN006",
        )
    finally:
        query_store_module.ASSAY_DATA_DIR = original_dir

    assert payload["intent"] == "analysis_transcriptomics_medication_compare"
    context = payload["data"]["context"]
    assert context["scope_patient_count"] == 2
    comparison = context["comparisons"][0]
    assert comparison["scoped_patient_ids_a"] == ["SYN001"]
    assert comparison["scoped_patient_ids_b"] == ["SYN006"]
    volcano_point = comparison["exploratory_volcano_points"][0]
    assert volcano_point["sample_count_a"] == 1
    assert volcano_point["sample_count_b"] == 1


def test_analysis_assay_medication_comparison_derives_patient_scope_from_sample_ids(tmp_path):
    write_json(
        tmp_path,
        "records.json",
        [
            {"id": "SYN001:week_0", "patient_id": "SYN001", "info": {"event_date": "2024-01-01"}, "treatments": [{"treatmentCode": {"label": "Infliximab"}}]},
            {"id": "SYN002:week_0", "patient_id": "SYN002", "info": {"event_date": "2024-01-01"}, "treatments": [{"treatmentCode": {"label": "Infliximab"}}]},
            {"id": "SYN003:week_0", "patient_id": "SYN003", "info": {"event_date": "2024-01-01"}, "treatments": [{"treatmentCode": {"label": "Infliximab"}}]},
            {"id": "SYN004:week_0", "patient_id": "SYN004", "info": {"event_date": "2024-01-01"}, "treatments": [{"treatmentCode": {"label": "Ustekinumab"}}]},
            {"id": "SYN005:week_0", "patient_id": "SYN005", "info": {"event_date": "2024-01-01"}, "treatments": [{"treatmentCode": {"label": "Ustekinumab"}}]},
        ],
    )

    original_dir = query_store_module.ASSAY_DATA_DIR
    transcriptomics_dir = tmp_path / "assays" / "transcriptomics"
    transcriptomics_dir.mkdir(parents=True)
    (transcriptomics_dir / "synthetic_transcriptome_raw_counts_infliximab.csv").write_text(
        "\n".join(
            [
                "gene_id;SYN001:week_0;SYN002:week_0;SYN003:week_0",
                "ENSG00000169429;1400;1300;1200",
                "ENSG00000170421;150;160;170",
            ]
        ),
        encoding="utf-8",
    )
    (transcriptomics_dir / "synthetic_transcriptome_raw_counts_ustekinumab.csv").write_text(
        "\n".join(
            [
                "gene_id;SYN004:week_0;SYN005:week_0",
                "ENSG00000169429;150;160",
                "ENSG00000170421;1200;1250",
            ]
        ),
        encoding="utf-8",
    )
    query_store_module.ASSAY_DATA_DIR = transcriptomics_dir
    try:
        payload = analysis_module.analysis_llm_reply(
            "Explain differences in gene expression according to medication",
            str(tmp_path),
            selected_patient_ids="SYN001:week_0,SYN002:week_0,SYN003:week_0",
            compare_mode=True,
            compare_selected_patient_ids="SYN004:week_0,SYN005:week_0",
        )
    finally:
        query_store_module.ASSAY_DATA_DIR = original_dir

    assert payload["intent"] == "analysis_transcriptomics_medication_compare"
    context = payload["data"]["context"]
    assert context["scope_patient_count"] == 5
    comparison = context["comparisons"][0]
    assert comparison["medication_a"] == "Infliximab"
    assert comparison["medication_b"] == "Ustekinumab"
    assert comparison["scoped_patient_ids_a"] == ["SYN001", "SYN002", "SYN003"]
    assert comparison["scoped_patient_ids_b"] == ["SYN004", "SYN005"]


def test_analysis_compare_follow_up_prompt_does_not_raise_name_error(tmp_path):
    write_json(
        tmp_path,
        "records.json",
        [
            {
                "id": "SYN001:week_0",
                "patient_id": "SYN001",
                "event_date": "2024-01-01",
                "diseases": [{"diseaseCode": {"label": "Crohn Disease"}}],
                "treatments": [{"treatmentCode": {"label": "Infliximab"}}],
            },
            {
                "id": "SYN002:week_0",
                "patient_id": "SYN002",
                "event_date": "2024-01-08",
                "diseases": [{"diseaseCode": {"label": "Crohn Disease"}}],
                "treatments": [{"treatmentCode": {"label": "Infliximab"}}],
            },
            {
                "id": "SYN003:week_0",
                "patient_id": "SYN003",
                "event_date": "2024-01-01",
                "diseases": [{"diseaseCode": {"label": "Crohn Disease"}}],
                "treatments": [{"treatmentCode": {"label": "Ustekinumab"}}],
            },
            {
                "id": "SYN004:week_0",
                "patient_id": "SYN004",
                "event_date": "2024-01-08",
                "diseases": [{"diseaseCode": {"label": "Crohn Disease"}}],
                "treatments": [{"treatmentCode": {"label": "Ustekinumab"}}],
            },
        ],
    )

    payload = analysis_module.analysis_llm_reply(
        "Can you explain the plot?",
        str(tmp_path),
        selected_patient_ids="SYN001,SYN002",
        compare_mode=True,
        compare_selected_patient_ids="SYN003,SYN004",
        deterministic_only=True,
        history=[
            {"role": "user", "content": "Compare relapse-free survival between Cohort A and Cohort B."},
            {"role": "assistant", "content": "Kaplan-Meier comparison completed."},
        ],
    )

    assert payload["intent"] == "analysis_compare"
    assert payload["data"]["source"] == "deterministic"
    assert "Deterministic Comparison Summary" in payload["reply"]
