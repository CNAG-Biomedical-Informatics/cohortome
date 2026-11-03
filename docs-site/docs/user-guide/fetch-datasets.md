# Fetch and prepare

**Downloaded and converted on your machine.** Start with processed study data from their provider.
COHORTome runs a reviewed recipe to create clinical records, link assays and
prepare DuckDB. You do not need to run conversion commands yourself.

## Available studies

| Dataset | Participants | Prepared data |
| --- | --- | --- |
| GSE85034 | 30 | Psoriasis treatment, PASI scores, 150 clinical visits and 179 skin-biopsy microarrays |
| GSE117239 | 89 | Psoriasis treatment, PASI scores and 324 microarrays |
| GSE191328 | 53 | 201 clinical snapshots and blood RNA-seq gene counts |
| GSE42296 | 39 | Crohn disease/RA, 78 paired clinical snapshots and microarrays |
| GSE68310 | 133 | 880 observations, respiratory expression and clinical metadata |
| IBDMDB | 112 | 898 clinical snapshots, 224 CRP/ESR measurements, metabolomics, metaproteomics and serology |

The catalogue in **Add dataset** is the current list. Choose **Refresh** to
check for new entries from [COHORTome Store](https://github.com/CNAG-Biomedical-Informatics/cohortome-store).
An entry marked **Requires app update** needs a newer shipped recipe or schema.

## Install

1. Open **Data → Add dataset** on Desktop, or **Admin → Data → Add dataset** on Web.
2. Choose **Browse available datasets** and select a study.
3. Read its source information and usage conditions, acknowledge the notice,
   then choose **Download and prepare**.
4. Keep the app open. When **Ready** appears, choose **Add to workspace
   selection**, then **Apply workspace**.

:::warning[Source terms and model access]

Acknowledging the notice is not a licence grant or permission to redistribute
the study. New imports start with **AI access blocked**. Review dataset policies
before enabling model access or sharing data with other Web users.

:::

## What is downloaded?

Processed expression/assay products and metadata—not FASTQ, BAM or raw array
intensities. Checksums pin the source versions. Preparation code ships with
COHORTome; the catalogue cannot supply executable scripts or arbitrary GEO accessions.
No GitHub token is needed for these studies.

<details>
<summary>Study-specific notes</summary>

- **GSE85034 / GSE117239:** microarray values are not RNA-seq counts. Repeated
  biopsies are not independent participants; ambiguous visit labels do not
  become invented elapsed times.
- **GSE191328:** one metadata file and 201 featureCounts files; downloading can
  take longer than conversion.
- **GSE42296:** retains the original processed matrix precision, both disease
  groups and paired visits.
- **GSE68310:** combines HR-VILAGE expression, earlier RIGEL metadata and a GEO
  phenotype supplement. Only wholly unmeasured columns are omitted and recorded.
  Visit timing starts at illness assessment, not enrollment. Clinical mapping
  includes sex and baseline enrollment age; other source metadata are retained.
- **IBDMDB:** four products, about 155 MB. All 81,867 metabolomics features are
  retained, including unnamed features. Metaproteomics is not a human protein
  panel. One unlinked serology column is excluded from the linked matrix and
  recorded in provenance. Repeated samples are not collapsed.

</details>

<details>
<summary>Tools, download checks and preparation records</summary>

Fetch-and-prepare uses Convert-Pheno 0.35 and ClarID-Tools 0.04 with codebook 0.04.
Native installations can configure `COHORTOME_CONVERT_PHENO_BIN`,
`COHORTOME_CLARID_TOOLS_BIN` and `COHORTOME_CLARID_CODEBOOK`. Missing tools are
reported before downloading.

The app verifies source sizes and SHA-256 checksums. It retains mappings,
checksums, preparation provenance and the source-review acknowledgement with
the dataset. Temporary source downloads and staging files are removed after the
attempt. Changed upstream bytes cause a failure, not a silently different dataset.

</details>

For storage, cancellation and removal, see [Installation and storage](install-datasets.md).
