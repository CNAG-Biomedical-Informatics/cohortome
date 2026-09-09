import pytest

from app import query_store


def summary(path):
    stat = path.stat()
    return query_store._expected_count_summary(str(path), stat.st_mtime_ns, stat.st_size)


def test_expected_counts_preserve_fractions_and_rank_genes(tmp_path):
    matrix = tmp_path / "matrix.tsv"
    matrix.write_text("gene\tS1\tS2\ng1\t0.25\t0\ng2\t1.5\t2.75\n")
    result = summary(matrix)
    assert result["mean_total_counts_per_sample"] == 2.25
    assert result["mean_detected_genes_per_sample"] == 1.5
    assert result["top_genes"][0]["gene_id"] == "g2"
    assert result["top_genes"][0]["total_count"] == 4.25
    matrix.write_text("gene\tS1\tS2\ng1\t0\t0\n")
    assert summary(matrix)["mean_total_counts_per_sample"] == 0


@pytest.mark.parametrize("row", ["g1,NaN,1", "g1,-1,1", "g1,1", "g1,1,2\ng1,2,3"])
def test_invalid_summary_is_unavailable_not_zero(tmp_path, row):
    matrix = tmp_path / "matrix.csv"
    matrix.write_text("gene,S1,S2\n" + row + "\n")
    result = summary(matrix)
    assert result["mean_total_counts_per_sample"] is None
    assert result["top_genes"] == []


def test_large_matrix_not_read(tmp_path):
    result = query_store._expected_count_summary(str(tmp_path / "does-not-exist"), 0, 65 * 1024 * 1024)
    assert result["count_summary_status"] == "matrix_too_large"


def test_manifest_inventory_includes_expected_count_summary(tmp_path, monkeypatch):
    matrix = tmp_path / "matrix.csv"
    matrix.write_text("gene,S1,S2\ng1,0.5,1.25\n")
    monkeypatch.setattr(query_store, "_assay_manifest_items", lambda _: [
        {"assay_id": "rna", "modality": "transcriptomics", "data_type": "rsem_expected_counts", "file": "matrix.csv"}])
    monkeypatch.setattr(query_store, "_manifest_item_root", lambda *_: tmp_path)
    monkeypatch.setattr(query_store, "_assay_matrix_stats", lambda *_: {
        "patient_ids": ["P1", "P2"], "sample_ids": ["S1", "S2"],
        "sample_count": 2, "patient_count": 2, "feature_count": 1})
    item = query_store._manifest_assay_inventory(str(tmp_path), set(), {"P1", "P2"})[0]
    assert item["mean_total_counts_per_sample"] == 0.875
    assert item["top_genes"][0]["total_count"] == 1.75
