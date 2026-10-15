"""Synthetic preparation and numerical checks for the actual limma-voom runner."""
import csv
import json
import random
import shutil
import subprocess
from pathlib import Path

import pytest

from app import analysis_external as external
from app import query_store
from bff_test_helpers import isolate_query_store, write_json


def write_rows(path, fieldnames, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def read_rows(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


@pytest.fixture
def assay(tmp_path, monkeypatch):
    isolate_query_store(monkeypatch, tmp_path)
    monkeypatch.setattr(query_store, "_workspace_dataset_ids", lambda _: [])
    root = tmp_path / "synthetic"
    directory = root / "assays" / "transcriptomics"
    directory.mkdir(parents=True)
    rows = []
    for i in range(20):
        cohort = "A" if i < 10 else "B"
        j = i % 10
        rows.append({"sample_id": f"LAB{i + 1:03d}", "patient_id": f"SUB{i + 1:03d}",
                     "cohort": cohort, "batch": "103" if j == 9 else "102" if j < (8 if cohort == "A" else 2) else "101",
                     "age": str(30 + (i * 7) % 33)})
    write_json(root, "records.json", [{"id": r["sample_id"], "patient_id": r["patient_id"]} for r in rows])
    metadata = directory / "metadata.tsv"
    fields = ["sample_id", "patient_id", "batch", "age"]
    write_rows(metadata, fields, [{k: r[k] for k in fields} for r in reversed(rows)])
    matrix = directory / "counts.tsv"
    rng = random.Random(20261015)
    order = list(range(len(rows)))
    rng.shuffle(order)
    with matrix.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter="\t")
        writer.writerow(["gene_id", *[rows[i]["sample_id"] for i in order]])
        for gene in range(402):
            values = []
            for row in rows:
                cohort_effect = 1.3 if gene < 8 and row["cohort"] == "A" else 0
                batch_effect = 1.8 if 8 <= gene < 32 and row["batch"] == "102" else 0
                age_effect = 0.004 * (float(row["age"]) - 45) if gene < 40 else 0
                value = (60 + gene % 101) * 2 ** (cohort_effect + batch_effect + age_effect + rng.gauss(0, .12))
                values.append(round(value, 6) if gene < 400 else .001)
            writer.writerow([f"G{gene:04d}", *[values[i] for i in order]])
    item = {"assay_id": "synthetic_expected_counts", "modality": "transcriptomics",
            "data_type": "rsem_expected_counts", "file": "assays/transcriptomics/counts.tsv",
            "sample_metadata_file": "assays/transcriptomics/metadata.tsv",
            "patient_linkage": "sample_metadata_file", "analysis_covariates": ["batch", "age"],
            "analysis_covariate_types": {"batch": "categorical", "age": "numeric"}}
    manifest = root / "assays" / "manifest.json"
    manifest.write_text(json.dumps({"version": 1, "assays": [item]}))
    return {"root": root, "metadata": metadata, "manifest": manifest, "item": item, "rows": rows,
            "a": ",".join(r["patient_id"] for r in rows if r["cohort"] == "A"),
            "b": ",".join(r["patient_id"] for r in rows if r["cohort"] == "B")}


def update_manifest(assay):
    assay["manifest"].write_text(json.dumps({"version": 1, "assays": [assay["item"]]}))


def bundle(assay, output):
    return external._prepare_transcriptomics_differential_expression_bundle(
        str(assay["root"]), prompt="Synthetic adjusted comparison", assay_id=assay["item"]["assay_id"],
        selected_patient_ids=assay["a"], compare_selected_patient_ids=assay["b"], output_dir=output,
        method="limma_voom", required_data_type="rsem_expected_counts", minimum_samples_per_group=2)


@pytest.fixture(scope="module")
def rscript():
    binary = shutil.which("Rscript")
    if binary is None:
        pytest.skip("Rscript is required for numerical verification")
    probe = subprocess.run([binary, "-e", 'quit(status=if (all(vapply(c("limma","edgeR","jsonlite"), requireNamespace, logical(1), quietly=TRUE))) 0 else 1)'],
                           capture_output=True, text=True, timeout=30)
    if probe.returncode:
        pytest.skip("limma, edgeR, and jsonlite are required for numerical verification")
    return binary


def execute(assay, output):
    return external.run_rscript_analysis(
        "transcriptomics_limma_voom_differential_expression", prompt="Synthetic adjusted comparison",
        data_dir=str(assay["root"]), assay_id=assay["item"]["assay_id"],
        selected_patient_ids=assay["a"], compare_selected_patient_ids=assay["b"],
        job_dir=output, timeout_seconds=60)


def test_bundle_uses_explicit_links_and_preserves_typed_covariates_and_fractional_counts(assay, tmp_path):
    prepared = bundle(assay, tmp_path / "prepared")
    rows = read_rows(prepared["sample_table_path"])
    original = {row["sample_id"]: row for row in assay["rows"]}
    assert len(rows) == 20
    assert all(row["patient_id"] == original[row["sample_id"]]["patient_id"] for row in rows)
    assert all(row["age"] == original[row["sample_id"]]["age"] for row in rows)
    assert all(row["batch"] == original[row["sample_id"]]["batch"] for row in rows)
    assert prepared["analysis_covariate_types"] == {"batch": "categorical", "age": "numeric"}
    with prepared["counts_matrix_path"].open() as handle:
        reader = csv.reader(handle, delimiter="\t")
        header, first = next(reader), next(reader)
    assert header[1:] == [row["sample_id"] for row in rows]
    assert any(float(value) != int(float(value)) for value in first[1:])


@pytest.mark.parametrize("bad_value", ["", "NA", "Inf", "not-a-number"])
def test_incomplete_or_invalid_covariates_stop_before_fitting(assay, tmp_path, bad_value):
    rows = read_rows(assay["metadata"])
    rows[0]["age"] = bad_value
    write_rows(assay["metadata"], rows[0].keys(), rows)
    with pytest.raises(RuntimeError, match="covariate"):
        bundle(assay, tmp_path / "invalid")


def test_constant_numeric_covariate_is_not_silently_removed(assay, tmp_path):
    rows = read_rows(assay["metadata"])
    for i, row in enumerate(rows):
        row["age"] = "1.0" if i % 2 else "1"
    write_rows(assay["metadata"], rows[0].keys(), rows)
    with pytest.raises(RuntimeError, match="constant"):
        bundle(assay, tmp_path / "constant")


def test_covariate_types_must_be_explicit(assay, tmp_path):
    del assay["item"]["analysis_covariate_types"]["batch"]
    update_manifest(assay)
    with pytest.raises(RuntimeError, match="type numeric or categorical"):
        bundle(assay, tmp_path / "untyped")


def test_exact_sample_linkage_accepts_technical_metadata_without_patient_column(assay, tmp_path):
    rows = read_rows(assay["metadata"])
    for row in rows:
        row.pop("patient_id")
    write_rows(assay["metadata"], rows[0].keys(), rows)
    assay["item"]["patient_linkage"] = "exact_sample_id"
    update_manifest(assay)
    assay["a"] = ",".join(r["sample_id"] for r in assay["rows"] if r["cohort"] == "A")
    assay["b"] = ",".join(r["sample_id"] for r in assay["rows"] if r["cohort"] == "B")
    prepared = bundle(assay, tmp_path / "technical")
    assert all(r["sample_id"] == r["patient_id"] for r in prepared["sample_table_rows"])
    assert prepared["analysis_covariates"] == ["batch", "age"]


def test_adjusted_runner_matches_independent_r_specification_and_reduces_batch_confounding(assay, tmp_path, rscript):
    output = tmp_path / "adjusted"
    payload = execute(assay, output)
    context = payload["data"]["context"]
    assert context["adjustment_status"] == "covariate_adjusted"
    assert context["covariates_used"] == ["batch", "age"]
    assert context["input_gene_count"] == 402
    assert context["tested_gene_count"] == 400
    assert "Adjusted for batch, age" in payload["reply"]
    assert context["coefficient"] == "cohortA"
    expected_path = tmp_path / "reference.tsv"
    reference_script = Path(__file__).parent / "fixtures" / "limma_voom_reference.R"
    subprocess.run([rscript, str(reference_script), str(output / "sample_table.tsv"),
                    str(output / "counts_matrix.tsv"), str(expected_path)],
                   check=True, capture_output=True, text=True, timeout=60)
    actual = {row["gene_id"]: row for row in read_rows(output / "de_results.tsv")}
    expected = {row["gene_id"]: row for row in read_rows(expected_path)}
    assert actual.keys() == expected.keys()
    for gene, expected_row in expected.items():
        for column in ["log2_fold_change", "t", "p_value", "adj_p_value"]:
            assert float(actual[gene][column]) == pytest.approx(float(expected_row[column]), rel=1e-6, abs=1e-12)
    assert float(actual["G0000"]["log2_fold_change"]) > .8
    assert len(read_rows(output / "gene_filter.tsv")) == 402
    assert sum(row["retained"] == "TRUE" for row in read_rows(output / "gene_filter.tsv")) == 400
    design = read_rows(output / "design_matrix.tsv")
    assert [r["sample_id"] for r in design] == [r["sample_id"] for r in read_rows(output / "sample_table.tsv")]
    assert [(r["coefficient"], r["weight"]) for r in read_rows(output / "contrast.tsv") if r["weight"] != "0"] == [("cohortA", "1")]
    model = json.loads((output / "model.json").read_text())
    assert model["design_rank"] == 5
    assert model["residual_degrees_of_freedom"] == 15
    assert model["covariates"][0]["levels"] == ["101", "102", "103"]
    assert model["versions"]["limma"]
    assert "limma" in (output / "session_info.txt").read_text()
    assert len(read_rows(output / "normalization_factors.tsv")) == 20
    # Same inputs, cohort-only sensitivity model. The targeted batch-only gene
    # is associated with cohort before adjustment because batch is imbalanced.
    assay["item"].pop("analysis_covariates")
    assay["item"].pop("analysis_covariate_types")
    update_manifest(assay)
    unadjusted_dir = tmp_path / "unadjusted"
    unadjusted = execute(assay, unadjusted_dir)
    assert unadjusted["data"]["context"]["adjustment_status"] == "unadjusted_exploratory"
    assert "Unadjusted exploratory" in unadjusted["reply"]
    other = {r["gene_id"]: r for r in read_rows(unadjusted_dir / "de_results.tsv")}
    assert abs(float(actual["G0008"]["log2_fold_change"])) < .2
    assert float(other["G0008"]["log2_fold_change"]) > .5


@pytest.mark.parametrize("saturated", [False, True])
def test_non_estimable_models_are_rejected_without_dropping_terms(assay, tmp_path, rscript, saturated):
    rows = read_rows(assay["metadata"])
    cohort_by_sample = {r["sample_id"]: r["cohort"] for r in assay["rows"]}
    for row in rows:
        if saturated:
            row["batch"] = "shared" if row["sample_id"] in {"LAB001", "LAB011"} else row["sample_id"]
        else:
            row["batch"] = cohort_by_sample[row["sample_id"]]
    write_rows(assay["metadata"], rows[0].keys(), rows)
    assay["item"]["analysis_covariates"] = ["batch"]
    assay["item"]["analysis_covariate_types"] = {"batch": "categorical"}
    update_manifest(assay)
    message = "no residual degrees" if saturated else "rank deficient"
    with pytest.raises(RuntimeError, match=message):
        execute(assay, tmp_path / "invalid-design")
