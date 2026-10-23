import json
from pathlib import Path
import pytest
from fastapi import HTTPException
from bff_test_helpers import isolate_query_store
from bff_test_helpers import write_json
import shutil
import subprocess
import app.analysis as analysis_module
import app.analysis_catalog as analysis_catalog_module
import app.analysis_external as analysis_external_module
import app.query_store as query_store_module
from bff_test_helpers import _write_synthetic_methylation_runner_fixture
from types import SimpleNamespace
import app.jobs as jobs_module
import app.pheno as pheno_module
from bff_test_helpers import _write_synthetic_quantitative_assay_runner_fixture


def test_pheno_cohort_graph_cutoffs_are_passed_to_runner(tmp_path, monkeypatch):
    reference_path = tmp_path / "reference.json"
    reference_path.write_text("[]", encoding="utf-8")
    fake_bin = tmp_path / "pheno-ranker"
    fake_bin.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_bin.chmod(0o755)
    job_dir = tmp_path / "runs" / "job"
    job_dir.mkdir(parents=True)

    monkeypatch.setattr(pheno_module, "PHENO_RANKER_BIN", fake_bin)
    monkeypatch.setattr(pheno_module, "pheno_ranker_job_dir", lambda: job_dir)
    monkeypatch.setattr(pheno_module, "resolve_pheno_ranker_reference_paths", lambda data_dir: [reference_path])

    executed_commands = []

    def _fake_run(command, capture_output, text, check, **kwargs):
        executed_commands.append(command)
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(pheno_module.subprocess, "run", _fake_run)

    payload = pheno_module.run_pheno_ranker(
        SimpleNamespace(
            action="compare",
            mode="cohort",
            data_dir=str(tmp_path),
            patient_id="",
            selected_patient_ids="",
            selected_saved_cohort_ids=[],
            disease_filter="",
            include_terms=[],
            exclude_terms=[],
            similarity_metric_cohort="jaccard",
            sort_by="",
            max_out=10,
            align=False,
            render_heatmap=False,
            render_mds=False,
            render_graph=True,
            graph_min_weight=0.25,
            graph_max_weight=0.95,
        )
    )

    assert executed_commands
    command = executed_commands[0]
    assert "-cytoscape-json" in command
    assert "-graph-stats" not in command
    assert "-graph-min-weight" in command
    assert command[command.index("-graph-min-weight") + 1] == "0.25"
    assert "-graph-max-weight" in command
    assert command[command.index("-graph-max-weight") + 1] == "0.95"
    assert payload["graph_min_weight"] == 0.25
    assert payload["graph_max_weight"] == 0.95


def test_pheno_runner_rejects_combined_include_and_exclude_terms(tmp_path, monkeypatch):
    reference_path = tmp_path / "reference.json"
    reference_path.write_text("[]", encoding="utf-8")
    fake_bin = tmp_path / "pheno-ranker"
    fake_bin.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_bin.chmod(0o755)

    monkeypatch.setattr(pheno_module, "PHENO_RANKER_BIN", fake_bin)
    monkeypatch.setattr(pheno_module, "resolve_pheno_ranker_reference_paths", lambda data_dir: [reference_path])

    executed_commands = []

    def _fake_run(command, capture_output, text, check, **kwargs):
        executed_commands.append(command)
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(pheno_module.subprocess, "run", _fake_run)

    with pytest.raises(HTTPException) as exc_info:
        pheno_module.run_pheno_ranker(
            SimpleNamespace(
                action="compare",
                mode="cohort",
                data_dir=str(tmp_path),
                patient_id="",
                selected_patient_ids="",
                selected_saved_cohort_ids=[],
                disease_filter="",
                include_terms=["diseases"],
                exclude_terms=["id"],
                similarity_metric_cohort="",
                sort_by="",
                max_out=10,
                align=False,
                render_heatmap=False,
                render_mds=False,
                render_graph=False,
            )
        )

    assert exc_info.value.status_code == 400
    assert "cannot combine include and exclude" in str(exc_info.value.detail)
    assert executed_commands == []


def test_analysis_catalog_loader_keeps_external_runner_metadata(tmp_path):
    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text(
        """
items:
  - id: external-r
    name: External R
    description: Demo.
    default_prompt: Run it.
    runner_type: rscript
    runner_ref: dummy_scope_snapshot
""".strip(),
        encoding="utf-8",
    )

    items = analysis_catalog_module.load_analysis_catalog(catalog_path)

    assert items[0]["runner_type"] == "rscript"
    assert items[0]["runner_ref"] == "dummy_scope_snapshot"
    assert items[0]["execution_backend"] == "sync"


def test_analysis_catalog_loader_accepts_workflow_runner_types(tmp_path):
    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text(
        """
items:
  - id: snakemake-demo
    name: Snakemake demo
    description: Demo.
    default_prompt: Run it.
    runner_type: snakemake
    runner_ref: dummy_queue_demo
    execution_backend: job
  - id: nextflow-demo
    name: Nextflow demo
    description: Demo.
    default_prompt: Run it.
    runner_type: nextflow
    runner_ref: dummy_queue_demo
    execution_backend: job
""".strip(),
        encoding="utf-8",
    )

    items = analysis_catalog_module.load_analysis_catalog(catalog_path)

    assert items[0]["runner_type"] == "snakemake"
    assert items[0]["execution_backend"] == "job"
    assert items[1]["runner_type"] == "nextflow"
    assert items[1]["execution_backend"] == "job"


def test_analysis_external_rscript_runner_executes_curated_catalog_item(tmp_path, monkeypatch):
    if shutil.which("Rscript") is None:
        pytest.skip("Rscript is not available")
    monkeypatch.setenv("COHORTOME_ANALYSIS_CATALOG_DEBUG", "true")

    write_json(
        tmp_path,
        "records.json",
        [
            {"id": "P1:baseline", "patient_id": "P1"},
            {"id": "P1:week4", "patient_id": "P1"},
            {"id": "P2:baseline", "patient_id": "P2"},
        ],
    )

    payload = analysis_module.analysis_llm_reply(
        "Run the external R cohort snapshot analysis for the current Analysis scope.",
        str(tmp_path),
        catalog_item_id="external-r-scope-snapshot",
        selected_patient_ids="P1",
    )

    assert payload["intent"] == "analysis_external_rscript"
    assert "External R scope snapshot" in payload["reply"]
    assert payload["data"]["execution"] == "external_runner"
    assert payload["data"]["runner_type"] == "rscript"
    assert payload["data"]["catalog_item_id"] == "external-r-scope-snapshot"
    assert payload["data"]["context"]["mode"] == "external_rscript"
    assert payload["data"]["context"]["scope_a_patient_count"] == 1


def test_analysis_external_rscript_clinical_profile_runner_executes(tmp_path):
    if shutil.which("Rscript") is None:
        pytest.skip("Rscript is not available")

    write_json(
        tmp_path,
        "records.json",
        [
            {
                "id": "P1:baseline",
                "event_date": "2025-01-10",
                "diseases": [{"diseaseCode": {"label": "Multiple Sclerosis"}}],
                "treatments": [{"treatmentCode": {"label": "Ocrelizumab"}}],
            },
            {
                "id": "P1:week4",
                "event_date": "2025-01-24",
                "diseases": [{"diseaseCode": {"label": "Multiple Sclerosis"}}],
                "treatments": [{"treatmentCode": {"label": "Ocrelizumab"}}],
            },
            {
                "id": "P2:baseline",
                "event_date": "2025-02-01",
                "diseases": [{"diseaseCode": {"label": "Healthy Control"}}],
                "treatments": [{"treatmentCode": {"label": "Mesalamine"}}],
            },
        ],
    )

    payload = analysis_external_module.run_rscript_analysis(
        "clinical_scope_profile",
        prompt="Run the external R clinical scope profile for the current Analysis scope.",
        data_dir=str(tmp_path),
        selected_patient_ids="P1",
    )

    assert payload["intent"] == "analysis_external_rscript"
    assert "External R clinical scope profile" in payload["reply"]
    assert "Cohort A top disease: Multiple Sclerosis" in payload["reply"]
    assert payload["data"]["execution"] == "external_runner"
    assert payload["data"]["runner_type"] == "rscript"
    assert payload["data"]["runner_ref"] == "clinical_scope_profile"
    assert payload["data"]["context"]["mode"] == "external_rscript_profile"
    assert payload["data"]["context"]["cohort_a_top_disease"] == "Multiple Sclerosis"
    assert payload["data"]["context"]["cohort_a_top_medication"] == "Ocrelizumab"
    assert payload["data"]["context"]["cohort_a_patient_count"] == 1


@pytest.mark.parametrize(
    "runner_ref",
    [
        "methylation_qc_pca",
        "methylation_limma_differential_methylation",
    ],
)
def test_methylation_runners_resolve_selected_assay_in_multi_dataset_workspace(
    tmp_path,
    monkeypatch,
    runner_ref,
):
    workspace_root = tmp_path / "multi-dataset-scope"
    workspace_root.mkdir()
    (workspace_root / "manifest.json").write_text(
        json.dumps({"dataset_ids": ["dataset-a", "dataset-b"]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        analysis_external_module.shutil,
        "which",
        lambda name: "/usr/bin/Rscript" if name == "Rscript" else None,
    )

    def selected_assay_resolution(*_args, **_kwargs):
        raise RuntimeError("Selected assay resolution reached")

    monkeypatch.setattr(
        analysis_external_module,
        "_choose_methylation_assay",
        selected_assay_resolution,
    )

    with pytest.raises(RuntimeError, match="Selected assay resolution reached"):
        analysis_external_module.run_rscript_analysis(
            runner_ref,
            prompt="Run methylation analysis.",
            data_dir=str(workspace_root),
            assay_id="dataset-a::methylation",
            selected_patient_ids="A1,A2",
            compare_selected_patient_ids="B1,B2",
            job_dir=tmp_path / f"{runner_ref}-job",
        )


@pytest.mark.parametrize("invalid_type", [None, "factor"])
def test_methylation_runner_requires_explicit_valid_covariate_types(tmp_path, monkeypatch, invalid_type):
    _write_synthetic_methylation_runner_fixture(tmp_path)
    manifest_path = tmp_path / "assays" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if invalid_type is None:
        manifest["assays"][0]["analysis_covariate_types"].pop("plate")
    else:
        manifest["assays"][0]["analysis_covariate_types"]["plate"] = invalid_type
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(
        analysis_external_module.shutil,
        "which",
        lambda name: "/usr/bin/Rscript" if name == "Rscript" else None,
    )

    with pytest.raises(RuntimeError, match="plate.*numeric or categorical"):
        analysis_external_module.run_rscript_analysis(
            "methylation_qc_pca",
            prompt="Run methylation QC.",
            data_dir=str(tmp_path),
            assay_id="synthetic_methylation_m_values",
            job_dir=tmp_path / "invalid-covariate-type-job",
        )


@pytest.mark.parametrize(
    ("metadata_problem", "error_pattern"),
    [
        ("missing", "Every selected assay matrix sample must have explicit patient linkage metadata"),
        ("duplicate", "duplicate sample identifiers"),
        ("ambiguous", "ambiguous row with extra fields"),
    ],
)
def test_methylation_runner_rejects_invalid_explicit_linkage(
    tmp_path,
    monkeypatch,
    metadata_problem,
    error_pattern,
):
    _write_synthetic_methylation_runner_fixture(tmp_path)
    metadata_path = tmp_path / "assays" / "methylation" / "sample_metadata.csv"
    lines = metadata_path.read_text(encoding="utf-8").splitlines()
    if metadata_problem == "missing":
        lines = [line for line in lines if not line.startswith("METH006;")]
    elif metadata_problem == "duplicate":
        lines.append("METH001;OTHER;61;103")
    else:
        lines[1] += ";unexpected"
    metadata_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    monkeypatch.setattr(
        analysis_external_module.shutil,
        "which",
        lambda name: "/usr/bin/Rscript" if name == "Rscript" else None,
    )

    with pytest.raises(RuntimeError, match=error_pattern):
        analysis_external_module.run_rscript_analysis(
            "methylation_qc_pca",
            prompt="Run methylation QC.",
            data_dir=str(tmp_path),
            assay_id="synthetic_methylation_m_values",
            job_dir=tmp_path / f"invalid-linkage-{metadata_problem}-job",
        )


def test_methylation_runner_requires_explicit_sample_metadata(tmp_path, monkeypatch):
    _write_synthetic_methylation_runner_fixture(tmp_path)
    manifest_path = tmp_path / "assays" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["assays"][0].pop("sample_metadata_file")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(
        analysis_external_module.shutil,
        "which",
        lambda name: "/usr/bin/Rscript" if name == "Rscript" else None,
    )

    with pytest.raises(RuntimeError, match="missing its sample_metadata_file declaration"):
        analysis_external_module.run_rscript_analysis(
            "methylation_qc_pca",
            prompt="Run methylation QC.",
            data_dir=str(tmp_path),
            assay_id="synthetic_methylation_m_values",
            job_dir=tmp_path / "missing-sample-metadata-job",
        )


def test_methylation_runner_rejects_exact_linkage_without_patient_column(tmp_path, monkeypatch):
    _write_synthetic_methylation_runner_fixture(tmp_path)
    manifest_path = tmp_path / "assays" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["assays"][0]["patient_linkage"] = "exact_sample_id"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    metadata_path = tmp_path / "assays" / "methylation" / "sample_metadata.csv"
    metadata_path.write_text(
        "sample_id;age;plate\n"
        "METH001;41;101\n"
        "METH002;47;102\n"
        "METH003;53;101\n"
        "METH004;43;102\n"
        "METH005;49;101\n"
        "METH006;55;102\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        analysis_external_module.shutil,
        "which",
        lambda name: "/usr/bin/Rscript" if name == "Rscript" else None,
    )

    with pytest.raises(RuntimeError, match="must contain sample_id and patient_id columns"):
        analysis_external_module.run_rscript_analysis(
            "methylation_qc_pca",
            prompt="Run methylation QC.",
            data_dir=str(tmp_path),
            assay_id="synthetic_methylation_m_values",
            job_dir=tmp_path / "exact-linkage-without-patient-job",
        )


def test_methylation_runner_rejects_selected_patient_missing_from_clinical_workspace(tmp_path, monkeypatch):
    _write_synthetic_methylation_runner_fixture(tmp_path)
    metadata_path = tmp_path / "assays" / "methylation" / "sample_metadata.csv"
    metadata_path.write_text(
        metadata_path.read_text(encoding="utf-8").replace("METH006;METH006;", "METH006;NOT_CLINICALLY_LINKED;"),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        analysis_external_module.shutil,
        "which",
        lambda name: "/usr/bin/Rscript" if name == "Rscript" else None,
    )

    with pytest.raises(RuntimeError, match="explicit clinical linkage.*1 selected patient"):
        analysis_external_module.run_rscript_analysis(
            "methylation_qc_pca",
            prompt="Run methylation QC.",
            data_dir=str(tmp_path),
            assay_id="synthetic_methylation_m_values",
            job_dir=tmp_path / "missing-clinical-linkage-job",
        )


def test_methylation_runner_rejects_matrix_location_outside_release(tmp_path, monkeypatch):
    assay_dir = tmp_path / "assays"
    assay_dir.mkdir()
    outside_matrix = tmp_path.parent / f"{tmp_path.name}-outside-methylation-matrix.csv"
    outside_matrix.write_text("feature_id;METH001;METH002\ncg00000001;0.1;0.2\n", encoding="utf-8")
    (assay_dir / "manifest.json").write_text(
        json.dumps(
            {
                "version": 1,
                "assays": [
                    {
                        "assay_id": "invalid_methylation",
                        "modality": "methylation",
                        "data_type": "m_values",
                        "file": f"../{outside_matrix.name}",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        analysis_external_module.shutil,
        "which",
        lambda name: "/usr/bin/Rscript" if name == "Rscript" else None,
    )

    with pytest.raises(RuntimeError, match="invalid file location"):
        analysis_external_module.run_rscript_analysis(
            "methylation_qc_pca",
            prompt="Run methylation QC.",
            data_dir=str(tmp_path),
            assay_id="invalid_methylation",
            job_dir=tmp_path / "invalid-methylation-job",
        )


def test_methylation_bundle_resolves_matrix_and_metadata_from_authorized_source_root(tmp_path, monkeypatch):
    source_root = tmp_path / "authorized-release"
    workspace_root = tmp_path / "workspace-scope"
    workspace_root.mkdir()
    _write_synthetic_methylation_runner_fixture(source_root)
    manifest = json.loads((source_root / "assays" / "manifest.json").read_text(encoding="utf-8"))
    item = dict(manifest["assays"][0])
    item["_release_root"] = str(source_root)
    item["assay_id"] = "authorized::synthetic_methylation_m_values"
    monkeypatch.setattr(
        analysis_external_module,
        "_choose_methylation_assay",
        lambda *_args, **_kwargs: item,
    )
    monkeypatch.setattr(
        query_store_module,
        "patient_inventory",
        lambda _data_dir: [f"METH00{index}" for index in range(1, 7)],
    )

    bundle = analysis_external_module._prepare_methylation_analysis_bundle(
        str(workspace_root),
        prompt="Run methylation QC.",
        assay_id=item["assay_id"],
        selected_patient_ids="",
        compare_selected_patient_ids="",
        output_dir=tmp_path / "authorized-root-job",
        analysis_type="qc_pca",
    )

    assert bundle["matrix_path"] == source_root / "assays" / "methylation" / "synthetic_m_values.csv"
    assert bundle["clinical_linkage_status"] == "complete_selected_scope"


@pytest.mark.parametrize('kind', ['methylation', 'quantitative'])
def test_assay_bundle_uses_only_selected_source_with_colliding_patient_ids(tmp_path, monkeypatch, kind):
    from app.identities import identity_key
    source = tmp_path / 'source'
    source.mkdir()
    if kind == 'methylation':
        _write_synthetic_methylation_runner_fixture(source)
        patient_ids = [f'METH00{i}' for i in range(1, 7)]
    else:
        _write_synthetic_quantitative_assay_runner_fixture(source)
        patient_ids = [f'SYN00{i}' for i in range(1, 7)]
    item = json.loads((source / 'assays' / 'manifest.json').read_text())['assays'][0]
    item.update(_source_dataset_id='source-a', _release_root=str(source))
    item['assay_id'] = 'source-a::' + item['assay_id']
    monkeypatch.setattr(query_store_module, '_workspace_dataset_ids', lambda _: ['source-a', 'source-b'])
    monkeypatch.setattr(query_store_module, 'patient_inventory', lambda _: [
        identity_key(dataset, 'patient', pid) for dataset in ['source-a', 'source-b'] for pid in patient_ids])
    monkeypatch.setattr(analysis_external_module, '_choose_methylation_assay', lambda *a: item)
    monkeypatch.setattr(query_store_module, '_queryable_external_assay_item', lambda *a, **kw: item)
    prepare = (analysis_external_module._prepare_methylation_analysis_bundle if kind == 'methylation'
               else analysis_external_module._prepare_quantitative_assay_comparison_bundle)
    kwargs = dict(prompt='Compare', assay_id=item['assay_id'], output_dir=tmp_path / 'run',
                  selected_patient_ids=','.join(identity_key('source-a', 'patient', p) for p in patient_ids[:3]),
                  compare_selected_patient_ids=','.join(identity_key('source-a', 'patient', p) for p in patient_ids[3:]))
    if kind == 'methylation':
        kwargs['analysis_type'] = 'differential_methylation'
    # Same source IDs from another dataset must neither collide nor add samples.
    kwargs['selected_patient_ids'] += ',' + ','.join(identity_key('source-b', 'patient', p) for p in patient_ids)
    bundle = prepare(str(tmp_path), **kwargs)
    assert bundle['patient_count'] == 6
    assert bundle['matrix_path'].is_relative_to(source)
    kwargs['selected_patient_ids'] = ','.join(identity_key('source-b', 'patient', p) for p in patient_ids[:3])
    with pytest.raises(RuntimeError, match='at least'):
        prepare(str(tmp_path), **kwargs)


def test_quantitative_assay_wilcoxon_runner_keeps_source_external_and_returns_aggregates(tmp_path, monkeypatch):
    if not shutil.which("Rscript"):
        pytest.skip("Rscript is not available")
    r_check = subprocess.run(
        ["Rscript", "-e", "quit(status=ifelse(requireNamespace('jsonlite', quietly=TRUE), 0, 1))"],
        check=False,
        capture_output=True,
        text=True,
    )
    if r_check.returncode != 0:
        pytest.skip("R jsonlite is not available")
    isolate_query_store(monkeypatch, tmp_path)
    matrix_path = _write_synthetic_quantitative_assay_runner_fixture(tmp_path)
    job_dir = tmp_path / "quantitative-assay-job"

    payload = analysis_external_module.run_rscript_analysis(
        "quantitative_assay_wilcoxon_comparison",
        prompt="Compare Cohort A and Cohort B.",
        data_dir=str(tmp_path),
        assay_id="synthetic_quantitative_serology",
        selected_patient_ids="SYN001,SYN002,SYN003",
        compare_selected_patient_ids="SYN004,SYN005,SYN006",
        job_dir=job_dir,
        timeout_seconds=30,
    )

    context = payload["data"]["context"]
    assert context["mode"] == "external_rscript_quantitative_assay_wilcoxon_comparison"
    assert context["adjustment_status"] == "unadjusted_exploratory"
    assert context["feature_count"] == 3
    assert context["tested_feature_count"] == 1
    assert context["skipped_feature_count"] == 2
    assert context["source_matrix_materialized_in_duckdb"] is False
    assert context["source_matrix_copied_to_job"] is False
    marker = next(row for row in context["results"] if row["feature_id"] == "Marker_up")
    assert marker["status"] == "tested"
    assert marker["rank_biserial_effect"] == pytest.approx(1.0)
    assert marker["median_difference"] == pytest.approx(7.0)
    assert 0 < marker["p_value"] <= marker["adj_p_value"] <= 1
    for artifact_name in (
        "compact_assay_results.tsv",
        "summary.json",
        "effect_plot.png",
        "manifest.yaml",
        "params.yaml",
    ):
        assert (job_dir / artifact_name).is_file()
    assert not (job_dir / matrix_path.name).exists()
    assert not (job_dir / ".analysis-private").exists()
    assert "sample_table.tsv" not in {
        item["name"] for item in jobs_module._artifact_inventory(job_dir)
    }
    assert "[protected assay matrix]" in (job_dir / "command.txt").read_text(encoding="utf-8")
    assert str(matrix_path) not in json.dumps(payload)
    for patient_id in [f"SYN00{index}" for index in range(1, 7)]:
        assert patient_id not in json.dumps(payload)
        assert patient_id not in (job_dir / "summary.json").read_text(encoding="utf-8")
        assert patient_id not in (job_dir / "compact_assay_results.tsv").read_text(encoding="utf-8")


def test_analysis_external_rscript_assay_deseq2_runner_executes(tmp_path, monkeypatch):
    write_json(
        tmp_path,
        "records.json",
        [
            {"id": "SYN001:baseline", "event_date": "2024-01-01"},
            {"id": "SYN002:baseline", "event_date": "2024-01-01"},
            {"id": "SYN003:baseline", "event_date": "2024-01-01"},
            {"id": "SYN004:baseline", "event_date": "2024-01-01"},
        ],
    )

    original_dir = query_store_module.ASSAY_DATA_DIR
    transcriptomics_dir = tmp_path / "assays" / "transcriptomics"
    transcriptomics_dir.mkdir(parents=True)
    (transcriptomics_dir / "synthetic_transcriptome_raw_counts.csv").write_text(
        "\n".join(
            [
                "gene_id;SYN001:baseline;SYN002:baseline;SYN003:baseline;SYN004:baseline",
                "ENSG00000111111;120;118;5;7",
                "ENSG00000122222;9;11;96;101",
                "ENSG00000133333;40;42;38;39",
            ]
        ),
        encoding="utf-8",
    )
    signature_files = {Path(item["path"]).name for item in query_store_module._source_files_signature(str(tmp_path))["assay_files"]}
    assert signature_files == {"synthetic_transcriptome_raw_counts.csv"}
    query_store_module.ASSAY_DATA_DIR = transcriptomics_dir
    monkeypatch.setattr(
        analysis_external_module.shutil,
        "which",
        lambda name: "/usr/bin/Rscript" if name == "Rscript" else None,
    )

    def fake_run(command, **kwargs):
        results_path = Path(command[command.index("--results-table") + 1])
        volcano_path = Path(command[command.index("--volcano-table") + 1])
        assert kwargs["env"]["OPENBLAS_NUM_THREADS"] == "1"
        assert kwargs["env"]["OMP_THREAD_LIMIT"] == "1"
        summary_path = Path(command[command.index("--summary-json") + 1])
        plot_path = Path(command[command.index("--plot-file") + 1])
        heatmap_path = Path(command[command.index("--heatmap-file") + 1])
        heatmap_table_path = Path(command[command.index("--heatmap-table") + 1])
        heatmap_clustering_path = Path(command[command.index("--heatmap-clustering") + 1])
        for path in (results_path, volcano_path, summary_path, plot_path, heatmap_path, heatmap_table_path, heatmap_clustering_path):
            path.parent.mkdir(parents=True, exist_ok=True)
        results_path.write_text("gene_id\tbase_mean\tlog2_fold_change\tadj_p_value\nGENE1\t100\t2.3\t0.001\n", encoding="utf-8")
        volcano_path.write_text("gene_id\tlog2_fold_change\tp_value\tadj_p_value\tneg_log10_p\nGENE1\t2.3\t1e-5\t0.001\t5\n", encoding="utf-8")
        summary_path.write_text('{"significant_gene_count":1,"shrinkage_method":"apeglm"}\n', encoding="utf-8")
        plot_path.write_text("png", encoding="utf-8")
        heatmap_path.write_text("png", encoding="utf-8")
        heatmap_table_path.write_text("gene_id\tSYN001:baseline\tSYN002:baseline\tSYN003:baseline\tSYN004:baseline\nGENE1\t1.2\t1.0\t-1.1\t-1.0\n", encoding="utf-8")
        heatmap_clustering_path.write_text('{"order":[1],"merge":[],"height":[],"labels":["GENE1"]}\n', encoding="utf-8")
        payload = {
            "reply": "### External R DESeq2 differential expression\n\n- Significant genes (BH < 0.05): 1",
            "context": {
                "mode": "external_rscript_transcriptomics_deseq2_differential_expression",
                "runner": "transcriptomics_deseq2_differential_expression",
                "dataset_name": "synthetic_transcriptome_raw_counts",
                "cohort_a_sample_count": 2,
                "cohort_b_sample_count": 2,
                "tested_gene_count": 3,
                "filtered_gene_count": 3,
                "significant_gene_count": 1,
                "shrinkage_method": "apeglm",
            },
        }
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(analysis_external_module.subprocess, "run", fake_run)

    try:
        job_dir = tmp_path / "job-output-deseq2"
        payload = analysis_external_module.run_rscript_analysis(
            "transcriptomics_deseq2_differential_expression",
            prompt="Run DESeq2 differential expression between Cohort A and Cohort B for the selected assay.",
            data_dir=str(tmp_path),
            assay_id="synthetic_transcriptome_raw_counts",
            selected_patient_ids="SYN001,SYN002",
            compare_selected_patient_ids="SYN003,SYN004",
            job_dir=job_dir,
            timeout_seconds=60,
        )
    finally:
        query_store_module.ASSAY_DATA_DIR = original_dir

    assert payload["intent"] == "analysis_external_rscript"
    assert payload["data"]["runner_ref"] == "transcriptomics_deseq2_differential_expression"
    assert payload["data"]["context"]["mode"] == "external_rscript_transcriptomics_deseq2_differential_expression"
    assert payload["data"]["context"]["shrinkage_method"] == "apeglm"
    assert (job_dir / "de_results.tsv").exists()
    assert (job_dir / "volcano_points.tsv").exists()
    assert (job_dir / "summary.json").exists()
    assert (job_dir / "volcano_plot.png").exists()
    assert (job_dir / "top_genes_heatmap.png").exists()
    assert (job_dir / "top_genes_heatmap.tsv").exists()
    assert (job_dir / "top_genes_heatmap_clustering.json").exists()


def test_analysis_external_rscript_assay_deseq2_runner_rejects_repeated_patient_samples(tmp_path):
    write_json(
        tmp_path,
        "records.json",
        [
            {"id": "SYN001:week_0", "event_date": "2024-01-01"},
            {"id": "SYN001:week_2", "event_date": "2024-01-15"},
            {"id": "SYN002:week_0", "event_date": "2024-01-01"},
            {"id": "SYN002:week_2", "event_date": "2024-01-15"},
            {"id": "SYN003:week_0", "event_date": "2024-01-01"},
            {"id": "SYN004:week_0", "event_date": "2024-01-01"},
        ],
    )

    original_dir = query_store_module.ASSAY_DATA_DIR
    transcriptomics_dir = tmp_path / "assays" / "transcriptomics"
    transcriptomics_dir.mkdir(parents=True)
    (transcriptomics_dir / "synthetic_transcriptome_raw_counts.csv").write_text(
        "\n".join(
            [
                "gene_id;SYN001:week_0;SYN001:week_2;SYN002:week_0;SYN002:week_2;SYN003:week_0;SYN004:week_0",
                "ENSG00000111111;100;120;90;110;5;7",
                "ENSG00000122222;6;8;7;9;90;110",
            ]
        ),
        encoding="utf-8",
    )
    query_store_module.ASSAY_DATA_DIR = transcriptomics_dir
    try:
        with pytest.raises(RuntimeError, match="one sample per patient"):
            analysis_external_module.run_rscript_analysis(
                "transcriptomics_deseq2_differential_expression",
                prompt="Run DESeq2 differential expression between Cohort A and Cohort B for the selected assay.",
                data_dir=str(tmp_path),
                assay_id="synthetic_transcriptome_raw_counts",
                selected_patient_ids="SYN001:week_0,SYN001:week_2",
                compare_selected_patient_ids="SYN002:week_0,SYN002:week_2",
                job_dir=tmp_path / "job-output-deseq2-invalid",
                timeout_seconds=60,
            )
    finally:
        query_store_module.ASSAY_DATA_DIR = original_dir


def test_analysis_external_rscript_assay_hallmark_pathway_runner_executes(tmp_path, monkeypatch):
    write_json(
        tmp_path,
        "records.json",
        [
            {"id": "SYN001:baseline", "event_date": "2024-01-01"},
            {"id": "SYN002:baseline", "event_date": "2024-01-01"},
            {"id": "SYN003:baseline", "event_date": "2024-01-01"},
            {"id": "SYN004:baseline", "event_date": "2024-01-01"},
        ],
    )

    original_dir = query_store_module.ASSAY_DATA_DIR
    transcriptomics_dir = tmp_path / "assays" / "transcriptomics"
    transcriptomics_dir.mkdir(parents=True)
    (transcriptomics_dir / "synthetic_transcriptome_raw_counts.csv").write_text(
        "\n".join(
            [
                "gene_id;SYN001:baseline;SYN002:baseline;SYN003:baseline;SYN004:baseline",
                "ENSG00000111111;120;118;5;7",
                "ENSG00000122222;9;11;96;101",
                "ENSG00000133333;40;42;38;39",
            ]
        ),
        encoding="utf-8",
    )
    query_store_module.ASSAY_DATA_DIR = transcriptomics_dir
    monkeypatch.setattr(
        analysis_external_module.shutil,
        "which",
        lambda name: "/usr/bin/Rscript" if name == "Rscript" else None,
    )

    def fake_run(command, **kwargs):
        results_path = Path(command[command.index("--results-table") + 1])
        rankings_path = Path(command[command.index("--rankings-table") + 1])
        assert kwargs["env"]["MC_CORES"] == "1"
        summary_path = Path(command[command.index("--summary-json") + 1])
        plot_path = Path(command[command.index("--plot-file") + 1])
        for path in (results_path, rankings_path, summary_path, plot_path):
            path.parent.mkdir(parents=True, exist_ok=True)
        results_path.write_text("pathway\tNES\tpadj\tleadingEdge\nHALLMARK_TNFA_SIGNALING_VIA_NFKB\t2.1\t0.01\tENSG1,ENSG2\n", encoding="utf-8")
        rankings_path.write_text("gene_id\tstatistic\tlog2_fold_change\tadjusted_p_value\nENSG1\t4.2\t1.8\t0.01\n", encoding="utf-8")
        summary_path.write_text('{"significant_pathway_count":1,"pathway_collection":"MSigDB Hallmark"}\n', encoding="utf-8")
        plot_path.write_text("png", encoding="utf-8")
        payload = {
            "reply": "### Hallmark pathway enrichment\n\n- Significant pathways (BH < 0.05): 1",
            "context": {
                "mode": "external_rscript_transcriptomics_hallmark_pathway_enrichment",
                "runner": "transcriptomics_hallmark_pathway_enrichment",
                "dataset_name": "synthetic_transcriptome_raw_counts",
                "cohort_a_sample_count": 2,
                "cohort_b_sample_count": 2,
                "ranked_gene_count": 3,
                "pathway_count": 50,
                "significant_pathway_count": 1,
                "pathway_collection": "MSigDB Hallmark",
                "top_positive_pathways": ["HALLMARK_TNFA_SIGNALING_VIA_NFKB"],
                "top_negative_pathways": [],
                "top_positive_pathway_labels": ["TNFA Signaling Via NFKB"],
                "top_negative_pathway_labels": [],
            },
        }
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(analysis_external_module.subprocess, "run", fake_run)

    try:
        job_dir = tmp_path / "job-output-pathway"
        payload = analysis_external_module.run_rscript_analysis(
            "transcriptomics_hallmark_pathway_enrichment",
            prompt="Run Hallmark pathway enrichment between Cohort A and Cohort B for the selected assay.",
            data_dir=str(tmp_path),
            assay_id="synthetic_transcriptome_raw_counts",
            selected_patient_ids="SYN001,SYN002",
            compare_selected_patient_ids="SYN003,SYN004",
            job_dir=job_dir,
            timeout_seconds=60,
        )
    finally:
        query_store_module.ASSAY_DATA_DIR = original_dir

    assert payload["intent"] == "analysis_external_rscript"
    assert payload["data"]["runner_ref"] == "transcriptomics_hallmark_pathway_enrichment"
    assert payload["data"]["context"]["mode"] == "external_rscript_transcriptomics_hallmark_pathway_enrichment"
    assert payload["data"]["context"]["pathway_collection"] == "MSigDB Hallmark"
    assert payload["data"]["context"]["top_positive_pathway_labels"] == ["TNFA Signaling Via NFKB"]
    assert (job_dir / "pathway_results.tsv").exists()
    assert (job_dir / "gene_rankings.tsv").exists()
    assert (job_dir / "summary.json").exists()
    assert (job_dir / "pathway_plot.png").exists()


def test_analysis_external_rscript_assay_hallmark_pathway_runner_rejects_repeated_patient_samples(tmp_path):
    write_json(
        tmp_path,
        "records.json",
        [
            {"id": "SYN001:week_0", "event_date": "2024-01-01"},
            {"id": "SYN001:week_2", "event_date": "2024-01-15"},
            {"id": "SYN002:week_0", "event_date": "2024-01-01"},
            {"id": "SYN002:week_2", "event_date": "2024-01-15"},
            {"id": "SYN003:week_0", "event_date": "2024-01-01"},
            {"id": "SYN004:week_0", "event_date": "2024-01-01"},
        ],
    )

    original_dir = query_store_module.ASSAY_DATA_DIR
    transcriptomics_dir = tmp_path / "assays" / "transcriptomics"
    transcriptomics_dir.mkdir(parents=True)
    (transcriptomics_dir / "synthetic_transcriptome_raw_counts.csv").write_text(
        "\n".join(
            [
                "gene_id;SYN001:week_0;SYN001:week_2;SYN002:week_0;SYN002:week_2;SYN003:week_0;SYN004:week_0",
                "ENSG00000111111;100;120;90;110;5;7",
                "ENSG00000122222;6;8;7;9;90;110",
            ]
        ),
        encoding="utf-8",
    )
    query_store_module.ASSAY_DATA_DIR = transcriptomics_dir
    try:
        with pytest.raises(RuntimeError, match="one sample per patient"):
            analysis_external_module.run_rscript_analysis(
                "transcriptomics_hallmark_pathway_enrichment",
                prompt="Run Hallmark pathway enrichment between Cohort A and Cohort B for the selected assay.",
                data_dir=str(tmp_path),
                assay_id="synthetic_transcriptome_raw_counts",
                selected_patient_ids="SYN001:week_0,SYN001:week_2",
                compare_selected_patient_ids="SYN002:week_0,SYN002:week_2",
                job_dir=tmp_path / "job-output-pathway-invalid",
                timeout_seconds=60,
            )
    finally:
        query_store_module.ASSAY_DATA_DIR = original_dir


def test_analysis_external_snakemake_runner_executes(tmp_path, monkeypatch):
    write_json(
        tmp_path,
        "records.json",
        [
            {"id": "P1:baseline", "patient_id": "P1"},
            {"id": "P2:baseline", "patient_id": "P2"},
        ],
    )

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
        result_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(
            json.dumps(
                {
                    "reply": "Snakemake dummy workflow completed for current Analysis scope.",
                    "context": {"mode": "external_snakemake_dummy", "scope_summary": "current Analysis scope"},
                }
            ),
            encoding="utf-8",
        )
        summary_path.write_text("dummy summary\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="snakemake ok\n", stderr="")

    monkeypatch.setattr(analysis_external_module.subprocess, "run", fake_run)

    job_dir = tmp_path / "snakemake-job"
    payload = analysis_external_module.run_snakemake_analysis(
        "dummy_queue_demo",
        prompt="Run the external Snakemake demo for the current Analysis scope.",
        data_dir=str(tmp_path),
        selected_patient_ids="P1",
        job_dir=job_dir,
        timeout_seconds=60,
    )

    assert payload["intent"] == "analysis_external_snakemake"
    assert "Snakemake dummy workflow completed" in payload["reply"]
    assert payload["data"]["runner_type"] == "snakemake"
    assert payload["data"]["runner_ref"] == "dummy_queue_demo"
    assert payload["data"]["context"]["mode"] == "external_snakemake_dummy"
    assert (job_dir / "command.txt").exists()
    assert (job_dir / "stdout.txt").exists()
    assert (job_dir / "stderr.txt").exists()


def test_analysis_external_nextflow_runner_executes(tmp_path, monkeypatch):
    write_json(
        tmp_path,
        "records.json",
        [
            {"id": "P1:baseline", "patient_id": "P1"},
            {"id": "P2:baseline", "patient_id": "P2"},
        ],
    )

    monkeypatch.setattr(
        analysis_external_module.shutil,
        "which",
        lambda name: "/usr/bin/nextflow" if name == "nextflow" else None,
    )
    monkeypatch.delenv("NEXTFLOW_BIN", raising=False)

    def fake_run(command, **kwargs):
        result_index = command.index("--result_json")
        summary_index = command.index("--summary_txt")
        result_path = Path(command[result_index + 1])
        summary_path = Path(command[summary_index + 1])
        result_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(
            json.dumps(
                {
                    "reply": "Nextflow dummy workflow completed for Cohort A vs Cohort B.",
                    "context": {"mode": "external_nextflow_dummy", "scope_summary": "Cohort A vs Cohort B"},
                }
            ),
            encoding="utf-8",
        )
        summary_path.write_text("dummy summary\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="nextflow ok\n", stderr="")

    monkeypatch.setattr(analysis_external_module.subprocess, "run", fake_run)

    job_dir = tmp_path / "nextflow-job"
    payload = analysis_external_module.run_nextflow_analysis(
        "dummy_queue_demo",
        prompt="Run the external Nextflow demo for the current Analysis scope.",
        data_dir=str(tmp_path),
        selected_patient_ids="P1",
        compare_selected_patient_ids="P2",
        job_dir=job_dir,
        timeout_seconds=60,
    )

    assert payload["intent"] == "analysis_external_nextflow"
    assert "Nextflow dummy workflow completed" in payload["reply"]
    assert payload["data"]["runner_type"] == "nextflow"
    assert payload["data"]["runner_ref"] == "dummy_queue_demo"
    assert payload["data"]["context"]["mode"] == "external_nextflow_dummy"
    assert (job_dir / "command.txt").read_text(encoding="utf-8").splitlines()[0].startswith("/usr/bin/nextflow ")
    assert (job_dir / "command.txt").exists()
    assert (job_dir / "stdout.txt").exists()
    assert (job_dir / "stderr.txt").exists()


def test_analysis_external_nextflow_runner_uses_env_override(tmp_path, monkeypatch):
    write_json(
        tmp_path,
        "records.json",
        [
            {"id": "P1:baseline", "patient_id": "P1"},
            {"id": "P2:baseline", "patient_id": "P2"},
        ],
    )

    nextflow_path = tmp_path / "nextflow"
    nextflow_path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    nextflow_path.chmod(0o755)

    monkeypatch.setattr(analysis_external_module.shutil, "which", lambda name: None)
    monkeypatch.setenv("NEXTFLOW_BIN", str(nextflow_path))

    def fake_run(command, **kwargs):
        result_index = command.index("--result_json")
        summary_index = command.index("--summary_txt")
        result_path = Path(command[result_index + 1])
        summary_path = Path(command[summary_index + 1])
        result_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(
            json.dumps(
                {
                    "reply": "Nextflow env override workflow completed for Cohort A vs Cohort B.",
                    "context": {"mode": "external_nextflow_dummy", "scope_summary": "Cohort A vs Cohort B"},
                }
            ),
            encoding="utf-8",
        )
        summary_path.write_text("dummy summary\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="nextflow ok\n", stderr="")

    monkeypatch.setattr(analysis_external_module.subprocess, "run", fake_run)

    job_dir = tmp_path / "nextflow-job-env"
    payload = analysis_external_module.run_nextflow_analysis(
        "dummy_queue_demo",
        prompt="Run the external Nextflow demo for the current Analysis scope.",
        data_dir=str(tmp_path),
        selected_patient_ids="P1",
        compare_selected_patient_ids="P2",
        job_dir=job_dir,
        timeout_seconds=60,
    )

    assert payload["intent"] == "analysis_external_nextflow"
    assert "env override workflow completed" in payload["reply"]
    assert (job_dir / "command.txt").read_text(encoding="utf-8").splitlines()[0].startswith(f"{nextflow_path} ")


def test_analysis_workflow_runner_creates_step_directories_and_manifest(tmp_path, monkeypatch):
    write_json(tmp_path, "records.json", [{"id": "P1:baseline", "patient_id": "P1"}])

    def fake_run_rscript_analysis(
        runner_ref,
        *,
        prompt,
        data_dir,
        assay_id="",
        selected_patient_ids="",
        compare_selected_patient_ids="",
        job_dir=None,
        timeout_seconds=30,
    ):
        assert job_dir is not None
        Path(job_dir).mkdir(parents=True, exist_ok=True)
        if runner_ref == "transcriptomics_deseq2_differential_expression":
            (Path(job_dir) / "volcano_plot.png").write_text("png", encoding="utf-8")
            (Path(job_dir) / "de_results.tsv").write_text("gene\tlog2FoldChange\nG1\t1.2\n", encoding="utf-8")
            context = {
                "mode": "external_rscript_transcriptomics_deseq2_differential_expression",
                "dataset_name": "synthetic_counts",
                "cohort_a_sample_count": 2,
                "cohort_b_sample_count": 2,
                "gene_count": 100,
                "significant_gene_count": 3,
            }
            return {"intent": "analysis_external_rscript", "reply": "DESeq2 done.", "data": {"context": context}}
        if runner_ref == "transcriptomics_hallmark_pathway_enrichment":
            (Path(job_dir) / "pathway_plot.png").write_text("png", encoding="utf-8")
            (Path(job_dir) / "pathway_results.tsv").write_text("pathway\tpadj\nHALLMARK_TNFA_SIGNALING_VIA_NFKB\t0.01\n", encoding="utf-8")
            context = {
                "mode": "external_rscript_transcriptomics_hallmark_pathway_enrichment",
                "dataset_name": "synthetic_counts",
                "ranked_gene_count": 100,
                "pathway_count": 50,
                "significant_pathway_count": 2,
                "top_positive_pathway_labels": ["HALLMARK_TNFA_SIGNALING_VIA_NFKB"],
            }
            return {"intent": "analysis_external_rscript", "reply": "Hallmark done.", "data": {"context": context}}
        raise AssertionError(f"Unexpected runner_ref {runner_ref}")

    monkeypatch.setattr(analysis_external_module, "run_rscript_analysis", fake_run_rscript_analysis)
    job_dir = tmp_path / "workflow-job"

    payload = analysis_external_module.run_workflow_analysis(
        "transcriptomics_signature",
        prompt="Run the assay signature workflow.",
        data_dir=str(tmp_path),
        assay_id="synthetic_counts",
        selected_patient_ids="P1,P2",
        compare_selected_patient_ids="P3,P4",
        job_dir=job_dir,
        timeout_seconds=120,
    )

    assert payload["intent"] == "analysis_workflow"
    assert payload["data"]["runner_type"] == "workflow"
    assert payload["data"]["context"]["mode"] == "workflow_transcriptomics_signature"
    assert payload["data"]["context"]["deseq2"]["significant_gene_count"] == 3
    assert payload["data"]["context"]["hallmark"]["significant_pathway_count"] == 2
    assert (job_dir / "workflow" / "01-deseq2" / "volcano_plot.png").exists()
    assert (job_dir / "workflow" / "02-hallmark" / "pathway_plot.png").exists()
    manifest = json.loads((job_dir / "workflow" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "completed"
    assert [step["status"] for step in manifest["steps"]] == ["completed", "completed"]
