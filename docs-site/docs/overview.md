---
sidebar_position: 1
---

# Patient Navigator

Patient Navigator is a multimodal clinical exploration app for:

- browsing dataset-backed patient workspaces
- building subsets in `Query`
- interpreting them in `Analysis`
- launching curated tool-like analyses from an Analysis Catalog
- running longer curated analyses as background jobs
- comparing phenotypic similarity in `Pheno-Ranker`

## What the app is optimized for

- exploratory cohort building from clinical data
- clinical plus molecular interpretation in one workspace
- saved subset reuse across tabs
- dataset-level access control for different users
- curated built-in and external analysis launchers
- background execution for longer curated analyses

![Login view](/img/screenshots/login-page.png)

## Current core concepts

- `Workspace`
  - the currently loaded dataset scope
  - may contain one or more authorized datasets
- `Saved cohort`
  - a reusable saved subset inside a workspace
- `Sample ID`
  - record-level or biosample-level identifier
- `Patient ID`
  - person-level identifier derived from one or more samples

## Typical workflow

For most users, the app flows like this:

1. choose one or more datasets in `Datasets`
2. inspect the loaded workspace in `Dashboard`
3. build a subset in `Query`
4. save that subset as a saved cohort when it becomes reusable
5. interpret it in `Analysis`
6. use `Pheno-Ranker` when you want sample-level phenotypic similarity

## Why the app uses the term workspace

The app originally behaved as if there were always one loaded cohort. That became too vague once:

- multiple datasets could be active at once
- saved cohorts became a reusable concept
- users needed to reason about broader dataset scope versus narrower saved subsets

The term `workspace` is now used for the currently loaded dataset scope because it is broader and more accurate.

## Main tabs

- `Dashboard`
  - orient yourself in the currently loaded workspace
- `Datasets`
  - choose the active dataset scope
- `Query`
  - build subsets and inspect deterministic or LLM-assisted results
- `Analysis`
  - summarize, compare, and visualize clinical or molecular patterns
  - mix catalog tools with lighter prompt-based questions
- `Pheno-Ranker`
  - compare patients or subsets using phenotypic similarity

## Documentation layout

This docs site is organized around four questions:

- what the main concepts mean
- how users are expected to work in the app
- how admins manage datasets and access
- how the application is structured internally

## Current status

The application is still evolving quickly. The documentation is being built to stabilize:

- terminology
- workflow expectations
- admin behavior
- patient-versus-sample semantics
