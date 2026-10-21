---
sidebar_position: 1
---

# Workspace and saved cohorts

A **workspace** is the set of datasets you have selected and applied.
A **saved cohort** records selected patients or samples for reuse.

For example, load the Synthetic longitudinal demo as your workspace, then save
“Crohn patients on Infliximab” as a cohort. A cohort can also contain members
from multiple datasets; their dataset identities remain attached.

## Where each is used

- **Datasets** changes the active workspace.
- **Dashboard** summarizes that workspace.
- **Query** searches it, or refines the previous result when **Prompt scope**
  requests that narrower scope.
- **Analysis** and **Pheno-Ranker** can use saved cohorts within their supported
  dataset and sample scope.

Query's previous-result scope does not change the global workspace.

## After changing datasets

Saved cohorts retain their source datasets rather than becoming selections of
the newly active data. Reload the required datasets before reusing a cohort;
access and source compatibility are checked again.

Chats also retain their original dataset selection. Use **Load this chat’s
datasets** to return to it when available. A saved project is a separate
same-installation resume file, not a portable dataset or backup.

See [Datasets](../user-guide/datasets.mdx) and
[Saved cohorts](../user-guide/saved-cohorts-and-handoffs.md) for the controls.
