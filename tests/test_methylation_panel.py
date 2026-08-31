import hashlib
from pathlib import Path

import pytest

from scripts.prepare_methylation_panel import (
    _ensure_external_output,
    extract_compact_matrix,
    filter_nonfinite_features,
    merge_compact_matrices,
    parse_sle_supplement,
    replicated_sle_panel,
)
from app import analysis_external, query_store


def test_published_sle_panel_parser_applies_replication_rule_and_handles_joined_gene_value():
    text = """
    Supplementary Table S2
    11 65171397 cg17087974 FRMD8 0.292 0.380 -0.088 2.4E-214 0.332 0.386 -0.054 1.8E-54
    3 52909345 cg11485012 TMEM110-MUSTN10.731 0.678 0.054 8.6E-55 0.724 0.683 0.041 2.8E-19
    1 100 cg00000001 TEST1 0.100 0.200 -0.100 1.0E-20 0.200 0.210 -0.010 7.0E-6
    1 200 cg00000002 TEST2 0.100 0.200 -0.100 1.0E-20 0.220 0.210 0.010 1.0E-10
    """

    rows = parse_sle_supplement(text)
    panel = replicated_sle_panel(rows)

    assert len(rows) == 4
    assert rows[1]["gene"] == "TMEM110-MUSTN1"
    assert rows[1]["discovery_sle"] == pytest.approx(0.731)
    assert [row["cpg_id"] for row in panel] == ["cg17087974", "cg11485012"]
    assert {row["direction"] for row in panel} == {"lower_in_sle", "higher_in_sle"}


def test_compact_matrix_extraction_preserves_header_and_requested_rows(tmp_path):
    source = tmp_path / "source.csv"
    source.write_bytes(
        b"feature_id;sample-a;sample-b\n"
        b"cg00000001;0.1;0.2\n"
        b"cg00000002;0.3;0.4\n"
        b"cg00000003;0.5;0.6\n"
    )
    output = tmp_path / "compact.csv"

    stats = extract_compact_matrix(source, output, ["cg00000003", "cg00000001", "cg99999999"])

    assert output.read_bytes() == (
        b"feature_id;sample-a;sample-b\n"
        b"cg00000001;0.1;0.2\n"
        b"cg00000003;0.5;0.6\n"
    )
    assert stats["requested_feature_count"] == 3
    assert stats["matched_feature_count"] == 2
    assert stats["missing_feature_count"] == 1
    assert stats["missing_feature_ids"] == ["cg99999999"]
    assert stats["sample_count"] == 2
    assert stats["source_matrix_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert stats["compact_matrix_sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()


def test_compact_matrix_extraction_rejects_duplicate_requested_source_probe(tmp_path):
    source = tmp_path / "source.tsv"
    source.write_text(
        "feature_id\tsample-a\tsample-b\n"
        "cg00000001\t0.1\t0.2\n"
        "cg00000001\t0.3\t0.4\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate requested CpG"):
        extract_compact_matrix(source, tmp_path / "compact.tsv", ["cg00000001"])


def test_compact_matrix_merge_deduplicates_identical_shared_samples(tmp_path):
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    first.write_text(
        "feature_id;case-a;shared-control\n"
        "cg00000001;0.1;0.2\n"
        "cg00000002;0.3;0.4\n",
        encoding="utf-8",
    )
    second.write_text(
        "feature_id;case-b;shared-control\n"
        "cg00000001;0.5;0.2\n"
        "cg00000002;0.6;0.4\n",
        encoding="utf-8",
    )
    output = tmp_path / "merged.csv"

    stats = merge_compact_matrices([first, second], output)

    assert output.read_text(encoding="utf-8") == (
        "feature_id;case-a;shared-control;case-b\n"
        "cg00000001;0.1;0.2;0.5\n"
        "cg00000002;0.3;0.4;0.6\n"
    )
    assert stats["matched_feature_count"] == 2
    assert stats["sample_count"] == 3
    assert stats["duplicate_sample_count"] == 1


def test_nonfinite_feature_filter_excludes_infinite_rows_but_keeps_missing_values(tmp_path):
    matrix = tmp_path / "panel.csv"
    matrix.write_text(
        "feature_id;sample-a;sample-b\n"
        "cg00000001;0.1;0.2\n"
        "cg00000002;Inf;0.4\n"
        "cg00000003;NA;-0.2\n",
        encoding="utf-8",
    )

    stats = filter_nonfinite_features(matrix)

    assert stats["retained_feature_count"] == 2
    assert stats["excluded_nonfinite_feature_count"] == 1
    assert stats["excluded_nonfinite_feature_ids"] == ["cg00000002"]
    assert matrix.read_text(encoding="utf-8") == (
        "feature_id;sample-a;sample-b\n"
        "cg00000001;0.1;0.2\n"
        "cg00000003;NA;-0.2\n"
    )


def test_panel_builder_refuses_repository_output():
    with pytest.raises(ValueError, match="outside the repository"):
        _ensure_external_output(Path(__file__).resolve().parents[1] / "generated-panel")


def test_manifest_panel_metadata_is_exposed_and_validated(tmp_path):
    panel_path = tmp_path / "assays" / "methylation" / "panel.tsv"
    panel_path.parent.mkdir(parents=True)
    panel_path.write_text("cpg_id\ncg00000001\ncg00000002\n", encoding="utf-8")
    panel_sha256 = hashlib.sha256(panel_path.read_bytes()).hexdigest()
    item = {
        "assay_id": "sle_panel_v1",
        "modality": "methylation",
        "data_type": "m_values",
        "feature_count": 2,
        "feature_panel": {
            "panel_id": "independent_sle_ewas",
            "panel_version": "1",
            "label": "Independent replicated SLE EWAS panel",
            "requested_feature_count": 3,
            "matched_feature_count": 2,
            "missing_feature_count": 1,
            "panel_file": "assays/methylation/panel.tsv",
            "panel_sha256": panel_sha256,
            "source_matrix_sha256": "a" * 64,
            "source_publication_doi": "10.1136/annrheumdis-2017-212379",
            "independent_of_target_cohort": True,
        },
    }

    inventory = query_store._assay_inventory_metadata("methylation", "m_values", item)
    validated = analysis_external._methylation_feature_panel(str(tmp_path), item)

    assert inventory["view_type"] == "feature_panel"
    assert inventory["feature_panel"]["matched_feature_count"] == 2
    assert validated["panel_id"] == "independent_sle_ewas"
    assert validated["panel_sha256"] == panel_sha256


def test_manifest_panel_rejects_changed_definition(tmp_path):
    panel_path = tmp_path / "panel.tsv"
    panel_path.write_text("cpg_id\ncg00000001\n", encoding="utf-8")
    item = {
        "assay_id": "changed_panel",
        "modality": "methylation",
        "data_type": "m_values",
        "feature_count": 1,
        "feature_panel": {
            "panel_id": "changed",
            "panel_version": "1",
            "label": "Changed panel",
            "requested_feature_count": 1,
            "matched_feature_count": 1,
            "missing_feature_count": 0,
            "panel_file": "panel.tsv",
            "panel_sha256": "0" * 64,
        },
    }

    with pytest.raises(RuntimeError, match="does not match"):
        analysis_external._methylation_feature_panel(str(tmp_path), item)
