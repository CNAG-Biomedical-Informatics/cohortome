# Project context

3TR is the first planned consortium deployment of COHORTome. The software can
also be configured for other approved clinical and assay datasets.

## Consortium context

[3TR](https://www.ihi.europa.eu/projects-results/project-factsheets/3tr) studies
response and non-response to therapy, relapse, and remission across seven
autoimmune, inflammatory, and allergic disease areas:

- systemic lupus erythematosus
- rheumatoid arthritis
- multiple sclerosis
- ulcerative colitis
- Crohn disease
- asthma
- chronic obstructive pulmonary disease

3TR researchers need to interpret longitudinal clinical data and molecular
measurements together across these conditions. COHORTome is being developed
to support that work.

## How COHORTome relates to the Omics DM Warehouse

The 3TR Omics DM Warehouse and COHORTome solve different problems.

| 3TR Omics DM Warehouse | COHORTome |
| --- | --- |
| Keeps and distributes project files. | Turns an authorized release into a research workspace. |
| Preserves the data delivered by each project. | Connects clinical records, assays, patients, samples, and visits. |
| Provides authorized study data releases. | Helps researchers explore data, find cohorts, run analyses, and keep the results. |
| Remains the source system. | Remains a separate application with its own access and analysis workflow. |

COHORTome can consume authorized warehouse exports, but core behavior must not depend
on warehouse-specific paths, APIs, or storage conventions. The same deployment
model can operate on institutional files or other approved services.

## Scientific use case

[PRECISESADS](https://www.ihi.europa.eu/projects-results/project-factsheets/precisesads)
studied molecular reclassification across systemic autoimmune diseases and
is one candidate for evaluating cross-condition cohort analysis. The dataset
and scientific question for the publication have not been finalized. Their
selection depends on access, available measurements, and scientific review.

The selected use case should exercise a complete path:

1. map restricted source files into explicit clinical and assay contracts
2. validate patients, samples, time points, conditions, and feature provenance
3. register datasets with their access rules
4. inspect cross-condition coverage and missingness
5. find and save cohorts using deterministic or permitted LLM-assisted queries
6. run a prespecified clinical-assay analysis
7. preserve the data scope, parameters, execution mode, and outputs
8. evaluate correctness, reproducibility, performance, and researcher utility

The exact disease contrast, assay, endpoint, and cohort sizes remain publication
decisions until they are agreed with the scientific collaborators and verified
against the selected data.

## Data categories

| Category | Repository status | Intended use |
| --- | --- | --- |
| Public synthetic fixtures | Checked in | Development, screenshots, smoke tests, and automated tests. |
| Restricted study files | Never checked in | Scientific analysis and evaluation under approved access. |
| Released 3TR datasets | Registered when authorized | Consortium-wide workspaces and cross-condition analyses. |
| Derived run artifacts | User- and deployment-scoped | Auditable analysis evidence subject to retention policy. |

## Publication role

The selected use case should test a complete workflow: prepare clinical and
assay data, select cohorts, run an analysis, and review the result with
collaborators. The paper will describe the reusable software and report the
results and limitations of that use case.
