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
- exploratory volcano plots

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
