# Platform Scope And Boundaries

BRN is a research workbench that sits between heterogeneous data delivery and
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

## Harmonization boundary

BRN defines a shared application contract:

- `clinical/` contains patient-centric clinical records
- `assays/` contains manifested assay datasets and imaging linkage
- patient, sample, visit, and time-point identity is explicit
- feature namespaces, data types, modality, and provenance remain available
- prepared stores normalize query behavior without erasing source-dataset
  identity

Source-specific conversion can happen in a project adapter or an upstream tool.
BRN should validate and expose the resulting contract rather than burying
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

BRN contributes explicit data scope, readiness checks, controlled execution,
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
