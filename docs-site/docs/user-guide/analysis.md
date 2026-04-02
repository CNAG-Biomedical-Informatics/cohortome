---
sidebar_position: 2
---

# Analysis

`Analysis` is the interpretation layer of the app.

## Main uses

- deterministic workspace summaries
- LLM-planned comparative analysis
- trajectories
- Kaplan-Meier curves
- molecular expression summaries
- exploratory volcano plots

## Two main modes

Analysis can work in two broad ways:

- single-workspace or single-subset interpretation
- saved-cohort comparison

## Starter prompts

The Analysis tab includes starter prompts with mode coding:

- `Deterministic`
- `LLM-planned`
- `LLM interpretation`

These labels are intended to reflect how the request is routed.

## Compare mode

Compare mode uses:

- `Cohort A`
- `Cohort B`

These are true saved cohorts, not the full workspace.

Manual workspace scope is allowed for single-analysis workflows, but saved cohorts are the intended model for explicit A/B comparison.

## Workspace context

Analysis always runs inside the current workspace. Saved cohorts narrow that workspace for a particular analysis.

## Common analyses

Examples of questions that fit well here:

- deterministic workspace summary
- temporal change over time
- trajectory of a numeric longitudinal measure
- Kaplan-Meier time to event
- molecular expression by medication
- exploratory volcano comparison

## Patient level versus sample level

Analysis may use either patient-level or sample-level scope depending on the analysis type.

Examples:

- broad clinical summaries
  - often patient-oriented
- molecular comparisons
  - often sample-aware
- Pheno-Ranker handoff
  - should preserve sample IDs

## Practical advice

Use `Analysis` when the main question is:

- what stands out in this subset
- how do these two saved cohorts differ
- what does this measure or event look like over time
