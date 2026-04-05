---
sidebar_position: 2
---

# Local Auth And Groups

The current app uses local authentication for development and controlled deployment scenarios.

## Source of truth

User identity currently comes from environment configuration, not from the browser UI.

Typical setup:

```bash
export PN_AUTH_MODE=local
export PN_LOCAL_USERS_JSON='[
  {"username":"admin","password":"admin","role":"admin","display_name":"Administrator","groups":["admin"]},
  {"username":"mrueda","password":"mrueda","role":"user","display_name":"mrueda","groups":["cnag"]},
  {"username":"nogroup","password":"nogroup","role":"user","display_name":"No Group User","groups":[]}
]'
```

## Roles versus groups

The app uses both concepts, but for different purposes.

### Role

A role controls application-level privileges such as:

- whether a user can see `Data Administration`
- whether a user can see `Users`

Current important role:

- `admin`

### Group

A group controls dataset access through dataset policy.

Examples:

- `cnag`
- `admin`

Groups are the preferred way to grant dataset access at scale.

## Recommended policy model

The intended operating rule is:

- groups first
- direct user access as exception

In practice that means:

- grant datasets to groups whenever possible
- use direct allowed users for special cases

## Groupless users

A user without groups is still valid.

Such a user:

- gets no dataset access through groups
- may still gain access through:
  - broad dataset visibility
  - direct `allowed_users`

This matters because not every local user needs to belong to an organizational group.

## What the UI can and cannot edit

### Editable in the UI

`Data Administration` can edit dataset policy:

- visibility
- allowed groups
- allowed users

### Not editable in the UI

The current `Users` tab is read-only.

It shows:

- configured users
- their roles
- their groups

But user creation, deletion, and group membership still come from the environment configuration.

## Admin group direction

The app is moving toward cleaner group-based administration.

That means the long-term model can be:

- the username `admin` is just one user
- real administrative capability can also be granted through the `admin` group

For now, local role-based admin support still exists and is useful during development.
