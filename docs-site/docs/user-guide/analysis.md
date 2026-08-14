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
- transcriptomics expression summaries
- DESeq2 differential expression on one raw-count dataset
- methylation matrix QC and PCA on one processed M-value dataset
- limma differential methylation between two cohorts
- exploratory immune-cell and quantitative-serology cohort comparisons
- Hallmark pathway enrichment from a DESeq2-ranked comparison
- curated external analyses through reviewed runners

![Analysis tab with a plotted result and follow-up queries](/img/screenshots/analysis-tab.png)

## Choose the question context

Analysis has the same explicit context switch as Query:

- `Workspace` uses the active data, scopes, saved cohorts, and Analysis Catalog.
- `General question` asks the selected approved model without workspace data.

In General-question mode, workspace setup and catalog controls are hidden
because they are not part of the request. The response is marked `No workspace
context`, and its history is kept separate from workspace analysis. Switching
back to `Workspace` restores the research workflow without mixing the two
conversations.

The typed question and recent General-question history are still sent to the
selected provider. Do not include confidential or patient-level information
when that provider is external.

## Two main modes

Within `Workspace` context, Analysis can work in two broad ways:

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

This is useful because clinical and assay interpretation often unfolds across several questions rather than one prompt.

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

For a curated tool, follow the workflow bar in order:

1. choose the analysis
2. complete its setup checklist
3. review the configured prompt
4. run it and inspect the result

The checklist shows only requirements that apply to that tool, such as Cohort A,
Cohort B, one compatible assay, minimum cohort overlap, a language model, or a
background worker. `Next` marks the first incomplete requirement and provides a
button that opens the relevant control. Completed requirements remain visible
as `Done`; later requirements wait until the preceding step is complete. Quick
prompts that do not select a curated tool continue to need no extra setup.

The catalog is intentionally narrower than the prompt surface. Prompt-like summaries such as “what stands out” or broad A/B interpretation belong in quick prompts, not in the catalog.

## Analysis workflows

Some catalog entries are pre-made workflows rather than single tools.

An Analysis Workflow is a curated project-approved sequence of analysis steps. Users do not assemble these step chains manually; the app exposes only reviewed workflows with fixed execution rules.

Current first workflow:

- `Transcriptomics signature workflow`
  - runs `DESeq2 differential expression`
  - then runs `Hallmark pathway enrichment`
  - stores one background job with step-level artifacts under one workflow result

This keeps the user-facing model simple: one workflow launch, one job in `Jobs`, one combined Analysis result.

The workflow is intentionally pre-made. Users choose the approved workflow, but they do not concatenate arbitrary catalog tools.

For this first workflow, select exactly one compatible raw-count transcriptomics dataset. If more than one compatible transcriptomics dataset is available, choosing a second one replaces the first selection. The workflow does not merge multiple count matrices or compare transcriptomics files against each other.

The workflow result keeps interpretation and plots visible first. Raw output files are folded under `Result files` and can be opened when needed.

## Assay tool contract

The current assay catalog tools are method-driven.

Examples:

- `DESeq2 differential expression`
- `Hallmark pathway enrichment`
- `Methylation QC and PCA`
- `limma differential methylation`
- `Immune-cell Wilcoxon cohort comparison`
- `Serology Wilcoxon cohort comparison`

These tools do not compare two transcriptomics assays against each other.

The transcriptomics comparison tools use:

- one selected raw-count transcriptomics assay
- `Cohort A`
- `Cohort B`

The cohorts define the groups.
The transcriptomics assay defines the transcriptomics matrix.

Both cohorts must overlap the same selected transcriptomics assay.

If the chosen dataset contributes samples to only one side, the curated differential-expression tools fail with a validation error instead of silently dropping one cohort.

For the current `DESeq2` and Hallmark pathway tools, the first-version constraints are:

- at least two samples in `Cohort A`
- at least two samples in `Cohort B`
- one sample per patient

In practice, that means baseline-only transcriptomics datasets are the safest first choice.

For the synthetic large transcriptome fixtures, remember that treatment-specific matrices only contain their own patient subset. For example, an `infliximab` matrix does not contain `vedolizumab` patients. If you want a broad split across many synthetic patients, use the baseline matrix for that workspace.

The methylation tools use one selected processed M-value assay. The complete probe matrix remains in its governed dataset release and is read by the curated runner; COHORTome does not materialize all CpG-by-sample values in DuckDB.

`Methylation QC and PCA` checks the supplied matrix and sample linkage in the current Analysis scope. It does not repeat raw-array preprocessing or probe filtering from IDAT files. `limma differential methylation` uses Cohort A and Cohort B as the comparison groups and requires both cohorts to overlap the same selected methylation assay.

The immune-cell and quantitative-serology tools also use one selected assay
plus disjoint saved Cohort A and Cohort B selections. Each cohort must overlap
the assay by at least three samples. The runner applies a Wilcoxon rank-sum test
to each feature, reports rank-biserial effect sizes, and controls the displayed
feature-wise false-discovery rate with Benjamini-Hochberg correction.

These comparisons are deliberately labeled **exploratory and unadjusted**.
They test values on the scale supplied by the assay release: COHORTome does not
normalize, batch-correct, transform, or impute those measurements in this
runner. A positive rank-biserial effect means higher ranks in Cohort A; a
negative effect means higher ranks in Cohort B. Demographic, recruitment,
treatment, technical, and other confounders remain unmodeled, so this result is
useful for screening and prioritization rather than confirmatory inference.
Immune-cell abundance features can also be compositional, while serology
missingness can vary by marker; inspect the cohort-specific missing counts
before interpreting the ranking.

The compact source matrices remain in the governed dataset release. They are
read directly by the curated runner, are not materialized in DuckDB, and are
not copied into the job output. Analysis stores only compact aggregate results
and provenance artifacts.


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
- `Assays`
- `Workflow`
- `Background jobs`
- `External`

These filters are meant to reduce browse cost quickly, not to replace the catalog structure.

When a selected catalog item requires assay data, a compatible assay selector appears below the catalog search and filters. For single-assay analyses, including transcriptomics, methylation, immune-cell, and quantitative-serology tools, the selector behaves as a single-select control.

The folded catalog in the main tab also shows a `Suggested` strip.

Suggestions are lightweight and local:

- the currently selected tool is favored
- recently used tools are favored
- frequently used tools are favored
- tools that fit the current workspace and setup are ranked higher

Examples of setup-aware suggestions:

- assay tools rank better when a compatible assay is available
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

Follow-up questions generated beneath an Analysis result are amber and labeled `LLM interpretation`. Selecting one prepares an LLM-only follow-up for the next run; it does not silently switch back to a deterministic analysis route.

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
- assay volcano follow-ups
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
- private dataset context is always blocked when the selected provider is external
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
- transcriptomics expression by medication
- exploratory volcano comparison
- curated external runner demo analyses

As a rule:

- summaries and interpretation requests fit best as prompts
- trajectories, Kaplan-Meier, assay tools, and external runners fit best as catalog analyses

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
- assay comparisons
  - often sample-aware
- Pheno-Ranker handoff
  - should preserve sample IDs

:::warning
Do not assume all Analysis questions are patient-level. Assay and Pheno-driven paths are often sample-aware.
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
