---
sidebar_position: 7
---

# Methylation feature panels

COHORTome treats a high-dimensional methylation matrix like another governed
analysis source, not like a table that must be fully materialized in DuckDB.
The complete processed matrix remains external and immutable. DuckDB stores
only assay inventory, sample-to-patient linkage, technical metadata, and compact
result summaries.

This boundary is not an admission that COHORTome cannot load every CpG. It is a
scientific scoping decision: an interactive or publication workflow often needs
a defined feature panel rather than every measured probe.

## Responsibility for data quality

The data producer remains responsible for array processing, normalization,
probe filtering, and primary assay quality control. COHORTome does not certify
or repeat those upstream steps from a supplied processed matrix.

COHORTome has two narrower responsibilities:

1. **Ingestion validation:** verify dimensions, identifiers, linkage, declared
   checksums, missingness, finite values, and compatibility with the selected
   panel.
2. **Exploratory diagnostics:** optionally report distributions, principal
   components, outliers, and associations with declared technical covariates.

The interface and persisted provenance must distinguish provider-declared QC,
COHORTome ingestion validation, and exploratory diagnostics.

### Non-finite M-values

Processed M-value exports can contain `Inf` or `-Inf`, commonly when the
underlying beta value is exactly zero or one. COHORTome does not replace these
values with an arbitrary finite number. During protected panel preparation, a
probe containing any infinite value is excluded from the compact analysis
matrix. Ordinary declared missing values remain missing and are handled by the
selected curated runner.

Panel provenance reports these categories separately:

- requested probes from the registered panel definition;
- probes absent from the supplied source matrix;
- source-matched probes excluded because at least one value was infinite;
- retained probes available to Analysis.

The excluded probe identifiers remain in the protected preparation report so
the decision is auditable. This is COHORTome ingestion validation, not a claim
that upstream array QC or normalization has been repeated.

## Full assay and panel views

A methylation assay can expose multiple replaceable feature views over the same
external source matrix. A panel is a small CSV or TSV containing at least:

```text
cpg_id
cg00000000
cg00000001
```

Optional columns may include `gene`, `module`, `direction`, `source`, and a
short description. The panel definition should record:

- a stable panel identifier, label, and version;
- the scientific selection rule and intended use;
- the source publication or registry;
- the panel-file checksum;
- the source-matrix checksum;
- requested, matched, missing, and duplicate probe counts;
- the array annotation or genome build when known;
- whether feature selection was independent of the analyzed cohort or outcome.

Replacing a shared panel creates a new version. It must not silently overwrite
the definition associated with an existing result. Administrators can register
shared dataset panels, while users select among approved panels for an Analysis
run. A later user-upload workflow may add temporary user-scoped panels using the
same contract, validation, and provenance fields.

## Efficient extraction

Panel installation should create a compact protected matrix once. Analyses then
read that derivative instead of scanning the complete source matrix repeatedly.

For delimited matrices whose first field is the CpG identifier, extraction does
not require parsing every numeric value:

1. preserve the source header;
2. perform one sequential fixed-string scan using the requested CpG IDs;
3. verify that each retained row's first field exactly matches the panel;
4. reject duplicate source or panel identifiers;
5. report requested, matched, and missing probes;
6. hash the panel, source, and compact output before publication.

This is substantially lighter than parsing, normalizing, or merging the full
matrix. If frequent ad hoc panel changes later make sequential scans expensive,
a small sidecar mapping CpG IDs to byte offsets can support direct row retrieval.
The sidecar contains identifiers and offsets, not methylation values. It should
only be added when actual usage justifies the extra format and lifecycle.

The repository includes `scripts/prepare_methylation_panel.py` for this
protected preparation step. It reconstructs the independent SLE panel directly
from the authors' supplementary Table S2, verifies that the published rule
selects exactly 7,245 unique CpGs, hashes the source and outputs, and performs a
single byte-streaming extraction. It refuses to write outputs inside the source
repository. The supplementary material is CC BY-NC 4.0 and is therefore fetched
or supplied separately rather than vendored in COHORTome's Apache-licensed
source tree.

For a generic administrator-supplied panel, use the same compact-matrix
contract and record the fields listed above. The first publication helper is
invoked from the repository root as follows, with all input and output paths in
the protected dataset-preparation area:

```bash
python3 scripts/prepare_methylation_panel.py \
  --supplement-pdf /protected/input/supplementary-table-s2.pdf \
  --source-matrix /protected/release/assays/methylation/m-values.csv \
  --output-dir /protected/next-release/assays/methylation/panels/independent-sle-ewas-v1
```

Repeat `--source-matrix` for disease-partition matrices. The helper requires
identical panel coverage and CpG order, compares every duplicated sample value,
and retains one canonical column only when those values agree exactly.
After extraction, probes containing infinite M-values are excluded rather than
coerced; requested, source-matched, absent, non-finite-excluded, and retained
counts are recorded separately in `panel.json`.

The output contains `panel.tsv`, the compact `m_values.csv`, and `panel.json`.
The dataset manifest registers the compact matrix as another methylation
M-value assay view and adds the `feature_panel` object from `panel.json`, using
release-relative paths. The source assay and panel view may coexist; Analysis
then shows the panel as an explicitly labelled assay choice.

## Publication panels

The PRECISESADS molecular-stratification study selected 4,144 CpGs by identifying
features with greater variability in cases than controls before its integrative
clustering analysis. That exact set is the best panel for reproducing the
published feature space, but the probe identifiers are not included in the
article or the supplementary-methods PDF available to this project. Re-running
the published rule on a smaller disease subset would produce a new panel and
must not be described as the original 4,144-CpG panel.

An independent alternative is the replicated systemic lupus erythematosus panel
reported by Imgenberg-Kreuz and colleagues. That whole-blood 450K study reported
7,245 replicated differentially methylated CpGs, with strong signals in type-I
interferon-regulated genes. Its probe table is provided as supplementary material
and is suitable for an external-replication analysis:

- [DNA methylation mapping identifies gene regulatory effects in patients with systemic lupus erythematosus](https://pmc.ncbi.nlm.nih.gov/articles/PMC5909746/)
- [EWAS Catalog downloads and metadata contract](https://www.ewascatalog.org/download/)

For a publication workflow, label this explicitly as an **independent replicated
SLE EWAS panel**, not as a PRECISESADS panel. A defensible analysis can test its
coverage in the supplied assay, its methylation pattern in the authorized SLE
cohort, and its concordance with interferon-related transcriptomic, immune-cell,
and serology measurements.

## Current implementation boundary

The first implementation is deliberately small:

- manifest-declared, versioned shared panel views;
- one selected complete-assay or panel view per methylation run;
- protected one-time compact-matrix extraction with checksums;
- panel identity, provenance, and match statistics in every result;
- no complete CpG-value ingestion into DuckDB.

In-app panel upload and lifecycle management remain deferred until the
publication workflow establishes the required user experience. For now,
administrators install panel views through protected dataset preparation and
users select an approved view in Analysis.
