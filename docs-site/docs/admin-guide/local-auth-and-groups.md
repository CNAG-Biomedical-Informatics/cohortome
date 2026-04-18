---
sidebar_position: 2
---

# Local Auth And Groups

The current app uses local authentication for development and controlled deployment scenarios.

## Source of truth

User identity is now persisted locally in:

- `state/auth/users.json`

Environment configuration is still used as bootstrap seed data when no local user store exists yet.

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

The app also accepts membership in the `admin` group as an administrative path for UI visibility and backend admin endpoints.

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

## What the UI can edit

### Dataset policy

`Data Administration` can edit:

- visibility
- allowed groups
- allowed users

### Users

The `Users` tab can now manage local users directly:

- create local users
- edit display name
- edit role
- edit groups
- enable or disable accounts
- reset passwords
- delete local users

Current protections include:

- no deleting the currently signed-in user
- no disabling the currently signed-in user
- no self-demotion from the current admin session
- no deleting the last enabled admin

## Admin group direction

The app is moving toward cleaner group-based administration.

That means the long-term model can be:

- the username `admin` is just one user
- real administrative capability can also be granted through the `admin` group

For now, local role-based admin support still exists and is useful during development.

## Future direction

The local auth model is now provider-ready:

- current provider: `local`
- future provider: external identity such as Google OIDC

Patient Navigator should continue to own authorization concepts such as:

- roles
- groups
- dataset access
- in-app disclosure policy
- AI-provider policy
