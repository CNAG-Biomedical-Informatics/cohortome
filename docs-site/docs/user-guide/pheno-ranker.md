---
sidebar_position: 3
---

import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

# Pheno-Ranker

`Pheno-Ranker` compares patients or subsets using phenotypic similarity.

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
- deterministic explanation
- LLM explanation

Selections from heatmap or MDS can be copied or opened in Analysis.

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
The explanation cards are meant to complement the ranked output, not replace it. Deterministic evidence remains the grounding layer.
:::
