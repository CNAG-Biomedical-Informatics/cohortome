import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from app.dataset_validation import SCHEMAS, PackageValidationError, main, validate_package

ROOT = Path(__file__).resolve().parents[1]


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


@pytest.fixture
def package(tmp_path):
    write_json(tmp_path / "manifest.json", {"schema_version": 1, "clinical": {"representation": "snapshot"}})
    write_json(tmp_path / "clinical/records.json", [{"id": "P1:v1", "patient_id": "P1"}])
    write_json(tmp_path / "assays/manifest.json", {"version": 1, "assays": [{
        "assay_id": "rna", "modality": "transcriptomics", "data_type": "raw_counts",
        "file": "assays/transcriptomics/counts.csv", "feature_namespace": "ensembl_gene_id",
        "feature_id_column": "gene_id", "sample_id_column": "matrix_columns",
        "patient_linkage": "sample_metadata_file", "sample_metadata_file": "assays/transcriptomics/samples.tsv",
    }]})
    folder = tmp_path / "assays/transcriptomics"
    folder.mkdir()
    (folder / "counts.csv").write_text('gene_id;P1:v1\ngene1;12\ngene2;0\n')
    (folder / "samples.tsv").write_text('sample_id\tpatient_id\nP1:v1\tP1\n')
    return tmp_path


def test_schemas_are_valid():
    for path in SCHEMAS.glob("*.json"):
        Draft202012Validator.check_schema(json.loads(path.read_text()))


@pytest.mark.parametrize("name", ["datasets/synthetic-longitudinal-demo", "tests/fixtures/synthetic-access-test", "tests/fixtures/synthetic-large", "datasets/synthetic-cross-sectional-demo"])
def test_bundled_packages_are_read_only_and_valid(name, monkeypatch):
    import duckdb
    monkeypatch.setattr(duckdb, "connect", lambda *a, **kw: pytest.fail("Validator must not open DuckDB"))
    root = ROOT / name
    def digest():
        return {p.relative_to(root): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}
    before = digest()
    result = validate_package(root)
    assert result["valid"] and result["patients"] > 0 and result["assays"] > 0
    assert digest() == before


def test_clinical_only_and_person_rules(tmp_path):
    write_json(tmp_path / "manifest.json", {"schema_version": 1, "clinical": {"representation": "person"}})
    write_json(tmp_path / "clinical/records.json", {"id": "P1"})
    assert validate_package(tmp_path)["assays"] == 0
    write_json(tmp_path / "clinical/records.json", [{"id": "P1:v1"}, {"id": "P1:v2"}])
    with pytest.raises(PackageValidationError, match="one record per patient"):
        validate_package(tmp_path)


@pytest.mark.parametrize("content,reason", [
    ('gene_id;P1:v1;P1:v1\ngene1;1;2\n', "duplicate matrix sample"),
    ('gene_id;P1:v1\ngene1;1;2\n', "row width"),
    ('gene_id;P1:v1\ngene1;1\ngene1;2\n', "duplicate feature"),
    ('gene_id;P1:v1\ngene1;word\n', "numeric value"),
    ('gene_id;P1:v1\ngene1;inf\n', "non-finite"),
    ('gene_id;P1:v1\ngene1;-1\n', "non-negative"),
    ('gene_id;P1:v1\ngene1;1.5\n', "integers"),
    ('gene_id;P1:v1\ngene1;9007199254740992.1\n', "integers"),
    ('gene_id;P1:v1\ngene1;NA\n', "missing values"),
    ('gene_id;P1:v1\n', "no feature rows"),
])
def test_invalid_matrices(package, content, reason):
    (package / 'assays/transcriptomics/counts.csv').write_text(content)
    with pytest.raises(PackageValidationError, match=reason):
        validate_package(package)


@pytest.mark.parametrize("content,reason", [
    ('sample_id\tpatient_id\nP1:v1\tunknown\n', "absent from clinical"),
    ('sample_id\tpatient_id\nP1:v1\tP1\nP1:v1\tP1\n', "duplicate sample"),
    ('sample_id\tpatient_id\nother\tP1\n', "missing patient linkage"),
    ('sample_id\tpatient_id\nP1:v1\n', "row width"),
])
def test_invalid_metadata(package, content, reason):
    (package / 'assays/transcriptomics/samples.tsv').write_text(content)
    with pytest.raises(PackageValidationError, match=reason):
        validate_package(package)


def test_versions_and_duplicate_assay_ids(package):
    path = package / 'assays/manifest.json'
    data = json.loads(path.read_text())
    data['version'] = 2
    write_json(path, data)
    with pytest.raises(PackageValidationError, match="const"):
        validate_package(package)
    data['version'] = 1
    data['assays'] *= 2
    write_json(path, data)
    with pytest.raises(PackageValidationError, match="duplicate assay_id"):
        validate_package(package)


def test_conflicting_clinical_ids(package):
    write_json(package / 'clinical/records.json', {"id": "P1:v1", "patient_id": "P2"})
    with pytest.raises(PackageValidationError, match="conflicts"):
        validate_package(package)


def test_symlink_escape_is_not_read(package, tmp_path):
    outside = tmp_path.parent / (tmp_path.name + '-outside.json')
    outside.write_text('sensitive-value-not-to-be-printed')
    (package / 'clinical/outside.json').symlink_to(outside)
    with pytest.raises(PackageValidationError, match="symlinks must stay inside") as error:
        validate_package(package)
    assert 'sensitive-value' not in str(error.value)


def test_undeclared_assay_and_missing_file(package):
    path = package / 'assays/transcriptomics/extra.csv'
    path.write_text('feature_id;P1:v1\nf1;1\n')
    with pytest.raises(PackageValidationError, match="not declared"):
        validate_package(package)
    path.unlink()
    (package / 'assays/transcriptomics/counts.csv').unlink()
    with pytest.raises(PackageValidationError, match="referenced file is missing"):
        validate_package(package)


def test_cli_aggregate_output_and_exit_status(package, capsys):
    assert main([str(package)]) == 0
    output = capsys.readouterr().out
    assert json.loads(output)['patients'] == 1
    assert 'P1' not in output
    write_json(package / 'manifest.json', {"schema_version": 2})
    assert main([str(package)]) == 1
    assert json.loads(capsys.readouterr().out)['valid'] is False


def test_processed_counts_accept_fractional_values_and_explicit_links(package):
    path = package / 'assays/manifest.json'
    data = json.loads(path.read_text())
    data['assays'][0]['data_type'] = 'rsem_expected_counts'
    write_json(path, data)
    (package / 'assays/transcriptomics/counts.csv').write_text('gene_id;sample-a\ngene1;1.25\ngene2;NA\n')
    (package / 'assays/transcriptomics/samples.tsv').write_text('sample_id\tpatient_id\nsample-a\tP1\n')
    assert validate_package(package)['missing_values'] == 1
    data['assays'][0]['data_type'] = 'raw_counts'
    write_json(path, data)
    with pytest.raises(PackageValidationError, match='prefixes to match'):
        validate_package(package)


def test_root_version_and_duplicate_records(package):
    path = package / 'manifest.json'
    data = json.loads(path.read_text())
    data['schema_version'] = 2
    write_json(path, data)
    with pytest.raises(PackageValidationError, match='const'):
        validate_package(package)
    data['schema_version'] = 1
    write_json(path, data)
    write_json(package / 'clinical/records.json', [{'id': 'P1:v1'}, {'id': 'P1:v1'}])
    with pytest.raises(PackageValidationError, match='duplicate clinical record'):
        validate_package(package)


def test_parent_paths_and_missing_linkage_declaration(package):
    path = package / 'assays/manifest.json'
    data = json.loads(path.read_text())
    data['assays'][0]['file'] = '../outside.csv'
    write_json(path, data)
    with pytest.raises(PackageValidationError, match='paths must stay inside'):
        validate_package(package)
    data['assays'][0]['file'] = 'assays/transcriptomics/counts.csv'
    del data['assays'][0]['patient_linkage']
    del data['assays'][0]['sample_metadata_file']
    write_json(path, data)
    with pytest.raises(PackageValidationError, match='declare sample_metadata_file'):
        validate_package(package)


def test_clarid_validation_is_reused(package):
    path = package / 'manifest.json'
    data = json.loads(path.read_text())
    data['identifiers'] = {'clarid_subjects': {
        'file': 'identifiers/clarid.csv', 'codebook_version': '0.04', 'tools_version': '0.04'}}
    write_json(path, data)
    with pytest.raises(PackageValidationError, match='ClarID subject data file is missing'):
        validate_package(package)
