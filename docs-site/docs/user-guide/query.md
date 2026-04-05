---
sidebar_position: 1
---

# Query

`Query` is the main subset-building interface.

:::tip Best use
Use `Query` first when your goal is to define a subset cleanly before interpreting it elsewhere.
:::

## What Query can do

- list patients or samples in the current workspace
- filter by disease or medication
- support deterministic and LLM-planned prompts
- save subsets as saved cohorts
- open the current result in Analysis

![Query tab with a subset result and workflow actions](/img/screenshots/query-tab.png)

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

:::info Wording matters
If you ask for `patients`, the answer should be patient-oriented.

If you ask for `samples`, `records`, or `timepoints`, the answer should be sample-oriented.
:::

## Current terminology

The app now prefers `workspace` for the loaded data scope. That means prompts like these are valid:

- `Tell me the list of patients in the workspace`
- `How many timepoints are in this workspace?`

## Prompt scope

`Query` now has its own local prompt-scope control.

This is different from the global workspace shown in the top bar:

- global `Scope`
  - the actual loaded app scope
- `Query` prompt scope
  - the scope used for the next Query prompt

The button in the Query composer can show states such as:

- `Prompt scope: workspace`
- `Prompt scope: previous result (5 patients)`
- `Prompt scope: waiting for previous result`

:::info
The top `Scope` pill still refers to the real loaded workspace.

`Prompt scope` is a Query-local refinement layer, not a replacement for the app-wide scope.
:::

## Query memory

By default, Query runs on the current workspace.

If the user enables `Prompt scope: previous result`, follow-up Query prompts can reuse the last Query subset instead.

Example:

1. `How many patients have Crohn Disease?`
2. enable `Prompt scope: previous result`
3. `How many are female?`

In that situation, the second question is interpreted inside the Crohn subset rather than the full workspace.

:::warning
Query memory is opt-in.

The app does not silently narrow follow-up prompts unless the user enables the prompt-scope control.
:::

## Full-workspace override

Even when Query memory is enabled, the user can explicitly ask for the broader scope again.

Examples:

- `How many female patients are in the full workspace?`
- `List all patients in the workspace`

That explicit wording tells Query to ignore the remembered subset and use the full current workspace.

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
- LLM fallback still uses the current Query prompt scope when one is active

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

:::note
The visible Query answer may be patient-oriented, but the handoff metadata can still preserve sample-level scope when available.
:::

## Practical advice

Use `Query` when the main question is:

- who is in the current subset
- how many match a condition
- which disease or medication filters define the subset you want to analyze next

Use `Prompt scope: previous result` when:

- the user is refining the same subset step by step
- the next question should stay local to the previous Query result

Leave it at `Prompt scope: workspace` when:

- the user wants a fresh question against the loaded workspace
- the previous Query result is no longer the intended scope
