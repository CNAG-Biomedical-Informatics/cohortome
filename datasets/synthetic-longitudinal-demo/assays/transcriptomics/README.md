# Molecular Data

Place molecular datasets here.

Current development fixture:

- `synthetic_transcriptome_raw_counts_baseline.csv`
  - Semicolon-delimited raw count matrix
  - Columns are untreated baseline `week_0` samples for all synthetic patients
  - Intended as a pre-treatment control/reference snapshot
- `synthetic_transcriptome_raw_counts_hc_baseline.csv`
  - Semicolon-delimited raw count matrix
  - Columns are untreated healthy-control `week_0` baseline samples
  - Intended as an external HC baseline cohort with different IDs
- `synthetic_transcriptome_raw_counts_infliximab.csv`
  - Post-treatment samples for synthetic Crohn Disease and other synthetic patients treated with Infliximab
- `synthetic_transcriptome_raw_counts_ustekinumab.csv`
  - Post-treatment samples for a synthetic Crohn Disease subset treated with Ustekinumab
- `synthetic_transcriptome_raw_counts_vedolizumab.csv`
  - Post-treatment samples for synthetic Ulcerative Colitis patients treated with Vedolizumab
- `synthetic_transcriptome_raw_counts_ocrelizumab.csv`
  - Post-treatment samples for synthetic Multiple Sclerosis patients treated with Ocrelizumab
- `synthetic_transcriptome_raw_counts_belimumab.csv`
  - Post-treatment samples for synthetic Systemic Lupus Erythematosus patients treated with Belimumab
- `synthetic_transcriptome_raw_counts_adalimumab.csv`
  - Post-treatment samples for synthetic Rheumatoid Arthritis patients treated with Adalimumab
- `synthetic_transcriptome_raw_counts_mepolizumab.csv`
  - Post-treatment samples for synthetic Asthma patients treated with Mepolizumab
- `synthetic_transcriptome_raw_counts_dupilumab.csv`
  - Post-treatment samples for synthetic COPD patients treated with Dupilumab

Notes:
- All sample IDs match the merged longitudinal IDs in `datasets/synthetic-longitudinal-demo/clinical/synthetic_longitudinal.json`.
- Healthy control baseline sample IDs match `datasets/synthetic-longitudinal-demo/clinical/synthetic_hc_baseline.json`.
- `week_0` is a true untreated baseline in the synthetic clinical fixture.
- Healthy controls are baseline-only and intentionally omit the `diseases` field.
- The expression panel is larger and structured into disease-relevant synthetic modules (inflammatory, interferon, B-cell, stromal, airway, eosinophil, barrier, housekeeping).
- Counts are deterministic synthetic raw counts intended for exploratory UI development, not biological realism.
- Large transcriptome fixtures use real HGNC-approved human protein-coding genes vendored in `scripts/data/hgnc_protein_coding_symbols.tsv`.
- Matrix row identifiers use Ensembl gene IDs (`ENSG...`) even for the large fixtures.
- The gene identifiers are real, but their module assignments and count dynamics remain synthetic and deterministic for timing and queue testing.
