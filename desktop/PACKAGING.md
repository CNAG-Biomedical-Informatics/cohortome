# Desktop packaging tests

This is a test bundle, not a release installer. It contains the Tauri window,
Python backend, two synthetic datasets and local Plotly/Cytoscape assets.
No developer runtime, credentials or research data are copied.
The workflows include a separately built Perl/Pheno-Ranker runtime. Linux
x86_64 and ARM64 passed the integrated tests; macOS and Windows integration
is awaiting its first CI verification.

## GitHub Actions

Open **Actions**, choose the Linux x86_64, Linux aarch64, macOS Apple Silicon,
macOS Intel, or Windows x86_64
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
- Real cohort and patient Pheno-Ranker runs through the packaged HTTP
  backend, using the bundled Perl runtime. Checks selected records, matrix,
  graph, Python MDS output and ranking without host executables on `PATH`.
- Native window startup in CI. This is not a full interactive UI test.

The packaged app stores state under the platform application-data directory
(`$XDG_DATA_HOME/org.cnag.cohortome.preview` on Linux, defaulting to
`~/.local/share/org.cnag.cohortome.preview`). It does not reuse the checkout's
`runtime/desktop-preview`. No data migration is performed.
Removing the portable bundle leaves that data folder intact. See the
[installation guide](../docs-site/docs/getting-started/desktop.md#storage-updates-and-removal)
for backup and reset instructions.

## Still needed before a release

### Perl/Pheno-Ranker runtime

The separate **Test Linux CPAN Pheno-Ranker runtime** workflow builds Perl
5.42.3 and installs Pheno-Ranker 1.09 from checksum-verified CPAN sources.
It precompiles the Inline::C metrics and runs a cohort comparison after moving
the runtime to a path with spaces, with an empty PATH and a fresh HOME.
Choose x86_64 or aarch64 when dispatching it.

Linux and macOS desktop workflows run `build_unix_pheno.py` and include its output under
`engine/runtimes/pheno/`. The packager verifies architecture and file checksums
before copying it. The frozen backend selects this runtime explicitly rather
than looking for a host installation. Linux x86_64 and ARM64 passed both the
packaged backend analysis checks and the native-window test on October 19.
macOS builds use relocatable Perl, copied non-system dynamic libraries with
relative load paths, and ad-hoc code signatures.

Windows uses `build_windows_pheno.py` with Strawberry Perl 5.42.x supplied by
the setup action on a clean runner. It stages the interpreter, installed CPAN
modules, runtime DLLs and portable marker, and precompiles Inline::C metrics.
A small native launcher starts the bundled Perl without `cmd.exe` or PATH
lookup. The manifest records the exact Perl version and hashes. This is not
yet a pinned Strawberry archive with a complete dependency lock.

For a local Linux build, first run:

```bash
.venv/bin/python desktop/build_unix_pheno.py --output dist/pheno-runtime
```

Add `--pheno-runtime dist/pheno-runtime` to the packaging command above, then
add `--require-pheno` to the `desktop/test_package.py` command. Building Perl
requires a compiler, make, curl and the OpenSSL, Expat, zlib and bzip2 development
libraries; the workflows install them explicitly.

This does not include R or UMAP. Reference record selection uses Python
directly. Transitive CPAN dependencies are resolved
at build time; their source archives and checksums are retained, but a complete
dependency lock and redistribution-notice review are still pending. The build
approach follows Pheno-Ranker's desktop scripts, without copying a local Perl
installation or requiring the Pheno-Ranker Git checkout.

### Remaining packaging work

- Verify the integrated macOS and Windows Perl/Pheno-Ranker builds.
- Bundle and test R/Bioconductor and optional UMAP.
- Package or download the viewer and other resources; custom scripts still
  require the separately installed Docker sandbox.
- Confirm all platform workflows before assembling release installers.
- Test successful scientific analyses and native save/open dialogs on the
  installed packages, not just the source application.
- Review redistribution notices, installer formats, signing and clean-machine
  compatibility. Building on a particular Linux release does not establish
  compatibility with older distributions.

The packaging reference is Pheno-Ranker's `app/scripts/` and
`.github/workflows/desktop-installers.yml`: relocatable Perl, frozen Python,
clean-environment tests, then inspection of the actual installers.
