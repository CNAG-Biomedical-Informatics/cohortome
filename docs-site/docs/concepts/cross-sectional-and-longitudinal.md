---
sidebar_position: 3
---

# Cross-sectional and longitudinal data

COHORTome supports studies that observe each participant once and studies that
follow the same participant over time.

The distinction matters because a single observation is not a visit history,
and repeated observations must not be collapsed into one person-level row.

## Two study shapes

| Study shape | What the data contain | How COHORTome treats it |
| --- | --- | --- |
| **Cross-sectional** | One clinical observation point per participant | One person-level clinical record. The interface can compare people and connect their assays without inventing a timeline. |
| **Longitudinal** | Two or more observations for the same participant | Separate timepoint records linked to the same person. The interface can show change over time and keep each visit's clinical and assay context. |

A dataset can still contain several files or assay modalities and remain
cross-sectional. What determines the study shape is whether its clinical record
follows a participant across distinct observation points.

## Why identifiers stay separate

Longitudinal research commonly involves several related identifiers:

- **participant ID** identifies the person
- **visit ID** identifies an observation point
- **clinical snapshot ID** identifies the record captured at that point
- **biosample ID** identifies collected biological material
- **assay sample ID** identifies the material or preparation measured by an assay

They may look similar in a source dataset, but they do not mean the same thing.
COHORTome keeps those links explicit so that an assay is attached to the right
person and timepoint and repeated samples are not mistaken for extra people.

## Clinical representations

COHORTome uses two corresponding BFF ingestion patterns:

- **Person representation** has one BFF individual object per participant. It
  fits a cross-sectional release with one clinical observation point.
- **Snapshot representation** has one BFF individual object per participant and
  timepoint. All snapshots retain a stable link to the participant and their
  visit context.

Do not create synthetic visits for a cross-sectional dataset. Likewise, do not
merge repeated visits into one BFF object merely because they belong to the
same participant.

:::note Beacon and visit context
Beacon Friendly Format is the clinical interchange model, but Beacon v2 does
not provide the complete visit model needed for every longitudinal study.
COHORTome therefore requires an ingestion mapping to preserve participant and
visit linkage explicitly instead of inferring it from file order.
:::

## What researchers see

For cross-sectional data, the Dashboard presents the available clinical state
and connected assays for each person. Analyses can compare groups at that
observation point.

For longitudinal data, the Dashboard can present repeated events in time order.
Analyses can use baseline, follow-up, change, or trajectory when the underlying
dataset actually contains those observations.

In both cases, the active workspace, access rules, provenance, and saved cohort
scope behave in the same way.

Read [Patient IDs vs Sample IDs](./patient-vs-sample) for the related selection
and handoff rules.
