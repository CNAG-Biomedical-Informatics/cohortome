---
title: Installation
---

import DeploymentNotice from '@site/src/components/DeploymentNotice';
import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

**Desktop is the recommended installation for individual use.**

[Web deployment](../admin-guide/starting-and-stopping) is recommended only for
a centralized system serving multiple users with managed dataset permissions.
Both use the same application code and research interface.

## Install a release

1. Open [COHORTome Releases](https://github.com/CNAG-Biomedical-Informatics/cohortome/releases).
2. Choose a release with an installer for your operating system and processor.
   Check its release notes for supported platforms and analysis dependencies.
3. Install the matching download, then open **COHORTome** and try a bundled
   synthetic dataset.

| Platform | Download | Install |
| --- | --- | --- |
| Linux x86_64 or ARM64 | `.AppImage` | Make the file executable, then open it. |
| macOS Apple Silicon or Intel | `.dmg` | Open the disk image and drag the app to Applications. |
| Windows x86_64 | `-setup.exe` | Run the installer for your user account. |

Each installer has an accompanying `.sha256` checksum file.

### First launch on macOS

The macOS installers are signed ad hoc but are not notarized by Apple. On the
first launch, macOS may therefore prevent COHORTome from opening.

1. Try to open **COHORTome** once and dismiss the warning.
2. Open **System Settings → Privacy & Security**.
3. Scroll to **Security** and click **Open Anyway** for COHORTome.
4. Confirm **Open** and authenticate if macOS asks you to do so.

macOS saves this approval for subsequent launches. Only override this protection
for an installer downloaded from the official COHORTome release page whose
SHA-256 checksum matches the accompanying `.sha256` file. See
[Apple's instructions for opening an unnotarized app](https://support.apple.com/en-gb/guide/mac-help/mh40617/mac).

<details>
<summary>Development: run from source</summary>

The current source setup targets Linux. Use Python 3.12, Rust's stable toolchain
and the [Tauri system prerequisites](https://tauri.app/start/prerequisites/).
The application requires Python 3.11 or newer. On Ubuntu 24.04:

```bash
sudo apt update
sudo apt install python3.12-venv build-essential pkg-config curl wget file \
  libwebkit2gtk-4.1-dev libxdo-dev libssl-dev libayatana-appindicator3-dev librsvg2-dev
```

Install Rust using the [rustup instructions](https://www.rust-lang.org/tools/install)
and confirm `cargo --version` works. R, Perl and external analysis/preparation
tools are installed separately when a selected operation requires them.

From the repository root:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[dicom,umap]'
cargo fetch --locked --manifest-path desktop/Cargo.toml
.venv/bin/python desktop/run.py
```

The launcher builds the native shell and starts the backend on a local loopback
address. It uses the checkout's `.deps` directory when available, otherwise the
active Python environment. Start from a fresh checkout without `.deps` to use
only the virtual environment above. The initial installation and Cargo fetch
need network access; subsequent launches reuse that environment. This is a
source-development recipe, not a locked installer build. Optional OHIF assets,
the custom-script Docker sandbox and external analysis tools are not installed
by these commands.

</details>

## First session

1. Open **Datasets**, select a bundled synthetic dataset, and apply it. Desktop
   prepares a bundled demo automatically the first time you use it.
2. Use **Dashboard** to inspect patients, assays, imaging, and modality coverage.
3. Open **Query** to find patients and save a cohort, then **Analysis** to select
   a method and check its required inputs.
4. Optionally configure a model in **Admin > Models**. Model inference starts
   disabled; choose its endpoint and data boundary before enabling it.

<DeploymentNotice mode="desktop" title="Desktop — local application, configurable model endpoint">

Desktop opens as the local owner without a login screen. Access to the computer
and its files remains your responsibility. Connecting a remote model can send
permitted context off the computer; a desktop installation does not make model
inference local.

</DeploymentNotice>

## Restricted data

Desktop can be used with restricted datasets when you are authorized to process
them on that computer and your organization's data-handling requirements are met.

- Protect source files, prepared stores, chats, results, exports, and backups
  through operating-system access controls and appropriate storage protection.
- Set the dataset's classification and model-context policy before enabling AI.
  Leave model access disabled when it is not approved.
- Verify the model endpoint and its actual data boundary. Marking a provider
  as local does not make it local. Private dataset context must not be sent to
  external providers.
- Review any connected imaging or other data service separately; the bundled
  development services are not suitable for restricted data without protection.

:::note[Before importing restricted data]

Installing a release does not certify a deployment for sensitive data. Confirm
that the installation meets your project's requirements before loading it.
See [Real-data security](../admin-guide/real-data-security) for additional checks;
shared-server authentication and Redis requirements apply to Web, not Desktop.

:::

## Jobs and saved work

Background analyses use a desktop-managed queue without Redis. Keep the app
open until a job finishes. Closing it interrupts active work; completed results
remain in the local runtime.

Desktop keeps its state separately from a web deployment. **Save project**
writes a small `.cohortome` file referring to the
installation's datasets and saved work. It does not bundle source data or result
files and is not a backup or a transfer between installations. Protect project
files like other research exports.

## Storage, updates, and removal

### Where desktop data is stored

The packaged app stores chats, saved cohorts, settings, dataset registrations,
prepared DuckDB stores, job logs and managed results in a **per-user data folder**,
separate from the installed program. Model-provider settings and saved API keys
also live there.

<Tabs groupId="desktop-os">
<TabItem value="linux" label="Linux" default>

`~/.local/share/org.cnag.cohortome.preview/`

If `XDG_DATA_HOME` is set, the folder is
`$XDG_DATA_HOME/org.cnag.cohortome.preview/` instead. In a file manager, press
**Ctrl+H** to show hidden folders, or enter the path directly.

</TabItem>
<TabItem value="macos" label="macOS">

`~/Library/Application Support/org.cnag.cohortome.preview/`

In Finder, use **Go → Go to Folder…** to enter the path.

</TabItem>
<TabItem value="windows" label="Windows">

`%LOCALAPPDATA%\org.cnag.cohortome.preview\`

Paste the path into File Explorer's address bar.

</TabItem>
</Tabs>

:::info[Application storage identifier]

These paths use the current application identifier, `org.cnag.cohortome.preview`.
Source launches use
`org.cnag.cohortome.source-preview` under the same platform app-data directory,
not the checkout. Source and packaged apps do not share saved work automatically.

:::

Dataset files you register remain in their original locations. Exports and
`.cohortome` files are saved wherever you choose. Bundled synthetic datasets
belong to the program bundle; prepared stores and saved work belong to the
data folder above.

### Update or uninstall

Close COHORTome before updating or uninstalling it. On Linux, replace or remove
the AppImage. On macOS, replace or remove the app in Applications. On Windows,
run the new installer to update, or uninstall through Settings → Apps.
**This does not remove the per-user data folder.**

Keeping that folder preserves saved work for reopening under the same operating
system account and application identifier. Dataset paths must still be available;
moving or changing datasets can require rebuilding their stores and can invalidate
saved project references.

### Reset or remove saved work

1. Close the app and back up its data folder and any source datasets you need.
2. To start fresh without losing the backup, move the data folder to a separate
   backup location. COHORTome creates a fresh one on its next launch.
3. Delete the old folder only when you no longer need its saved work. Files
   outside that folder—original datasets, exports and project files—are unchanged.

:::caution[Project files are not backups]

Deleting the data folder removes chats, cohorts, settings, provider credentials,
prepared stores and managed results. A `.cohortome` file cannot restore them:
it references that installation's saved work. Back up the data folder itself,
with the app closed, and keep source datasets separately.

:::

<details>
<summary>Desktop and centralized Web: differences</summary>

| Area | Desktop | Web |
| --- | --- | --- |
| Accounts | One local owner; no sign-in | Multiple users with individual accounts |
| Dataset access | Local owner manages datasets | Administrator assigns permissions |
| Background jobs | App-managed local queue | Server-managed Redis and RQ workers |
| Saved work | Local installation | Server, under each user's account |
| Model configuration | Local owner configures providers | Administrator configures approved providers |

Desktop's **Admin** controls configure datasets and models. User accounts and
groups are only needed for Web. Dataset classification and model-context policies
apply in both: local access to data does not imply permission to send it to a model.

The user guides cover the shared interface. **Web only** notices identify
instructions for shared-server accounts and permissions.

Desktop and Web do not synchronize automatically. Saved project files are not
portable data bundles or backups.

</details>
