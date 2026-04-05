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

### Pheno-Ranker

Consumes workspace files and sample-level scope.

It can attach saved cohorts as separate references and can hand selected samples into Analysis.

## Provenance

Dataset provenance matters more as soon as several datasets are active at once.

Current UI behavior already reflects that in several places:

- patient lists
- dashboard views
- saved cohorts
- analysis workspace context

This is an important architectural principle, not just a display choice.

## Where to read next

For more detail on specific decisions, continue with:

- [Design Decisions](./design-decisions)
- [State and Persistence](./state-and-persistence)
- [API Reference](./api-reference)
