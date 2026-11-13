---
title: Agent access (MCP)
---

# Agent access (MCP)

Let an agent inspect a patient selection and propose analyses in **COHORTome
Desktop**. Access is limited to the two bundled synthetic demos. **You approve
each run in COHORTome**; the agent cannot approve its own requests.
The connector is **included in Desktop builds**; no separate Python installation
or terminal command is needed. It is off by default.

:::note[Ask from another application]

With MCP, you ask questions **in Codex**, which calls COHORTome's tools to read
your shared selection. You do not need LM Studio or a model configured inside
COHORTome. To use model assistance **inside COHORTome's Query and Analysis**,
see [Connect an LLM](../admin-guide/model-providers.mdx) instead.

:::

:::info[Client compatibility]

**Codex Desktop and Codex CLI worked on macOS.** In our test, **ChatGPT Work did
not expose the COHORTome MCP tools** with the same local configuration. Use Codex
for this setup; a working CLI connection does not mean the tools are available
in a ChatGPT conversation.

:::

:::warning[Where results go]

The connection is local, but the agent may use a cloud model. **STDIO or a
localhost URL does not establish where data are processed.** Treat the assistant
as external unless its processing environment has been independently verified.
Review its data handling before sharing. Connecting an agent is separate from configuring
LM Studio or another provider inside COHORTome.

:::

## Share a selection

1. Load a bundled demo. Use **Apply to scope** if you have changed filters.
2. Open **Settings → Query & AI → Agent access (MCP)**.
3. Confirm the permission and choose **Enable and share scope**.
4. Copy the connection settings. Sharing takes effect immediately; the general
   **Save changes** button is not required for this action.

## Connect Codex Desktop

Keep Codex and COHORTome on the **same computer**. On macOS, install COHORTome
in Applications before configuring the connector.

In Codex, open **Settings → MCP servers**, add a server named `cohortome`, and
choose **STDIO**. Copy the values shown by COHORTome:

| Setting | Value |
| --- | --- |
| Command | Full path to the bundled `cohortome-mcp` executable |
| Arguments / working directory | Leave empty |
| `COHORTOME_MCP_URL` | Exact URL, including the port and `/local-agent/call` |
| `COHORTOME_MCP_TOKEN` | Connection token |

Save the server and restart **Codex's MCP connection**, then open a new local
conversation. If editing configuration directly, choose COHORTome's
**Codex (TOML)** format and use the generated entry in `~/.codex/config.toml`
(older builds label this **ChatGPT Work / Codex**). See the
[client setup guide](https://learn.chatgpt.com/docs/extend/mcp).

:::tip[Copy the port; do not type it from memory]

A wrong port prevents the connection even when the server is enabled.
The loopback URL is an internal connector address, **not** a remote MCP URL.
This local STDIO setup needs no tunnel or additional OpenAI API key.

:::

Other local MCP clients can use the **Other clients (JSON)** format. See the
[connector guide](https://github.com/CNAG-Biomedical-Informatics/cohortome/tree/main/integrations/mcp)
for source-development setup.

![Desktop settings for explicitly sharing a synthetic patient scope with a local agent](/img/screenshots/local-agents.png)

Keep Desktop open. Treat the connection token like a password; do not paste it
into a chat. **Turn off** revokes access immediately. Access also ends after
eight hours or when Desktop restarts. After expiry, restart, or turning access
off, enable sharing again, copy the new settings and restart the client's MCP
connection. If you lose the token, turn access off and enable it again.

### Change the shared selection

Apply your new scope in COHORTome, then choose **Update shared selection** in
Agent access. **The token stays the same; no client restart is needed.** Ask
the assistant to call `describe_scope` again; earlier chat answers still refer
to the previous selection. Updating does not extend the original expiry time.

The MCP badge shows whether access is **on** and how many patients are shared,
even when the settings section is folded. **On** means access is enabled, not
that an assistant is connected. **Selection changed—not shared yet** means the
assistant still sees the previous snapshot. A failed update keeps that snapshot.

## Try a query

First verify that the conversation uses MCP, not screen control:

> Use only the cohortome MCP tools. Do not use screenshots, mouse, keyboard,
> browser automation, or terminal commands. Call describe_scope, then summarize
> the result.

Look for a **`cohortome/describe_scope`** tool call and check that the returned
datasets and patient count match the shared selection. Then ask:

> Among patients with rheumatoid arthritis in the shared selection, how many
> have linked transcriptomics data? Break the counts down by dataset. Use only
> the cohortome MCP tools.

Counts depend on the selection you shared. These are patient-level links, not
proof that assays were performed at the same visit or on the same specimen.

| If you see… | Check |
| --- | --- |
| No COHORTome tools in this chat | Server enabled in Codex, correct local host, and a new conversation after restarting the MCP connection |
| Cannot reach COHORTome | Desktop is open; the copied URL and port are exact |
| Expired or revoked connection | Share again, copy the new settings, and restart the MCP connection |

General terminal permission is not needed to call MCP tools. The client does
need permission to start the configured connector process.

## What an agent can do

| Tool | Purpose |
| --- | --- |
| Describe scope | Identify the shared datasets and patient count |
| List filter fields | Discover the available clinical filters |
| Find patients | Combine supported filters and page through matching IDs |
| Summarize selection | Describe patients within the shared group |
| Describe dataset | Read its description and linked assay coverage within the share |
| Get clinical records | Page through one shared patient's clinical records |
| List biosamples | Inspect recorded specimen metadata for a shared patient |
| List assay features | Search feature IDs in a dataset's assay |
| Get assay measurements | Read one numeric feature, retaining patient and sample links |
| List analyses | Discover curated analyses and their input requirements |
| Check analysis requirements | Identify basic blockers and checks still needed; does not launch a run |
| Prepare analysis run | Validate two groups and request your approval for a supported comparison |
| Inspect analysis run | Check an approved run's status; read result rows only with separate permission |

For example:

> Describe the shared datasets and their assays. Find a proteomics feature,
> then show its values for shared patients, keeping sample IDs and missing values.

> Which curated analyses could use these data? Check their requirements and
> tell me what I still need to select in COHORTome. Do not run anything.

Measurement browsing accepts compact numeric matrices up to **64 MiB**, one
feature at a time. Values keep their source scale; no normalization, imputation
or averaging is applied. Clinical record tools omit arbitrary `info` and
provenance fields. Missing biosample records do not mean assays are absent.

Analysis checks are **partial**, not a readiness guarantee: cohort definitions,
measurements, usable sample counts and runtime availability still need validation
in COHORTome. Preparing a run performs those additional checks before requesting
approval.

## Approve an analysis

Share **one bundled dataset** and ask the agent to select two non-overlapping
groups of shared patients. Supported comparisons are **DESeq2**, **limma-voom**,
and **Wilcoxon tests for flow cytometry or serology**. The assay must have the
required input type and enough usable samples; the corresponding R packages
must be installed.

> Find the available flow cytometry assay. Prepare a Wilcoxon comparison of
> patients with rheumatoid arthritis against patients with lupus. Use only
> shared patients and wait for my approval in COHORTome.

1. Follow **Review requests**, or open **Settings → Query & AI → Agent access (MCP)**.
2. Review the assay, patient groups, sample counts and covariates.
3. Optionally allow the agent to read feature-level result tables. **This is
   unchecked by default** and is separate from permission to run the analysis.
4. Choose **Approve and run**, or **Reject**.

The approved run appears in **Analysis chats, Jobs and Run history**, labelled
**MCP**. Your active tab and scope do not change. Ask the agent to inspect the
plan's status; plots and full outputs remain available in COHORTome.

:::note[Approval lifetime]

Unapproved requests expire after **15 minutes**, or when the shared selection
changes. Turning MCP off prevents further agent access but **does not cancel an
already approved job**. Restarting Desktop clears MCP plans and permissions;
saved chats and run outputs remain in COHORTome.

:::

The share is a **snapshot**. Later Dashboard selections do not change it, and
agent queries cannot expand it. Use **Update shared selection** to replace the snapshot; saving a
cohort is not required. Tools cannot submit arbitrary scripts, modify data, or
change the app's scope. Remote connections and Web deployments are not included
in this prototype. Synthetic results are software tests, not biological evidence.
