---
sidebar_position: 3
---

# Pheno-Ranker

`Pheno-Ranker` compares patients or subsets using phenotypic similarity.

## Modes

- patient mode
- cohort mode

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

## Prefixes in multi-file runs

When several reference files are passed to Pheno-Ranker, selected IDs may temporarily appear with prefixes like:

```text
C1_SYN001:week_0
```

These prefixes indicate reference-file grouping inside the Pheno run. They should be removed when:

- copying IDs
- handing the selection to Analysis

## Explanation modes

The current UI offers two explanation paths:

- `Explain results`
  - deterministic
- `Explain with LLM`
  - model-generated interpretation

The intent is:

- deterministic explanation gives structured evidence from the similarity output
- LLM explanation gives a narrative interpretation, with deterministic evidence shown as support
