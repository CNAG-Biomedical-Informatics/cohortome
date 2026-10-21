# IBDMDB processed multi-omics

Prepared locally from the four processed products linked by the
[IBDMDB download catalogue](https://ibdmdb.org/results).
Original study: [Lloyd-Price et al., 2019](https://doi.org/10.1038/s41586-019-1237-9).
Source URLs, sizes and SHA-256 checksums are in provenance/preparation.json.

## Contents

- 112 participants and 898 clinical snapshots, grouped by exact participant,
  source visit and study week. Stool and serum sample links remain separate.
- 224 structured measurements: 112 CRP and 112 ESR observations.
- Metabolomics: 546 samples and 81,867 features, including unnamed features.
- Metaproteomics: 450 samples and 11,284 features. This is not a human protein panel.
- Serology: 210 linked samples and five numeric ELISA measurements.

## Conversion and limitations

Convert-Pheno maps diagnoses, sex, CRP and ESR to BFF v2. Other nonempty metadata
remain under info.source_metadata. No calendar dates, baseline propagation,
doses or additional clinical measurements are inferred.

Published assay values are retained without further normalization or replicate
collapse. Omitted sparse BIOM entries become zero under the BIOM 1.0 convention;
this does not establish biological absence. Original metabolite annotations are
retained; the separate 2021 annotation update is not applied.

One serology column (220948) has no exact match in the published serology
metadata. It is omitted from the linked matrix, listed in exclusions.json and
retained in assays/serology_source.tsv. No participant identity is guessed.

Subject ClarIDs use codebook/tools 0.04. CD maps to K50.9, UC to K51.9 and the
non-IBD comparison group to Z00.00, following the ClarID identifier convention.
The last code is not a BFF diagnosis or a claim that the comparison group is
healthy. Unknown age remains unavailable. Both identifier formats are decoded
and checked before installation.

## Source conditions

Review the source conditions and cite the original study. The
[iHMP consortium report](https://pmc.ncbi.nlm.nih.gov/articles/PMC6784865/)
describes public unrestricted-use data. Do not assign COHORTome's software
licence to third-party data. This package was built from the original provider,
not downloaded from COHORTome Store.
