# Local MCP connector

Connect a local MCP client to a selection explicitly shared by COHORTome Desktop.
The connector uses the official [Python MCP SDK](https://github.com/modelcontextprotocol/python-sdk/tree/v1.x)
and stdio. It does not open databases or reuse the desktop browser cookie.

## Installed Desktop

The connector is bundled with Desktop under `engine/mcp`; users do not need
Python, pip or another application. In **Settings → Query & AI → Local agents
(MCP)**, confirm consent, then choose **Enable and share scope**. Copy the full
configuration for ChatGPT Work / Codex (TOML) or another client (JSON).

In the client's MCP settings, add a **STDIO** server using that executable and
the supplied environment values. Do not use the loopback URL as a remote MCP
URL. On macOS, first move COHORTome to Applications, not the mounted DMG.
**Turn off** revokes access immediately. Restarting COHORTome or replacing a
share requires copying fresh settings and restarting the client connection.
The connector is not included in the Web deployment.

## Source-development setup

From the COHORTome repository root, with Python 3.11 or newer:

```bash
python3 -m venv integrations/mcp/.venv
integrations/mcp/.venv/bin/python -m pip install -r integrations/mcp/requirements.txt
```

On Windows, use `py -3` for the first command and
`integrations\mcp\.venv\Scripts\python.exe` for the second. Keep this environment
separate from COHORTome: the SDK requires newer dependencies than the app.

1. Open Desktop and load one or both bundled synthetic demos.
2. Apply any patient filters, then open **Settings → Query & AI → Local agents (MCP)**.
3. Review the consent checkbox and share the applied scope. Copy the connection
   values into your MCP client's local configuration:

```json
{
  "mcpServers": {
    "cohortome": {
      "command": "/absolute/path/to/cohortome/integrations/mcp/.venv/bin/python",
      "args": ["/absolute/path/to/cohortome/integrations/mcp/cohortome_mcp.py"],
      "env": {
        "COHORTOME_MCP_URL": "http://127.0.0.1:PORT/local-agent/call",
        "COHORTOME_MCP_TOKEN": "COPY_FROM_COHORTOME"
      }
    }
  }
}
```

Replace both paths and both environment values. Windows JSON paths need escaped
backslashes, or forward slashes. The exact configuration wrapper depends on your
client. The URL above is an internal adapter endpoint, **not** a remote MCP URL.
Do not put the token in a prompt, command argument, screenshot or Git repository.

Keep Desktop open. Restart the client connection after replacing its values.
Tokens expire after eight hours, when replaced or revoked, and on app restart.

## Try it

Ask: **“Describe the shared selection, then find patients with transcriptomics
and proteomics. Give the count before listing any IDs.”**

Tools discover clinical fields, filter patients and summarize the shared group.
They do not run analyses, edit datasets, save cohorts or change the Dashboard.
Changing the app's selection does not change an existing share; share again to
replace it. An empty selection stays empty.

This prototype accepts only the two verified bundled synthetic demos. **A local
connector is not a local-model guarantee:** the client may forward results to a
cloud model. There is no remote/Web connector in this prototype.

## Focused tests

```bash
integrations/mcp/.venv/bin/python -m pip install 'pytest>=8.3,<9'
integrations/mcp/.venv/bin/python -m pytest integrations/mcp/test_connector.py
```

These use a disposable loopback server and the real MCP SDK. No user runtime or
real patient data is accessed.

To also test the actual Desktop backend, set the Python interpreter used to run
the source app (with its dependencies installed):

```bash
COHORTOME_TEST_APP_PYTHON=/usr/bin/python3 integrations/mcp/.venv/bin/python -m pytest integrations/mcp/test_desktop_e2e.py
```

This creates a temporary profile and synthetic DuckDB store; it does not open
the app window or alter your saved workspace.
