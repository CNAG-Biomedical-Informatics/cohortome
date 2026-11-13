---
title: Local agents (MCP)
---

# Local agents (MCP)

Let an agent inspect a patient selection from **COHORTome Desktop**. This optional
prototype is read-only and accepts the two bundled synthetic demos only.

:::warning Where results go

The connection is local, but the agent may use a cloud model. Review its data
handling before sharing. Connecting an agent is separate from configuring
LM Studio or another provider inside COHORTome.

:::

## Share a selection

1. Load a bundled demo. Use **Apply to scope** if you have changed filters.
2. Open **Settings → Query & AI → Local agents (MCP)**.
3. Review the permission, then share the current scope.
4. Configure your local MCP client using the
   [connector setup](https://github.com/CNAG-Biomedical-Informatics/cohortome/tree/main/integrations/mcp).

Keep Desktop open. Treat the connection token like a password; do not paste it
into a chat. You can revoke access from the same panel. Access also ends after
eight hours or when Desktop restarts.

## What an agent can do

| Tool | Purpose |
| --- | --- |
| Describe scope | Identify the shared datasets and patient count |
| List filter fields | Discover the available clinical filters |
| Find patients | Combine supported filters and page through matching IDs |
| Summarize selection | Describe patients within the shared group |

For example: **“Within the shared selection, how many patients have both
transcriptomics and proteomics?”**

The share is a **snapshot**. Later Dashboard selections do not change it, and
agent queries cannot expand it. Share again to replace the snapshot; saving a
cohort is not required. Tools cannot run scripts or analyses, modify data, or
change the app's scope. Remote connections and Web deployments are not included
in this prototype. Synthetic results are software tests, not biological evidence.
