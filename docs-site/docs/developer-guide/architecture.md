---
sidebar_position: 1
---

# Architecture

This page describes how the current app is structured at a high level.

## High-level components

- FastAPI backend
- browser-based tabbed frontend
- DuckDB-backed query store/cache
- dataset registry and per-user dataset scope
- saved cohorts
- Analysis sessions
- YAML-backed Analysis Catalog for tool-like analyses
- curated external analysis runners
- shared background jobs via `RQ + Redis`
- Pheno-Ranker integration

## Backend

The backend is a FastAPI application that exposes:

- UI shell routes
- auth routes
- dataset registry routes
- patient and dashboard routes
- Query routes
- Analysis routes
- molecular routes
- Pheno-Ranker routes

The backend is also responsible for:

- dataset authorization
- dataset scope resolution
- multi-dataset scope materialization
- saved cohort persistence
- Analysis session persistence
- analysis catalog loading and validation
- dispatching curated analysis runners
- submitting and resolving queued analysis jobs

## Frontend

The frontend is a browser-based app organized around top-level tabs:

- `Dashboard`
- `Datasets`
- `Data Administration`
- `Users`
- `Query`
- `Analysis`
- `Pheno-Ranker`

The frontend is stateful and uses:

- in-memory UI state
- local persisted mirrors for some sessions
- backend persistence for important reusable objects

## Workspace resolution

The app operates on an active workspace, not directly on arbitrary file paths.

That workspace may represent:

- one dataset
- several selected datasets materialized into one combined scope

This is why the rest of the app can talk about one active workspace even when the user selected multiple datasets.

## Query store and DuckDB

The app uses a DuckDB-backed query layer to normalize and reuse clinical data efficiently.

This query layer is:

- scoped to the active workspace root
- cached when possible
- reused across tabs

The purpose of this layer is to make deterministic querying and summarization fast enough to feel interactive.

## How the tabs relate to one another

### Dashboard

Uses the active workspace to provide orientation and provenance-aware summaries.

### Query

Builds subsets and counts from the active workspace.

It is the main subset-building surface.

### Analysis

Consumes either:

- the full workspace
- a manual scope
- saved cohorts

It is session-based and supports both deterministic and LLM-assisted interpretation.

The Analysis tab now has two launch surfaces:

- `Analysis Catalog`
  - curated tools loaded from YAML
  - not prompt-like summary or interpretation questions
- `Quick prompts`
  - lighter exploratory questions that still reuse the same Analysis backend

Catalog entries are a launch/configuration layer, not a second execution engine.
They can point to:

- built-in Python analysis routes
- curated external runners such as reviewed `Rscript`, `Snakemake`, or `Nextflow` integrations

### Pheno-Ranker

Consumes workspace files and sample-level scope.

It can attach saved cohorts as separate references and can hand selected samples into Analysis.

Current operational guardrails:

- cohort runs above `1500` resolved samples are submitted as background jobs
- cohort runs above `2500` resolved samples are rejected at route admission time
- the hard cap exists because the current downstream post-processing path for large `matrix.txt` outputs is not robust enough to support larger cohorts safely

## Provenance

Dataset provenance matters more as soon as several datasets are active at once.

Current UI behavior already reflects that in several places:

- patient lists
- dashboard views
- saved cohorts
- analysis workspace context

This is an important architectural principle, not just a display choice.

## Curated external analysis execution

External analysis execution is intentionally curated.

The current model is:

- YAML defines the catalog item
- backend code owns the runner implementation
- the runner receives scoped inputs only

For longer curated runs, the catalog can also declare the execution backend:

- `sync`
- `job`

The current queued path uses:

- `RQ`
- `Redis`
- per-user persisted job records and artifacts under `state/users/<user>/jobs/`

This means the catalog is allowed to describe external integrations such as:

- `rscript`
- CLI tools
- container-backed jobs later

But it does not execute arbitrary pasted commands from YAML.

## Where to read next

For more detail on specific decisions, continue with:

- [Design Decisions](./design-decisions)
- [State and Persistence](./state-and-persistence)
- [API Reference](./api-reference)
