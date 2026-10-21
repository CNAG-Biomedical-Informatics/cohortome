# Desktop preview

The desktop source preview uses this repository's Python application,
templates and styles. Tauri opens the local web interface;
File and View menus invoke its buttons. Project save/open uses shared Python
and JavaScript, with native file dialogs supplied by Tauri.

For experimental Linux, macOS and Windows bundles and manual GitHub Actions workflows,
see [Packaging tests](PACKAGING.md). The source launcher below is not an installer.
It currently targets Linux development with Python
dependencies, Rust and Tauri system libraries installed.

## Linux source setup

Use Python 3.12 for the development recipe below (the application requires
Python 3.11 or newer). Install Rust's stable toolchain and the platform libraries
listed in the [Tauri prerequisites](https://tauri.app/start/prerequisites/).
On Ubuntu 24.04, install the system packages with:

```bash
sudo apt update
sudo apt install python3.12-venv build-essential pkg-config curl wget file \
  libwebkit2gtk-4.1-dev libxdo-dev libssl-dev libayatana-appindicator3-dev librsvg2-dev
```

Install Rust using the [official rustup instructions](https://www.rust-lang.org/tools/install),
then verify that `cargo --version` works in your terminal. In a fresh checkout:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[dicom,umap]'
cargo fetch --locked --manifest-path desktop/Cargo.toml
.venv/bin/python desktop/run.py
```

The first setup needs network access for Python and Rust dependencies. The
launcher builds Cargo offline, so the explicit fetch is required on a clean
machine. This source setup resolves Python dependencies from the declared
ranges; it is not a fully locked release build. The packaging tests use separate
pinned requirements.

For later launches with the same environment:

```bash
.venv/bin/python desktop/run.py
```

The launcher builds with the included lockfile and uses this checkout's `.deps`
if available, otherwise the active Python environment. Application code always
comes from this repository. No sibling checkout is required. A distributed
installer must still bundle its own runtime.

R/Bioconductor, Pheno-Ranker, Convert-Pheno and ClarID are not installed by the
Python command above. Analyses and dataset preparation that need them remain
unavailable until those tools are installed. See [packaging and runtime
instructions](PACKAGING.md) and the app's readiness checks. Docker is only needed
for the custom-script sandbox or optional imaging setup, not the desktop queue.
The local OHIF assets are also a separate setup step; see
[DICOM viewing](../docs-site/docs/admin-guide/dicom-viewing.md).

State stays outside the checkout in the platform application-data directory,
under `org.cnag.cohortome.source-preview` (on Linux, normally
`~/.local/share/org.cnag.cohortome.source-preview/`). Source previews and packaged
apps use separate directories. Only the
default and synthetic autoimmune datasets are registered initially. Research
configuration is not loaded. Model inference is disabled initially. In
**Admin > Models**, edit **System default (LM Studio)**, set the endpoint and
data boundary, check **Enabled**, and **Save** before testing the connection.
These settings persist in the desktop runtime; restarting does not reset them.
The bundled 2D DICOM viewer uses software rendering on Linux desktop to avoid
blank viewports with WebKitGTK/VM graphics drivers. Other platforms and the web
app retain the default renderer. A warning on a single-image demo series means
it cannot be reconstructed as a 3D volume; it does not indicate a corrupt image.
The default can be disabled but not deleted. Deployment-managed web providers
remain read-only. Apply a
dataset in Datasets and prepare its store if prompted. The local owner has
administrative access without entering credentials.

The backend binds a random loopback port, requires a per-launch cookie, rejects
foreign origins, and exits when its parent input closes. The native window cannot
navigate outside that origin. External HTTP(S) links open in the system browser;
native downloads and dialogs still require installed-package checks on each
platform. Restricted datasets require authorization to process
them locally, protected source files and runtime artifacts, and correctly
configured dataset and model-provider policies. Keep model access disabled unless
approved; never label an external provider as local to bypass dataset policy.
This source preview is not a security certification. See the
[Desktop restricted-data guidance](../docs-site/docs/getting-started/desktop.md#restricted-data)
before importing sensitive datasets.

Background jobs run through a desktop-managed queue, one subprocess at a time,
without Redis. They use the same analysis functions, permissions, result files
and job history as the web deployment. The Jobs panel reports the local worker
as online while the app is open. Direct queries and synchronous analyses are
unchanged. The desktop never connects to the research deployment's Redis.

Analysis child processes use one-thread limits for BLAS, OpenMP and supported
numerical libraries. Pathway enrichment explicitly uses a serial backend.
The custom-script container also has a one-CPU quota. Native thread settings
are not an OS-level CPU quota for arbitrary external programs; concurrent-job
capacity is a separate setting and the desktop currently runs one job at a time.

Keep the app open until a run finishes. Closing it stops active work and marks
unfinished jobs as failed; reopening also marks interrupted jobs as failed,
rather than silently rerunning them. Completed results remain available.
Timeouts stop the analysis process tree. Only one desktop instance may own this
runtime. R/Perl and other analysis dependencies must still be installed; their
existing runner checks explain missing dependencies. Experimental packagers can
include Python, Perl, R and UMAP. Their platform verification status, remaining
redistribution review, signing and installer work are recorded in
[PACKAGING.md](PACKAGING.md).

## Check navigation during a background run

For a controlled one-minute test, select **Synthetic autoimmune demo**, then
**Custom Python / R script (synthetic prototype)** in Analysis. This requires
Docker and the configured sandbox image; the Inputs checks show their availability.
Choose Python and paste this complete script. Input preparation happens when you
click Run; generating or copying a template is not required:

```python
import time
from pathlib import Path

print("Background-run diagnostic started", flush=True)
time.sleep(60)
output = Path('/work/output')
output.mkdir(parents=True, exist_ok=True)
(output / "diagnostic.txt").write_text(
    "One-minute background-run diagnostic completed. No scientific analysis performed.\n"
)
```

Run it, visit Dashboard or Query, then return to Analysis. Check the running
status in Jobs and the completed result/files afterwards. Keep the desktop open.
The script deliberately waits rather than doing scientific work; it tests UI
responsiveness and completion delivery, not computational performance. Keep the
delay below the sandbox's 90-second execution limit.

## Save and reopen a project

Apply a dataset, then use **Save project…** in the sidebar or **File > Save
Project As…**. Use **Open project…** to resume. In a browser, these controls
download and upload the same `.cohortome` file.

The small JSON file records dataset fingerprints, the selected page, a Query
draft and the last 16 conversation messages, plus references to the analysis
session, saved cohorts and runs. Matrices and results stay in the installation.
Analysis references reopen the latest saved session, not a frozen snapshot.
Query messages return as text; rerun queries for tables and cohort actions.

Projects currently require the same user and installation, unchanged authorized
datasets, and prepared stores. They are not portable data bundles or backups.
Conversation text can be sensitive: handle these files like exported results.
Opening a project does not execute analyses.

Web and desktop now share this implementation in one repository. The older
sibling prototype is not a development dependency. Its runtime has not been
copied: projects saved there remain bound to that installation.
