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

## Patient overview

Open **Dashboard → Patients** and start typing a patient ID or ClarID.
The search shows up to 12 matches from the active datasets. Select a match with
the mouse, or use the arrow keys and Enter. Each result identifies its source
dataset; matching identifiers from different datasets are not combined.

The patient card shows clinical record and assay counts, followed by one row
per linked sample identifier and assay. Collection date, visit, specimen
material, and sample ClarID appear only when supplied in sample metadata.
Unknown fields say **Not recorded**. Patient linkage is labelled as a metadata
table, exact identifier, or an explicitly declared dataset ID convention.

This is an inventory of data available in COHORTome, not a record of every assay
ever performed. Sample identifiers do not necessarily denote distinct biological
specimens. Unavailable assays and missing linkage are reported under inventory
limitations, not counted as successful matches. Imaging remains in its own view.
The inventory reads matrix headers and linkage metadata; it does not scan assay
values or perform quality control.

Patient search and details require **Detailed** access to all datasets in the
workspace. **View this patient's timeline** opens
Timeline filtered to that patient. Returning to Patients preserves the inventory.
In a multi-dataset workspace, the timeline keeps patients separate by dataset,
even when their source identifiers match.

## Timeline

The graphical timeline shows patients by dataset and recorded date. Patient-span
bars, coloured modality markers, zoom and click-to-inspect remain available.

Use **Has data → Proteomics** to find patients with linked proteomics data.
Multiple checked types mean the patient must have **all** of them. Clinical visits
remain visible; click plot legend items to hide or show modality markers without
changing which patients match. Grey bars span the earliest to latest recorded
observations; they do not imply continuous monitoring between those dates.
OLINK assays are grouped under Proteomics; their assay names remain in inspection.

The **Date not recorded** column includes available modalities without a usable
collection date. These patients are not discarded, and assays are never placed at
an inferred clinical visit. Dates are calendar dates, not aligned study visits.

Select a dataset or explore all workspace datasets, 40 patients per page.
Matching patient IDs in different datasets remain separate. Click a marker, span
or patient name to inspect clinical evidence and linked samples/assays below.
Patients provides ID/ClarID lookup; Query provides cohort building.

Availability reads assay headers and declared patient linkage metadata, not matrix
values. Undeclared or invalid links are excluded with a visible warning. Missing
entries do not prove an assay was never performed. Imaging here means linked
imaging-derived measurements; DICOM studies remain in Imaging. Detailed access
is required for every selected dataset.

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

Use **Compare measurements in Analysis** to open the comparison setup. The
Dashboard keeps coverage and overlap information; feature selection and results
belong to [Analysis](analysis.md#compare-two-measurements).

### Coverage and feature preview

The multimodal dashboard checks how well clinical records and different assays overlap.

The coverage and linkage panel reports modality coverage, patient-level overlap,
exact sample/timepoint overlap, and DICOM-clinical linkage issues. Use **Compare
measurements in Analysis** to move to analysis setup. This panel does not run
cross-modal statistics or assess the quality of the underlying measurements.

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
