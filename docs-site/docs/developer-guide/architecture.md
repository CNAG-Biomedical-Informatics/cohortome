---
sidebar_position: 1
---

# Architecture

This page will document the internal app architecture in more detail.

## High-level components

- FastAPI backend
- browser-based tabbed frontend
- DuckDB-backed query store/cache
- dataset registry and per-user dataset scope
- saved cohorts
- Analysis sessions
- Pheno-Ranker integration

## Current notes

- the active workspace may span multiple datasets
- the backend materializes a combined dataset scope when needed
- Query, Analysis, and Pheno-Ranker each consume that workspace differently
