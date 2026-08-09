# 3TR And PRECISESADS

3TR is the first planned consortium-scale deployment of COHORTome, not the boundary of
the software. COHORTome is a generic open-source tool that can be configured for other
approved longitudinal clinical and assay datasets.

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

Its research model depends on joint interpretation of longitudinal clinical
data and multiple molecular measurements across conditions. This makes 3TR a
strong first deployment setting for the reusable COHORTome workbench.

## How COHORTome relates to the Omics DM Warehouse

The 3TR Omics DM Warehouse and COHORTome solve different problems.

| 3TR Omics DM Warehouse | COHORTome |
| --- | --- |
| Keeps and distributes project files. | Turns an authorized release into a research workspace. |
| Preserves the data delivered by each project. | Connects clinical records, assays, patients, samples, and visits. |
| Provides PRECISESADS and other authorized data releases. | Helps researchers explore data, find cohorts, run analyses, and keep the results. |
| Remains the source system. | Remains a separate application with its own access and analysis workflow. |

COHORTome can consume authorized warehouse exports, but core behavior must not depend
on warehouse-specific paths, APIs, or storage conventions. The same deployment
model can operate on institutional files or other approved services.

## PRECISESADS as the first real reference implementation

[PRECISESADS](https://www.ihi.europa.eu/projects-results/project-factsheets/precisesads)
studied molecular reclassification across systemic autoimmune diseases and
provides an appropriate real-world setting for cross-condition cohort analysis.
The PRECISESADS data are stored in the 3TR Omics DM Warehouse. COHORTome receives an
authorized release from that warehouse; PRECISESADS is not a separate storage
system. The COHORTome demonstrator is being developed with collaborators at FPS in
Granada.

The reference implementation is intended to exercise a complete path:

1. map restricted source files into explicit clinical and assay contracts
2. validate patients, samples, time points, conditions, and feature provenance
3. register separately governed disease datasets
4. inspect cross-condition coverage and missingness
5. formulate and save cohorts using deterministic or governed LLM-assisted Query
6. run a prespecified clinical-assay analysis
7. preserve the data scope, parameters, execution mode, and outputs
8. evaluate correctness, reproducibility, performance, and researcher utility

The exact disease contrast, assay, endpoint, and cohort sizes remain publication
decisions until they are agreed with the scientific collaborators and verified
against the restricted files.

## Data categories

| Category | Repository status | Intended use |
| --- | --- | --- |
| Public synthetic fixtures | Checked in | Development, screenshots, smoke tests, and automated tests. |
| Restricted PRECISESADS files | Never checked in | Scientific demonstrator and evaluation under approved access. |
| Released 3TR datasets | Registered when authorized | Consortium-wide workspaces and cross-condition analyses. |
| Derived run artifacts | User- and deployment-scoped | Auditable analysis evidence subject to retention policy. |

## Publication role

PRECISESADS should demonstrate the platform rather than redefine it as a
PRECISESADS-only application. The software claim is general: an independently
deployable layer can connect harmonized clinical and assay data, governed
natural-language interaction, reusable cohorts, curated workflows, and
reproducible evidence across heterogeneous translational projects.
