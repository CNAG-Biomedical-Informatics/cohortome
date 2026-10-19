"""Run the real R adapter against bundled synthetic assays in a packaged backend."""
import csv


def check(root, runtime):
    from app.analysis_external import run_rscript_analysis
    from app.query_store import prepare_dataset_query_store
    from app.r_runtime import rscript_binary, rscript_unavailable_reason

    binary = rscript_binary()
    assert binary and "runtimes/r/bin/Rscript" in binary.replace("\\", "/")
    runner = "transcriptomics_limma_voom_differential_expression"
    assert not rscript_unavailable_reason(runner)
    prepare_dataset_query_store("synthetic-autoimmune-demo")
    dataset = root / "synthetic_autoimmune_demo"
    with (dataset / "assays/transcriptomics/sample_metadata.tsv").open() as handle:
        patients = list(dict.fromkeys(row["patient_id"] for row in csv.DictReader(handle, delimiter="\t")))
    assert len(patients) >= 8
    output = runtime / "r-analysis-probe"
    result = run_rscript_analysis(runner, prompt="Synthetic packaging check",
        data_dir=str(dataset), assay_id="synthetic_autoimmune_transcriptomics",
        selected_patient_ids=",".join(patients[:4]), compare_selected_patient_ids=",".join(patients[-4:]),
        job_dir=output, timeout_seconds=120)
    assert result["intent"] == "analysis_external_rscript"
    assert (output / "model.json").is_file()
    assert any(path.stat().st_size for path in output.glob("*.png"))
    print("PASS: packaged R adapter ran synthetic limma-voom and retained model/plot artifacts")
