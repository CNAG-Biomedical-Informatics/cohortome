---
sidebar_position: 2
---

# Design Decisions

This page captures stable architectural decisions that shape how COHORTome behaves today.

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
  assays/
    transcriptomics/
    proteomics/
    imaging/
```

Why:

- clinical and assay discovery can stay predictable
- permissions apply at dataset level
- dataset boundaries remain explicit

Consequence:

- many files may contribute to one dataset
- one dataset may contribute several active workspace files to Pheno-Ranker

## 3. Multi-dataset query stores stay independent

Each registered dataset has an independently prepared DuckDB store. When
several datasets are selected, the backend attaches the authorized stores into
one query context rather than rebuilding a permanent database for every
combination.

Materialized compatibility scopes may still exist under
`<runtime>/state/datasets/scopes/` for helpers that require files.

Why:

- administrators can prepare and validate each dataset once
- users can change workspaces without repeated ingestion
- dataset authorization and provenance remain explicit

Consequence:

- the application exposes one active workspace while preserving the identity of
  every contributing dataset
- a compatibility scope directory is not the query-store identity boundary

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
- assay and Pheno-Ranker workflows often require samples

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

## 11. Data classification is separate from visibility

Dataset visibility controls authorization inside COHORTome. Public/private data
classification controls whether context may cross the deployment boundary.

Why:

- data shared with every authenticated consortium member may still be private
- deriving egress permission from application visibility would be unsafe

Consequence:

- missing classification defaults to private
- private context can reach an explicitly local provider when dataset policy
  permits it
- private context is always blocked from external providers

## 12. Local user administration is now real, but provider-ready

The current app now lets the frontend edit local users, while still keeping the auth model provider-ready.

Current local-user operations include:

- create user
- edit display name
- edit role
- edit groups
- enable or disable
- reset password
- delete user

Why:

- local controlled deployments need real admin ergonomics
- the app still needs a clean path toward external identity providers later

Consequence:

- local users persist in state, not only environment variables
- environment JSON acts as bootstrap seed data
- future Google/OIDC-style authentication can plug into the same authorization model

## 13. Query disclosure is policy-driven, not manually user-switched

`Query` no longer treats `Summary` vs `Detailed` as a normal user toggle.

Why:

- disclosure policy is easier to reason about at dataset/workspace level
- mixed workspaces need strictest-wins behavior
- manual disclosure switching caused avoidable privacy and UX edge cases

Consequence:

- dataset policy defines the ceiling
- the active workspace applies the strictest selected dataset policy
- Query shows the effective mode as read-only state

## 14. Analysis Catalog is a launch layer, not an execution engine

The Analysis Catalog exists to make built-in and curated analyses discoverable, not to replace the Analysis backend.

Why:

- existing analyses were becoming hidden behind prompts and chips
- users need stable, named analysis entry points
- future external runners need a registry layer
- prompt-like summaries and interpretation requests are better expressed as questions, not catalog entries

Consequence:

- catalog items preconfigure the current Analysis thread
- catalog is reserved for tools, methods, and runner-backed analyses
- built-in analyses and curated external analyses share the same Analysis tab
- quick prompts still exist for lighter analysis questions
- the catalog may choose between synchronous and queued execution without changing the Analysis UX model
- assay tools can require a stricter contract than prompt-based interpretation
  - one selected raw-count dataset
  - compare mode
  - sample-level compatibility checks

## 15. External analysis runners are curated, not arbitrary code execution

External integrations should be declared and dispatched through reviewed runner types such as:

- `rscript`
- `snakemake`
- `nextflow`
- CLI tools
- containers later

Why:

- arbitrary pasted code execution creates security and operational problems too early
- curated runners are easier to audit, test, and document

Consequence:

- YAML can describe an analysis runner
- backend code still owns execution
- the product moves toward an Analysis Catalog, not a live code box

The current catalog browsing model is intentionally lightweight:

- shared search state between the folded catalog and the drawer
- coarse filters rather than deep faceting
- local per-user suggestion ranking in the browser

Search currently matches:

- tool name
- description
- category
- runner type
- tags

Suggestions are not a server-side personalization system. They are derived from:

- the currently selected tool
- recent local usage
- frequent local usage
- current workspace/setup fit

This keeps catalog navigation fast without introducing a separate recommendation backend or catalog-specific persistence model.

## 16. Background jobs are a shared substrate, not an Analysis-only special case

Longer curated analyses should not hold the request open.

Why:

- external runners can take tens of seconds or more
- blocking HTTP requests creates poor UX and brittle operational behavior
- future queued work is likely to matter outside `Analysis` too

Consequence:

- catalog items can declare `execution_backend: job`
- the backend submits queued work through `RQ + Redis`
- the app exposes a shared jobs drawer rather than a separate top-level jobs tab
- completed results can be reopened into Analysis, even when the original session is gone
- current queued `Pheno-Ranker` cohort runs are intentionally capped at `2500` resolved samples until the large-output path is redesigned

## 17. OpenAPI is a product asset, not only an integration artifact

The API contract is being formalized through FastAPI response and request models.

Why:

- the frontend already depends on this API
- future tooling, docs, and integrations benefit from a stable contract

Consequence:

- OpenAPI is worth maintaining even if the main consumer is still the app itself

## 18. COHORTome is independent of the upstream warehouse

The 3TR Omics DM Warehouse may supply authorized data exports, but COHORTome must not
depend on its filesystem layout, API, or storage implementation.

Why:

- storage/distribution and harmonization/analysis have different lifecycles
- PRECISESADS arrives as an authorized Omics DM Warehouse release, while other
  approved institutional sources may use different delivery paths
- a reusable open-source platform needs explicit application contracts

Consequence:

- source adapters terminate at the COHORTome clinical and assay contracts
- the warehouse remains an upstream source, not the active workspace model
- public documentation must not describe COHORTome as the warehouse or ADEx

## 19. The product model is clinical plus assays

Transcriptomics, OLINK, proteomics, genotyping, and imaging are assay
modalities. `Molecular` is not a top-level product peer to `Assays`.

Why:

- the assay model supports molecular and imaging measurements consistently
- modality-specific behavior can be declared through metadata
- the UI can derive available controls from the active workspace

Consequence:

- use `clinical + assays` in code and documentation
- show transcriptomics-only controls only for compatible assays
- keep patient/sample/time-point linkage explicit across modalities

## 20. LLM assistance is first-class and governed

LLM assistance is a product capability for cohort discovery, planning, and
interpretation. Query and Analysis also provide an explicitly selected
General-question utility, but COHORTome is not an unrestricted agent and never
attaches workspace context to that mode.

Why:

- natural-language interaction can lower the operational barrier for clinical
  and translational researchers
- record-level context and model execution introduce disclosure and correctness
  risks

Consequence:

- administrators approve providers
- dataset policy constrains context before provider calls
- general questions send only their own prompt and separate recent history
- unsupported workspace requests are not silently rerouted as general questions
- deterministic execution remains visible
- the UI reports unavailable or blocked providers explicitly
- publication claims require reference-task evaluation
