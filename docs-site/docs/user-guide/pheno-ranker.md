---
sidebar_position: 3
---

import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

# Pheno-Ranker

`Pheno-Ranker` compares patients or subsets using phenotypic similarity.

## Saved chats

Choose **New → Pheno-Ranker chat** in the shared sidebar. Keep using the normal
scope, setup and run controls; an LLM is not required. Run settings, completed
results, queued-job references and result explanations are saved in the chat.
Expand **Chat history** to reopen an earlier result in the existing interactive
plots and tables. Reopening a result does not run Pheno-Ranker again.

Chats support the same folders, pinning, search, rename and deletion controls as
Query and Analysis. Deleting a chat keeps generated files and runs in Run history.
If those files are later removed, the chat cannot reconstruct the interactive
result. Queued entries check the job when opened; they are not live job monitors.

A chat stays bound to its original workspace. Choose **Load this chat’s datasets** before
continuing; start a new chat if its source data changed. Save errors are shown
beside the chat title. **Save chat** retries a save; **Reload saved** can discard
unsaved edits after a conflict with another window.

:::warning
Despite the historical wording around cohort mode, current Pheno-Ranker workflows are fundamentally sample-level.
:::

## Modes

- patient mode
- cohort mode

![Pheno-Ranker tab](/img/screenshots/pheno-tab.png)

<Tabs>
  <TabItem value="patient-mode" label="Patient mode" default>
    <div>
      <p>Use patient mode when you want one target patient or sample to be matched against the active workspace references.</p>

      <p>Typical output:</p>
      <ul>
        <li>ranked matches</li>
        <li>alignment details</li>
        <li>deterministic or LLM explanation</li>
      </ul>
    </div>

  </TabItem>
  <TabItem value="cohort-mode" label="Cohort mode">
    <div>
      <p>Use cohort mode when you want a selected subset to be compared at the sample level.</p>

      <p>Important current rule:</p>
      <ul>
        <li>this mode still operates on sample-level records</li>
        <li>if patient IDs are supplied, backend expansion may be needed before the run</li>
      </ul>
    </div>

  </TabItem>
</Tabs>

## What cohort mode really means here

In the current app, Pheno-Ranker cohort mode still operates on sample-level records.

That means the scope may contain:

- one or more sample IDs
- records coming from multiple reference files

## Active workspace files

Pheno-Ranker works from the clinical JSON files currently present in the active workspace.

This is why:

- one dataset can contribute more than one active workspace file
- a multi-dataset workspace can produce several Pheno reference files

:::info
Do not confuse dataset count with Pheno reference-file count. One dataset may contribute several clinical JSON files.
:::

## Current scope behavior

Pheno-Ranker works on sample-level identifiers.

That means:

- selected records remain sample IDs
- copied selected IDs should remain sample IDs
- when sent to Analysis, they should remain sample IDs

## Current UX

The tab provides:

- interactive heatmap
- interactive MDS
- optional interactive UMAP
- interactive graph, when graph rendering is enabled
- deterministic explanation
- LLM explanation

Selections from MDS, UMAP or graph views can be copied, saved as cohorts, or opened in Analysis.

Enable **Render UMAP** in Settings to add a UMAP projection to subsequent
cohort runs. It is off by default and requires the optional `cohortome[umap]`
installation in the app and worker environment. It uses precomputed Hamming
distances or `1 − Jaccard similarity`, one CPU, seed 42, up to 30 neighbours and
minimum distance 0.3. At least three records are required. Parameters and package
versions are saved in `umap_metadata.json`. UMAP emphasizes local neighbourhoods;
distances between clusters should not be interpreted as original distances.

For graph runs, optional edge-weight cutoffs can be set in the advanced setup:

- Jaccard graphs usually use a minimum edge weight, because higher values mean stronger similarity
- Hamming graphs usually use a maximum edge weight, because lower values mean stronger similarity

## Limitation: raw measures are weak phenotypic tokens

Numeric clinical measures are currently carried into `Pheno-Ranker` as observed values.

That is often not ideal for cross-sample similarity because:

- raw values are not directly comparable across all patients or settings
- very close numeric values may behave like separate phenotypic tokens
- clinically meaningful patterns are often ordinal or categorical rather than exact-value based

Examples:

- `CRP = 9.8` vs `CRP = 10.1`
- `Leukocyte Count = 8.9` vs `Leukocyte Count = 9.2`

These are usually better interpreted as:

- normal
- mildly elevated
- highly elevated

:::warning
For measure-driven similarity, the current approach is exploratory. Raw numeric values are often less informative than binned or categorized representations.
:::

### Recommended preprocessing direction

Before similarity calculation, numeric measures should ideally be transformed into bins or categories such as:

- below normal
- normal
- above normal
- high inflammatory burden

This would make measure-based similarity more clinically meaningful and more stable across samples.

## Prefixes in multi-file runs

When several reference files are passed to Pheno-Ranker, selected IDs may temporarily appear with prefixes like:

```text
C1_SYN001:week_0
```

These prefixes indicate reference-file grouping inside the Pheno run. They should be removed when:

- copying IDs
- handing the selection to Analysis

:::tip
If you see identifiers like `C1_SYN001:week_0`, treat the `C1_` part as temporary run-local labeling, not part of the underlying sample ID.
:::

## Explanation modes

The current UI offers two explanation paths:

- `Explain results`
  - deterministic
- `Explain with LLM`
  - model-generated interpretation

The intent is:

- deterministic explanation gives structured evidence from the similarity output
- LLM explanation gives a narrative interpretation, with deterministic evidence shown as support

:::note
Read explanation cards alongside the ranks and scores. Check any interpretation
against those computed results.
:::

## Planner follow-up questions

After previewing a plan, Pheno-Ranker can show suggested follow-up questions. Their routing is disclosed before selection:

- blue `Deterministic` means the suggestion came from deterministic planning
- green `LLM-planned` means the suggestion came from the model planner

Selecting one only places it in the prompt editor for review. It does not automatically preview or run a new Pheno-Ranker job.
