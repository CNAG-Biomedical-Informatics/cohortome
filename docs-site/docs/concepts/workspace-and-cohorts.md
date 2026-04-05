---
sidebar_position: 1
---

# Workspace And Saved Cohorts

The app now distinguishes between two different scopes:

:::tip Terminology shortcut
If the question is about the currently loaded universe of data, think `workspace`.

If the question is about a reusable subset inside that universe, think `saved cohort`.
:::

## Workspace

The workspace is the active loaded dataset scope.

- it may contain one dataset
- or multiple authorized datasets
- it is the default scope for Dashboard, Query, Analysis, and Pheno-Ranker

You can think of the workspace as the loaded universe of data the user is currently working inside.

## Saved cohort

A saved cohort is a reusable subset inside the current workspace.

- it is narrower than the workspace
- it can be reused in Analysis compare mode
- it can be reopened later without rebuilding the subset manually

A saved cohort is not a second name for the workspace. It is a saved slice of that workspace.

## Why this distinction matters

When the app had only one dataset loaded at a time, `cohort` was used for almost everything. Now that multiple datasets can be active, the broader term is:

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
