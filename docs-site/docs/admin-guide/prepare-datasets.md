# COHORTome Store

**[COHORTome Store](https://github.com/CNAG-Biomedical-Informatics/cohortome-store)
is the repository for dataset preparation and contributions.** It holds the
preparation scripts, clinical mappings, worked examples, and study-specific
provenance and licensing notes.

Use **Store** to prepare a dataset; use the **COHORTome app** to import, explore,
and analyze it. This guide explains that workflow. Start with the small example,
then adapt the mapping to your study.

:::tip[Just want to use a listed study?]

Follow [Install datasets](../user-guide/install-datasets). The app can fetch and
prepare supported studies for you; you do not need to work in Store yourself.

:::

## Try the example first

The [worked example](https://github.com/CNAG-Biomedical-Informatics/cohortome-store/tree/main/examples/minimal-dataset)
uses **two invented patients, two visits each, and three count features**.
Follow its README commands to create and validate an importable ZIP.

<figure className="datasetWorkflow" aria-label="Dataset preparation and import workflow">
  <div className="datasetWorkflowPanel">
    <div className="datasetWorkflowLabel">Prepare</div>
    <div className="datasetWorkflowTitle">COHORTome Store</div>
    <ol className="datasetWorkflowSteps">
      <li><strong>Gather inputs</strong><span>Clinical table, processed assays, sample links</span></li>
      <li><strong>Map and validate</strong><span>Run the recipe and review the checks</span></li>
    </ol>
  </div>
  <div className="datasetWorkflowTransfer">
    <span className="datasetWorkflowArrow" aria-hidden="true">→</span>
    <span className="datasetWorkflowPackage">ZIP</span>
    <span>Dataset package</span>
  </div>
  <div className="datasetWorkflowPanel">
    <div className="datasetWorkflowLabel">Use</div>
    <div className="datasetWorkflowTitle">COHORTome app</div>
    <ol className="datasetWorkflowSteps" start="3">
      <li><strong>Import the package</strong><span>DuckDB is prepared automatically</span></li>
      <li><strong>Select and explore</strong><span>Apply the dataset to your workspace</span></li>
    </ol>
  </div>
</figure>

**You need:** Python 3.11+, COHORTome's Python dependencies, and Convert-Pheno
0.35. Preparation needs no source downloads, LLM, R, Redis, or running server.
The example demonstrates packaging and patient–sample links, not biology.
ClarIDs are optional and omitted here.

Already using a Store recipe? Read that study's README, mapping, and licensing
notes, then run its preparation command.

## Prepare your study in five steps

### 1. Check the source

Use processed assay products. Record where they came from and what you are
allowed to do with them.

**Keep:** the study citation, source, retrieval date, checksums, and access and
reuse conditions.

:::warning[Access is not permission to redistribute]

A recipe may be shareable when its data are not. Keep restricted inputs and
patient-level outputs outside source repositories, including ignored folders.
Never include credentials or private access details in shared provenance.

:::

### 2. Link patients, visits, and samples

Identify these columns **before converting**. For longitudinal data, create one
Beacon Friendly Format (BFF) object per patient and timepoint. Link assay columns
to those records through a sample table, retaining original identifiers.

**Check:** can every assay sample be traced to the correct patient and visit?

<details>
<summary>Repeated samples, technical replicates, and missing dates</summary>

Document repeated specimens and technical replicates. Do not count them as
independent patients, average them, or discard them without a study-specific
reason. Do not invent dates from relative study days or merge conflicting rows
just because they share a patient ID.

</details>

### 3. Map the clinical table

Use **Convert-Pheno CSV → BFF** with an explicit mapping file. Review the
resulting diagnoses, measurements, units, and timing—not just whether conversion
finishes.

**Keep:** a decision for every source column: structured mapping, source
metadata, assay metadata, or exclusion with a reason.

<details>
<summary>Clinical mapping checks</summary>

Follow the [clinical mapping guidance](dataset-packages#prepare-clinical-csv-data-with-convert-pheno).
Check ontology matches, units, negative findings, and converter placeholders.
Unknown fields should remain unknown, not be filled to match the example.

</details>

### 4. Describe the assays

Provide numeric matrices with **features as rows and samples as columns**,
explicit sample links, and the measurement scale. Record any upstream
normalization, filtering, or batch correction; do not silently redo it.

**Check:** integer counts, RSEM expected counts, normalized expression,
microarray values, and methylation values are distinct input types.

<details>
<summary>Required files and optional data</summary>

See the [assay fields and links](dataset-packages#assay-tables-and-links).
A clinical-only package needs no assay manifest. ClarIDs and imaging are
optional. COHORTome is not a sequencing or array-QC pipeline.

</details>

### 5. Validate and open it

Run the validator in your COHORTome preparation environment:

```bash
python -m app.dataset_validation /path/to/package
```

Then test the ZIP in a disposable installation:

1. Open **Data → Add dataset → Import local package** (under **Admin** on Web).
2. Wait for import and automatic DuckDB preparation to finish.
3. Select the dataset and apply it to the workspace.
4. Inspect patients, visits, clinical fields, and assay coverage.

**Keep:** the validator version or commit and its report. Validation checks
structure, identities, and assay values; clinical meaning and terminology still
need review.

<details>
<summary>ZIP metadata and checksums</summary>

Include `resource.json` inside the single dataset root, with
`manifest_version: 1`, `schema_version: 1`, a dataset ID, and a resource version.
The worked example creates the archive and records file checksums and provenance.
A checksum detects changed bytes; it does not establish source trustworthiness.
See the [package reference](dataset-packages) for the full format.

Installation does not change the active workspace: selecting and applying the
dataset is a separate step.

</details>

## Ready to contribute?

Use the [review checklist](dataset-review-checklist) before sharing a recipe or
package. Keep these together or clearly linked in Store:

- **Study README:** sources, licensing, expected counts, and known limitations.
- **Mapping and script:** reproducible preparation commands and field decisions.
- **Validation record:** the checks performed and unresolved issues.

Generated datasets and archives are not Git source files. Review their contents
and distribution terms before adding release assets or catalogue entries.
Adding a Store recipe does **not** make it executable in the app: fetch-and-build
recipes are separately reviewed and shipped with COHORTome.

<details>
<summary>Preparing data with a coding agent</summary>

Have the agent read this page, the package reference, the worked example, and the
study README first. Do not guess clinical meaning, units, sample relationships,
replicate handling, or licensing. Record unresolved decisions and ask the dataset
owner when they affect the result.

</details>
