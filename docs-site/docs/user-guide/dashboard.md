---
sidebar_position: 2
---

# Dashboard

`Dashboard` is the orientation layer of the app.

Use it to answer:

- what is currently loaded
- how many patients and timepoints are in the workspace
- which diseases and medications dominate the workspace
- which molecular datasets are available in the current scope

## Clinical dashboard

The clinical dashboard gives a workspace-level summary of:

- total patients
- total timepoints
- disease distribution
- medication distribution
- visit burden

This is the fastest way to sanity-check that the right datasets are loaded before you start filtering in `Query` or interpreting in `Analysis`.

## Molecular dashboard

The molecular dashboard is dataset-aware.

It shows:

- molecular datasets currently visible in the workspace
- dataset-level counts and metadata
- workspace-level molecular summary

In a multi-dataset workspace, molecular provenance matters. If two datasets are active, the dashboard helps confirm whether the molecular side really comes from both.

## Patient list and patient detail

The left-side patient list is still patient-oriented, even if some downstream operations become sample-aware.

When multiple datasets are active:

- patient cards may show dataset provenance
- patient detail may show dataset provenance as well

This is intentional. It helps avoid confusion about where a patient summary came from.

## When to use Dashboard first

Use `Dashboard` before `Query` if you need to:

- confirm the current workspace after changing datasets
- verify that healthy controls or private datasets are really loaded
- check whether the workspace looks mixed across several datasets
- understand whether the molecular side is populated before asking molecular questions

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
