---
title: Frequently Asked Questions
---

# Frequently Asked Questions

[General](#general) · [Desktop](#desktop) · [Web](#web)

## General

<details>
<summary>Why is it called COHORTome?</summary>

The name combines **cohort**, the people or samples studied together, with the
scientific suffix **-ome**, which suggests a connected view across clinical,
assay, imaging-derived, and analytical data.

The typography makes that meaning explicit: **COHORT** is the primary term and
**ome** is a quieter suffix. A secondary reading, "cohort to me", reflects the
idea of bringing an authorized cohort into a researcher's workspace, but it is
wordplay rather than the main identity.

</details>

<details>
<summary>What is ClarID?</summary>

ClarID is an identifier format that encodes selected biomedical metadata in a
human-readable code, with a compact form called a stub. It supports identifiers
for subjects and biosamples.

In COHORTome, ClarID is an optional annotation alongside the original identifier.
Click a **ClarID** label to inspect its decoded fields, including the condition
name when available. You can also search for a patient by ClarID.

A **Subject ClarID** shown beside a sample describes the linked patient; it is
not a biosample ClarID. In Timeline, an assay row can instead show a **biosample
ClarID** when it explicitly links to a labelled specimen. Different specimens
may share that label. The original patient and sample IDs, together with their
source dataset, remain the identifiers COHORTome uses to link records. See
[biosamples in Dashboard](../user-guide/dashboard.md#inspect-samples-and-clinical-records).

:::note[ClarID is not anonymization]

A code can reveal metadata such as a condition. Treat it with the same care as
the record it describes; a compact stub is not encryption.

:::

See the [ClarID paper](https://doi.org/10.1186/s13326-026-00349-6)
and [clarid-tools](https://github.com/mrueda/clarid-tools).

</details>

<details>
<summary>Is COHORTome only for 3TR?</summary>

No. COHORTome is generic open-source software that can be deployed for other
approved biomedical datasets. It is being developed in the context of 3TR,
but does not depend on a particular consortium or study.

Read [Project context](../project/3tr-and-precisesads.md) for that project
context.

</details>

<details>
<summary>Is COHORTome a data warehouse?</summary>

No. Warehouses and institutional services remain responsible for storing and
distributing source data. COHORTome receives authorized releases and provides a
workspace for linking records, exploring patients and assays, finding cohorts,
and running traceable analyses.

Read [Scope And Boundaries](../project/scope-and-boundaries.md) for the division
of responsibilities.

</details>

<details>
<summary>Does COHORTome process raw medical images?</summary>

No. COHORTome can open an authorized DICOM study in OHIF, but it does not
implement a viewer, PACS, segmentation pipeline, or pixel-level model. Qualified
imaging systems and teams produce processed measurements; COHORTome can combine
those derived features with clinical and assay data.

</details>

<details>
<summary>Are results from the synthetic demo datasets biologically informative?</summary>

No. The bundled synthetic datasets are provided to test and demonstrate
COHORTome. Their values combine predefined patterns with random variation so
users can try cohort selection, missing-data handling, and analysis workflows.
The results reflect those programmed patterns, not biological findings or
clinical evidence. A significant difference or correlation in a demo is not
evidence about a disease or treatment.

See the [cross-sectional demo](../user-guide/included-datasets.md#synthetic-cross-sectional-demo)
for its contents and limitations.

</details>

<details>
<summary>Are the bundled MRI images realistic multiple-sclerosis scans?</summary>

No. Their metadata exercises an MS brain-MRI workflow, but the visible pixels
are generated procedurally without patient images. They are smoke-test fixtures for DICOM
linkage and OHIF rendering, not medically realistic MS images or scientific
evidence.

</details>

<details>
<summary>Is a language model required?</summary>

**No. COHORTome works without an LLM.** You can browse data, build cohorts,
run the built-in analyses and Pheno-Ranker, and export results.

**Connect an LLM** if you want help interpreting questions or explaining results.
Without one, Query supports the application's predefined query patterns, not
arbitrary questions. **LM Studio and an AI subscription are not required.**

You control which dataset information can be sent to a model. See
[Governed AI](../concepts/governed-ai.md) for the permissions.

</details>

<details>
<summary>How does COHORTome take RSEM expected counts into limma-voom?</summary>

RSEM expected counts estimate the fragments assigned to each gene. They remain
non-negative count-scale measurements, but can be fractional because RSEM
distributes ambiguously mapped fragments across possible transcripts or genes.
They are therefore not the same input as integer raw read counts. COHORTome
routes assays declared as `rsem_expected_counts` to a dedicated limma-voom
analysis; its DESeq2 catalog entry is reserved for assays declared as
`raw_counts`.

The current limma-voom runner performs these steps:

1. It aligns matrix columns with the selected samples, checks for finite,
   non-negative values, requires one sample per patient, and requires at least
   two samples in both Cohort A and Cohort B.
2. It creates an edgeR `DGEList`, removes weakly expressed genes with
   `filterByExpr(..., group = cohort)`, and calculates TMM normalization factors
   with `calcNormFactors`.
3. `voom` transforms the retained values to log2 counts per million and
   estimates the mean-variance trend and observation-level precision weights.
4. limma fits the weighted linear model `~ cohort`. Cohort B is the reference,
   so the tested cohort coefficient and reported log2 fold change are **Cohort
   A minus Cohort B**. A positive value means higher expression in Cohort A.
5. `eBayes` applies limma's empirical-Bayes variance moderation. `topTable`
   reports every retained gene, with Benjamini-Hochberg adjusted p-values;
   the run summary counts genes with adjusted p-value below 0.05.

:::warning[Exploratory analysis]

The current model is deliberately simple: it contains the cohort term only. It
does **not yet adjust** for age, sex, recruitment center, treatment, batch, RIN,
or other technical or clinical covariates. Treat it as an exploratory result
until an appropriate covariate-aware design is specified and validated for the
study.

:::

The short sentence shown in the Analysis thread is only the run synopsis. The
completed job's folded `Result files` section retains the full gene-level table
(`de_results.tsv`), volcano-point table, volcano plot, machine-readable summary,
run parameters, provenance bundle, and command logs.

</details>

<details>
<summary>Is COHORTome intended for clinical decisions?</summary>

No. It is an exploratory research workbench. Results require appropriate
scientific review and must not be presented as diagnosis, treatment advice, or
validated clinical decision support.

</details>

## Desktop

<details>
<summary>Do I need an account or extra setup to run analyses?</summary>

**No.** Desktop opens without signing in and runs analyses within the app.
Keep it open until an analysis finishes. Closing it interrupts active analyses,
but completed results remain saved.

</details>

<details>
<summary>Where is my work saved? Will updating the app remove it?</summary>

Chats, cohorts, settings and managed results live in a **per-user data folder**,
separate from the installed app. Replacing the app does not remove that folder.
Registered source datasets must remain available at their recorded locations.

See [storage, updates and removal](../getting-started/desktop.md#storage-updates-and-removal)
for paths and backup instructions. **Save project is not a backup**: it stores
references, not copies of datasets or results.

</details>

<details>
<summary>LM Studio is running. Why is the model unavailable?</summary>

Check that a model is loaded and its API server is running. In **Admin → Models**,
save the API URL and model name, enable the connection, then **Test connection**.
Use an address reachable from the computer running COHORTome. If LM Studio is
on your host and COHORTome is in a VM, `localhost` points to the VM, not the host.

Choose the correct **Local / External** data boundary; it is not a connectivity
switch. The connection settings persist after closing the app. See
[Connect an LLM](../admin-guide/model-providers.mdx).

</details>

## Web

<details>
<summary>Why can't I see or open a dataset?</summary>

A web administrator must enable the dataset and grant your account access.
Its query store must also be ready. Select it in **Datasets** and apply the
workspace. Ask the administrator if it is missing or needs preparation; signing
in alone does not grant access to every dataset.

See [dataset configuration](../admin-guide/datasets-and-access.mdx).

</details>

<details>
<summary>Why are background jobs unavailable?</summary>

Web background jobs need **Redis and an RQ worker**, using the same runtime and
configuration as the web server. An administrator manages these services.
The complete Docker Compose deployment includes them; starting only the web
process does not. See [starting and stopping](../admin-guide/starting-and-stopping.md).

</details>

<details>
<summary>Can I change the model connection or its dataset permissions?</summary>

An **administrator** configures providers and dataset policies. Users select an
approved provider in Settings. A deployment-managed provider may be read-only
in the interface. With multiple datasets, the strictest model-context policy
applies; selecting a provider does not override it.

See [Connect an LLM](../admin-guide/model-providers.mdx). Desktop has the same
data-sharing controls, but its local owner manages them without web accounts.

</details>
