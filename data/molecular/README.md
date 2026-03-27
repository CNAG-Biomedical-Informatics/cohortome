# Molecular Data

Place molecular datasets here.

Current development fixture:

- `synthetic_transcriptome_raw_counts.csv`
  - Semicolon-delimited raw count matrix
  - Columns are the same merged longitudinal IDs used by the clinical synthetic cohort:
    `SYN001:week_0` to `SYN010:week_26`
  - Five timepoints per patient, aligned to the clinical records
  - Rows are Ensembl-like gene identifiers
- `synthetic_transcriptome_raw_counts_infliximab.csv`
  - Semicolon-delimited raw count matrix
  - Columns are the merged longitudinal IDs for the synthetic Infliximab-treated patients:
    `SYN001:week_0` to `SYN005:week_26`
  - Five timepoints per patient, aligned to the clinical records
  - Rows are Ensembl-like gene identifiers
- `synthetic_transcriptome_raw_counts_vedolizumab.csv`
  - Semicolon-delimited raw count matrix
  - Columns are the merged longitudinal IDs for the synthetic Vedolizumab-treated patients:
    `SYN006:week_0` to `SYN010:week_26`
  - Five timepoints per patient, aligned to the clinical records
  - Rows are Ensembl-like gene identifiers
