---
sidebar_position: 6
---

import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

# User Journeys

## Choose an appearance

In **Settings**, choose **Light**, **Dark**, or **System** under Appearance, then
select **Save**. The preference is stored with your user account. System follows
your browser's operating-system colour preference, including changes while the
app is open. Light remains the default.

Interactive charts update with the app theme; their data colour scales do not
change. Exported image files and the separate OHIF DICOM viewer retain their own
appearance.

This page collects realistic end-to-end journeys that combine `Query`, `Analysis`, `Saved Cohorts`, and `Pheno-Ranker`.

Use it as a practical companion to the reference-style pages in the rest of the docs.

:::tip
Each example starts with a research task and shows the steps in the app.
The execution path may still be deterministic, LLM-planned, or LLM-interpreted depending on the prompt and the available context.
:::

## Journey 1: Find patients taking biologics

**Goal:** understand how many patients in the current workspace take biologics, even if the wording is natural or multilingual.

### Start in Query

Example prompts:

- `How many patients take biologics?`
- `Which patients take biologics?`
- `Wie viele Patienten Biologika haben?`

Typical follow-up prompts:

- `How many patients take steroids?`
- `Which patients do not have Crohn Disease but take Infliximab?`

If the user is refining one subset step by step, enable:

- `Prompt scope: previous result`

<Tabs>
  <TabItem value="journey-intent" label="Intent">
    <div>
      <p>The user is trying to express a medication-class concept, not necessarily one exact drug name.</p>
      <ul>
        <li><code>biologics</code></li>
        <li><code>steroids</code></li>
        <li>mixed disease plus medication conditions</li>
      </ul>
    </div>
  </TabItem>
  <TabItem value="journey-routing" label="Likely routing">
    <div>
      <ul>
        <li><strong>Deterministic</strong> if the condition maps cleanly to known medications or disease filters</li>
        <li><strong>LLM-planned</strong> if the phrasing is broader, multilingual, or semantically indirect</li>
      </ul>
    </div>
  </TabItem>
</Tabs>

### Why this journey matters

This is a good example of where the app may need more than exact string matching:

- the user may refer to medication classes rather than one drug
- the prompt may mix disease and medication conditions
- the user may write in Spanish, German, or another language

:::info
The visible reply can still be patient-level even when the app preserves sample-aware metadata for later handoff.
:::

:::note Multilingual prompts
Prompts such as `Wie viele Patienten Biologika haben?` are a good example of why `LLM-planned` interpretation can be useful in `Query`. The exact outcome still depends on the deployed model and the current app logic, so treat multilingual support as a capability to validate in your own instance.
:::

### Expected outcome

By the end of this journey, the user should have:

- a count or list of matching patients
- a reusable subset that can be sent to `Analysis`
- enough confidence to refine the subset with additional clinical conditions

## Journey 2: Learn more about the biologics subset

**Goal:** take the subset built in `Query` and interpret it further.

### Typical flow

1. Run a Query such as `Which patients take biologics?`
2. Click `Open in Analysis`
3. Ask follow-up questions in the Analysis chat
4. Save the subset as a saved cohort if it will be reused

### Good Analysis follow-ups

- `Can you summarize this workspace?`
- `What stands out clinically in these patients?`
- `Can you explain this in simpler terms?`
- `What should I look at next?`

<Tabs>
  <TabItem value="analysis-routing" label="Analysis modes" default>
    <div>
      <ul>
        <li><strong>Deterministic</strong> for structured workspace summaries and known analysis paths</li>
        <li><strong>LLM-planned</strong> when the user asks for a more open analytical action</li>
        <li><strong>LLM interpretation</strong> when the user wants narrative explanation or a clinician-style interpretation</li>
      </ul>
    </div>
  </TabItem>
  <TabItem value="analysis-followups" label="What to save">
    <div>
      <p>Save the subset as a cohort when:</p>
      <ul>
        <li>the subset will be reused in Analysis later</li>
        <li>the same subset will be compared against another one</li>
        <li>the user wants a stable named object rather than a transient Query result</li>
      </ul>
    </div>
  </TabItem>
</Tabs>

### What this journey demonstrates

- `Query` is the subset builder
- `Analysis` runs methods and helps you interpret results
- saved cohorts are the reusable bridge between tabs and sessions

:::note
The Analysis session may use deterministic, LLM-planned, or LLM-interpreted behavior depending on the question. The user does not need to decide that up front.
:::

## Journey 3: Compare two medication cohorts clinically

**Goal:** compare two clinically meaningful subsets with survival and longitudinal analysis.

### Build the two cohorts

Start from `Dashboard` or `Query` to understand which medications and diseases are represented in the workspace.

Then build and save two subsets in `Query`, for example:

- `Which patients have Crohn Disease and take Infliximab?`
- `Which patients have Crohn Disease but do not take Infliximab?`

Save both subsets as saved cohorts.

### Move to Analysis compare mode

Attach one saved cohort as `Cohort A` and the other as `Cohort B`.

Typical analyses:

- Kaplan-Meier curve for clinical relapse
- trajectory of `Leukocyte Count`

Typical follow-up questions:

- `Can you explain the plot?`
- `Which cohort appears to do better and why?`
- `How many events drove this separation?`
- `Which cohort changes faster over time?`

<Tabs>
  <TabItem value="clinical-survival" label="Kaplan-Meier" default>
    <div>
      <p>Good for event-oriented clinical comparison, for example time to relapse.</p>
      <p>Typical interpretation style:</p>
      <ul>
        <li>deterministic plot generation</li>
        <li>deterministic or LLM-assisted explanation afterwards</li>
      </ul>
    </div>
  </TabItem>
  <TabItem value="clinical-trajectory" label="Trajectory">
    <div>
      <p>Good for longitudinal measures such as <code>Leukocyte Count</code>.</p>
      <p>Typical interpretation style:</p>
      <ul>
        <li>measure-specific trend analysis</li>
        <li>follow-up questions about which cohort changes faster or more clearly</li>
      </ul>
    </div>
  </TabItem>
</Tabs>

:::warning
If the comparison matters, use saved cohorts rather than temporary manual scope. That keeps the session stable and understandable.
:::

### Expected outcome

By the end of this journey, the user should have:

- two clearly defined saved cohorts
- one or more clinical comparisons in Analysis
- an interpretable thread that can be revisited later

## Journey 4: Explore transcriptomics differences between two groups

**Goal:** compare two subsets at the assay level.

### Typical flow

1. Reuse two saved cohorts that were built in `Query`
2. Open `Analysis`
3. Ask for a transcriptomics comparison such as:
   - exploratory volcano plot
   - expression of one gene

Example prompts:

- `Show an exploratory volcano plot for these two cohorts`
- `Show expression of ENSG00002700028 in the current Analysis scope.`

<Tabs>
  <TabItem value="assay-exploratory" label="Exploratory volcano" default>
    <div>
      <p>Use this when the user wants a broad exploratory contrast between two groups.</p>
      <ul>
        <li>good for ranking features and directional inspection</li>
        <li>good for asking what drives the main separation</li>
      </ul>
    </div>
  </TabItem>
  <TabItem value="assay-gene" label="Gene-focused follow-up">
    <div>
      <p>Use this when the user already has a concrete feature in mind, for example one gene identifier.</p>
      <ul>
        <li>good for targeted follow-up after a broader exploratory result</li>
        <li>sample-aware interpretation matters here</li>
      </ul>
    </div>
  </TabItem>
</Tabs>

### Why this journey is different

Assay analysis is often sample-aware rather than purely patient-level.

That means:

- the saved cohort can still be displayed in patient-oriented language elsewhere
- the underlying scope sent into assay analysis may stay sample-level

:::tip
If the result comes from `Pheno-Ranker` or another sample-driven path, preserve the sample-level handoff into Analysis.
:::

### Expected outcome

The user should be able to:

- inspect one exploratory differential expression view
- ask gene-specific follow-up questions
- keep the interpretation in the same Analysis thread

## Journey 5: Use Pheno-Ranker and reuse selected samples

**Goal:** run `Pheno-Ranker`, interpret the results, and reuse selected samples elsewhere in the app.

### Typical flow

1. Open `Pheno-Ranker`
2. Run either:
   - patient mode
   - cohort mode
3. Inspect the heatmap and MDS views
4. Select samples from the MDS plot
5. Reuse the selected sample IDs

<Tabs>
  <TabItem value="pheno-patient" label="Patient mode" default>
    <div>
      <p>Good when one target patient or sample should be matched against the active workspace references.</p>
    </div>
  </TabItem>
  <TabItem value="pheno-selection" label="Selection reuse">
    <div>
      <p>Good when the user wants to take a visually selected region or cluster from MDS and reuse it elsewhere in the app.</p>
    </div>
  </TabItem>
  <TabItem value="pheno-explain" label="Explanation modes">
    <div>
      <ul>
        <li><strong>Explain results</strong> for deterministic explanation</li>
        <li><strong>Explain with LLM</strong> for narrative interpretation grounded in the ranked evidence</li>
      </ul>
    </div>
  </TabItem>
</Tabs>

### Reuse options

From the current Pheno selection, the user can:

- copy selected IDs
- open the selection in `Analysis`
- save the selection as a saved cohort

### Important scope rule

Selections coming from `Pheno-Ranker` should remain sample-level.

If a multi-file run shows temporary prefixes such as:

```text
C1_SYN001:week_0
```

the app should normalize them before:

- copying to the clipboard
- opening in Analysis
- saving as a cohort

:::info
`Pheno-Ranker` may operate on several active workspace files even when the workspace contains only a small number of datasets.
:::

### Interpreting results

The user may then ask for:

- deterministic explanation
- LLM explanation

This is useful when the ranked output is strong but the user also wants a narrative interpretation of why certain samples cluster or match.

## Choosing the right journey

Use this rough rule of thumb:

- use `Query` when the first question is `who matches this condition?`
- use `Analysis` when the question becomes `what does this mean?`
- use saved cohorts when the subset must survive across tabs or sessions
- use `Pheno-Ranker` when similarity between phenotypic profiles is the main task

:::tip
If a workflow starts in `Query`, becomes explanatory in `Analysis`, and later needs phenotypic similarity, that is normal. The tabs are meant to compose rather than behave like isolated tools.
:::

## Settings and software versions

Settings saves your preferences for your account. Enable background-run
notifications to see an in-app message when an observed queued or running job
completes or fails. The app must remain open; these are not email or operating
system notifications. Previously completed runs do not trigger messages on login.
Use **View runs** to inspect the results or failure details.

Open **Settings → About COHORTome** for the application version, source checkout
revision and detected dependency versions. **Copy version report** prepares a
short report for troubleshooting, without user details, dataset information,
paths or configuration. Missing optional tools are labelled. The report describes
the web server, not separate workers, Redis server or external imaging viewers;
use the Queue worker indicator to check worker availability. Versions are cached
until the web server restarts. A checkout revision does not describe uncommitted
edits.
