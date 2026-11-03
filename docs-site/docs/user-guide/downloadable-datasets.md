# Prepared packages

**Prepared packages are ready to import.** Open **Add dataset** to download an
available package or import a ZIP you already have.

## Install from the catalogue

1. Open **Data → Add dataset** (Desktop) or **Admin → Data → Add dataset** (Web).
2. Browse the catalogue and review the package contents and terms.
3. Choose **Download and install**. COHORTome checks the published SHA-256
   checksum, validates the package and prepares its database.
4. When **Ready** appears, add it to the workspace selection and apply it.

Public downloads do not need a GitHub token. If an archive is private, its
download may require a token with read access. The token is used for that
download only and is not saved; never paste it into a chat or dataset URL.

## Import a local package

Choose **Import local package** in the same dialog and select a resource ZIP
from a trusted source. It must contain one dataset folder with `resource.json`,
the dataset manifest and the declared files. Local ZIPs are structurally
validated but have no independently reviewed archive checksum.

| Limit | Value |
| --- | --- |
| ZIP size | 1 GiB |
| Extracted contents | 4 GiB |
| Unsafe paths, symlinks or encrypted entries | Rejected |

:::note[Installation does not grant sharing permission]

Check the package's source terms. New imports start with AI access blocked and,
on Web, administrator-only visibility. Review these policies before sharing.

:::

For storage and removal, see [Installation and storage](install-datasets.md).
To prepare your own package, follow [COHORTome Store](../admin-guide/prepare-datasets.md).
