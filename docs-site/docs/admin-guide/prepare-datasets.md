# Prepare and contribute datasets

Start here to turn clinical tables and processed assays into a COHORTome
package. Preparation scripts and study mappings live in
[COHORTome Store](https://github.com/CNAG-Biomedical-Informatics/cohortome-store).
This guide explains the workflow; the [package reference](dataset-packages)
describes the format and validator.

## Choose a route

| Your starting point | Next step |
| --- | --- |
| A study listed in the app | [Install datasets](../user-guide/install-datasets): use its reviewed fetch-and-prepare recipe. |
| A Store recipe you want to inspect or reproduce | Read that dataset's README, mapping and licensing notes, then run its preparation command. |
| Your own clinical table and assay products | Follow the steps below, starting with the small worked example. |

Adding a Store recipe does **not** make it executable from the app. The app's
fetch-and-build recipes are separately reviewed and shipped with COHORTome.
This guide does not change that mechanism.

## Start with the worked example

The Store's [minimal dataset example](https://github.com/CNAG-Biomedical-Informatics/cohortome-store/tree/main/examples/minimal-dataset)
contains a clinical CSV, a Convert-Pheno mapping, an assay matrix and explicit
sample links. Run its README commands in order to create a ZIP, validate it and
import it through **Admin → Data → Add dataset → Import local package**.

It has two invented patients, two visits each and three invented count features.
It demonstrates identity and packaging, not differential expression or biology.
No source downloads, LLM, R, Redis or running COHORTome server are needed to
prepare it. Python 3.11+, COHORTome's Python dependencies and Convert-Pheno 0.35
are required. ClarIDs are optional and deliberately omitted from this example.

## Prepare your own data

### 1. Review the source

Record the study citation, product URLs or authorized source, retrieval date,
checksums, access conditions and permitted use. Work from processed assay
products when possible; COHORTome is not a sequencing or array-QC pipeline.

Permission to access data is not permission to redistribute it. A recipe may be
shareable when its input data are not. Keep restricted inputs and patient-level
outputs outside source repositories, including their ignored folders. Do not
copy tokens, credentials or private access details into shared provenance.

### 2. Resolve identities and timepoints

Identify the patient, visit, specimen and assay-sample columns before converting.
Use one BFF object per patient/timepoint for longitudinal data, and link assay
columns through a sample table. Keep original identifiers when adapting them to
the package's conventions.

Document repeated specimens and technical replicates. Do not count them as
independent patients, average them, or discard them without a study-specific
reason. Do not invent dates from relative study days or merge conflicting rows
merely because they share a patient ID.

### 3. Map clinical variables

Use Convert-Pheno's CSV-to-BFF route with an explicit mapping file. Follow the
[clinical mapping guidance](dataset-packages#prepare-clinical-csv-data-with-convert-pheno).
Record a decision for every source column: structured mapping, retained source
metadata, assay metadata or exclusion with a reason. Review ontology matches,
units, timing, negative findings and converter placeholders.

### 4. Describe the assays

Provide feature-by-sample numeric matrices, their measurement scale and explicit
sample-to-patient links. Distinguish integer counts, RSEM expected counts,
normalized expression, microarray values and methylation scales. Record any
upstream normalization, filtering and batch correction; do not silently redo it.

Required fields are listed in the [package reference](dataset-packages#assay-tables-and-links).
A clinical-only package needs no assay manifest. ClarIDs and imaging are optional.
Unknown clinical fields should remain unknown, not be filled to match an example.

### 5. Validate, package and inspect

Run `python -m app.dataset_validation /path/to/package` using the COHORTome
checkout/environment selected for preparation. Record the validator version or
commit and its report. BFF content and terminology need separate review; this
command primarily checks package structure, identities and assay values.

For ZIP import, include `resource.json` inside the single dataset root, with
`manifest_version: 1`, `schema_version: 1`, a dataset ID and a resource version.
The example shows file checksums, provenance and archive creation. A checksum
detects changed bytes; it does not establish that the source is trustworthy.

Import into a disposable COHORTome instance, then inspect patients, visits,
clinical fields and assay coverage. Import prepares DuckDB automatically.
Installation does not change the active workspace: add the dataset to the
selection and apply it. Use the [review checklist](dataset-review-checklist)
before sharing a recipe or package.

## Contribute to Store

Keep the study README, mapping and preparation script together or clearly linked.
Include expected aggregate counts, source-specific limitations and reproducible
commands. Generated datasets and archives are not Git source files. Do not add
a release asset or catalogue entry until its contents and distribution terms
have been reviewed.

For a coding agent, read this page, the package reference, the example and the
target study's README first. Do not guess clinical meaning, units, sample
relationships, replicate handling or licensing. Record unresolved decisions
and ask the dataset owner when they affect the result.
