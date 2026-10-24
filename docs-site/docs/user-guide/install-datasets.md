# Install a dataset

Open **Admin → Data → Add dataset**. Desktop owners and web administrators can
install packages. Other web users select datasets already made available to them.

Choose **Browse available datasets**, then **Download and install**. Each entry
shows its version, download size, contents and source terms. The two bundled
synthetic datasets show **Included with COHORTome** and cannot be reinstalled,
including through ZIP import.

The catalogue downloads packages from
[COHORTome Store](https://github.com/CNAG-Biomedical-Informatics/cohortome-store),
a curated collection of datasets ready to use in COHORTome.
The repository is currently private. Open **GitHub access for private
downloads** and supply a token with read access to its contents. COHORTome uses
it for that download only; it is not saved. Public releases need no token.
Never paste a token into a chat or a dataset URL.

## Fetch and prepare from the original source

The research datasets below use **Fetch and prepare**, rather than a Store
archive. Review the linked study and source terms, then confirm the download.
No GitHub token is needed. The confirmation links to the study and its usage
policy or consortium data-access statement. Check
**I have reviewed the source information and applicable usage conditions** to
enable **Download and prepare**. The installation receipt records the local
account, UTC time, dataset/recipe version, notice and links acknowledged. This
records your acknowledgement, not a licence grant or proof of legal permission.
The app downloads the processed products from their original provider,
checks its exact size and SHA-256 checksum, and prepares the dataset locally.
This is not a download of raw sequencing or array-intensity files.

| Dataset | Prepared contents |
| --- | --- |
| GSE85034 | 30 participants, PASI and treatment groups, 179 microarrays |
| GSE117239 | 89 participants, PASI and treatment groups, 324 microarrays |
| GSE191328 | 53 participants, 201 clinical snapshots and blood RNA-seq gene counts |
| GSE42296 | 39 Crohn/RA participants, 78 paired clinical snapshots and microarrays |
| GSE68310 | 133 participants, 880 observations, harmonized respiratory expression and clinical metadata |
| IBDMDB | 112 participants, 898 clinical snapshots, 224 CRP/ESR measurements, metabolomics, metaproteomics and serology |

IBDMDB downloads four products, approximately 155 MB in total, from the
[official catalogue](https://ibdmdb.org/results). Metabolomics retains all
81,867 features, including unnamed features; metaproteomics is not a human
protein panel. One unlinked serology column remains in the auxiliary source
table but is excluded from the linked matrix. This exclusion is recorded in the
package. Preparation does not normalize values or collapse repeated samples.

If an older IBDMDB package is already installed, remove it through Admin → Data
before testing the locally built replacement. The app does not silently replace
an installed dataset or repair references in existing chats/cohorts.

GSE191328 downloads one metadata file and 201 processed featureCounts files;
download time can exceed conversion time. GSE42296 now reads the original GEO
processed matrix, retaining its precision instead of using the older float32
intermediate export. Both disease groups and all paired visits remain included.

GSE68310 combines HR-VILAGE expression, earlier RIGEL metadata and an original
GEO phenotype supplement. Its confirmation links to the separate source
declarations. Only wholly unmeasured expression columns are omitted and listed;
measured values are neither imputed nor filtered. Numeric visits are timed from
first illness assessment, not enrollment baseline. Clinical mapping remains
limited to sex and baseline enrollment age; other source information is retained.

GSE65391 remains on hold while replicate
identities are checked. GSE11903 is excluded from this catalogue.

The first recipe includes 30 participants, 150 clinical visits, 179 skin-biopsy
arrays and 47,323 probes. Convert-Pheno maps the clinical data to BFF v2;
ClarID-Tools generates subject identifiers. Expression values are retained
without further normalization. They are microarray measurements, not counts
suitable for limma-voom. Multiple biopsies from one participant are not
independent participants. Ambiguous source visit labels retain their labels
without invented elapsed times.

Progress reports downloading, local preparation, validation and database
preparation. The final dataset uses the same permissions and workspace selection
as a package import. Source downloads and intermediate staging files are removed
when the attempt ends; source checksums, the mapping and preparation provenance
remain with the installed dataset.

Only reviewed recipes shipped with COHORTome can run. An arbitrary GEO accession,
download URL or script cannot be supplied. If the upstream bytes change, the app
stops instead of silently preparing a different release. Hugging Face downloads
allow bounded HTTPS redirects only within that provider's download hosts and
still require the exact checksum. Public access does not
establish permission for unrestricted redistribution; check the original terms
and cite the study. These data are not hosted by COHORTome Store.

This path requires Convert-Pheno 0.35 and ClarID-Tools 0.04, with codebook 0.04.
The new shared Perl runtime includes these tools; older desktop bundles may
contain Pheno-Ranker only. Native deployments can configure
`COHORTOME_CONVERT_PHENO_BIN`, `COHORTOME_CLARID_TOOLS_BIN` and
`COHORTOME_CLARID_CODEBOOK` (the versioned YAML file). Missing tools produce an
error before the download starts.

## Import a package

Alternatively, choose **Import local package** and select a resource ZIP.
It must contain one dataset folder, including `resource.json`, the dataset
manifest and source files. A local import is structurally validated; unlike a
catalogue download, it has no independently reviewed archive checksum.
Only import packages from sources you trust.

COHORTome downloads to disk, verifies catalogue checksums, checks the package
structure and prepares its DuckDB store. ZIPs are limited to 1 GiB and extracted
contents to 4 GiB. Unsafe paths, symlinks and encrypted ZIPs are rejected.
Cancellation is available before database preparation. Keep the app open until
installation finishes. Failed installations are rolled back; retry downloads
start again rather than resuming a partial archive.

Once **Ready** appears, choose **Add to workspace selection**, then **Apply
workspace**. Installation alone never changes the active workspace. New imports
start with private classification, AI access blocked and admin-only visibility
on the web. Review these policies under **Admin → Data → Installed datasets** before sharing them.

## Storage

Under **Settings → Jobs & storage → Dataset storage**, choose the folder for
new imports. Desktop provides a folder picker. On the web, enter an existing
absolute server path; only administrators can edit it. The app checks write
access and reports available disk space.

The selected folder holds temporary downloads/extraction files and an
`installed/` subfolder with a separate directory for each imported package.
Existing datasets do not move when this setting changes. Their registered
paths remain in use, and duplicate detection still checks them. The query-store
cache remains in the app's runtime directory.

The default import location is `state/resources/` under the runtime directory.
Desktop uses its per-user application-data directory, separately for source
launches and packaged apps. See [Desktop storage](../getting-started/desktop#where-desktop-data-is-stored)
for the paths.

In Docker, select a path backed by a persistent mounted volume. This setting
does not create a Docker mount. An external disk must remain connected while
its datasets are in use.

The current installer runs in the app process, separately from analysis jobs.
It does not need Redis. Progress can be reopened while that process is running;
after a restart, retry an interrupted installation. A completed dataset that an
administrator disabled is preserved, not replaced by a retry.

## Remove an installed dataset

In **Admin → Data**, expand the dataset and choose **Remove dataset**.
Type its dataset ID to confirm. Bundled examples cannot be removed.
Finish or cancel queued and running jobs first; the removal check covers
all users, including jobs for other datasets.

Removal unregisters the dataset and clears its prepared DuckDB store.
Saved chats, cohorts and results remain, but references to the removed dataset
will no longer load. Reimporting a package does not repair those references.

Source files are retained by default. The optional file-removal checkbox
only accepts installer-managed packages. It moves the package to a `removed/`
directory beside `installed/` in its original storage location, allowing manual
recovery. This does not free disk space or permanently erase data.
Other source folders are never moved or deleted.

After removal, use **Reload workspace**, then select and apply the datasets
you want to use. A revised resource must have a new resource version and
matching archive checksum; do not overwrite an existing release.
