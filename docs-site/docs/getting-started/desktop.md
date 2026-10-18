---
title: Installation
---

import DeploymentNotice from '@site/src/components/DeploymentNotice';

**Desktop is the recommended installation for individual use.**

[Web deployment](../admin-guide/starting-and-stopping) is recommended only for
a centralized system serving multiple users with managed dataset permissions.
Both use the same application code and research interface.

## Install a release

1. Open [COHORTome Releases](https://github.com/mrueda/cohortome/releases).
2. Choose a release with an installer for your operating system and processor.
   Check its release notes for supported platforms and analysis dependencies.
3. Follow the installation instructions supplied with that release, then open
   **COHORTome** and try a bundled synthetic dataset.

:::info[Downloads forthcoming]

Packaged installers have not yet been published. These instructions describe
the release installation path; the source setup below is available for development.

:::

<details>
<summary>Development: run from source</summary>

The current source setup targets Linux and requires Python dependencies, Rust,
and Tauri system libraries. R, Perl, and other external analysis tools must be
installed separately when a selected method requires them.

From the repository root:

```bash
python3 desktop/run.py
```

The launcher builds the native shell and starts the backend on a local loopback
address. It uses the checkout's `.deps` directory when available, otherwise the
active Python environment. This assumes the development dependencies are already
installed; it is not a standalone installation command.

</details>

## First session

1. Open **Datasets**, select a bundled synthetic dataset, and apply it. Prepare
   its store if prompted.
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

Desktop keeps its state separately from a web deployment. The development
launcher uses `runtime/desktop-preview/`; packaged-release storage locations
will be documented with the release. **Save project** writes a small `.cohortome` file referring to the
installation's datasets and saved work. It does not bundle source data or result
files and is not a backup or a transfer between installations. Protect project
files like other research exports.

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
