---
sidebar_position: 2
---

# State And Persistence

Patient Navigator mixes:

- backend persisted state
- browser-local UI state
- derived workspace cache

This page summarizes what lives where.

## Dataset registry

Datasets are persisted as first-class records.

Key file:

- `state/datasets/registry.json`

This registry stores metadata such as:

- `dataset_id`
- name
- root path
- visibility
- allowed users
- allowed groups
- enabled state

## Materialized workspace scopes

When a user selects multiple datasets, the backend materializes a combined workspace under:

- `state/datasets/scopes/`

This lets the rest of the app operate on one resolved workspace root while preserving dataset provenance in filenames.

## Saved cohorts

Saved cohorts are persisted per user under:

- `state/users/<user>/saved-cohorts.json`

Important stored fields include:

- `sample_ids`
- `patient_ids`
- `dataset_ids`
- `is_full_dataset`
- source metadata

These are application objects, not just temporary UI selections.

## Analysis sessions

Analysis sessions are also persisted per user under:

- `state/users/<user>/analysis-sessions.json`

An analysis session stores:

- prompt draft
- scope
- compare scope
- saved cohort references
- short history
- rendered turns

This is why Analysis behaves like a threaded workspace rather than a stateless prompt box.

## Browser-local state

The frontend still uses browser-local state for responsiveness, including:

- current tab
- current in-memory turns
- pending dataset selection
- session mirrors cached in `localStorage`

The browser copy is not the only source of truth. For important objects such as saved cohorts and analysis sessions, backend persistence exists too.

## Query store and DuckDB cache

The app reuses a DuckDB-backed query layer.

Cache location:

- `.cache/query-store/`

This cache is reused when:

- the dataset scope path is the same
- file signatures still match
- schema expectations still match

## Why this split exists

The app needs several levels of state because it is doing several different jobs:

- interactive UI rendering
- reusable saved subsets
- per-user analysis chats
- multi-dataset workspace materialization
- repeated query execution over the same data

Treating all of that as only browser state or only raw files would make the app much less robust.
