# Molecular Data

Place molecular datasets here.

Current development fixture:

- `synthetic_transcriptome_raw_counts_baseline.csv`
  - Semicolon-delimited raw count matrix
  - Columns are untreated baseline `week_0` samples for all synthetic patients
  - Intended as a pre-treatment control/reference snapshot
- `synthetic_transcriptome_raw_counts_infliximab.csv`
  - Post-treatment samples for synthetic Crohn Disease patients treated with Infliximab
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
- All sample IDs match the merged longitudinal IDs in `data/clinical/synthetic_longitudinal.json`.
- `week_0` is a true untreated baseline in the synthetic clinical fixture.
- The expression panel is larger and structured into disease-relevant synthetic modules (inflammatory, interferon, B-cell, stromal, airway, eosinophil, barrier, housekeeping).
- Counts are deterministic synthetic raw counts intended for exploratory UI development, not biological realism.
