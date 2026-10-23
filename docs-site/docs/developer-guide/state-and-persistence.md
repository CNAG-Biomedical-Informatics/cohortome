---
sidebar_position: 2
---

# State and persistence

COHORTome saves chats, cohorts, settings, and completed results in its runtime
directory. Source datasets remain separate.

## What is saved?

| Item | Where to reopen it |
| --- | --- |
| Query, Analysis, and Pheno-Ranker chats | Chats sidebar |
| Saved cohorts | Cohorts |
| Runs and output files | Run history or the originating chat |
| Preferences | Settings |
| Project resume file | Open project |

Chats retain their dataset selection. They do not freeze the source data.
If that data changes, a saved analysis may no longer be runnable.

Saved work belongs to an installation and user. Changing the runtime directory
or username can make existing work appear missing. On Web, see
[changing login methods](../admin-guide/local-auth-and-groups#keep-saved-work-when-changing-login-methods).

## Temporary Query results

Detailed list queries keep their full ordered result for one hour. The browser
receives a result handle and one page: 50 rows by default, at most 100 per request.

Paging, exports, and cohort actions recheck the user, dataset access, and source
fingerprint. Reopening a saved Query chat restores its text, not a live result
handle. Rerun the query to use those actions, or save the selection as a cohort
before it expires.

## Projects and backups

A `.cohortome` file stores enough information to resume work in the same
installation. It references datasets and saved results; it does not contain
their matrices or output files.

Back up the runtime and source datasets, not just project files.
Chats, project files, and results may contain patient information.

Deleting a chat keeps generated run files. Artifact cleanup is a separate
action in Settings. Removing result files can prevent a saved result from
reopening fully.

## Runtime storage

Web uses `COHORTOME_RUNTIME_ROOT`; a source launch defaults to `runtime/`.
The Desktop development launcher uses `runtime/desktop-preview/`.
Packaged Desktop uses the operating system's per-user application-data directory.
See [Desktop storage, updates, and removal](../getting-started/desktop#storage-updates-and-removal)
for the exact paths, uninstall behaviour and reset instructions. Removing the
portable app does not remove its saved data.

| Runtime area | Contents |
| --- | --- |
| `state/datasets/` | Dataset registry and file-based workspace scopes |
| `state/users/<user>/` | Chats, cohorts, settings, and job state |
| `state/auth/` | Local Web accounts |
| `state/llm/` | Runtime-managed model providers |
| `cache/query-store/` | Prepared DuckDB stores and readiness metadata |
| `runs/` | Run artifacts where used by the runner |

Defaults under `config/` seed new installations; they are not the live runtime
configuration. Browser state holds temporary display choices, pending selections,
and cached session copies, not the only copy of saved chats or cohorts.

<details>
<summary>Prepared stores and workspace files</summary>

Each dataset has its own DuckDB store and source fingerprint. A source or schema
change can make it stale. The app reports missing, building, stale, or failed
stores instead of rebuilding them during an ordinary query.

Multi-dataset queries attach those stores. Some file-based helpers also need
materialized workspace files under `state/datasets/scopes/`; these do not
replace the per-dataset stores.

</details>

<details>
<summary>Storage configuration for restricted data</summary>

Use an absolute runtime path on protected storage outside the source checkout.
Private methylation jobs and materialized workspaces containing private datasets
enforce this requirement before writing patient- or sample-level files.

Docker Compose uses a named volume at `/var/lib/cohortome`. With a bind mount,
choose the protected host directory explicitly; the container cannot determine
whether the host path is inside a Git checkout.

See [Security configuration](../admin-guide/real-data-security.md).

</details>

<details>
<summary>Job files and provider credentials</summary>

Queued jobs keep status, logs, and result files under
`state/users/<user>/jobs/<job_id>/`. Workflow steps use subdirectories.
Before execution, workers recheck the submitting user's access and resolve the
registered datasets; a stored filesystem path is not an authorization grant.

Job directories use mode `0700`; COHORTome-owned JSON and log files use
`0600`. Runtime-managed provider configuration can contain API keys and also
uses `0600`. Provider API responses report whether a key is stored, not its
value.

The selected model is a user preference. Provider endpoints and credentials are
installation configuration. See [Model configuration](../admin-guide/model-providers.mdx).

</details>
