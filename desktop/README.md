# Desktop source preview

COHORTome Desktop runs the shared application in a Tauri window, with one local
owner and no login screen. This launcher is for Linux development, not an installer.
For release-build status and other platforms, see [Packaging](PACKAGING.md).

## Set up and launch

Use Python 3.12 and Rust's stable toolchain. Install Rust with
[rustup](https://www.rust-lang.org/tools/install) and confirm that
`cargo --version` works. On Ubuntu 24.04, install the
[Tauri prerequisites](https://tauri.app/start/prerequisites/):

```bash
sudo apt update
sudo apt install python3.12-venv build-essential pkg-config curl wget file \
  libwebkit2gtk-4.1-dev libxdo-dev libssl-dev libayatana-appindicator3-dev librsvg2-dev
```

From the repository root:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[dicom,umap]'
cargo fetch --locked --manifest-path desktop/Cargo.toml
.venv/bin/python desktop/run.py
```

For later launches, run the last command again. Initial setup needs network
access; the launcher builds Cargo offline. It uses the checkout's `.deps`
when present, otherwise the active Python environment. Use a fresh checkout
without `.deps` to use only the virtual environment above.

R, Pheno-Ranker, Convert-Pheno and ClarID require separate installation.
Docker is needed for custom-script sandboxes, not the desktop queue.
See [runtime packaging](PACKAGING.md) and
[optional imaging setup](../docs-site/docs/admin-guide/dicom-viewing.md).

## Data and first use

Source-preview state lives outside the checkout in the platform app-data folder,
under `org.cnag.cohortome.source-preview`; on Linux this is normally
`~/.local/share/org.cnag.cohortome.source-preview/`. Packaged apps use a separate
folder. No research deployment configuration is loaded.

Select a bundled demo in **Datasets** and prepare its store if prompted.
Models start disabled; configure an endpoint and its data boundary in
**Admin > Models**. Keep the app open until background jobs finish.

## Guides

- [Installation, saved work, backups and restricted data](../docs-site/docs/getting-started/desktop.md)
- [Desktop development and background-run diagnostic](../docs-site/docs/developer-guide/desktop-development.md)
- [Packaging, platform checks and redistribution review](PACKAGING.md)
