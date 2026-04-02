---
sidebar_position: 2
---

# Patient IDs vs Sample IDs

This is one of the most important concepts in the app.

## Patient IDs

Patient IDs identify a person, for example:

```text
SYN001
```

## Sample IDs

Sample IDs identify a specific record or biosample, for example:

```text
SYN001:week_0
```

## Current rule of thumb

- `Query`
  - may answer at patient level, but can also expose sample-level metadata when needed
- `Analysis`
  - may work at patient or sample level depending on the analysis
- `Pheno-Ranker`
  - works at sample level

## Why this distinction exists

Some analyses are naturally patient-level:

- how many patients have Crohn Disease
- which patients take biologics
- broad clinical summaries

Other analyses are naturally sample-level:

- Pheno-Ranker comparisons
- biosample-oriented molecular views
- timepoint-specific record selection

The app therefore needs both levels, but they should not be mixed carelessly.

## Working examples

### Patient-level

```text
Which patients have Crohn Disease?
```

Expected answer shape:

- patient count
- patient list
- optional sample metadata behind the scenes

### Sample-level

```text
Use selected Pheno-Ranker MDS points in Analysis
```

Expected behavior:

- keep sample IDs
- do not collapse them to patients

## Important practical rule

When an ID list comes from `Pheno-Ranker`, it should be treated as sample-level unless explicitly transformed.

## Important detail

When `Pheno-Ranker` uses multiple reference files, it may temporarily prefix IDs like:

```text
C1_SYN001:week_0
```

This prefix is only a cohort/reference marker for the Pheno run. It should be pruned when copying or handing selected IDs to other tabs.

## Mental model

Use this shortcut:

- if you are asking about people, think patient IDs
- if you are selecting a concrete record, timepoint, or biosample, think sample IDs
