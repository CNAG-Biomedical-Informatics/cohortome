---
sidebar_position: 1
---

import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

# Datasets And Access

Datasets are first-class resources in the app.

:::tip Recommended policy
Use groups as the default way to grant dataset access. Use direct allowed users only for exceptions.
:::

## Dataset structure

Each dataset has its own root directory, for example:

```text
dataset_root/
  clinical/
  molecular/
```

<Tabs>
  <TabItem value="user-view" label="User view" default>
    <div>
      <p>Regular users are expected to:</p>
      <ul>
        <li>see only authorized datasets</li>
        <li>choose one or more datasets in <code>Datasets</code></li>
        <li>apply the active workspace</li>
      </ul>

      <p>They do not manage dataset policy from this view.</p>
    </div>

  </TabItem>
  <TabItem value="admin-view" label="Admin view">
    <div>
      <p>Admins are expected to:</p>
      <ul>
        <li>review dataset visibility</li>
        <li>assign allowed groups</li>
        <li>assign allowed users</li>
        <li>inspect effective local access</li>
      </ul>

      <p>This happens in <code>Data Administration</code>, not in the user-facing <code>Datasets</code> tab.</p>
    </div>

  </TabItem>
</Tabs>

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

:::info
Effective access is granted if any allowed path matches:

- visibility
- group membership
- direct user assignment
:::

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

:::note
Groupless users are valid. They do not need to be forced into a group just to be usable in the app.
:::

## What Data Administration edits

`Data Administration` edits dataset policy, not user identity.

It currently allows admins to edit:

- `Visibility`
- `Allowed groups`
- `Allowed users`

User records and group membership still come from local auth configuration.

:::warning
The current UI edits dataset policy, not user identity. Changing local users or groups still requires updating the auth configuration source.
:::

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
