---
sidebar_position: 1
---

# Architecture

This page describes how the current app is structured and where it sits in a
consortium data environment.

<picture>
  <source media="(max-width: 700px)" srcSet="/img/cohortome-platform-workflow-mobile.svg" />
  <img
    src="/img/cohortome-platform-workflow.svg"
    alt="COHORTome architecture from source systems through data preparation, access control, research workspaces, analysis, and saved results."
  />
</picture>

## Platform boundary

COHORTome is generic and independent of any one upstream warehouse. In the planned
3TR deployment, the Omics DM Warehouse supplies the authorized PRECISESADS
release and may supply other 3TR releases, but it is not a runtime dependency or
the application. Other deployments can register approved
institutional sources that satisfy the same clinical and assay contracts.

The platform owns:

- application-level clinical and assay contracts
- patient, sample, visit, time-point, and source linkage
- prepared query stores and workspace composition
- authorization, disclosure, and AI-provider policy
- cohort persistence and analysis scope
- curated execution and generated evidence

It does not own the upstream warehouse, primary DICOM archive, or specialist
statistical algorithms.

## High-level components

- FastAPI backend
- browser-based tabbed frontend
- clinical and assay harmonization contracts
- DuckDB-backed query store/cache
- dataset registry and per-user dataset scope
- saved cohorts
- Analysis sessions
- YAML-backed Analysis Catalog for tool-like analyses
- curated external analysis runners
- multimodal readiness and feature preview
- optional OHIF/DICOMweb integration
- shared background jobs via `RQ + Redis`
- Pheno-Ranker integration
- local/OIDC authentication with local authorization
- admin-configured OpenAI-compatible LLM provider registry

## Backend

The backend is a FastAPI application that exposes:

- UI shell routes
- auth routes
- dataset registry routes
- patient and dashboard routes
- Query routes
- Analysis routes
- assay routes
- multimodal and DICOM routes
- Pheno-Ranker routes

The backend is also responsible for:

- dataset authorization
- dataset scope resolution
- multi-dataset workspace resolution
- dataset-store readiness checks and admin-triggered store preparation
- saved cohort persistence
- Analysis session persistence
- analysis catalog loading and validation
- dispatching curated analysis runners
- submitting and resolving queued analysis jobs
- resolving the active LLM provider for each authenticated user
- enforcing dataset AI-provider policy before provider calls
- keeping explicit General-question calls separate from workspace resolution

## Frontend

The frontend is a browser-based app organized around top-level tabs:

- `Dashboard`
- `Datasets`
- `Query`
- `Analysis`
- `Pheno-Ranker`
- `Admin`
  - `Data`
  - `Users`
  - `Models`

The frontend is stateful and uses:

- in-memory UI state
- local persisted mirrors for some sessions
- backend persistence for important reusable objects

`static/js/dashboard.js` coordinates Dashboard views and shared patient/ClarID
presentation. `static/js/timeline.js` handles timeline plots, event inspection,
filters and whole-patient selection. Both use the existing workspace state;
Timeline remains a Dashboard subtab, not a separate application page.

### Shared presentation definitions

- `static/css/shared.css` defines theme colours and reusable dimensions. The
  `--radius-md` and `--radius-lg` tokens preserve the existing 12px and 14px
  corners. Reuse these for matching components rather than repeating literals.
  Scientific colour scales are separate from interface styling.
- `static/js/assay_labels.js` holds assay modality and data-type display names
  used by Dashboard and Analysis. Unknown identifiers retain readable fallback
  labels. This is presentation only: backend catalogs still define available
  methods, required inputs and capabilities.
- `static/js/shared.js` provides shared escaping, activity cards and clipboard
  fallback behaviour. Query, Pheno-Ranker, ClarID and About reuse the clipboard
  helper; failed copies remove temporary elements and restore keyboard focus.

Keep view-specific layouts local. Extract repeated behaviour when it has the
same meaning across views, not just similar markup. This does not require a
frontend framework or making every heading and CSS value configurable.

## Workspace resolution

The app operates on an active workspace, not directly on arbitrary file paths.

That workspace may represent:

- one dataset
- several selected datasets attached into one query context

Prepared DuckDB stores remain per dataset. File-based compatibility helpers may
still materialize a resolved scope directory, but that directory is not the
query store. Both approaches retain each record's source dataset.

## Query store and DuckDB

The app uses a DuckDB-backed query layer to normalize and reuse clinical and assay data efficiently.

Current model:

- each dataset has its own prepared DuckDB store
- admins prepare or rebuild these stores in `Admin > Data`
- merged workspaces attach the selected dataset stores into one in-memory DuckDB session
- the app no longer relies on building one physical DuckDB per dataset combination during user workspace reload

Temporary scope directories can still exist under `<runtime>/state/datasets/scopes/`.
DuckDB stores remain attached to individual registered datasets.

This query layer is:

- reused across tabs
- reused across workspace reloads when dataset signatures still match
- blocked at route admission if any selected dataset store is not ready

The purpose of this layer is to make deterministic querying and summarization fast enough to feel interactive.

### Assay ingest path

The assay build path keeps the same schema and indexes, but ingestion is now more DuckDB-native:

- matrix CSVs are loaded directly into DuckDB
- counts are unpivoted inside DuckDB
- the app no longer builds one large Python `transcript_counts` row list before insertion

This keeps rebuild time low without changing the product-facing data model.

## How the tabs relate to one another

### Dashboard

Shows Timeline, Clinical, Assays, Imaging, and Multimodal views of the active workspace.
Summaries retain information about their source datasets.

The Multimodal view reports overlap, missingness, DICOM linkage, and readiness.
Its bounded feature matrix is an inspectable preview, not a trained model or a
validated integration method.

### Query

Builds subsets and counts from the active workspace.

Researchers use it to select patients or samples for later analysis.

Its explicit `General question` context calls the approved model without
resolving a workspace. It has separate history and cannot produce workspace
actions or scopes.

### Analysis

Consumes either:

- the full workspace
- a manual scope
- saved cohorts

It is session-based and supports both deterministic and LLM-assisted interpretation.

The same explicit `General question` context is available for background
knowledge without attaching dataset, cohort, assay, or result context.

The Analysis tab offers two ways to start:

- `Analysis Catalog`
  - curated tools loaded from YAML
  - not prompt-like summary or interpretation questions
- `Quick prompts`
  - lighter exploratory questions that still reuse the same Analysis backend

Catalog entries are a launch/configuration layer, not a second execution engine.
They can point to:

- built-in Python analysis routes
- curated external runners such as reviewed `Rscript`, `Snakemake`, or `Nextflow` integrations
- curated multi-step Analysis workflows

Current assay tool pattern:

- one selected raw-count transcriptomics assay
- scoped `Cohort A` and `Cohort B`
- Python materializes a job-local bundle
  - `manifest.yaml`
  - `params.yaml`
  - `sample_table.tsv`
  - `counts_matrix.tsv`
- curated `Rscript` runners consume that bundle and return structured artifacts

Current examples include:

- lightweight external differential expression
- `DESeq2` differential expression
- Hallmark pathway enrichment using `DESeq2` ranking plus `fgsea`
- Transcriptomics signature workflow
  - runs `DESeq2` first
  - runs Hallmark pathway enrichment second
  - stores one user-facing job with step directories under `workflow/`

LLM-assisted Analysis routes resolve the current user's selected provider before
they plan or interpret a request. Provider failures appear as provider
availability or policy messages for LLM-only routes; they should not silently
turn into deterministic clinical interpretation.

### Pheno-Ranker

Consumes workspace files and sample-level scope.

It can attach saved cohorts as separate references and can hand selected samples into Analysis.

Current operational guardrails:

- cohort runs above `1500` resolved samples are submitted as background jobs
- cohort runs above `2500` resolved samples are rejected at route admission time
- the hard cap exists because the current downstream post-processing path for large `matrix.txt` outputs is not robust enough to support larger cohorts safely

Pheno-Ranker can also call the selected LLM provider for narrative explanation,
subject to the active workspace AI-provider policy.

### DICOM and OHIF

COHORTome stores dataset-authorized study linkage and opens the configured OHIF
viewer. Orthanc or another DICOMweb archive serves pixel objects. COHORTome does not
perform raw-pixel segmentation; derived imaging features enter through an assay
matrix produced by an external method.

The bundled Orthanc configuration is a synthetic local-development service and
must not be used as the security boundary for real patient imaging.

### Model providers

Model providers are admin-defined OpenAI-compatible endpoints.

Current model:

- `system-default` comes from the existing `LM_STUDIO_*` environment variables
- additional providers come from `COHORTOME_LLM_PROVIDERS_JSON` or `COHORTOME_LLM_PROVIDERS_FILE`
- providers created in `Admin > Models` live in protected runtime state
- users select a provider in persisted Settings
- admins manage runtime providers and inspect provider health in `Admin > Models`
- dataset policy still controls what, if anything, can be sent to a provider

The provider registry accepts both `providers` and `llm_providers` as the JSON
list key so future model/tool configuration can stay explicit without breaking
current deployments.

Model assistance is part of the platform contract, but deployment availability
is configurable. Dataset policy can permit detailed context, restrict calls to
safe summaries, or block provider access. Publication claims about model
assistance require task-level evaluation in addition to provider health checks.

## Provenance

Dataset provenance matters more as soon as several datasets are active at once.

Current UI behavior already reflects that in several places:

- patient lists
- dashboard views
- saved cohorts
- analysis workspace context

This is an important architectural principle, not just a display choice.

## Curated external analysis execution

External analysis execution is intentionally curated.

The current model is:

- YAML defines the catalog item
- backend code owns the runner implementation
- the runner receives scoped inputs only

For longer curated runs, the catalog can also declare the execution backend:

- `sync`
- `job`

The current queued path uses:

- `RQ`
- `Redis`
- per-user persisted job records and artifacts under `<runtime>/state/users/<user>/jobs/`

This means the catalog is allowed to describe external integrations such as:

- `rscript`
- CLI tools
- container-backed jobs later

But it does not execute arbitrary pasted commands from YAML.

## Where to read next

For more detail on specific decisions, continue with:

- [Design Decisions](./design-decisions)
- [State and Persistence](./state-and-persistence)
- [API Reference](./api-reference)
