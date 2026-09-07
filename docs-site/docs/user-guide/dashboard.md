---
sidebar_position: 2
---

# Dashboard

Use `Dashboard` to check the data in your current workspace before choosing an analysis.

The Dashboard distinguishes loading, an empty workspace, and an unavailable
summary. If loading fails or the summary request times out after 30 seconds,
use **Retry dashboard**. This requests the summary again without switching
datasets, preparing stores, or importing data. A workspace with no patient
records is shown as empty, not as a connection failure.

When a dataset switch fails before it is applied, the previous workspace stays
active. Check the message in **Datasets** before retrying. A dataset whose store
is not ready must be prepared by an administrator; waiting for the Dashboard
will not prepare it.

Use it to answer:

- what is currently loaded
- how many patients and timepoints are in the workspace
- which diseases and medications are most common
- which assay modalities are available in the current scope

## Clinical dashboard

The clinical dashboard gives a workspace-level summary of:

- total patients
- total timepoints
- disease distribution
- medication distribution
- visit burden

This is the fastest way to sanity-check that the right datasets are loaded before you start filtering in `Query` or interpreting in `Analysis`.

## Timeline

Use Timeline to inspect dated clinical records and available samples. **Show
events** controls which event categories appear in the plot and Events table.
Click a marker to inspect that event, or a coverage bar to inspect the patient's
first visible event. The table's Inspect buttons also work without using the plot.
Drag to zoom; zooming changes the plot only, not the Events table or analysis scope.

The **Select patient** checkboxes are separate from inspection and filtering.
They select whole patients, including records outside the visible dates or event
categories. Selecting one does not hide other patients' events. **Save cohort**
and **Open in Analysis** appear when patients are selected; neither action saves
a time-window restriction. Timepoint-restricted analysis is not implemented by
this view.

A single dated observation is a point, not a follow-up duration. Undated events
remain available in the table when their event categories are shown.

## Assays dashboard

The assays dashboard shows which dataset each assay comes from.

It shows:

- assay modalities currently visible in the workspace
- dataset-level counts and metadata
- workspace-level assay summary
- laboratory assay coverage, excluding imaging

In a multi-dataset workspace, assay provenance matters. If two datasets are active, the dashboard helps confirm whether the assay side really comes from both.

## Imaging dashboard

Open **Dashboard → Imaging** for DICOM studies, viewer readiness, and derived
imaging measurement cards. Imaging is not included in the Assays filters or
totals. Multimodal still includes imaging alongside clinical and laboratory data.

COHORTome lists authorized study metadata and launches OHIF. Pixel data stays in Orthanc or another DICOMweb service.

In the bundled demo dataset, the first DICOM study is a stable viewer smoke test
and the additional synthetic MS brain MRI studies behave like patient examples.
They appear in the same DICOM imaging list because COHORTome treats both as authorized
study metadata linked to samples. The smoke-test study is useful when checking
that OHIF renders real pixels; the MS brain studies are better examples for the
kind of clinical imaging workflow the project is expected to support.

## Multimodal dashboard

The multimodal dashboard checks how well clinical records and different assays overlap.

`Multimodal analysis readiness` is a QC panel. It reports modality coverage,
patient-level overlap, exact sample/timepoint overlap, DICOM-clinical linkage
issues, and deterministic suggestions for what analyses are valid next. It does
not run cross-modal statistics; it tells you whether the workspace is ready for
them. Suggestions whose requirements are met include `Open in Analysis`, which
prefills a focused Analysis prompt for the current workspace but does not run it
automatically.

`Multimodal feature matrix` builds a bounded sample-level preview for the full
workspace. It joins clinical covariates, selected assay features, derived
imaging matrices, and DICOM viewer metadata by exact sample/timepoint ID. Raw
DICOM pixels are not converted into numeric analysis features in this step.

## Patient list and patient detail

The patient list groups records by person. An analysis may still use individual
samples or timepoints from those records.

When multiple datasets are active:

- patient cards may show dataset provenance
- patient detail may show dataset provenance as well

This is intentional. It helps avoid confusion about where a patient summary came from.

## When to use Dashboard first

Use `Dashboard` before `Query` if you need to:

- confirm the current workspace after changing datasets
- verify that healthy controls or private datasets are really loaded
- check whether the workspace looks mixed across several datasets
- understand whether the assay side is populated before asking assay questions

## Practical workflow

Typical pattern:

1. apply one or more datasets in `Datasets`
2. open `Dashboard`
3. confirm patient/timepoint totals and high-level distributions
4. continue to `Query` or `Analysis`

## What Dashboard is not for

`Dashboard` is not the main place for:

- saving reusable subsets
- A/B cohort comparison
- long threaded interpretation
- Pheno-Ranker similarity work

Those belong respectively to:

- `Query`
- `Analysis`
- `Pheno-Ranker`
