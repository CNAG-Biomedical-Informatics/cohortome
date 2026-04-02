---
sidebar_position: 1
---

# Query

`Query` is the main subset-building interface.

## What Query can do

- list patients or samples in the current workspace
- filter by disease or medication
- support deterministic and LLM-planned prompts
- save subsets as saved cohorts
- open the current result in Analysis

## Typical use cases

Common examples include:

- `Tell me the list of patients in the workspace`
- `How many patients take biologics?`
- `Which patients have Crohn Disease?`
- `Which patients do not have Crohn Disease but take Infliximab?`

## Result types

Query can return:

- patient-level lists
- sample-level lists
- counts
- deterministic summaries

The wording matters:

- `patients`
  - patient-level result
- `samples`, `biosamples`, `specimens`, `records`
  - sample-level result

## Current terminology

The app now prefers `workspace` for the loaded data scope. That means prompts like these are valid:

- `Tell me the list of patients in the workspace`
- `How many timepoints are in this workspace?`

## Deterministic versus LLM-planned

`Query` supports more than one execution style:

- `Deterministic`
  - direct app logic and known filters
- `LLM-planned`
  - the model interprets the language, but the app still tries to execute a structured result
- `LLM answer`
  - model-generated answer when there is not a structured deterministic path

In practice:

- exact disease or medication filters often behave deterministically
- more natural phrasing and mixed conditions often benefit from `Use LLM planner`

## Disease shortcuts

The disease selector in Query is a shortcut for deterministic or LLM-planned subset building. It is especially useful for:

- common diseases
- Healthy Controls
- quickly opening a subset in Analysis

## Handoff actions

Query results can be reused through the action buttons:

- `Open in Analysis`
- `Save cohort`
- `More actions`

These are available for subset-style results and can also be useful when the current result spans the full workspace.

## Practical advice

Use `Query` when the main question is:

- who is in the current subset
- how many match a condition
- which disease or medication filters define the subset you want to analyze next
