# Desktop packaging tests

These builds are portable test bundles, not release installers. They contain
the Tauri window, Python backend, two synthetic demos and local chart assets.
Only allowlisted, tracked application files are copied—not developer state,
credentials or research data.

## Verification status

- October 21 packaging tests passed on Linux x86_64/ARM64, Windows and both
  macOS architectures, including shared Perl, R and UMAP checks.
- The shared Perl bundle includes Pheno-Ranker, Convert-Pheno and ClarID-Tools.
- Subsequent DICOM folder-linking changes were tested locally on Linux ARM64,
  including image rendering in native WebKit. They are not yet covered by a
  new cross-platform package run.

These results are not clean-machine installer validation. Previous remote artifacts
were removed after selected builds were archived privately; old run IDs cannot
retrieve them. Public-repository testing has resumed without binary uploads.

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

## Runtime options

| Runtime | Build/package options | Verification |
| --- | --- | --- |
| Shared Perl | `build_unix_pheno.py` or `build_windows_pheno.py`; package with `--perl-runtime PATH` | `--require-pheno` |
| R | `build_linux_r.py` or `build_native_r.py`; package with `--r-runtime PATH` | `--require-r`, `--require-extended-r` |
| UMAP | Install `requirements-umap-test.txt`; package with `--with-umap` | `--require-umap` |

All five Desktop workflows include the pinned OHIF static files. A Linux job
extracts them without executing the image, then passes a one-day build-input
artifact to the target runner. Docker is not needed on users' machines.

For local packaging, on a build host with Docker:

```bash
python scripts/dicom/prepare_bundled_viewer.py --output /path/to/ohif
```

Then pass `--ohif-assets /path/to/ohif` to the packager.
The packager verifies the generated file checksums and records viewer provenance.
Use `desktop/test_package.py --require-viewer` to check asset, metadata and image
delivery. This is not a rendered-image test. Review redistribution notices before
publishing installers; the new workflow wiring still needs a CI run.

### Shared Perl

The builders install Pheno-Ranker 1.09, Convert-Pheno 0.35 and ClarID-Tools 0.04
from checksum-verified CPAN sources. They precompile Inline::C metrics and test
relocation, phenotype comparison, CSV-to-BFF mapping and ClarID encoding.
The packager rejects older Pheno-Ranker-only runtimes.

For Linux, with compiler, make, curl and OpenSSL, Expat, zlib and bzip2
development libraries installed:

```bash
.venv/bin/python desktop/build_unix_pheno.py --output dist/pheno-runtime
```

Unix builds use Perl 5.42.3. macOS relocates copied dynamic libraries and applies
ad-hoc signatures. Windows stages Strawberry Perl 5.42.x, DLLs and a portable
marker, and applies the checksum-pinned Net::IDN::Encode compatibility patch.
It invokes `perl.exe` directly, without `cmd.exe`.

The bundle lives under `engine/runtimes/perl/`. Source deployments can instead
set `COHORTOME_CONVERT_PHENO_BIN`, `COHORTOME_CLARID_TOOLS_BIN`, and on Windows
`COHORTOME_PREPARATION_PERL_BIN`; otherwise tools resolve from PATH.
Packaged apps select their bundled executables automatically.

Convert-Pheno's small terminology databases and ClarID's codebook/ICD files are
included; Convert-Pheno's optional 3.1 GB OHDSI database is not. Source archives
and top-level notices are retained, but transitive dependencies are not fully locked.

### R and UMAP

The Linux builder stages installed R and libraries; it does not install host
packages. Core R includes limma, edgeR and jsonlite. Extended builds add DESeq2,
apeglm, fgsea, msigdbr and ggplot2. Use a clean build host for distribution.

The native macOS/Windows workflow selects R 4.5.2 and Bioconductor 3.22.
macOS relocates libraries and signs them ad hoc; Windows retains the official
R layout and invokes `Rscript.exe` directly.

Relocation checks use a path with spaces, isolated library paths and empty PATH.
They exercise limma-voom, DESeq2/apeglm, synthetic fgsea enrichment and plots.
Manifests record versions and file hashes, not a complete dependency lock.
Linux builds still depend on compatible system libraries/glibc.

UMAP is collected with its optional Python dependencies. Hallmark enrichment
may need network access for gene sets; tests use invented sets, not MSigDB data.
Docker sandboxes, OHIF assets and Nextflow/Snakemake demo runners are separate.

## GitHub Actions

Four workflows can be started manually: desktop installers, Docker release,
Docker smoke test, and documentation. The five desktop platform builders and
viewer helper are reusable workflows called by the release workflow.

The release workflow wraps the tested engine with the pinned
Tauri CLI used by Pheno-Ranker Desktop (2.11.4): Linux AppImage, macOS DMG,
and Windows per-user NSIS with a WebView2 bootstrapper.
ARM64 Linux/macOS and x86_64 Windows installer builds passed CI; clean-machine
installation still needs testing.

Downloads follow Pheno-Ranker's release layout: one installer per platform and
architecture, plus its `.sha256` file. No DEB or portable runtime archives are
uploaded. Portable archives and macOS app bundles remain build/test intermediates.
`desktop/collect_installer.py` checks the installer against its build manifest
before collecting and naming downloads. Required third-party sources/notices are separate
release obligations, not extra application installer formats.

For a clean checkout and matching portable package:

```bash
python desktop/build_installers.py --package /path/to/cohortome-package --output /path/to/new-installer-build
```

The builder checks the package commit, platform and file hashes before embedding
`engine/` as a Tauri resource. It retains the preview application identifier,
records installer hashes and never publishes. macOS signing remains ad hoc;
these are not notarized installers. No Docker workflow is involved.

macOS uses Tauri to build and sign the `.app`, then Apple's `hdiutil` to create
and verify a compressed DMG from a folder containing the app and an Applications
shortcut. No mounted-volume customization is used; Finder uses its default layout.

macOS/Windows packaging builds and tests R on the same runner, using shared
R preparation steps. No runtime artifact from an earlier run is required.

Linux caches successful R/Perl builds using architecture, Ubuntu baseline,
builder scripts and workflow content as keys, without partial-key fallbacks.
`clean_build` bypasses cache restore and save. Dependency changes or cache
eviction trigger a rebuild; application changes normally reuse runtimes.
Relocation and native-window tests still run on every package.

Extract the resulting archive and keep `cohortome-desktop` (Windows:
`cohortome-desktop.exe`) beside `engine/`.

- Linux needs GTK 3 and WebKitGTK 4.1; the archive is not an AppImage.
- macOS archives are not DMGs or application bundles. Ad-hoc signing does not
  establish Gatekeeper acceptance or notarization.
- Windows tests use the runner's WebView2. The archive does not install it;
  state-file access uses inherited directory ACLs.

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

For runtime locations and backup/reset instructions, see the
[installation guide](../docs-site/docs/getting-started/desktop.md#storage-updates-and-removal).

## Before release

Run **Build desktop installers** on `main` and choose one platform or `all` for
testing. Leave `tag` empty and `create_draft` unchecked. Installers are available
as workflow artifacts; no release is created.

For release, select `all`, check `create_draft`, and enter an existing annotated
tag such as `v0.1.0`. It verifies the tag and version metadata, builds all five
installers from the resolved commit, checks their hashes, and creates a draft
with the matching changelog notes. Pushing a tag alone does nothing. The
platform builders retain their runtime and package checks as reusable workflows.

Verify scientific runs, source preparation, native save/open dialogs
and clean-machine installation. Confirm Hallmark access, viewer distribution,
installer formats, signing and the review below before advertising full coverage.

### Redistribution review

**Binary redistribution review is not complete.**
[Third-party notices](../THIRD_PARTY_NOTICES.md) records attribution, not release
approval. Before distributing a binary bundle, inspect the exact artifact and
provide:

- Python and included Python-package licence texts, including the scientific
  stack and native libraries collected by the freezer;
- Rust/Tauri dependency notices for the locked dependency graph;
- Perl, CPAN module and copied native-library notices and any required sources;
- R, Bioconductor/CRAN package and copied native-library notices and any required
  corresponding sources;
- viewer and browser-library notices if OHIF assets are included;
- separate provenance and applicable terms for terminology databases shipped by
  Convert-Pheno and ClarID, including their exact vocabulary editions.

Python packaging now retains available distribution notices under
`licenses/python/`, with an inventory of the clean build environment and explicit
missing-notice flags. This is not an exact frozen-module inventory or approval.
R sources and copied native-library sources/notices still need to be retained;
in particular, the Linux R bundle also copies GNU `rm`. Rust dependency notices
and viewer dependency coverage remain open checks.

ClarID's source documentation identifies its tables as **CDC ICD-10-CM 2026**,
not an unspecified ICD-10 edition. Verify that against the pinned CPAN archive
and retain its provenance before closing the terminology review. The
[CDC description](https://www.cdc.gov/nchs/icd/icd-10-cm/index.html) identifies
the relationship to WHO ICD-10; it does not by itself settle every redistribution
question for the bundled derived files. For source-distribution requirements,
use the [GNU distribution FAQ](https://www.gnu.org/licenses/gpl-faq.html#UnchangedJustBinary).

Retaining top-level tool notices does not cover all transitive dependencies.
Do not infer permission for a terminology database from its tool's software
licence. Identify the actual ICD edition and source before applying
[WHO's classification terms](https://www.who.int/about/policies/publishing/copyright).
MSigDB gene sets are not part of the synthetic packaging tests. Installing
`msigdbr` does not establish permission to redistribute its downloaded data.

Keep required sources and notices with each approved release, rather than
relying on expiring CI artifacts. Experimental artifacts are not approved
release downloads. The existing artifacts were removed on 21 October 2026
after selected builds were archived privately. Review any future artifacts
before publication, even when no GitHub Release has been created.
