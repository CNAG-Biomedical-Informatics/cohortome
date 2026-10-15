---
sidebar_position: 2
---

import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

# Analysis

The numbered bar shows **Method → Patients → Inputs → Review → Results**.
Click a step to reach its controls. Status labels identify missing setup;
methods without additional inputs show **Not required**. These are setup checks,
not a guarantee that the statistical model or data will pass execution checks.

Choose a method under **What analysis would you like to run?** The page shows
the inputs for that method. **Describe my cohort** and **Associate two
measurements** do not need a language model. Catalog methods identify whether
they need a model or are unavailable; their existing input and worker checks
still apply.

Use **Patients and cohorts** to change the scope. Review the method description,
required inputs and research question, then run. The generated request remains
available under **Review or edit the analysis request**. Choose **Write a
request / follow-up** for direct text entry, or **Browse method details** for
the full catalog. Selecting a method does not execute it.

## Custom Python / R scripts (synthetic prototype)

Select **Custom Python / R script** with only the bundled **Synthetic autoimmune
demo** loaded. This is available to users with Detailed access, not just admins.
Other datasets, modified demo files and mixed workspaces are rejected by the
server. Restricted data cannot be enabled by changing a dataset label.

1. Keep your current patient/cohort selections. Selected demo assays are used;
   if no assays are selected, all four demo modalities are prepared.
2. In **Inputs**, choose **Python** or **R**, then **Prepare / reset template**. COHORTome creates `patients`,
   `clinical`, `samples`, and `assays[modality]` objects. The template documents
   column types, units/value kinds, feature IDs, matrix orientation and linkage.
3. Use **Copy template for AI**, describe your question to an external coding
   assistant, and paste its completed script into the editor. The copied
   template contains schemas and feature metadata, not patient IDs or values.
   You can also edit or run the template without any AI.
4. Review the code and click **Run**. It runs through the background queue.
   Open the completed run in Analysis for output files, plots and audit details.

Before copying, check **Check before copying**: it shows the prepared language,
package versions, cohort patient counts and matched A/B sample counts for each
assay. A single-cohort template explicitly says that Cohort B is not used. For
an A-versus-B question, turn on comparison in **Patients** and attach both groups;
preparation and copying are blocked if either group is missing. An assay with
zero samples in one group cannot support that comparison, even when both patient
cohorts exist. Assays with no samples in the scope are listed as not included.

The copied template instructs the external AI to use the declared language and
packages, treat the input contract as authoritative, and explain missing
requirements instead of inventing groups or substituting a different method.
It also asks generated scripts to fail explicitly when required inputs are
missing. These instructions help guide the AI; they do not enforce statistical
correctness. Review the returned code before running it.

Changing language, cohorts or assays requires a fresh preparation. The server checks the
input fingerprint and image identity again at submission and execution. One
custom run per user may be queued/running at a time. Draft code is saved with
the Analysis session; resetting the template replaces that draft, not old runs.

The Python 3.11 environment includes fixed versions of NumPy, pandas, SciPy,
Matplotlib and statsmodels. The R 4.2.2 environment includes base R, limma 3.54.1,
edgeR 3.40.2 and ggplot2 3.4.1. Versions are listed in the generated template.
These are the pinned prototype versions, not a claim to provide the latest releases.
Administrators add packages when building the image; users do not install them
during execution. Scripts have no network, package-installation service or access
to the COHORTome runtime. Limits are 90 seconds, one CPU, 512 MiB RAM and 64
processes. Scratch space is memory-backed and bounded. Save up to eight files
(4 MiB total) as CSV, TXT or PNG under `/work/output`; unsupported or oversized
files are not collected. Logs are truncated. CSV files are script-generated;
review them before opening them in spreadsheet software.

### Audit

Custom runs retain `analysis.py` or `analysis.R`, `input_contract.json`, exact synthetic input
files, logs, output files and `audit.json` with script hash and immutable image ID.
Audit files and results use the existing user ownership and Detailed-access
checks. A completed process is not evidence that its statistics are appropriate.

New direct Analysis replies expose an **Analysis implementation** source snapshot
and hash. These snapshots are deduplicated and retained independently of subsequent
source edits. They identify the core Analysis module, not a standalone reproducer
or an archive of every dependency. Curated background runners retain their adapter
source; R runners execute retained copies of their R script (and the methylation
helper where applicable). Existing command logs and result parameters remain
part of the audit. Older runs cannot acquire historical code retroactively.

### Administrator setup

The web app can remain native Uvicorn. Build the separate execution image:

```bash
docker build -t cohortome-script-sandbox:prototype-v1 docker/script-sandbox
```

The prototype uses the local Unix Docker socket on the native web/worker host.
Both processes need permission to inspect the image; the worker creates containers.
Never mount that socket into the script container. This does **not** wire the
Docker Compose web/worker services to a host daemon. Deploying that arrangement
needs a separate design; do not add a Docker socket mount to solve it casually.

Start Redis and the ordinary Analysis worker using the existing launch recipe.
Restart web and worker after installing backend changes. Missing Docker/image
access blocks execution but does not prevent template preparation. There is no
fallback to running scripts on the host.

The container uses a read-only root and inputs, no network, dropped capabilities,
non-root execution and `no-new-privileges`, following the controls documented in
[Docker's container run reference](https://docs.docker.com/reference/cli/docker/container/run/).
It still shares the host kernel. These checks are a development prototype, not a
claim of safe multi-tenant arbitrary-code execution. Restricted-data support
requires a separate threat review and stronger isolation assessment.

## Clinical measurement selection

For trajectory, treatment-response and Kaplan–Meier methods, select a **Clinical
measurement** in **Inputs**. The list comes from numeric measurements in the
current patient scope and includes units. Coverage shows how many patients have
values and how many have observations on at least two different dates. In A/B
mode, both groups are checked. Missing values are not imputed.

These methods require at least one patient with repeated dated observations in
each group. Kaplan–Meier also requires at least two patients with dated values
per group. These are minimum execution checks, not evidence of adequate sample
size. Measurements with inconsistent units are blocked; harmonize them upstream.

The selected measurement, rather than the example marker in the prompt, controls
the run. It is saved with the session and result. Treatment-response requests
still specify the treatment in the prompt; Kaplan–Meier requests specify the
event operator and threshold there. Review those choices before running.
Measurement selection and these clinical runners do not require an LLM.

## Compare two measurements

Select **Associate two measurements** in Analysis, or follow the shortcut from
Dashboard → Multimodal. Select two matrices from different modalities and an exact feature ID from each.
Each feature dropdown lists up to 50 matches, with readable names where supplied.
Search by name, description, units or ID, then select a match to see its description
and units. Missing annotations are marked explicitly. Gene names come from the
bundled gene annotation; other descriptions must be supplied with the assay.
Changing a matrix or
search clears the previous feature selection. Select **Use these measurements**, review the research question and active scope,
turn off A/B comparison, then run. No language model is used. Parameters,
results and matrix hashes are saved with the Analysis conversation.

For a first trial, select only **Synthetic autoimmune demo** and compare:

- Immune-cell / flow-cytometry matrix: `CD4_T_cells_fraction`
- Serology matrix: `CRP_mg_L`

The synthetic demo also offers explained example buttons: CD4 T cells versus
C-reactive protein, and B cells versus anti-double-stranded DNA antibodies.
These fill the selectors without running an analysis. The measurements and
their associations are simulated, not biological findings.

Dataset authors can add an optional `feature_annotations` object to an assay
entry in `assays/manifest.json`, keyed by the exact feature ID. Each entry can
supply `label`, `description` and `unit` strings. These describe existing features;
they do not rename IDs or convert values. Only annotations for returned features
are sent to the browser. Compact external matrices up to 64 MiB can be browsed
without importing their measurement values into DuckDB.

Results include a scatter plot coloured by recorded clinical disease, overall
and within-group Spearman correlations, and matched, unmatched, missing,
invalid-linkage and repeated-observation counts. Matching requires exact clinical
sample/timepoint IDs and agreeing patient links, not patient ID alone. The
earliest complete dated pair per patient is retained; undated pairs sort last,
with sample ID breaking ties.

This first version requires one dataset, explicit sample-to-patient metadata,
at least three complete patients, and matrices no larger than 64 MiB or 1,000
samples. Large matrices need a prepared feature panel. Constant features and
groups with fewer than three patients have undefined correlations.

Values use their supplied scales: no normalization, imputation or covariate
adjustment is performed. Use normalized RNA data for biological interpretation;
raw or expected counts can reflect library size. Group differences can produce
an overall correlation without a within-group relationship. No p-values,
significance claims, causal claims or predictive models are provided.
Synthetic results demonstrate software behaviour only.

## Research question and hypothesis

Before submitting a workspace analysis, open **Question this analysis addresses**
above the Run button. Exploratory is the default: you can record the question
without asserting an expected result. Hypothesis-driven runs require both a
research question and a hypothesis. State these before running, not after
examining the findings.

Each submission captures its own note and browser timestamp in the saved
conversation. Editing the draft affects future submissions, not earlier result
labels. Background results retain the note in their originating conversation.
Older results without a note are not retrospectively labelled.

This framing documents intent; it does not configure covariates, alter the
statistical method, or get sent to a language model. It is not a tamper-proof
preregistration record. General questions do not use research framing.

Completed responses have an **Analysis result** heading. Summary metrics, plots,
method notes and suggested follow-ups remain together. Expand **Result files**
to see the available file count and a list labelled by format (such as TSV, PNG
or JSON). Opening a file uses a new browser tab; the file endpoint determines
whether it is displayed or downloaded.

Use `Analysis` to summarize data, compare cohorts, run statistical methods, and
review their results.

:::tip Best use
Use `Analysis` after you already know what subset or workspace you want to interpret.
:::

## Main uses

- deterministic workspace summaries
- LLM-planned comparative analysis
- trajectories
- Kaplan-Meier curves
- transcriptomics expression summaries
- DESeq2 differential expression on one raw-count dataset
- methylation matrix QC and PCA on one processed M-value dataset
- limma differential methylation between two cohorts
- exploratory immune-cell and quantitative-serology cohort comparisons
- Hallmark pathway enrichment from a DESeq2-ranked comparison
- curated external analyses through reviewed runners

![Analysis tab with a plotted result and follow-up queries](/img/screenshots/analysis-tab.png)

## Choose the question context

Analysis has the same explicit context switch as Query:

- `Workspace` uses the active data, scopes, saved cohorts, and Analysis Catalog.
- `General question` asks the selected approved model without workspace data.

In General-question mode, workspace setup and catalog controls are hidden
because they are not part of the request. The response is marked `No workspace
context`, and its history is kept separate from workspace analysis. Switching
back to `Workspace` restores the research workflow without mixing the two
conversations.

The typed question and recent General-question history are still sent to the
selected provider. Do not include confidential or patient-level information
when that provider is external.

## Two main modes

Within `Workspace` context, Analysis can work in two broad ways:

- single-workspace or single-subset interpretation
- saved-cohort comparison

<Tabs>
  <TabItem value="single" label="Single scope" default>
    <div>
      <p>Use this mode when you want to interpret:</p>
      <ul>
        <li>the full workspace</li>
        <li>a manually selected scope</li>
        <li>one saved cohort without explicit A/B comparison</li>
      </ul>

      <p>Typical questions:</p>
      <ul>
        <li>what stands out in this workspace</li>
        <li>how does this measure change over time</li>
        <li>what does this Kaplan-Meier curve mean</li>
      </ul>
    </div>

  </TabItem>
  <TabItem value="compare" label="Compare mode">
    <div>
      <p>Use this mode when you want explicit A/B interpretation between:</p>
      <ul>
        <li><code>Cohort A</code></li>
        <li><code>Cohort B</code></li>
      </ul>

      <p>This is the intended place for:</p>
      <ul>
        <li>disease and medication burden comparison</li>
        <li>trajectory comparison</li>
        <li>Kaplan-Meier A/B analysis</li>
        <li>clinician-style cohort review</li>
      </ul>
    </div>

  </TabItem>
</Tabs>

## Analysis sessions

Analysis is session-based.

That means each thread can preserve:

- its own prompt history
- scope
- compare mode state
- attached saved cohorts
- generated turns and plots

This is useful because clinical and assay interpretation often unfolds across several questions rather than one prompt.

## Analysis Catalog and quick prompts

The Analysis tab separates two things:

- `Analysis Catalog`
  - tools
  - curated analyses with real setup requirements, validation rules, or structured outputs
- `Quick prompts`
  - questions
  - open-ended summaries, interpretation requests, and clinician-style prompts

The practical rule is simple:

- if it can be naturally asked, it belongs in prompts
- if it invokes a specific method or runner, it belongs in the catalog

The main tab shows:

- a foldable catalog strip for curated tools
- a `Browse analyses` drawer with the full catalog
- a visible quick-prompt area for direct questions

The foldable catalog strip and the drawer share the same browsing state:

- search text
- active filter
- selected analysis

Searches and filters therefore stay the same in both places.

The catalog is available only when the active workspace allows `Detailed` in-app access.

In a summary-only workspace, the tab explains that the catalog requires `Detailed` access instead of showing a generic load failure.

Selecting a catalog item does not create a separate execution system. It preconfigures the current Analysis thread with:

- the prompt
- compare-mode defaults when needed
- the preferred execution mode

For a curated tool, follow the workflow bar in order:

1. choose the analysis
2. complete its setup checklist
3. review the configured prompt
4. run it and inspect the result

The checklist shows only requirements that apply to that tool, such as Cohort A,
Cohort B, one compatible assay, minimum cohort overlap, a language model, or a
background worker. `Next` marks the first incomplete requirement and provides a
button that opens the relevant control. Completed requirements remain visible
as `Done`; later requirements wait until the preceding step is complete. Quick
prompts that do not select a curated tool continue to need no extra setup.

Use quick prompts for summaries such as “what stands out” or an explanation of
differences between cohorts. Use the catalog to choose a specific method.

## Analysis workflows

Some catalog entries are pre-made workflows rather than single tools.

An Analysis Workflow is a curated project-approved sequence of analysis steps. Users do not assemble these step chains manually; the app exposes only reviewed workflows with fixed execution rules.

Current first workflow:

- `Transcriptomics signature workflow`
  - runs `DESeq2 differential expression`
  - then runs `Hallmark pathway enrichment`
  - stores one background job with step-level artifacts under one workflow result

This keeps the user-facing model simple: one workflow launch, one job in `Jobs`, one combined Analysis result.

The workflow is intentionally pre-made. Users choose the approved workflow, but they do not concatenate arbitrary catalog tools.

For this first workflow, select exactly one compatible raw-count transcriptomics dataset. If more than one compatible transcriptomics dataset is available, choosing a second one replaces the first selection. The workflow does not merge multiple count matrices or compare transcriptomics files against each other.

The workflow result keeps interpretation and plots visible first. Raw output files are folded under `Result files` and can be opened when needed.

## Assay tool requirements

The current assay catalog tools are method-driven.

Examples:

- `DESeq2 differential expression`
- `Hallmark pathway enrichment`
- `Methylation QC and PCA`
- `limma differential methylation`
- `Immune-cell Wilcoxon cohort comparison`
- `Serology Wilcoxon cohort comparison`

These tools do not compare two transcriptomics assays against each other.

The transcriptomics comparison tools use:

- one selected transcriptomics assay with the value type required by the method
- `Cohort A`
- `Cohort B`

The cohorts define the groups.
The transcriptomics assay defines the transcriptomics matrix.

Both cohorts must overlap the same selected transcriptomics assay.

### limma-voom adjustment

The limma-voom method accepts fractional RSEM expected counts. An administrator
can declare numeric and categorical adjustment variables in the assay manifest:

```json
{
  "sample_metadata_file": "assays/transcriptomics/sample_metadata.tsv",
  "patient_linkage": "sample_metadata_file",
  "analysis_covariates": ["age", "sex", "batch"],
  "analysis_covariate_types": {
    "age": "numeric",
    "sex": "categorical",
    "batch": "categorical"
  }
}
```

The metadata table must contain `sample_id`, `patient_id`, and the declared
covariate columns. Numeric-looking batch identifiers remain categorical when
declared that way. Exact-sample linkage may also use a technical metadata table
without a patient column when the manifest explicitly declares `exact_sample_id`.

The selected cohorts determine which samples enter the model. All selected
covariate values must be complete; prepare and document a complete-case cohort
before running if necessary. The runner stops for missing or invalid values,
constant requested covariates, rank-deficient designs, or no residual degrees
of freedom. It does not silently remove patients or adjustment variables.

The result states which covariates were used and reports the Cohort A minus
Cohort B effect. Without declared covariates it is labelled an unadjusted
exploratory model. Result files include `model.json`, `design_matrix.tsv`,
`contrast.tsv`, `gene_filter.tsv`, `normalization_factors.tsv`, and
`session_info.txt`, alongside the scoped sample table, covariate specification,
and existing expression results. These files retain the actual design,
filtering, normalisation, and package versions for review.

Expression filtering uses the final design matrix. The input-gene count and
the genes actually tested after filtering are reported separately. Model
selection remains an explicit study decision; an LLM does not choose or remove
adjustment variables automatically.

If the chosen dataset contributes samples to only one side, the curated differential-expression tools fail with a validation error instead of silently dropping one cohort.

For the current `DESeq2` and Hallmark pathway tools, the first-version constraints are:

- at least two samples in `Cohort A`
- at least two samples in `Cohort B`
- one sample per patient

In practice, that means baseline-only transcriptomics datasets are the safest first choice.

For the synthetic large transcriptome fixtures, remember that treatment-specific matrices only contain their own patient subset. For example, an `infliximab` matrix does not contain `vedolizumab` patients. If you want a broad split across many synthetic patients, use the baseline matrix for that workspace.

The methylation tools use one selected processed M-value assay view. A view can
be the complete externally stored assay or an administrator-installed,
versioned feature panel. Panel choices are labelled in the assay selector and
their identity, version, source, and match counts are retained with the result.
The complete probe matrix remains in the protected dataset files; COHORTome
does not materialize all CpG-by-sample values in DuckDB.

The panel summary distinguishes probes that were absent from the supplied
matrix from probes excluded during ingestion validation. In particular, a CpG
with any `Inf` or `-Inf` M-value is excluded from the compact analysis view and
counted explicitly; COHORTome does not coerce an infinite value to a finite
number. This filtering decision and the resulting retained feature count are
stored with the analysis provenance.

`Methylation QC and PCA` checks the supplied matrix and sample linkage in the current Analysis scope. It does not repeat raw-array preprocessing or probe filtering from IDAT files. `limma differential methylation` uses Cohort A and Cohort B as the comparison groups and requires both cohorts to overlap the same selected methylation assay.

The immune-cell and quantitative-serology tools also use one selected assay
plus disjoint saved Cohort A and Cohort B selections. Each cohort must overlap
the assay by at least three samples. The runner applies a Wilcoxon rank-sum test
to each feature, reports rank-biserial effect sizes, and controls the displayed
feature-wise false-discovery rate with Benjamini-Hochberg correction.

These comparisons are deliberately labeled **exploratory and unadjusted**.
They test values on the scale supplied by the assay release: COHORTome does not
normalize, batch-correct, transform, or impute those measurements in this
runner. A positive rank-biserial effect means higher ranks in Cohort A; a
negative effect means higher ranks in Cohort B. Demographic, recruitment,
treatment, technical, and other confounders remain unmodeled, so this result is
useful for screening and prioritization rather than confirmatory inference.
Immune-cell abundance features can also be compositional, while serology
missingness can vary by marker; inspect the cohort-specific missing counts
before interpreting the ranking.

The compact source matrices remain in the protected dataset files. They are
read directly by the curated runner, are not materialized in DuckDB, and are
not copied into the job output. Analysis stores only compact aggregate results
and records of the inputs and method used.


## Catalog search, filters, and suggestions

Search and filter the Analysis Catalog to find a suitable tool.

Search matches against:

- tool name
- description
- category
- runner type
- tags

Filters are intentionally coarse:

- `All`
- `Clinical`
- `Assays`
- `Workflow`
- `Background jobs`
- `External`

Use these filters to shorten the list of tools.

When a selected catalog item requires assay data, a compatible assay selector appears below the catalog search and filters. For single-assay analyses, including transcriptomics, methylation, immune-cell, and quantitative-serology tools, the selector behaves as a single-select control.

The folded catalog in the main tab also shows a `Suggested` strip.

Suggestions are lightweight and local:

- the currently selected tool is favored
- recently used tools are favored
- frequently used tools are favored
- tools that fit the current workspace and setup are ranked higher

Examples of setup-aware suggestions:

- assay tools rank better when a compatible assay is available
- compare-oriented tools rank better when compare mode is active

:::note
Suggested tools are a convenience ranking, not a backend recommendation service. They are derived from local browser state for the current user.
:::

## Starter prompts

Quick prompts still include mode coding:

- `Deterministic`
- `LLM-planned`
- `LLM interpretation`

These labels reflect how the request is routed.

For `LLM interpretation` prompts, the app no longer silently falls back to a deterministic clinical summary when the provider cannot be used.

Instead, Analysis returns an explicit provider-policy or provider-unavailable message.

Follow-up questions generated beneath an Analysis result are amber and labeled `LLM interpretation`. Selecting one prepares an LLM-only follow-up for the next run; it does not silently switch back to a deterministic analysis route.

## Compare mode

Compare mode uses:

- `Cohort A`
- `Cohort B`

These are true saved cohorts, not the full workspace.

Manual workspace scope is allowed for single-analysis workflows, but saved cohorts are the intended model for explicit A/B comparison.

:::warning
If the comparison matters, prefer saved cohorts over temporary manual scope.

That keeps the session understandable and reduces accidental drift.
:::

## Follow-up queries

Analysis suggests follow-up questions for several result types, including plots.

Examples:

- Kaplan-Meier follow-ups
- trajectory follow-ups
- assay volcano follow-ups
- A/B comparison follow-ups

Follow-up questions are amber and labeled `LLM interpretation`. Selecting one
prepares the question; the selected model is called when you run it, subject to
the workspace's model-access rules.

:::info
Follow-up chips are generated from the latest result context plus short recent Analysis history, not from an unlimited chat memory.
:::

## What happens if a saved cohort disappears

Analysis sessions may depend on saved cohorts.

Because of that, the app now protects saved cohorts from deletion when they are still referenced by an Analysis session.

This prevents a session from silently losing the cohort it depends on.

:::note
If a cohort is still attached in the current page, the UI can block deletion locally. If an older saved Analysis session still references it, the backend will block deletion as well.
:::

## Workspace context

Analysis always runs inside the current workspace. Saved cohorts narrow that workspace for a particular analysis.

## In-app disclosure and AI providers

Analysis follows the same policy split as Query:

- in-app detail policy
- AI-provider policy

That means:

- a deterministic Analysis turn may show a local clinical summary without sending it anywhere
- if AI providers are `Safe summary`, provider-facing Analysis context is reduced to structural/provider-safe context only
- if AI providers are `Blocked`, Analysis stays local
- private dataset context is always blocked when the selected provider is external
- `LLM interpretation` prompts that require a provider may return a policy or availability message instead of silently degrading into a richer local summary

:::note
The in-app answer the user sees is not automatically the same as what an AI provider would be allowed to receive.
:::

## Common analyses

Examples of questions that fit well here:

- deterministic workspace summary
- temporal change over time
- trajectory of a numeric longitudinal measure
- Kaplan-Meier time to event
- transcriptomics expression by medication
- exploratory volcano comparison
- curated external runner demo analyses

As a rule:

- summaries and interpretation requests fit best as prompts
- trajectories, Kaplan-Meier, assay tools, and external runners fit best as catalog analyses

## Curated external analyses

The Analysis Catalog can now describe curated external runners, not only built-in Python analyses.

Current supported idea:

- catalog entries define a `runner_type`
- the backend dispatches to a reviewed executor
- catalog entries also define an `execution_backend`
  - `sync`
  - `job`

This keeps the catalog stable while allowing future curated integrations such as:

- `Rscript`
- `Snakemake`
- `Nextflow`
- external CLI tools
- containerized runners

:::warning
This is not arbitrary pasted-code execution. External analyses are curated and backend-controlled.
:::

## Background jobs

Longer curated external analyses can now run through a background queue instead of holding the HTTP request open.

Current model:

- queue backend: `RQ + Redis`
- progress and results: the `Jobs` drawer
- current queued runner types include curated `Rscript`, `Snakemake`, `Nextflow`, and pre-made Analysis workflows

When a catalog item is configured as a background job:

- the Analysis thread shows that the job was submitted
- the `Jobs` drawer shows queued, running, completed, failed, or cancelled state
- completed jobs can be reopened into `Analysis`
- generated result files are folded under `Result files` in the `Jobs` drawer

If the original Analysis session no longer exists, the app can recover the completed result into a fresh Analysis session shell instead of dropping the result.

## Deleting chats and generated data

There are two deletion options:

- `Delete chat only`
  - removes the Analysis session record
- `Delete chat and generated data`
  - removes the Analysis session
  - removes linked terminal job data on disk for that session

Current guardrail:

- if linked jobs are still `queued` or `running`, `Delete chat and generated data` is blocked

This keeps active background work from being destroyed mid-run.

## Patient level versus sample level

Analysis may use either patient-level or sample-level scope depending on the analysis type.

Examples:

- broad clinical summaries
  - often patient-oriented
- assay comparisons
  - often sample-aware
- Pheno-Ranker handoff
  - should preserve sample IDs

:::warning
Do not assume all Analysis questions are patient-level. Assay and Pheno-driven paths are often sample-aware.
:::

## Practical advice

Use `Analysis` when the main question is:

- what stands out in this subset
- how do these two saved cohorts differ
- what does this measure or event look like over time

Use saved cohorts instead of manual scope text when:

- the comparison matters
- you will come back to the same subset later
- you want the session to remain understandable over time
