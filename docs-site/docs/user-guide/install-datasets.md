# Installation and storage

Open **Data → Add dataset** on Desktop, or **Admin → Data → Add dataset** on
Web. The desktop owner and web administrators install data; other Web users
select datasets already made available to them.

| Dataset source | Instructions |
| --- | --- |
| Examples shipped with COHORTome | [Pre-installed datasets](included-datasets.md) |
| Already converted archives or local resource ZIPs | [Prepared packages](downloadable-datasets.md) |
| Processed study products converted locally | [Fetch and prepare](fetch-datasets.md) |

![Add dataset dialog with catalogue and local ZIP import](/img/screenshots/install-dataset.png)

Filter the catalogue by **Included**, **Ready to install** or **Fetch & prepare**.
Each card shows the same icon and label. **Import ZIP** remains available separately.

Choose **Refresh** to update catalogue metadata from COHORTome Store. This does
not install data or change the workspace. Offline, the app uses its last valid
catalogue or the bundled list. Preparation recipes ship with the app, not with
catalogue updates.

:::tip[Ready means installed—not yet selected]

DuckDB preparation is automatic. When installation finishes, choose **Add to
workspace selection**, then **Apply workspace**. The two included demos cannot
be reinstalled or removed.

:::

## Storage location

Change **Settings → Jobs & storage → Dataset storage** before importing.

| Deployment | Location |
| --- | --- |
| Desktop | Choose a folder with the folder picker. |
| Web | An administrator enters an existing absolute server path. |
| Docker | Use a path inside a persistent mounted volume. |

This affects **new imports only**. Existing datasets stay at their registered
paths. Keep external disks connected while using their data.

<details>
<summary>Storage layout and interrupted installations</summary>

Imported packages live in an `installed/` subfolder of the selected location.
The default is `state/resources/` under the runtime directory; the DuckDB cache
remains in the runtime directory. See [Desktop storage](../getting-started/desktop#where-desktop-data-is-stored)
for platform paths. Choosing a path does not create a Docker volume mount.

Keep the app open during installation. Cancellation is available before database
preparation; failed installs are rolled back. After an interruption, retry the
installation. Downloads restart rather than resume. The installer does not need
Redis, and completed but disabled datasets are preserved rather than replaced.

</details>

## Remove a dataset

Open its entry in **Data**, choose **Remove dataset**, and type its ID.
Finish or cancel running and queued jobs first. Included datasets cannot be removed.

:::warning[Saved work can lose access to its data]

Chats, cohorts and results remain, but their references to the removed dataset
stop working. Reimporting does not repair those references. Source files are
kept unless you explicitly choose file removal.

:::

| Item | After removal |
| --- | --- |
| Dataset registration and prepared DuckDB store | Removed |
| Chats, cohorts and results | Kept; dataset references no longer load |
| Source files, by default | Kept in place |
| Installer-managed files, with file removal selected | Moved to `removed/` beside `installed/` for manual recovery |
| Other source folders | Never moved or deleted |

Moving files does not free disk space. After removal, reload the workspace and
apply the datasets you want to use. Changed published packages need a new
resource version and checksum; do not overwrite an existing release.
