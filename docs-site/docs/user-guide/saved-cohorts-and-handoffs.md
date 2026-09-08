---
sidebar_position: 4
---

# Saved Cohorts And Handoffs

Saved cohorts are the main reusable objects in the app.

They sit between:

- `Query`
- `Analysis`
- `Pheno-Ranker`

## What a saved cohort contains

A saved cohort is more than a label.

It stores:

- canonical `sample_ids`
- derived `patient_ids`
- `dataset_ids`
- counts for patients and samples
- source metadata such as:
  - `query`
  - `pheno_ranker_selection`

This is why a saved cohort can be reused across tabs without reparsing IDs every time.

## Why saved cohorts matter

The app distinguishes:

- workspace
  - the currently loaded dataset scope
- saved cohort
  - a narrower reusable subset inside that workspace

This distinction is important because the same workspace may contain:

- several datasets
- several diseases
- several assay files

A saved cohort gives you a stable subset that can be compared, saved, and revisited later.

## Where cohorts can be created

Currently the main sources are:

- `Query`
  - from patient/sample subset results
- `Pheno-Ranker`
  - from MDS selection

## Main handoffs

### Query -> Analysis

Use:

- `Open in Analysis`

This sends the current subset into `Analysis`.

The visible Query answer may list patients, but the underlying handoff can still preserve sample-level scope when available.

Important rule:

- Query must be running with `Detailed` in-app access
- `Summary` Query results do not hand off to Analysis

### Query -> Save cohort

Use:

- `Save cohort`

This creates a reusable saved cohort from the current Query result.

Important rule:

- Query must be running with `Detailed` in-app access
- `Summary` Query results do not expose `Save cohort`

### Query -> Pheno-Ranker

Use:

- `Use IDs in Pheno-Ranker`

This is most useful when the result already has sample-level or record-level IDs.

Important rule:

- Query must be running with `Detailed` in-app access
- `Summary` Query results do not expose this handoff

### Pheno-Ranker -> Analysis

Selections from MDS or the output area can be sent into `Analysis`.

Important rule:

- Pheno-Ranker selections should remain sample-level when handed to `Analysis`

### Pheno-Ranker -> Save cohort

Selections can also be saved as a cohort.

This is useful when a phenotypic cluster found in Pheno-Ranker should become a reusable comparison group elsewhere in the app.

## Deleting saved cohorts safely

The app now protects against deleting cohorts that are still in use.

Two protections exist:

- local UI protection
  - a cohort currently attached in the page shows `In use here`
- backend protection
  - if a persisted Analysis session still references the cohort, deletion is blocked

This is important because an Analysis chat may depend on a saved cohort long after it was first selected.

## Export a saved cohort

Choose **Export ZIP** on a saved-cohort card. The archive contains:

- `membership.tsv`: separate patient and sample membership rows, with available
  subject ClarIDs and exact sample-to-subject links. Unavailable or ambiguous
  links remain blank; the exporter does not infer them from ID prefixes.
- `metadata.json`: cohort name, stored membership with original identifiers,
  source kind/prompt, dataset IDs, timestamps and format notes. Internal data
  directories and credentials are excluded. Review user-entered names/prompts
  before sharing.

Membership is exported as saved, not silently refreshed from a new query.
ClarIDs and sample links are taken from the current authorized workspace.
This is not a project backup or an importable workspace snapshot.

Downloads require current Detailed access to every source dataset and ownership
of the saved cohort. The export is limited to 100,000 combined membership rows
and 32 MiB of uncompressed content. Existing result-file downloads in Analysis
and Pheno-Ranker are unchanged.

## Best practice

Use saved cohorts when:

- a subset will be reused more than once
- you want explicit A/B comparison in `Analysis`
- a Pheno-Ranker selection should become part of a later workflow

Do not rely only on temporary scope text when the subset is analytically important.
