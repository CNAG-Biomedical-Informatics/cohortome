# Evaluation And Evidence

COHORTome needs tests of software correctness and usefulness for research.
The public synthetic fixture supports the first level. The restricted
PRECISESADS demonstrator is required for the second.

## Evaluation areas

| Area | Question | Representative evidence |
| --- | --- | --- |
| Functional | Can each user role complete the intended workflow? | Automated tests and reviewed task scripts. |
| Reproducibility | Does the same dataset, cohort, and method reproduce the same evidence? | Source fingerprints, manifests, parameters, artifact comparison, and pinned environments. |
| Performance | Does preparation and interactive use remain practical at representative scale? | Preparation, reload, dashboard, matrix, and workflow timings. |
| Model assistance | Does the model select the right data, give supported answers, and follow access rules? | Reference tasks, cohort agreement, review of unsupported claims, and disclosure tests. |
| Usability | Can clinical and translational researchers complete tasks without manual scripting? | Prespecified task completion, errors, time, and structured collaborator feedback. |
| Scientific demonstrator | Does PRECISESADS produce a meaningful, reviewed analysis result? | Prespecified cohorts, real assay output, statistics, figures, and collaborator interpretation. |

## What the synthetic data can test

The checked-in data is synthetic. It can verify:

- patient, sample, visit, and assay linkage
- cross-dataset workspace behavior
- authorization and disclosure policy
- deterministic and model-provider failure paths
- transcriptomics workflow plumbing
- DICOM metadata and OHIF rendering
- multimodal overlap and missingness behavior

It cannot validate disease mechanisms, treatment-response biomarkers,
PRECISESADS clusters, medically realistic MRI findings, or model utility for
real clinical research.

## PRECISESADS demonstrator requirements

Before a publication claim is considered supported, record:

1. approved disease groups and scientific question
2. patient, sample, assay, and time-point counts
3. inclusion, exclusion, and missingness rules
4. mapping and harmonization decisions
5. saved cohort definitions and dataset fingerprints
6. one complete clinical-assay or cross-condition analysis
7. statistical parameters and generated artifacts
8. model-assisted tasks with reviewed reference answers
9. performance and reproducibility measurements
10. collaborator interpretation and limitations

## LLM reference tasks

The evaluation set should contain tasks that exercise different risks:

- exact deterministic cohort counts
- semantic cohort criteria requiring planning
- patient-versus-sample and baseline-versus-follow-up distinctions
- cross-condition comparisons
- insufficient-data and missing-modality responses
- summary-only and blocked-provider workspaces
- interpretation of a fixed curated-analysis output
- provider unavailability

For each task, preserve the task text, expected structured scope, allowed
context, execution mode, provider and model identity, observed output, scoring
decision, and reviewer.

## Release evidence

A paper or public release should use pinned Python and R environments, fixed
container tags or digests, a versioned analysis catalog, a green automated test
baseline, and a checked data/configuration manifest. Results should be
reproducible without access to the private manuscript or developer chat history.
