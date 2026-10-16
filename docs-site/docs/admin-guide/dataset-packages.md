# Validate a dataset package

A COHORTome dataset package is a directory of clinical JSON, optional assay
tables and manifests. It is not a DuckDB database or a saved user workspace.
Bundled synthetic examples use the same checks as contributed packages.

This first contract describes the existing input format. It does not introduce
a new clinical data model, an archive installer or a scientific QC pipeline.

## Validate before importing

From a COHORTome checkout with its Python dependencies installed:

```bash
python3 -m app.dataset_validation /path/to/prepared-dataset
```

The command reads files without modifying them, registering a dataset, opening
DuckDB or changing application state. It prints aggregate counts and warnings,
or the first structural error, and exits with status 0 for success or 1 for an
invalid package. Errors identify fields and record/row positions without
printing patient identifiers or measurement values.

It scans matrix rows to check structure and value types, so validation time is
proportional to input size. Run it during package preparation, not on each
Dashboard visit. No matrix normalization or filtering is performed.

Validation is currently a standalone preparation command. Registration and
store preparation retain their existing checks; they do not yet automatically
invoke this validator. A successful report is not a licence review, a complete
BFF validation or a guarantee that every analysis supports the dataset.

## Two small schemas

The canonical JSON Schemas ship with the Python application:

- `app/dataset_schemas/dataset.schema.json` checks `manifest.json`.
- `app/dataset_schemas/assays.schema.json` checks `assays/manifest.json`.

They use JSON Schema draft 2020-12. The existing `schema_version: 1` and assay
`version: 1` are required; other versions are rejected. Additional descriptive
fields are allowed, but are not automatically understood by the application.
These are format versions, not dataset release numbers. Resource recipes should
pin the COHORTome release/commit providing their validator.

```text
dataset/
  manifest.json
  clinical/
    records.json
  assays/                         Optional
    manifest.json
    transcriptomics/
      counts.csv
      sample_metadata.tsv
  identifiers/                    Optional
    clarid_subjects.csv
```

### Clinical records

The root manifest must declare `clinical.representation` as `person` or
`snapshot`. Each `clinical/*.json` file contains a BFF-style record object or
an array of record objects, with nonempty string `id` values unique across the
package. An `individuals` wrapper is not supported by this contract.

The validator uses the importer's patient/visit extraction rules. `person`
requires one record per patient; `snapshot` permits repeated patients but not
duplicate patient/visit pairs. A supplied `patient_id` must agree with the
patient resolved from `id`. In the existing convention, `P1:week_0` resolves to
patient `P1`. Clinical identifiers are strings; numeric ClarID subject numbers
are separate identifiers.

This checks record identity, not every nested BFF field, ontology term, date,
unit or clinical measurement. Unknown clinical information need not be invented
to make an example complete. Missing dates or measurements can still make a
particular analysis unavailable.

### Assay tables and links

Each manifest entry requires `assay_id`, `modality`, `data_type`, `file`,
`feature_namespace`, `feature_id_column` and `sample_id_column: matrix_columns`.
Assay IDs are unique within the package. Modality and data-type names are
nonempty strings, not an ever-growing enum; declaring a new value does not
add an analysis implementation for it.

Matrices are numeric CSV, semicolon-delimited CSV or TSV, with one explicit
feature-ID header followed by sample-ID columns. Features and samples must be
unique within each matrix, rows must match the header width, and any declared
`feature_count` must match. R-style implicit row-name headers must be repaired
by the preparer, not guessed during validation.

Use `sample_metadata_file` with unique `sample_id` and `patient_id` columns.
Every matrix sample must link to a clinical patient; metadata may contain
additional samples, provided their patient links are valid. All metadata rows
must have consistent width. Visit, specimen and covariate columns are optional;
their scientific interpretation and analysis-specific requirements remain
outside this first validator.

The existing declared alternatives remain supported: `patient_linkage:
exact_sample_id`, or `patient_id_column: derived_from_sample_id_prefix`.
Prefix linkage produces a warning; explicit metadata is preferred for new
packages. The same linking helper is used by ingestion and validation.

Empty cells, `NA`, `N/A`, `NaN`, `nan` and `null` are counted as missing values
in processed matrices. Other values must be numeric and finite. Count types
must be non-negative. `raw_counts` must be non-missing integers within the
signed 64-bit range; `rsem_expected_counts` may be fractional. These checks
verify the declared representation, not whether the processing method was
scientifically appropriate.

**Current integer-count importer limitations:** transcriptomic `raw_counts`
matrices require the header `gene_id`, and sample-ID prefixes must match their
linked patients. The validator rejects other combinations because this importer
still derives patient links from sample IDs. It also rejects missing raw counts
because the importer would otherwise convert them to zero. These limitations
must be resolved explicitly before preparing packs that require another layout.

Every referenced assay file must exist inside the package. CSV files discovered
under `assays/*/` must be declared as assay or auxiliary files, preventing
accidental ingestion through filename-based fallback. Paths cannot be absolute,
contain parent traversal or resolve through symlinks outside the package.

### Optional ClarIDs and imaging

When a ClarID subject sidecar is declared, the validator reuses the existing
column, uniqueness and exact clinical-coverage checks. ClarIDs are not required.

Numeric imaging-derived assay tables follow the same matrix checks. DICOM
pixels, DICOM study manifests and DICOMweb services are not validated by this
command. They still need their own checks before distribution or viewing.

## What this does not package

Keep user accounts, access grants, model-provider policies, credentials and
runtime caches out of distributed datasets. The receiving deployment sets its
own access rules. Provenance, licence review, archive checksums and reproducible
preparation recipes belong to resource release preparation; they are not yet
required fields in these minimal schemas.
