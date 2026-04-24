---
sidebar_position: 2
---

import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

# Analysis

`Analysis` is the interpretation layer of the app.

:::tip Best use
Use `Analysis` after you already know what subset or workspace you want to interpret.
:::

## Main uses

- deterministic workspace summaries
- LLM-planned comparative analysis
- trajectories
- Kaplan-Meier curves
- molecular expression summaries
- DESeq2 differential expression on one raw-count dataset
- legacy approximate differential expression for comparison/debugging
- Hallmark pathway enrichment from a DESeq2-ranked comparison
- curated external analyses through reviewed runners

![Analysis tab with a plotted result and follow-up queries](/img/screenshots/analysis-tab.png)

## Two main modes

Analysis can work in two broad ways:

- single-workspace or single-subset interpretation
- saved-cohort comparison

<Tabs>
  <TabItem value="single" label="Single scope" default>
    <div>
      <p>Use this mode when you want to interpret:</p>
      <ul>
        <li>the full workspace</li>
        <li>a manually selected scope</li>
        <li>one saved cohort without explicit A/B comparison</li>
      </ul>

      <p>Typical questions:</p>
      <ul>
        <li>what stands out in this workspace</li>
        <li>how does this measure change over time</li>
        <li>what does this Kaplan-Meier curve mean</li>
      </ul>
    </div>

  </TabItem>
  <TabItem value="compare" label="Compare mode">
    <div>
      <p>Use this mode when you want explicit A/B interpretation between:</p>
      <ul>
        <li><code>Cohort A</code></li>
        <li><code>Cohort B</code></li>
      </ul>

      <p>This is the intended place for:</p>
      <ul>
        <li>disease and medication burden comparison</li>
        <li>trajectory comparison</li>
        <li>Kaplan-Meier A/B analysis</li>
        <li>clinician-style cohort review</li>
      </ul>
    </div>

  </TabItem>
</Tabs>

## Analysis sessions

Analysis is session-based.

That means each thread can preserve:

- its own prompt history
- scope
- compare mode state
- attached saved cohorts
- generated turns and plots

This is useful because clinical and molecular interpretation often unfolds across several questions rather than one prompt.

## Analysis Catalog and quick prompts

The Analysis tab separates two things:

- `Analysis Catalog`
  - tools
  - curated analyses with real setup requirements, validation rules, or structured outputs
- `Quick prompts`
  - questions
  - open-ended summaries, interpretation requests, and clinician-style prompts

The practical rule is simple:

- if it can be naturally asked, it belongs in prompts
- if it invokes a specific method or runner, it belongs in the catalog

The main tab shows:

- a foldable catalog strip for curated tools
- a `Browse analyses` drawer with the full catalog
- a visible quick-prompt area for direct questions

The foldable catalog strip and the drawer share the same browsing state:

- search text
- active filter
- selected analysis

That means if you search or filter in one place, the other surface stays in sync.

The catalog is available only when the active workspace allows `Detailed` in-app access.

In a summary-only workspace, the tab explains that the catalog requires `Detailed` access instead of showing a generic load failure.

Selecting a catalog item does not create a separate execution system. It preconfigures the current Analysis thread with:

- the prompt
- compare-mode defaults when needed
- the preferred execution mode

The catalog is intentionally narrower than the prompt surface. Prompt-like summaries such as “what stands out” or broad A/B interpretation belong in quick prompts, not in the catalog.

## Analysis workflows

Some catalog entries are pre-made workflows rather than single tools.

An Analysis Workflow is a curated project-approved sequence of analysis steps. Users do not assemble these step chains manually; the app exposes only reviewed workflows with fixed execution rules.

Current first workflow:

- `Molecular signature workflow`
  - runs `DESeq2 differential expression`
  - then runs `Hallmark pathway enrichment`
  - stores one background job with step-level artifacts under one workflow result

This keeps the user-facing model simple: one workflow launch, one job in `Jobs`, one combined Analysis result.

The workflow is intentionally pre-made. Users choose the approved workflow, but they do not concatenate arbitrary catalog tools.

For this first workflow, select exactly one compatible raw-count transcriptomics dataset. If more than one compatible transcriptomics dataset is available, choosing a second one replaces the first selection. The workflow does not merge multiple count matrices or compare transcriptomics files against each other.

The workflow result keeps interpretation and plots visible first. Raw output files are folded under `Result files` and can be opened when needed.

## Molecular tool contract

The current molecular catalog tools are method-driven.

Examples:

- `DESeq2 differential expression`
- `Differential expression (legacy)`
- `Hallmark pathway enrichment`

These tools do not compare two molecular datasets against each other.

They use:

- one selected raw-count molecular dataset
- `Cohort A`
- `Cohort B`

The cohorts define the groups.
The molecular dataset defines the transcriptomics matrix.

Both cohorts must overlap the same selected molecular dataset.

If the chosen dataset contributes samples to only one side, the curated differential-expression tools fail with a validation error instead of silently dropping one cohort.

For the current `DESeq2` and Hallmark pathway tools, the first-version constraints are:

- at least two samples in `Cohort A`
- at least two samples in `Cohort B`
- one sample per patient

In practice, that means baseline-only transcriptomics datasets are the safest first choice.

For the synthetic large transcriptome fixtures, remember that treatment-specific matrices only contain their own patient subset. For example, an `infliximab` matrix does not contain `vedolizumab` patients. If you want a broad split across many synthetic patients, use the baseline matrix for that workspace.

`Differential expression (legacy)` remains available as a lighter approximate method based on log2-CPM plus per-gene t-tests. It is retained for comparison/debugging, not as the preferred RNA-seq result.

## Catalog search, filters, and suggestions

The Analysis Catalog is optimized for tool discovery, not only for scrolling.

Search matches against:

- tool name
- description
- category
- runner type
- tags

Filters are intentionally coarse:

- `All`
- `Clinical`
- `Molecular`
- `Workflow`
- `Background jobs`
- `External`

These filters are meant to reduce browse cost quickly, not to replace the catalog structure.

When a selected catalog item requires molecular data, the compatible molecular dataset selector appears below the catalog search and filters. For single-dataset molecular analyses, including the current workflow, the selector behaves as a single-select control.

The folded catalog in the main tab also shows a `Suggested` strip.

Suggestions are lightweight and local:

- the currently selected tool is favored
- recently used tools are favored
- frequently used tools are favored
- tools that fit the current workspace and setup are ranked higher

Examples of setup-aware suggestions:

- molecular tools rank better when molecular datasets are available
- compare-oriented tools rank better when compare mode is active

:::note
Suggested tools are a convenience ranking, not a backend recommendation service. They are derived from local browser state for the current user.
:::

## Starter prompts

Quick prompts still include mode coding:

- `Deterministic`
- `LLM-planned`
- `LLM interpretation`

These labels reflect how the request is routed.

For `LLM interpretation` prompts, the app no longer silently falls back to a deterministic clinical summary when the provider cannot be used.

Instead, Analysis returns an explicit provider-policy or provider-unavailable message.

## Compare mode

Compare mode uses:

- `Cohort A`
- `Cohort B`

These are true saved cohorts, not the full workspace.

Manual workspace scope is allowed for single-analysis workflows, but saved cohorts are the intended model for explicit A/B comparison.

:::warning
If the comparison matters, prefer saved cohorts over temporary manual scope.

That keeps the session understandable and reduces accidental drift.
:::

## Follow-up queries

Analysis can now suggest follow-up queries after strong result types, especially plots.

Examples:

- Kaplan-Meier follow-ups
- trajectory follow-ups
- molecular volcano follow-ups
- A/B comparison follow-ups

These follow-ups are intentionally neutral in color. They are suggestions about the next analytical question, not a promise about whether the reply will be deterministic or LLM-assisted.

:::info
Follow-up chips are generated from the latest result context plus short recent Analysis history, not from an unlimited chat memory.
:::

## What happens if a saved cohort disappears

Analysis sessions may depend on saved cohorts.

Because of that, the app now protects saved cohorts from deletion when they are still referenced by an Analysis session.

This prevents a session from silently losing the cohort it depends on.

:::note
If a cohort is still attached in the current page, the UI can block deletion locally. If an older saved Analysis session still references it, the backend will block deletion as well.
:::

## Workspace context

Analysis always runs inside the current workspace. Saved cohorts narrow that workspace for a particular analysis.

## In-app disclosure and AI providers

Analysis follows the same policy split as Query:

- in-app detail policy
- AI-provider policy

That means:

- a deterministic Analysis turn may show a local clinical summary without sending it anywhere
- if AI providers are `Safe summary`, provider-facing Analysis context is reduced to structural/provider-safe context only
- if AI providers are `Blocked`, Analysis stays local
- `LLM interpretation` prompts that require a provider may return a policy or availability message instead of silently degrading into a richer local summary

:::note
The in-app answer the user sees is not automatically the same as what an AI provider would be allowed to receive.
:::

## Common analyses

Examples of questions that fit well here:

- deterministic workspace summary
- temporal change over time
- trajectory of a numeric longitudinal measure
- Kaplan-Meier time to event
- molecular expression by medication
- exploratory volcano comparison
- curated external runner demo analyses

As a rule:

- summaries and interpretation requests fit best as prompts
- trajectories, Kaplan-Meier, molecular tools, and external runners fit best as catalog analyses

## Curated external analyses

The Analysis Catalog can now describe curated external runners, not only built-in Python analyses.

Current supported idea:

- catalog entries define a `runner_type`
- the backend dispatches to a reviewed executor
- catalog entries also define an `execution_backend`
  - `sync`
  - `job`

This keeps the catalog stable while allowing future curated integrations such as:

- `Rscript`
- `Snakemake`
- `Nextflow`
- external CLI tools
- containerized runners

:::warning
This is not arbitrary pasted-code execution. External analyses are curated and backend-controlled.
:::

## Background jobs

Longer curated external analyses can now run through a background queue instead of holding the HTTP request open.

Current model:

- queue backend: `RQ + Redis`
- user-facing surface: shared `Jobs` drawer in the app shell
- current queued runner types include curated `Rscript`, `Snakemake`, `Nextflow`, and pre-made Analysis workflows

When a catalog item is configured as a background job:

- the Analysis thread shows that the job was submitted
- the `Jobs` drawer shows queued, running, completed, failed, or cancelled state
- completed jobs can be reopened into `Analysis`
- generated result files are folded under `Result files` in the `Jobs` drawer

If the original Analysis session no longer exists, the app can recover the completed result into a fresh Analysis session shell instead of dropping the result.

## Deleting chats and generated data

Analysis session deletion now has two distinct semantics:

- `Delete chat only`
  - removes the Analysis session record
- `Delete chat and generated data`
  - removes the Analysis session
  - removes linked terminal job data on disk for that session

Current guardrail:

- if linked jobs are still `queued` or `running`, `Delete chat and generated data` is blocked

This keeps active background work from being destroyed mid-run.

## Patient level versus sample level

Analysis may use either patient-level or sample-level scope depending on the analysis type.

Examples:

- broad clinical summaries
  - often patient-oriented
- molecular comparisons
  - often sample-aware
- Pheno-Ranker handoff
  - should preserve sample IDs

:::warning
Do not assume all Analysis questions are patient-level. Molecular and Pheno-driven paths are often sample-aware.
:::

## Practical advice

Use `Analysis` when the main question is:

- what stands out in this subset
- how do these two saved cohorts differ
- what does this measure or event look like over time

Use saved cohorts instead of manual scope text when:

- the comparison matters
- you will come back to the same subset later
- you want the session to remain understandable over time
