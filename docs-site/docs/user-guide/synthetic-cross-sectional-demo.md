# Synthetic cross-sectional demo

This cross-sectional dataset lets users test and demonstrate autoimmune research
workflows in COHORTome. Its measurements, group effects, technical variation, and
missingness are generated using predefined rules and random variation.

:::note[Software demonstration, not biological evidence]

Analysis results reflect programmed patterns. They should not be interpreted as
biological findings, treatment effects, or clinical evidence. Disease and marker
names provide context for testing the app; they do not validate the generated
values as a model of a real patient cohort.

:::

The Synthetic longitudinal demo remains available for longitudinal demonstrations.

## Synthetic identifiers

The numeric part of each synthetic patient ID is also its ClarID subject ID.
Prefixes are readable labels; they do not restart the numeric counter.

| Fixture | Source patient IDs | ClarID subject numbers |
| --- | --- | --- |
| Default | `SYN001`–`SYN030`, `HC031`–`HC038` | 1–38 |
| Private synthetic fixture | `PRIV10001` | 10001 |
| Large synthetic fixture | `SYN20001`–`SYN20030`, `HC20031`–`HC20038` | 20001–20038 |
| Autoimmune demo | `DEMOAI30001`–`DEMOAI30090` | 30001–30090 |

Sample IDs retain the source patient ID and their visit suffix. The ClarID
generator reads the numeric suffix rather than assigning numbers by row order,
and rejects duplicate numbers or IDs outside each fixture's reserved range.
These conventions apply only to synthetic fixtures; imported studies retain their source identifiers.

Older synthetic cohorts, projects and runs are not migrated after renumbering.
Prepare the synthetic query stores again and create new selections. Regenerate
subject sidecars with `scripts/generate_synthetic_clarids.py` and clarid-tools
0.04 after changing a fixture population. For a new large fixture, pass a fresh
directory using `--large-dataset-root`; the generator refuses to overwrite one.

## Contents

| Component | Synthetic content |
| --- | --- |
| Clinical | 90 fictional participants: 30 RA, 30 SLE, 30 healthy controls; one baseline sample each |
| RNA | 1,000 genes, 90 samples; positive fractional expected-count-like values |
| Methylation | 128 fictional CpG features, 84 samples; M-values |
| Immune cells | Six cell measurements, 81 samples |
| Serology | Six quantitative markers, 87 samples |

Dashboard summarises RSEM expected-count matrices without rounding to integers:
mean expected counts per sample, mean genes with counts above zero, and the five
genes with the largest total expected counts. These are descriptive summaries,
not expression filtering or differential-expression results. On-demand summaries
are limited to matrices up to 64 MiB and cached in memory until the file changes.
Larger matrices or matrices with invalid count values show unavailable summaries,
not zero counts. No extra DuckDB import is required.

Assays share participant identifiers. Different participants lack different
assays; immune-cell and serology matrices also contain some missing values.
Age, sex, batch and fictional recruitment center are provided in assay metadata.
Group sizes and technical batches are deliberately balanced for demonstration.
No treatment history or repeated visits are simulated.

## Try it in the app

Select **Synthetic cross-sectional demo** in Datasets and apply the workspace. If its
query store is not ready, an administrator must prepare it in Data Administration.

1. Inspect Dashboard's clinical, assay and multimodal coverage views.
2. Ask Query to list patients with Systemic Lupus Erythematosus. Save that cohort;
   save a healthy-control cohort too.
3. In Analysis, select those A/B cohorts and the synthetic RNA assay. Run
   limma-voom, not DESeq2: this assay is labelled `rsem_expected_counts` for
   compatibility with the expected-count workflow.
4. Inspect the methylation panel using PCA or a cohort comparison. Compare
   immune-cell and quantitative-serology measurements between the same groups.
5. Check sample counts: assay coverage means some analyses include fewer than
   30 participants per group.

Selected interferon-labelled genes have a planted SLE-group increase and selected
inflammation-labelled genes have a planted RA-group increase. Some methylation
features and quantitative markers have artificial group effects. A shared
participant component creates limited cross-modal correlation; RNA and methylation
also have batch effects. `simulation_truth.json` records feature-level planted
effects. These are engineering checks, not biological findings or a reproduction
of published study results. No exact significance threshold is guaranteed.

The RNA values were **not produced by RSEM**. Fictional CpG identifiers cannot
be used for genomic annotation. The small gene panel is not a transcriptome-wide
pathway-enrichment benchmark. Cell fractions are separate measurements, not a
complete partition of blood cells. Marker names do not make their simulated
distributions clinically realistic.

## Installation and regeneration

The source checkout and Docker image include `datasets/synthetic-cross-sectional-demo/`.
A fresh runtime lists it automatically;
existing registries are not silently changed. An administrator can register its
directory in Data Administration and prepare its query store.

To generate an independent copy in a new directory:

```bash
python3 scripts/generate_synthetic_autoimmune_demo.py --output /tmp/autoimmune-demo
```

The generator uses a fixed seed and the vendored public HGNC identifier list. It
does not read study data, runtime configuration, or network resources. It refuses
to overwrite an existing output directory. Share a clean installation and this
synthetic dataset, **not a copy of an existing research runtime or its backups**.
