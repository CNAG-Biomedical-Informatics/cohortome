---
sidebar_position: 1
---

# Workspace And Saved Cohorts

Workspaces and saved cohorts determine which data you are working with.

:::tip Terminology shortcut
Your `workspace` contains the datasets you have selected and applied.

A `saved cohort` records a selection of patients or samples for reuse.
:::

## Workspace

The workspace contains your currently active datasets.

- it may contain one dataset
- or multiple authorized datasets
- it is the default scope for Dashboard, Query, Analysis, and Pheno-Ranker

Changing the workspace changes the data available to these tabs.

## Saved cohort

A saved cohort is a reusable subset inside the current workspace.

- it is narrower than the workspace
- it can be reused in Analysis compare mode
- it can be reopened later without rebuilding the subset manually

A saved cohort is not a second name for the workspace. It is a saved slice of that workspace.

## Why this distinction matters

Use these terms when choosing data:

- `workspace` for the active loaded scope
- `saved cohort` for a reusable subset

## Examples

### Example 1: single dataset

- active workspace:
  - `default`
- saved cohort:
  - `Crohn patients on Infliximab`

### Example 2: multi-dataset workspace

- active workspace:
  - `default + private-dataset`
- saved cohort:
  - `All Healthy Controls`

In the second example, the workspace spans multiple datasets, while the saved cohort is still just a subset inside that combined scope.

## UI implications

- `Datasets`
  - defines the workspace
- `Query`
  - usually starts from the full workspace, then narrows it
  - can optionally follow the previous Query result through `Prompt scope`
- `Analysis`
  - can use the full workspace or saved cohorts
- `Pheno-Ranker`
  - runs inside the active workspace, unless you narrow it with saved cohorts or scope

:::note Query-local scope
`Query` has a local `Prompt scope` control that can temporarily refine the next Query prompt to the previous Query result.

That local prompt scope is not the same thing as the global workspace shown in the shell.
:::

:::warning Do not treat workspace and saved cohort as synonyms
This distinction matters more now that one workspace may span multiple datasets.

`Analysis` compare mode is cohort-oriented, while `Datasets` defines the broader workspace.
:::
