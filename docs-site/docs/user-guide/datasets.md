---
sidebar_position: 1
---

# Datasets

The `Datasets` tab defines the active workspace.

## What the tab does

This tab is where a user chooses which authorized datasets should be active at the same time.

The result is the current workspace used by:

- `Dashboard`
- `Query`
- `Analysis`
- `Pheno-Ranker`

## Active vs pending selection

The dataset picker distinguishes two states:

- `Active`
  - currently applied to the workspace
- `Pending`
  - selected in the picker but not yet applied

The workspace does not change immediately when a checkbox changes. It changes only when the user clicks:

- `Apply workspace`

## Why this matters

This avoids a misleading state where the UI would appear to use one set of datasets while the backend is still operating on another.

## Typical workflow

1. open `Datasets`
2. check one or more authorized datasets
3. review the pending changes
4. click `Apply workspace`
5. move to `Dashboard` or `Query`

## Important rule

The workspace cannot be empty.

At least one dataset must remain selected.

## Notes on permissions

Users only see datasets they are allowed to access.

Access can come from:

- dataset visibility
- matching group membership
- direct allowed-user assignment
