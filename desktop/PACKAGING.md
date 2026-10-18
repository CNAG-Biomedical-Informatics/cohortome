# Desktop packaging tests

This is a test bundle, not a release installer. It contains the Tauri window,
Python backend, two synthetic datasets and local Plotly/Cytoscape assets.
No developer runtime, credentials or research data are copied.

## GitHub Actions

Open **Actions**, choose the Linux x86_64, Linux aarch64, macOS Apple Silicon, or Windows x86_64
package workflow, then **Run workflow**. Each is manual only and does not create
tags or releases. Keep workflows separate until they are stable.

Each job builds a `.tar.gz` (Windows: `.zip`), extracts it, tests its backend from another
directory and opens its native window (under Xvfb on Linux). Download the test artifact
from the completed run. Artifacts expire after seven days.

Extract the archive and run `cohortome-desktop` beside its `engine/` directory.
Keep those files together. This portable bundle still requires Linux GTK 3 and
WebKitGTK 4.1 libraries; it is not yet an AppImage. The macOS test archive is not
yet a DMG or an application bundle. Its executables are ad-hoc signed, not
Developer ID signed or notarized; a successful CI run does not test Gatekeeper
behaviour after downloading the archive.

On Windows, run `cohortome-desktop.exe`. The test uses the runner's WebView2
runtime; this is not an NSIS installer and does not install WebView2. Windows
state files inherit directory ACLs, rather than Unix file permission modes.

## Build locally

Use Python 3.12, Rust and the Tauri build libraries (or Xcode tools on macOS). From the repository
root, in a clean virtual environment:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r desktop/requirements-desktop-test.txt
.venv/bin/python -m pip install --no-deps --no-build-isolation .
npm install --prefix dist/charts --no-save --package-lock=false plotly.js-dist-min@2.35.2 cytoscape@3.33.1
.venv/bin/python desktop/package_desktop.py --with-native --chart-modules dist/charts/node_modules --output dist/cohortome-linux-test
.venv/bin/python desktop/test_package.py dist/cohortome-linux-test/engine
```

Use a new output directory for each build; the builder refuses to overwrite
an existing one. The manifest records dependency versions and file checksums.
Only tracked files under the package allowlist are copied; new application
assets must therefore be tracked before packaging.

## What is checked

- Relocation to a path containing spaces, with an empty executable `PATH`,
  no user Python packages, and fresh temporary state.
- Private loopback startup, bootstrap cookie, Host/Origin guards and shutdown.
- Both synthetic datasets: store preparation and patient queries.
- Saved cohort creation and membership/clinical ZIP export.
- Local chart asset delivery and settings persistence after restart.
- Real packaged job subprocesses: expected invalid-analysis failure, persisted
  error, queue reuse and clean child exit. This is not a successful scientific run.
- Native window startup in CI. This is not a full interactive UI test.

The packaged app stores state under the platform application-data directory
(`$XDG_DATA_HOME/org.cnag.cohortome.preview` on Linux, defaulting to
`~/.local/share/org.cnag.cohortome.preview`). It does not reuse the checkout's
`runtime/desktop-preview`. No data migration is performed.
Removing the portable bundle leaves that data folder intact. See the
[installation guide](../docs-site/docs/getting-started/desktop.md#storage-updates-and-removal)
for backup and reset instructions.

## Still needed before a release

- Bundle and test Perl/Pheno-Ranker, `jq`, R/Bioconductor and optional UMAP.
- Package or download the viewer and other resources; custom scripts still
  require the separately installed Docker sandbox.
- Confirm the Windows workflow and add macOS Intel coverage.
- Test successful scientific analyses and native save/open dialogs on the
  installed packages, not just the source application.
- Review redistribution notices, installer formats, signing and clean-machine
  compatibility. Building on a particular Linux release does not establish
  compatibility with older distributions.

The packaging reference is Pheno-Ranker's `app/scripts/` and
`.github/workflows/desktop-installers.yml`: relocatable Perl, frozen Python,
clean-environment tests, then inspection of the actual installers.
