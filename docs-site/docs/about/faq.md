---
title: Frequently Asked Questions
---

# Frequently Asked Questions

## Why is it called COHORTome?

The name combines **cohort**, the people or samples studied together, with the
scientific suffix **-ome**, which suggests a connected view across clinical,
assay, imaging-derived, and analytical data.

The typography makes that meaning explicit: **COHORT** is the primary term and
**ome** is a quieter suffix. A secondary reading, "cohort to me", reflects the
idea of bringing an authorized cohort into a researcher's workspace, but it is
wordplay rather than the main identity.

The displayed name is **COHORTome**. Technical identifiers stay lowercase and
simple: the repository, Python package, documentation path, and asset prefix use
`cohortome`, while application environment variables use `COHORTOME_`.

## Is COHORTome only for 3TR?

No. COHORTome is generic open-source software that can be deployed for other
approved biomedical datasets. Its first planned consortium-scale deployment is
in the context of 3TR, with PRECISESADS as the first real reference
implementation.

Read [3TR And PRECISESADS](../project/3tr-and-precisesads.md) for that project
context.

## Is COHORTome a data warehouse?

No. Warehouses and institutional services remain responsible for storing and
distributing source data. COHORTome receives authorized releases and provides a
workspace for linking records, exploring patients and assays, finding cohorts,
and running traceable analyses.

Read [Scope And Boundaries](../project/scope-and-boundaries.md) for the division
of responsibilities.

## Does COHORTome process raw medical images?

No. COHORTome can open an authorized DICOM study in OHIF, but it does not
implement a viewer, PACS, segmentation pipeline, or pixel-level model. Qualified
imaging systems and teams produce processed measurements; COHORTome can combine
those derived features with clinical and assay data.

## Are the bundled MRI images realistic multiple-sclerosis scans?

No. Their metadata exercises an MS brain-MRI workflow, but the visible pixels
are derived from pydicom test data. They are smoke-test fixtures for DICOM
linkage and OHIF rendering, not medically realistic MS images or scientific
evidence.

## Is a language model required?

No. Supported questions and analyses can run through deterministic application
logic. An administrator may optionally configure approved language-model
providers for more flexible query planning and result explanation. Dataset
policy still determines what information, if any, may be sent.

Read [Governed AI](../concepts/governed-ai.md) for the operating model.

## How does COHORTome take RSEM expected counts into limma-voom?

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

The current model is deliberately simple: it contains the cohort term only. It
does **not yet adjust** for age, sex, recruitment center, treatment, batch, RIN,
or other technical or clinical covariates. Treat it as an exploratory result
until an appropriate covariate-aware design is specified and validated for the
study.

The short sentence shown in the Analysis thread is only the run synopsis. The
completed job's folded `Result files` section retains the full gene-level table
(`de_results.tsv`), volcano-point table, volcano plot, machine-readable summary,
run parameters, provenance bundle, and command logs.

## Is COHORTome intended for clinical decisions?

No. It is an exploratory research workbench. Results require appropriate
scientific review and must not be presented as diagnosis, treatment advice, or
validated clinical decision support.
