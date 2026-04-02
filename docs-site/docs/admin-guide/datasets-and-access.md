---
sidebar_position: 1
---

# Datasets And Access

Datasets are first-class resources in the app.

## Dataset structure

Each dataset has its own root directory, for example:

```text
dataset_root/
  clinical/
  molecular/
```

## Access model

Dataset access is granted through:

- visibility
- allowed groups
- allowed users

The effective rule is a union:

- visible to everyone if visibility allows it
- or visible through matching groups
- or visible through explicit direct user assignment

This is intentionally a union, not a conflict model.

## Groups versus direct users

The intended operating model is:

- groups are the default
- direct users are exceptions

That means:

- a dataset can be granted to a whole group such as `cnag`
- a specific user can still be granted access directly even if they have no group

This is especially important for:

- temporary access
- exceptional reviewers
- local users without group membership

## Groupless users

A user with no groups is still valid.

Such a user:

- receives no dataset access from groups
- but can still receive access through:
  - broad visibility
  - direct `allowed_users`

## What Data Administration edits

`Data Administration` edits dataset policy, not user identity.

It currently allows admins to edit:

- `Visibility`
- `Allowed groups`
- `Allowed users`

User records and group membership still come from local auth configuration.

## Effective local access

The admin UI also shows an `Effective local access` preview.

This preview answers:

- who currently gets this dataset
- under the current local auth configuration
- after visibility, groups, and direct users are combined

This is useful because it makes the group-versus-user rule explicit instead of forcing admins to infer it.

## Current admin workflow

In `Data Administration`, admins can:

- review dataset visibility
- assign allowed groups
- assign allowed users

Users and group membership themselves still come from local auth configuration.
