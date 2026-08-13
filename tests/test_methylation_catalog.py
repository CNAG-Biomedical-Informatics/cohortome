from app import analysis_catalog


def _catalog_items_by_id():
    return {item["id"]: item for item in analysis_catalog.load_analysis_catalog()}


def test_methylation_catalog_declares_thin_external_matrix_contract():
    items = _catalog_items_by_id()

    qc = items["methylation-qc-pca"]
    assert qc["runner_ref"] == "methylation_qc_pca"
    assert qc["runner_type"] == "rscript"
    assert qc["execution_backend"] == "job"
    assert qc["required_modalities"] == ["methylation"]
    assert qc["required_data_types"] == ["m_values"]
    assert qc["analysis_level"] == "sample"
    assert qc["default_compare_mode"] is False

    differential = items["methylation-limma-differential-methylation"]
    assert differential["runner_ref"] == "methylation_limma_differential_methylation"
    assert differential["runner_type"] == "rscript"
    assert differential["execution_backend"] == "job"
    assert differential["required_modalities"] == ["methylation"]
    assert differential["required_data_types"] == ["m_values"]
    assert differential["analysis_level"] == "sample"
    assert differential["default_compare_mode"] is True
    assert differential["supports_compare_mode"] is True
    assert differential["minimum_samples_per_cohort"] == 2


def test_methylation_catalog_requires_a_matching_processed_m_value_assay(monkeypatch):
    item = _catalog_items_by_id()["methylation-qc-pca"]
    monkeypatch.setattr(analysis_catalog.shutil, "which", lambda name: "/usr/bin/Rscript")

    available = analysis_catalog._availability_for_item(
        item,
        granularity_ceiling="detailed",
        assay_datasets=[{"modality": "methylation", "data_type": "m_values"}],
    )
    incompatible = analysis_catalog._availability_for_item(
        item,
        granularity_ceiling="detailed",
        assay_datasets=[{"modality": "methylation", "data_type": "beta_values"}],
    )

    assert available["available"] is True
    assert incompatible["available"] is False
    assert "m_values" in incompatible["unavailable_reason"]
