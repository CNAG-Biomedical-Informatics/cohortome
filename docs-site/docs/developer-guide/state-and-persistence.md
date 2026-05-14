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

This primarily supports compatibility with file-based clinical helpers while preserving dataset provenance in filenames.

It is no longer the primary storage boundary for DuckDB query stores.

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

Current prepared-store model:

- one DuckDB store per dataset:
  - `dataset-<dataset_id>.duckdb`
  - `dataset-<dataset_id>.meta.json`
  - `dataset-<dataset_id>.status.json`
- merged workspaces attach the selected dataset stores in one in-memory DuckDB session
- the app does not need to persist one separate DuckDB file for every dataset combination

Prepared stores are reused when:

- the dataset source signature still matches
- schema expectations still match

Store readiness is persisted separately so the app can distinguish:

- `not_built`
- `building`
- `ready`
- `failed`
- `stale`

This lets user routes block with a clear readiness error instead of rebuilding heavy stores on demand.

## Local auth state

When local auth is enabled, persisted users live in:

- `state/auth/users.json`

If this file already exists, it overrides bootstrap seed users from env or built-in defaults.

## User settings

Per-user UI preferences live under:

- `state/users/<user>/settings.json`

Current settings include:

- start tab behavior
- Query disclosure preference
- Query execution preference
- Analysis job drawer behavior
- Pheno-Ranker default metric and rendering toggles
- Dashboard molecular view preference
- compact dataset card preference
- selected LLM provider ID

Settings are user-owned preferences. They do not override dataset policy,
authentication, authorization, or provider availability.

## Model provider configuration

The approved model-provider registry is configuration, not user state.

Current sources:

- `LM_STUDIO_*` environment variables for `system-default`
- `PN_LLM_PROVIDERS_JSON`
- `PN_LLM_PROVIDERS_FILE`

The selected provider ID is stored per user, but provider endpoints and secrets
remain deployment/admin configuration.

## Why this split exists

The app needs several levels of state because it is doing several different jobs:

- interactive UI rendering
- reusable saved subsets
- per-user analysis chats
- per-user background jobs and generated artifacts
- multi-dataset workspace materialization
- repeated query execution over the same data

Treating all of that as only browser state or only raw files would make the app much less robust.

## Background jobs and artifacts

Curated queued analyses now persist per-user job state on disk.

Current location:

- `state/users/<user>/jobs/<job_id>/`

Typical contents include:

- `job.json`
- `result.json` when completed
- `stdout.txt`
- `stderr.txt`
- `command.txt`

These records back the in-app `Jobs` drawer and let completed results be reopened into `Analysis`.

Workflow jobs keep one top-level job record and write step-level artifacts beneath the job directory, for example:

- `workflow/manifest.json`
- `workflow/01-deseq2/`
- `workflow/02-hallmark/`

Artifact paths are preserved as nested relative paths so the Jobs drawer and Analysis result can link to individual step outputs without exposing separate user-facing jobs for internal workflow steps.
