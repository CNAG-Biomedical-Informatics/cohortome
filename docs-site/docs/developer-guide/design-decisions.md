---
sidebar_position: 2
---

# Design Decisions

This page captures stable architectural decisions that shape how Patient Navigator behaves today.

It is not a changelog. It records decisions that are important for future implementation and maintenance.

## 1. Dataset scope is a first-class concept

The app no longer assumes one global shared dataset.

Current model:

- datasets are first-class registry entries
- users can access different datasets depending on permissions
- a user may select one or more authorized datasets as the active workspace

Why:

- permissions differ by user
- different projects may live in separate dataset roots
- some users need multi-dataset workspaces

Consequence:

- the active workspace is per user, not global

## 2. A dataset is a root directory, not one file

Each dataset is a directory with the same internal shape:

```text
dataset_root/
  clinical/
  molecular/
```

Why:

- clinical and molecular discovery can stay predictable
- permissions apply at dataset level
- dataset boundaries remain explicit

Consequence:

- many files may contribute to one dataset
- one dataset may contribute several active workspace files to Pheno-Ranker

## 3. Multi-dataset workspaces are materialized, not merged in place

When several datasets are selected, the backend materializes a combined workspace under:

- `state/datasets/scopes/`

Why:

- the rest of the app can keep operating on one resolved workspace root
- query-store and DuckDB caching stay simpler
- dataset provenance can still be preserved in namespaced filenames

Consequence:

- the app behaves as if it has one active workspace root, even when that workspace spans several datasets

## 4. Saved cohorts are sample-first

Saved cohorts store:

- canonical `sample_ids`
- derived `patient_ids`

Why:

- Query can hand off subsets without losing sample-level information
- Pheno-Ranker works naturally with sample-level records
- Analysis can choose whether to operate at patient or sample level

Consequence:

- user-facing language may still refer to patients
- but saved cohort persistence does not throw sample-level detail away

## 5. Patient and sample semantics stay explicit

The app intentionally supports both:

- patient-level identifiers
- sample-level or record-level identifiers

It does not globally normalize everything to one level.

Why:

- clinical interpretation often thinks in patients
- molecular and Pheno-Ranker workflows often require samples

Consequence:

- some handoffs preserve sample IDs
- some deterministic helpers derive patient IDs locally only where needed

## 6. Query is the main subset-building surface

`Query` is the primary place where users build subsets and discover reusable groups.

Why:

- it is the most direct place to turn natural-language conditions into reusable subsets
- it is where Save cohort and Open in Analysis fit most naturally

Consequence:

- downstream tabs should reuse Query outputs rather than reinvent subset-building logic

## 7. Analysis compare mode is cohort-oriented

Explicit A/B comparison in `Analysis` is based on saved cohorts.

Why:

- saved cohorts are stable reusable objects
- manual compare scope is too fragile for threaded interpretation

Consequence:

- compare mode should not rely on ad hoc free-text scope input as the main workflow

## 8. Analysis is session-based

Analysis is not a stateless prompt box.

Sessions persist:

- prompt draft
- turns
- scope
- compare scope
- saved cohort references

Why:

- interpretation usually unfolds across several turns
- users need to revisit prior analyses

Consequence:

- cohort lifecycle matters
- deleting a cohort that an Analysis session depends on is unsafe

## 9. In-use cohorts are protected from deletion

Saved cohorts cannot be deleted when they are still referenced by persisted Analysis sessions.

Why:

- otherwise Analysis sessions can silently lose the subset they depend on

Consequence:

- deletion is guarded in the backend
- UI can disable obvious local deletions, but backend protection is the real safety layer

## 10. Groups are primary, direct users are exceptions

Dataset access is intentionally a union of:

- visibility
- allowed groups
- allowed users

But the intended administrative model is:

- groups first
- direct users only as exceptions

Why:

- most access follows organizational structure
- some users still need temporary or exceptional access

Consequence:

- groupless users are still valid
- they simply need broad visibility or direct allowed-user access

## 11. UI should not fake authority it does not have

The current app lets the frontend edit:

- dataset policy

But not:

- user identity
- group membership

Why:

- users and groups still come from environment-backed local auth
- pretending the UI edits that would be misleading

Consequence:

- `Users` is read-only
- `Data Administration` edits dataset access, not identities

## 12. OpenAPI is a product asset, not only an integration artifact

The API contract is being formalized through FastAPI response and request models.

Why:

- the frontend already depends on this API
- future tooling, docs, and integrations benefit from a stable contract

Consequence:

- OpenAPI is worth maintaining even if the main consumer is still the app itself
