---
sidebar_position: 3
---

import ModalityTable from '@site/src/components/ModalityTable';

# Supported data and modalities

**Clinical** describes patients and visits. **Assays** contains laboratory
measurements. **Imaging** links studies and derived measurements.
**Multimodal** shows which patients have combinations of these data.

## Supported data

<ModalityTable />

**DNA sequencing and genotyping arrays are separate assay types.** Both can
produce genotype calls. The variant browser accepts prepared panels from either
technology, but does not browse dosage matrices directly. The bundled synthetic
genotyping matrix is simulated data, not measurements from an array.

:::note[Prepared data, not raw-data processing]

COHORTome does not align reads, call variants, preprocess IDAT files, gate FCS
files, process mass spectra or segment images. Importing a modality does not
make every analysis suitable for it.

:::

## Multimodal readiness

| Question | What to check |
| --- | --- |
| Which patients have RNA **and** proteins? | Patient overlap in Multimodal |
| Were measurements taken from the same specimen or visit? | Explicit sample and timepoint links—not patient overlap alone |
| Can I analyse an image? | DICOM supports viewing; quantitative analyses need externally derived measurements |

Save the matching patients as a cohort, then select a compatible tool in Analysis.

## Analysis requirements

The selected assay's **value type**, sample links and cohort coverage determine
which tools can run. Normalized expression is not interchangeable with counts.

<details>
<summary>Requirements for curated analyses</summary>

| Workflow | Required input |
| --- | --- |
| Count-based transcriptomics | Raw counts, or the separate RSEM expected-count workflow; two compatible cohorts for comparisons |
| Methylation QC/PCA | Processed M-values and linked samples |
| Differential methylation | M-values and two disjoint cohorts overlapping the same assay |
| Immune-cell / serology comparison | Processed abundance / quantitative measurements, detailed access and at least three linked samples per cohort |

Immune-cell and serology comparisons use exploratory Wilcoxon tests with
Benjamini–Hochberg correction. They do not normalize, impute or adjust for
covariates. Review missingness and whether cell abundances are compositional.

Methylation uses externally prepared matrices or
[replaceable CpG panels](../developer-guide/methylation-feature-panels.md).
Declared covariates can support adjusted methylation models; runs without
varying covariates are labelled unadjusted.

</details>

<details>
<summary>Preparing data and linking samples</summary>

Assay manifests declare the modality, value type, feature identifiers and file
locations. Sample metadata links each assay column to a patient; imported
sample names do not have to resemble patient IDs. Use explicit specimen and
visit links rather than inferring them from a shared patient.

See [Dataset packages](../admin-guide/dataset-packages.md) for the manifest,
sample metadata and optional biosample input.

</details>

<details>
<summary>DICOM viewing and synthetic images</summary>

OHIF displays linked DICOM studies; COHORTome is not a PACS. Images may be
served locally or through a configured DICOM service. Derived measurements,
such as lesion volume, are separate assay inputs.

Bundled brain images are generated phantoms, not patient images or validated
clinical examples. See [Imaging setup](../admin-guide/dicom-viewing.md) and
[Pre-installed datasets](../user-guide/included-datasets.md).

</details>
