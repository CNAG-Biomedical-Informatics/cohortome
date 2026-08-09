# Platform Scope And Boundaries

COHORTome is a research workbench that sits between heterogeneous data delivery and
project-specific statistical or bioinformatics environments. It standardizes
how data is registered, linked, governed, queried, and handed to curated
analyses without pretending that every source study has the same semantics.

## What works now and what comes next

| Area | Implemented now | Next step |
| --- | --- | --- |
| Clinical input | Beacon v2 / Beacon Friendly Format-style patient records. | Project adapters and mapping validation, starting with released 3TR datasets. |
| Assay input | Manifested transcriptomics, OLINK, proteomics, genotyping, and derived-imaging matrices. | Additional assay definitions, quality metadata, and consistent feature names. |
| Imaging | DICOM metadata linkage, OHIF launch, and derived-feature matrices. | Authenticated institutional DICOMweb plus validated external preprocessing outputs. |
| Workspaces | One or more authorized prepared dataset stores with preserved provenance. | Cross-study workspaces, first over released and approved 3TR datasets. |
| Query | Deterministic clinical questions and policy-controlled LLM assistance. | Evaluated natural-language cohort tasks, starting with PRECISESADS and 3TR use cases. |
| Analysis | Clinical summaries, trajectories, survival views, transcriptomics, enrichment, external runners, and Pheno-Ranker. | Prespecified cross-condition and multimodal analyses selected with collaborators. |
| Multimodal | Readiness, overlap, missingness, and a bounded feature preview. | Exportable analysis matrices, modality-specific QC, and curated integration methods. |
| Deployment | Local/source operation and a single-VM Docker pilot. | Hardened institutional deployment with protected data services and reproducible releases. |

## Related tools and where COHORTome fits

COHORTome enters a mature ecosystem. The tools below solve important parts of the
research-data journey, but they start from different data and serve different
primary tasks. This is therefore a positioning map, not a claim that COHORTome
replaces them or a feature-by-feature ranking.

| Area | Representative tools | Primary role | Relationship to COHORTome |
| --- | --- | --- | --- |
| Clinical cohort discovery | [i2b2](https://i2b2.org/) and [OHDSI ATLAS](https://github.com/OHDSI/Atlas) | Query clinical warehouses or standardized observational data and define reusable patient cohorts. | COHORTome shares the cohort-discovery concern but keeps longitudinal clinical records connected explicitly to samples, visits, assays, and source datasets. An OMOP or i2b2 source could be handled through an adapter rather than reimplemented. |
| Translational clinical-omics exploration | [tranSMART](https://pmc.ncbi.nlm.nih.gov/articles/PMC4333702/) | Bring clinical and high-dimensional molecular data together for translational exploration and analysis. | tranSMART is an important conceptual predecessor and manuscript comparator. COHORTome revisits this problem with deployable multi-dataset workspaces, explicit patient/sample scope, current external analysis runners, and policy-controlled LLM assistance. |
| Data commons and research stewardship | [Gen3](https://gen3.org/products/) and [FAIRDOM-SEEK](https://docs.seek4science.org/) | Manage data commons, files, metadata, research assets, models, protocols, and controlled access. | These systems can remain upstream sources or complementary stewardship services. COHORTome consumes authorized releases and organizes the researcher-facing cohort and analysis workflow; it is not intended to become another primary archive. |
| Reproducible computational analysis | [Galaxy](https://galaxyproject.org/) | Make a broad catalogue of computational tools and workflows accessible through a reproducible web environment. | COHORTome curates a smaller set of analyses around an active cohort and can hand work to Galaxy or another workflow service instead of reproducing a general workflow platform. |
| Federated analysis | [DataSHIELD](https://datashield.org/) | Analyze sensitive data across sites without giving analysts direct access to individual-level records or moving those records centrally. | DataSHIELD is relevant when a consortium question must be computed where the data reside. COHORTome currently works from authorized releases, but a federated runner could become a complementary execution path. |
| Lightweight DICOM viewing | [OHIF](https://docs.ohif.org/) with [Orthanc](https://www.orthanc-server.com/static.php?page=about) or another DICOMweb archive | Display medical images in the browser and provide the DICOM storage or transport behind the viewer. | This is COHORTome's deliberately narrow imaging implementation. COHORTome links an authorized study to OHIF and does not implement its own viewer, PACS, or pixel renderer. Orthanc remains useful for local development and smoke testing. |
| Imaging repositories and processing platforms | [XNAT](https://wiki.xnat.org/documentation/getting-started-with-xnat), [Kaapana](https://kaapana.readthedocs.io/en/stable/), and [QMENTA](https://support.qmenta.com/knowledge/qmenta-platform) | Manage imaging studies and support quality control, processing, annotation, or imaging-specific workflows at research or clinical-trial scale. | These are specialist imaging environments, not components COHORTome needs to reproduce. In the planned 3TR setting, imaging experts and QMENTA perform the image processing; COHORTome consumes their approved quantitative outputs and may retain links for visual inspection and provenance. |
| Medical-imaging AI development | [MONAI](https://monai.readthedocs.io/en/stable/modules.html) | Provide reusable deep-learning components for medical-image preprocessing, training, evaluation, and inference. | MONAI is appropriate for teams developing pixel-level models. COHORTome does not train such models; it treats validated outputs such as lesion burden or regional volumes as derived imaging features. |

The resulting boundary is intentional: COHORTome is not another warehouse, PACS,
general workflow engine, or medical-imaging AI platform. It is a downstream
research workbench that turns authorized heterogeneous releases into a governed,
patient- and sample-aware workspace. It connects cohort construction,
longitudinal clinical context, assay availability, curated analyses,
policy-controlled LLM assistance, and persisted evidence. Specialist systems
remain responsible for their domains, while COHORTome records their processed outputs
in a form that can be combined with clinical and other assay features.

For imaging specifically, the manuscript should distinguish three operations:

1. source images may be opened in OHIF for authorized visual inspection
2. image processing and validation are performed by QMENTA or another qualified
   imaging pipeline
3. COHORTome receives processed measurements, quality information, pipeline versions,
   and patient/visit linkage for downstream multimodal statistics or machine
   learning

This positioning avoids claiming imaging expertise while still making imaging
evidence usable alongside the other 3TR modalities.

## Harmonization boundary

COHORTome defines a shared application contract:

- `clinical/` contains patient-centric clinical records
- `assays/` contains manifested assay datasets and imaging linkage
- patient, sample, visit, and time-point identity is explicit
- feature namespaces, data types, modality, and provenance remain available
- prepared stores normalize query behavior without erasing source-dataset
  identity

Source-specific conversion can happen in a project adapter or an upstream tool.
COHORTome should validate and expose the resulting contract rather than burying
project-specific mapping assumptions inside user-interface code.

## Analysis boundary

The platform launches curated analyses; it does not replace specialist methods.
For example:

- DESeq2 remains responsible for differential expression
- fgsea remains responsible for pathway enrichment
- Pheno-Ranker remains responsible for phenotype similarity
- OHIF remains responsible for DICOM visualization
- an appropriate external pipeline must produce MRI lesion or regional-volume
  features

COHORTome contributes explicit data scope, readiness checks, controlled execution,
persisted parameters, artifacts, and a coherent researcher workflow around
those methods.

## AI boundary

Models may help formulate and interpret research operations, but they do not
receive ambient access to every dataset or an unrestricted shell. Dataset policy
and approved-provider configuration apply before model invocation. Results must
identify whether they came from deterministic logic, LLM planning, LLM-only
interpretation, or a curated analysis runner.

## Scientific boundary

The checked-in fixture is designed to exercise the seven-condition scope of the
first planned 3TR deployment. Its clinical trajectories, assay values, treatment
effects, and DICOM pixels are synthetic. They validate software behavior, not
disease biology.

Scientific claims require the restricted PRECISESADS demonstrator or another
approved real dataset, a prespecified question, appropriate statistical methods,
and collaborator review.

## Non-goals

- primary warehouse or file-sharing replacement
- clinical care or autonomous treatment recommendation
- unrestricted model access to record-level data
- arbitrary user or model code execution
- in-browser raw-image segmentation
- hiding patient-versus-sample or baseline-versus-follow-up scope
- silently merging datasets while discarding provenance
