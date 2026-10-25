# Validate a dataset package

For the preparation workflow and a runnable example, start with
[Prepare and contribute datasets](prepare-datasets). This page is the format
reference; the canonical schemas and validator remain in the application.

## Source preparation

The app ships reviewed recipes for GSE85034, GSE117239, GSE191328, GSE42296,
GSE68310 and IBDMDB. They download original processed products, verify fixed
sizes/checksums and create the same package contract described below. No remote
preparation code runs. `app/source_builders/sources.json` records the additional
source products; GSE85034's original specification is in `app/geo_source.py`.
The catalogue in `config/resources.json` supplies the source-review notices.

The adapters reuse the reviewed COHORTome Store mappings and preserve source
patient/sample/visit relationships. Convert-Pheno and ClarID-Tools perform the
clinical mapping and identifier generation. Pandas is a Python runtime
dependency for the additional tabular recipes. Generated data belong in the
configured import storage, never in a source checkout or release bundle.

Each package retains its source checksums, clinical mapping, terminology audit,
recipe version and relevant exclusions. The local installation receipt also
records the source-review acknowledgement. These records document preparation;
they do not establish biological validity or grant data redistribution rights.

GSE65391 is deliberately not enabled until its replicate ambiguity is resolved.
GSE11903 remains excluded. The two bundled synthetic datasets cannot be installed
again through the catalogue.

## Package structure and validation

A COHORTome dataset package is a directory of clinical JSON, optional assay
tables and manifests. It is not a DuckDB database or a saved user workspace.
Bundled synthetic examples use the same checks as contributed packages.

This contract describes the input format. It does not introduce a new clinical
data model or a scientific QC pipeline. To install a prepared archive, see
[Install datasets](../user-guide/install-datasets).

## Prepare clinical CSV data with Convert-Pheno

For project-specific clinical tables, use **Convert-Pheno's CSV → BFF route**
with a reviewed Mapping V2 YAML or JSON file. This avoids writing a separate
clinical converter for each resource. When preparing your own package, run
conversion before ZIP import; that import does not run Convert-Pheno. The app's
separate fetch-and-prepare route does run the tools in its shipped recipes.

The mapping relates source columns to demographics, diagnoses, phenotypic
features, measurements, treatments and other BFF fields. Convert-Pheno can
resolve ontology labels against its terminology databases and write an audit
of those decisions. See its **Mapping Files** documentation and
`t/csv2bff/in/csv_mapping.yaml` example in the Convert-Pheno repository.

```bash
convert-pheno \
  -icsv clinical.csv --separator ',' \
  --mapping-file mapping.yaml --search exact \
  --term-audit terminology.tsv \
  -obff individuals.json

bff-tools validate -i individuals.json -nc -ne
```

Review the terminology audit and validation report before packaging the output
under `clinical/`. A successful ontology lookup confirms a label match, not
that the concept correctly describes the source variable. Check direct term
IDs too; do not relax matching thresholds just to obtain a result.

### Keep timepoints separate

For longitudinal resources, prepare **one BFF object per patient/timepoint**,
with a stable patient identity and distinct record/visit identity. Set
`clinical.representation: snapshot` in the package manifest. A composite ID
such as `P1:visit_2` keeps the patient and snapshot distinguishable.

In the Convert-Pheno mapping, use the patient and timepoint columns in
`beacon.individuals.id.sourceFields`. Use `records: {}` when neither `_visit`
annotations nor baseline propagation is wanted. The containing snapshot
provides the timepoint context for its clinical fields, including changing
phenotypes; there is no need to annotate every measurement with `_visit`.

Source rows may describe specimens or assay products rather than visits.
Reconcile them before conversion using documented visit identifiers. Do not
merge solely on patient and week, select the first conflicting value, or
silently carry measurements into later visits. Keep distinct specimens linked
through assay sample metadata. Relative study weeks are not calendar dates.

### Account for every source variable

Keep a mapping inventory with one decision per source column:

- Map clinical variables to suitable BFF fields, retaining units, timing and
  explicit negative findings.
- Preserve useful source-specific information when no suitable BFF field or
  ontology term exists. Convert-Pheno retains source columns under
  `info.CSV_columns` by default; this is provenance, not structured mapping.
- Keep assay processing metadata with the assays or samples.
- Document exclusions and ambiguous meanings. Missing values are not zero,
  negative findings or evidence that a treatment was never taken.

Do not automatically use identifiers, administrative fields or all retained
source columns as Pheno-Ranker inputs. Review medication status separately
from medication history, and distinguish age at consent from age at a visit.
Check converter defaults: placeholder dates or unknown-age sentinels must not
be imported as observations.

### IBDMDB mapping status

The current recipe maps sex, Crohn disease/ulcerative colitis and 224 CRP/ESR
measurements into 898 clinical snapshots for 112 participants. It reconciles
source modality rows using participant, visit and relative week, retains other
source fields, and removes converter placeholders. This is not a complete
structured mapping of every clinical variable. See the Store's
[mapping notes](https://github.com/CNAG-Biomedical-Informatics/cohortome-store/blob/main/datasets/ibdmdb/CLINICAL_MAPPING.md)
for decisions and the distinction between the integrated package and the older pilot.

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

Run this command before packaging. The ZIP/source installer also invokes the
package validator before registration and automatic DuckDB preparation. Direct
registration and store rebuilding have their own checks; they are not a
substitute for this preparation review. A successful report is not a licence
review, complete BFF validation or a guarantee that every analysis supports the dataset.

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

For ZIP import, the single dataset root must also contain `resource.json` with
`manifest_version: 1`, `schema_version: 1`, `dataset_id` and `version`. This is
release metadata, separate from `manifest.json`. See the
[worked example](https://github.com/CNAG-Biomedical-Informatics/cohortome-store/tree/main/examples/minimal-dataset)
for file checksums, preparation provenance and the archive checksum record.

Keep user accounts, access grants, model-provider policies, credentials and
runtime caches out of distributed datasets. The receiving deployment sets its
own access rules. Provenance, licence review, archive checksums and reproducible
preparation recipes belong to resource release preparation; they are not yet
required fields in these minimal schemas.
