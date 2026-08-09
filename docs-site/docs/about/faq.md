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

## Is COHORTome intended for clinical decisions?

No. It is an exploratory research workbench. Results require appropriate
scientific review and must not be presented as diagnosis, treatment advice, or
validated clinical decision support.
