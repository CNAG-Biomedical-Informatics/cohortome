# Desktop packaging tests

This is a test bundle, not a release installer. It contains the Tauri window,
Python backend, two synthetic datasets and local Plotly/Cytoscape assets.
No developer runtime, credentials or research data are copied.
The workflows include a separately built Perl/Pheno-Ranker runtime. Linux
x86_64, ARM64, Windows and both macOS architectures passed the original integrated Pheno-Ranker Perl
tests. Both Linux architectures also passed extended R and UMAP integration.
Both macOS architectures and Windows have passed standalone extended R tests.
At commit `56382f3`, the combined Intel macOS and Windows desktop workflows
passed (runs `39390043773` and `39390024447`). The Apple Silicon run
`39390035341` failed; its earlier passing desktop build did not verify this
combined revision. These CI results are not clean-machine installer validation.

The newer shared Perl bundle adds Convert-Pheno 0.35 and ClarID-Tools 0.04.
Its local Linux ARM64 build and relocated conversion/identifier probes passed.
The expanded bundle has not yet been retested on Windows or macOS; the earlier
cross-platform results above concern Pheno-Ranker, not the new conversion tools.

## GitHub Actions

For macOS and Windows, supply `r_runtime_run_id`: the run ID from **Test macOS
and Windows R runtimes** containing the successful matching platform artifact.
This avoids compiling the same R libraries again. The archive must still be
available (CI artifacts expire after seven days); rerun the runtime workflow if
it has expired. Each package verifies the runtime's platform, architecture and
file checksums before staging it. No host R installation is used.

The package tests require extended R package loading and a real synthetic
limma-voom run after relocation, as well as Perl, UMAP and native-window checks.

Open **Actions**, choose the Linux x86_64, Linux aarch64, macOS Apple Silicon,
macOS Intel, or Windows x86_64
package workflow, then **Run workflow**. Each is manual only and does not create
tags or releases. Keep workflows separate until they are stable.

Linux workflows cache the built R and Perl runtime directories after a
successful job. Cache keys include architecture, Ubuntu baseline, runtime
builder scripts and that platform's workflow. There are no partial-key
fallbacks. Application-only changes reuse the runtimes; dependency-recipe
changes rebuild them. The packager still validates their checksums, and the
relocated backend, analysis and native-window tests run every time.

Select **clean_build** when dispatching a Linux workflow to bypass both cache
restore and save. Use this periodically and before a release to check a fresh
dependency build. Caches are an optimization, not a dependency lock: package
versions remain recorded in the runtime manifests. The first run for a new
key still performs the full build; later runs can reuse it. Cache eviction
also triggers a full build. No runtime state or research data is cached.

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
- With `--require-r`: the actual COHORTome limma-voom adapter, using bundled
  synthetic assays, must retain a model and plot. This is a direct analysis;
  the background-worker test above still exercises its failure path only.
- With `--require-umap`: a Pheno-Ranker cohort run must produce finite UMAP
  coordinates for all selected records.
- With `--require-extended-r`: also require every curated runner's R packages
  to load from the relocated desktop bundle. The R builder separately tests
  DESeq2/apeglm and synthetic fgsea enrichment before packaging.

The packaged app stores state under the platform application-data directory
(`$XDG_DATA_HOME/org.cnag.cohortome.preview` on Linux, defaulting to
`~/.local/share/org.cnag.cohortome.preview`). Source previews use the separate
`org.cnag.cohortome.source-preview` directory in the same location.
No automatic data migration is performed.
Removing the portable bundle leaves that data folder intact. See the
[installation guide](../docs-site/docs/getting-started/desktop.md#storage-updates-and-removal)
for backup and reset instructions.

## Still needed before a release

### Shared Perl runtime

The separate **Test Linux CPAN Pheno-Ranker runtime** workflow builds Perl
5.42.3 and installs Pheno-Ranker 1.09, Convert-Pheno 0.35 and ClarID tools 0.04
from checksum-verified CPAN sources into one prefix. It precompiles the Inline::C
metrics, then moves the runtime to a path with spaces and tests a cohort
comparison, CSV-to-BFF conversion with NCIT/PASI mapping, and both ClarID formats.
The checks use a clean home and no host tools on PATH.
Choose x86_64 or aarch64 when dispatching it.

Linux and macOS desktop workflows run `build_unix_pheno.py` and include its output under
`engine/runtimes/perl/`. The packager verifies architecture and file checksums
before copying it. All three pinned tool versions are required; an older
Pheno-Ranker-only runtime is rejected. The frozen backend selects this runtime explicitly rather
than looking for a host installation. Linux x86_64 and ARM64 passed both the
packaged backend analysis checks and the native-window test on October 19.
macOS builds use relocatable Perl, copied non-system dynamic libraries with
relative load paths, and ad-hoc code signatures.

The existing builder filenames retain `pheno` to avoid renaming workflow entry
points; their output is now the shared runtime. The package option is
`--perl-runtime` and the installed location is `engine/runtimes/perl/`.

Windows uses `build_windows_pheno.py` with Strawberry Perl 5.42.x supplied by
the setup action on a clean runner. It stages the interpreter, installed CPAN
modules, runtime DLLs and portable marker, and precompiles Inline::C metrics.
Like Pheno-Ranker Desktop, the app starts the bundled `perl.exe` directly,
passing the CLI script as an argument, without `cmd.exe` or a separate launcher.
Before installing the tools, it installs the checksum-pinned Net::IDN::Encode
patch used by Convert-Pheno Desktop for Perl 5.42 compatibility.
The manifest records the exact Perl and tool versions and hashes. This is not
yet a pinned Strawberry archive with a complete dependency lock.

For a local Linux build, first run:

```bash
.venv/bin/python desktop/build_unix_pheno.py --output dist/pheno-runtime
```

Add `--perl-runtime dist/pheno-runtime` to the packaging command above, then
add `--require-pheno` to the `desktop/test_package.py` command. Building Perl
requires a compiler, make, curl and the OpenSSL, Expat, zlib and bzip2 development
libraries; the workflows install them explicitly.

The Perl runtime itself does not include R or UMAP. Reference record selection uses Python
directly. Transitive CPAN dependencies are resolved
at build time; their source archives and checksums are retained, but a complete
dependency lock and redistribution-notice review are still pending. The build
approach follows Pheno-Ranker's desktop scripts, without copying a local Perl
installation or requiring the Pheno-Ranker Git checkout.

Convert-Pheno includes its small terminology databases; its optional 3.1 GB
OHDSI database is absent from the CPAN archive. ClarID includes the 0.04 codebook
and ICD lookup files. Software notices are retained under `licenses/`, and
the source archives remain under `sources/`. Vocabulary terms require separate
redistribution review before a public release; a software licence does not
establish rights to every bundled terminology database.

Native deployments can select tools with `COHORTOME_CONVERT_PHENO_BIN` and
`COHORTOME_CLARID_TOOLS_BIN`. Otherwise the commands are resolved from PATH.
On Windows, `COHORTOME_PREPARATION_PERL_BIN` selects the interpreter. Packaged
desktop apps set these paths to the bundle automatically. About reports both
preparation-tool versions. The source-download installation UI now uses these
tools to prepare supported studies locally. Its current changes are not covered
by the older CI bundles.

The expanded runtime must be verified on each platform before shipping.
GitHub Actions testing is paused while the account's minutes are limited.

### Remaining packaging work

- Resolve the latest combined Apple Silicon package failure, then verify the
  expanded shared Perl bundle and source preparation on every target platform.
- Verify Hallmark gene-set access before claiming
  complete curated-analysis coverage.
- Package or download the viewer and other resources; custom scripts still
  require the separately installed Docker sandbox.
- Confirm all platform workflows before assembling release installers.
- Test successful scientific analyses and native save/open dialogs on the
  installed packages, not just the source application.
- Review redistribution notices, installer formats, signing and clean-machine
  compatibility. Building on a particular Linux release does not establish
  compatibility with older distributions.

See [Third-party notices](../THIRD_PARTY_NOTICES.md) for the binary-distribution
checklist. CI artifacts are experimental, not approved release downloads.
Before making the repository public, review or remove existing artifacts and
review workflow logs. Do not assume that keeping Releases empty prevents access
to artifacts from a public repository.

### Linux ARM64 R experiment

`build_linux_r.py` stages installed R plus `limma`, `edgeR`, `jsonlite` and
their required packages into a new directory. It does not install or modify
anything on the host. Use a clean build machine for distributable artifacts.
The manual **Test Linux ARM64 R runtime** workflow uses Ubuntu packages and
records their R package versions and runtime file hashes; this is not a locked
cross-distribution build or a completed redistribution-license review.

The relocation check runs TMM normalization, voom and limma on synthetic counts,
writes JSON, SVG and PNG, and asserts that R and package search paths belong to
the moved bundle. A bundled `rm` provides R's temporary-directory cleanup; no
host R or user R libraries should be used. Linux system/glibc compatibility is
still required. This core runtime passed the standalone ARM64 CI test.

To include it in a desktop build, pass `--r-runtime PATH` to
`package_desktop.py`, then test with `--require-r`. The frozen app explicitly
uses the bundled R, not a host installation. Analysis readiness checks the
packages required by each runner; core R alone does not enable DESeq2.

For UMAP, install `desktop/requirements-umap-test.txt` in the build environment,
package with `--with-umap`, and test with `--require-umap`. These options follow
the dynamic-import handling used in Pheno-Ranker Desktop. The ARM64 desktop
workflow passed both core R and UMAP. Both Linux desktop workflows now request
extended R plus UMAP; x86_64 retains Ubuntu 22.04 and ARM64 Ubuntu 24.04.

The standalone R workflow has an **extended** option. It installs DESeq2,
apeglm, fgsea, msigdbr and ggplot2 on the CI build host and calls
`build_linux_r.py --extended`. Its relocation test adds a synthetic DESeq2 fit,
apeglm shrinkage, fgsea enrichment and a ggplot2 plot. This extended build is
verified on ARM64 as a standalone runtime and is now requested by both Linux
desktop workflows. Integrated extended-R tests passed on both Linux architectures. Package versions are
recorded, but build-time resolution is not a complete dependency lock.

The test uses invented gene sets, not MSigDB data. The current Hallmark runner
calls msigdbr and may need network access to obtain its gene sets. Installing
the package does not establish offline Hallmark availability or permission to
redistribute those data. Docker remains a separate requirement for custom
scripts; Nextflow/Snakemake demonstration runners are not bundled.

The packaging reference is Pheno-Ranker's `app/scripts/` and
`.github/workflows/desktop-installers.yml`: relocatable Perl, frozen Python,
clean-environment tests, then inspection of the actual installers.

### macOS and Windows R builds

The manual **Test macOS and Windows R runtimes** workflow tests Apple Silicon,
Intel macOS and Windows x86_64 independently. It selects R 4.5.2 and
Bioconductor 3.22 using `r-lib/actions/setup-r`, installs the analysis packages,
and stages them with `build_native_r.py`. Standalone runtime checks passed on
all three targets. Combined desktop verification differs by platform, as
recorded at the top of this document.

The macOS builder reuses the Perl builder's dynamic-library relocation and
ad-hoc signing. Windows retains the official R directory layout and runs
Rscript.exe directly. Both run the same synthetic limma/voom, DESeq2/apeglm,
fgsea and plot checks as Linux after moving the bundle to a path with spaces,
with empty PATH and isolated R library paths. No MSigDB gene sets are bundled.
Each manifest records package versions and file hashes; neither a complete
dependency lock nor a redistribution review is implied.

The three existing macOS/Windows desktop workflows now also request UMAP and
test it through a packaged Pheno-Ranker cohort run. Passing older tests does
not verify the newer Convert-Pheno/ClarID additions or all current application
changes. The latest combined Apple Silicon failure remains unresolved.
