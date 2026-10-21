---
sidebar_position: 2
---

# Patient IDs vs Sample IDs

A patient ID identifies a person, such as `SYN001`. A sample or clinical-record
ID identifies a particular specimen or observation, such as `SYN001:week_0`.
Several records can belong to one person, so record counts are not patient counts.

## Choose the right scope

| Task | Selection |
| --- | --- |
| Find people with a disease or treatment | Patients |
| Compare clinical snapshots in Pheno-Ranker | Records/timepoints |
| Analyze molecular measurements | Assay samples linked to patients |
| Reuse a plot selection | Preserve the original record or sample IDs |

Analysis requirements determine whether repeated samples are allowed.
Selecting patients does not by itself resolve which visit or assay sample to use.

## Transfer selections

Use **Save cohort** or **Open in Analysis** to preserve dataset, patient and
sample identities. Do not strip prefixes or merge matching IDs manually:
different datasets may use the same source ID, and Pheno-Ranker may add
temporary reference markers.

The app recognizes patient terms such as *subject* and *individual*, and sample
terms such as *biosample*, *specimen*, *record* and *timepoint*. Review the
result's actual scope before handing it to another tool.

See [cross-sectional and longitudinal data](cross-sectional-and-longitudinal.md)
for participant, visit and assay linkage.
