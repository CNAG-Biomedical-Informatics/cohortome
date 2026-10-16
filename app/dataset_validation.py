"""Read-only package checks. No registration, DuckDB writes or scientific QC."""
from __future__ import annotations

import argparse
import csv
import json
import math
from decimal import Decimal
from pathlib import Path

from jsonschema import Draft202012Validator

from app.bff import extract_patient_id, extract_visit_id
from app.query_store import (
    _detect_matrix_delimiter, _manifest_assay_sample_patient_links,
    _read_subject_clarid_rows,
)

SCHEMAS = Path(__file__).parent / "dataset_schemas"
MISSING = {"", "NA", "N/A", "NaN", "nan", "null"}


class PackageValidationError(ValueError):
    """A structural failure, with a location but no source record values."""


def _fail(location, message):
    raise PackageValidationError(f"{location}: {message}")


def _inside(root, relative):
    if not isinstance(relative, str) or not relative or "\\" in relative:
        _fail("file reference", "expected a nonempty relative POSIX path")
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        _fail("file reference", "paths must stay inside the package")
    path = root / path
    if not path.resolve().is_relative_to(root):
        _fail("file reference", "symlinks must stay inside the package")
    return path


def _json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, ValueError):
        _fail(path.name, "missing, unreadable or invalid JSON file")


def _manifest(root, relative, schema):
    data = _json(_inside(root, relative))
    validator = Draft202012Validator(_json(SCHEMAS / schema))
    error = next(validator.iter_errors(data), None)
    if error:
        location = "/".join(str(part) for part in error.absolute_path) or "$"
        # jsonschema's default message can echo entire records; never print it.
        detail = f"does not satisfy {error.validator}; see {schema}"
        if error.validator == "required" and isinstance(error.instance, dict):
            detail = "missing required fields: " + ", ".join(key for key in error.validator_value if key not in error.instance)
        elif error.validator == "anyOf":
            detail = "declare sample_metadata_file, exact_sample_id linkage, or the sample-ID prefix convention"
        _fail(f"{relative} [{location}]", detail)
    return data


def _identifier(value, location):
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        _fail(location, "identifier must be a nonempty string without surrounding whitespace")
    return value


def _clinical(root, representation):
    folder = _inside(root, "clinical")
    paths = sorted(folder.glob("*.json"))
    if not paths:
        _fail("clinical/", "at least one JSON file is required")
    patients, records, visits = set(), set(), set()
    for path in paths:
        payload = _json(_inside(root, path.relative_to(root).as_posix()))
        rows = payload if isinstance(payload, list) else [payload]
        if not rows:
            _fail(path.name, "clinical records must not be empty")
        for number, row in enumerate(rows, 1):
            location = f"clinical/{path.name}, record {number}"
            if not isinstance(row, dict):
                _fail(location, "expected a BFF record object")
            record_id = _identifier(row.get("id"), location + " id")
            if record_id in records:
                _fail(location, "duplicate clinical record id")
            try:
                patient = extract_patient_id(row)
                visit = extract_visit_id(row, fallback=record_id)
            except (TypeError, ValueError, AttributeError):
                _fail(location, "malformed patient or visit identity")
            _identifier(patient, location + " patient")
            _identifier(visit, location + " visit")
            if "patient_id" in row and _identifier(row["patient_id"], location) != patient:
                _fail(location, "patient_id conflicts with the patient resolved by the importer from id")
            if representation == "person" and patient in patients:
                _fail(location, "person representation requires one record per patient")
            if representation == "snapshot" and (patient, visit) in visits:
                _fail(location, "duplicate patient/visit pair")
            records.add(record_id)
            visits.add((patient, visit))
            patients.add(patient)
    return patients, len(records)


def _table(path):
    """Stream CSV/TSV/semicolon rows with the same delimiter detection as ingestion."""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        first = handle.readline()
        delimiter = _detect_matrix_delimiter(first)
        handle.seek(0)
        yield from csv.reader(handle, delimiter=delimiter, strict=True)


def _metadata(root, relative, patients):
    rows = _table(_inside(root, relative))
    header = next(rows, [])
    if len(set(header)) != len(header) or not {"sample_id", "patient_id"} <= set(header):
        _fail(relative, "unique headers including sample_id and patient_id are required")
    samples = set()
    for number, row in enumerate(rows, 2):
        location = f"{relative}, row {number}"
        if len(row) != len(header):
            _fail(location, "row width differs from header")
        sample = _identifier(row[header.index("sample_id")], location + " sample_id")
        patient = _identifier(row[header.index("patient_id")], location + " patient_id")
        if sample in samples:
            _fail(location, "duplicate sample_id")
        if patient not in patients:
            _fail(location, "patient_id is absent from clinical records")
        samples.add(sample)


def _matrix(root, item, patients):
    relative = item["file"]
    rows = _table(_inside(root, relative))
    header = next(rows, [])
    if len(header) < 2 or header[0] != item["feature_id_column"]:
        _fail(relative, "expected declared feature-ID header followed by sample columns")
    samples = [_identifier(s, relative + " header") for s in header[1:]]
    if len(set(samples)) != len(samples):
        _fail(relative, "duplicate matrix sample columns")
    if item.get("sample_metadata_file"):
        _metadata(root, item["sample_metadata_file"], patients)
    links = _manifest_assay_sample_patient_links(root, item, samples)
    if links["unlinked_sample_ids"]:
        _fail(relative, "matrix samples are missing patient linkage metadata")
    if any(patient not in patients for patient in links["links"].values()):
        _fail(relative, "linked patient is absent from clinical records")
    if item["modality"] == "transcriptomics" and item["data_type"] == "raw_counts":
        # The integer-count store currently uses this fixed column and prefix.
        # Do not approve a pack whose inventory and stored linkage would differ.
        if header[0] != "gene_id":
            _fail(relative, "the raw-count importer currently requires the gene_id header")
        if any(sample.split(":", 1)[0] != links["links"][sample] for sample in samples):
            _fail(relative, "the raw-count importer currently requires sample-ID prefixes to match linked patients")
    features, missing = set(), 0
    for number, row in enumerate(rows, 2):
        location = f"{relative}, row {number}"
        if len(row) != len(header):
            _fail(location, "row width differs from header")
        feature = _identifier(row[0], location + " feature_id")
        if feature in features:
            _fail(location, "duplicate feature_id")
        features.add(feature)
        for column, value in enumerate(row[1:], 2):
            if value in MISSING:
                if item["data_type"] == "raw_counts":
                    _fail(location, "raw_counts must not contain missing values (the importer would replace them with zero)")
                missing += 1
                continue
            try:
                numeric = float(value)
            except ValueError:
                _fail(f"{location}, column {column}", "expected a numeric value or documented missing token")
            if not math.isfinite(numeric):
                _fail(f"{location}, column {column}", "non-finite numeric value")
            if item["data_type"] in {"raw_counts", "rsem_expected_counts"} and numeric < 0:
                _fail(location, "count values must be non-negative")
            if item["data_type"] == "raw_counts":
                exact = Decimal(value)
                if exact != exact.to_integral_value() or exact >= 2**63:
                    _fail(location, "raw_counts requires integers in the signed 64-bit range")
    if not features:
        _fail(relative, "matrix has no feature rows")
    if "feature_count" in item and item["feature_count"] != len(features):
        _fail(relative, "declared feature_count differs from matrix")
    return len(samples), len(features), missing, links["linkage_source"]


def validate_package(root):
    """Return aggregate counts or raise PackageValidationError. Never writes files."""
    root = Path(root).resolve()
    try:
        manifest = _manifest(root, "manifest.json", "dataset.schema.json")
        patients, records = _clinical(root, manifest["clinical"]["representation"])
        clarid = manifest.get("identifiers", {}).get("clarid_subjects")
        if clarid:
            _inside(root, clarid["file"])
            _read_subject_clarid_rows(root, patients)
        assays_path = _inside(root, "assays/manifest.json")
        items = _manifest(root, "assays/manifest.json", "assays.schema.json")["assays"] if assays_path.exists() else []
        seen, declared, warnings = set(), set(), []
        samples = features = missing = 0
        for number, item in enumerate(items, 1):
            if item["assay_id"] in seen:
                _fail(f"assays/manifest.json, assay {number}", "duplicate assay_id")
            seen.add(item["assay_id"])
            for key, value in item.items():
                if key == "file" or key.endswith("_file"):
                    path = _inside(root, value)
                    if not path.is_file():
                        _fail(f"assays/manifest.json, assay {number}, {key}", "referenced file is missing")
                    declared.add(path.resolve())
            count, size, absent, linkage = _matrix(root, item, patients)
            samples += count
            features += size
            missing += absent
            if linkage == "sample_id_prefix":
                warnings.append(f"Assay {number} uses declared sample-ID prefix linkage; prefer explicit sample metadata for new packages.")
        # The runtime discovers these files even when omitted from a manifest.
        for path in _inside(root, "assays").glob("*/*.csv"):
            if path.resolve() not in declared:
                _fail("assays/", "a CSV file is not declared in the assay manifest")
        return dict(valid=True, clinical_records=records, patients=len(patients),
                    assays=len(items), assay_sample_columns=samples, feature_rows=features,
                    missing_values=missing, warnings=warnings)
    except PackageValidationError:
        raise
    except (OSError, UnicodeError, csv.Error):
        _fail("package", "unreadable file or malformed delimited table")
    except ValueError as exc:
        # Shared linkage and ClarID validators report field names/counts, not values.
        raise PackageValidationError(str(exc)) from None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="Prepared dataset directory (read only)")
    args = parser.parse_args(argv)
    try:
        result = validate_package(args.root)
    except PackageValidationError as exc:
        print(json.dumps({"valid": False, "error": str(exc)}))
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
