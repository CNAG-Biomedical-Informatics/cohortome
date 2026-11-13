---
title: Local agents (MCP)
---

# Local agents (MCP)

Let an agent inspect a patient selection from **COHORTome Desktop**. This optional
prototype is read-only and accepts the two bundled synthetic demos only.
The connector is **included in Desktop builds**; no separate Python installation
or terminal command is needed. It is off by default.

:::warning Where results go

The connection is local, but the agent may use a cloud model. Review its data
handling before sharing. Connecting an agent is separate from configuring
LM Studio or another provider inside COHORTome.

:::

## Share a selection

1. Load a bundled demo. Use **Apply to scope** if you have changed filters.
2. Open **Settings → Query & AI → Local agents (MCP)**.
3. Confirm the permission and choose **Enable and share scope**.
4. Copy the connection settings. In your client's MCP settings, add a **STDIO**
   server using the displayed command and environment values.

Choose **ChatGPT Work / Codex (TOML)** or **Other clients (JSON)** for the
configuration format. The command points to the connector inside COHORTome;
the loopback URL alone is **not** an MCP server URL. See the
[connector guide](https://github.com/CNAG-Biomedical-Informatics/cohortome/tree/main/integrations/mcp)
for source-development setup.

![Desktop settings for explicitly sharing a synthetic patient scope with a local agent](/img/screenshots/local-agents.png)

Keep Desktop open. Treat the connection token like a password; do not paste it
into a chat. **Turn off** revokes access immediately. Access also ends after
eight hours or when Desktop restarts. After restarting or replacing the share,
copy the new settings and restart the client's MCP connection.
On macOS, install COHORTome in Applications before configuring the connector.

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
