---
sidebar_position: 3
---

# Assays and modalities

Biomedical Research Navigator workspaces combine clinical records with assay data. Clinical data describes patients, visits, diagnoses, treatments, and measurements. Assays describe measured sample-level data that can be linked back to patients and visits.

## Assay model

Each assay dataset is identified by stable metadata:

- `assay_id`: stable identifier for the matrix or resource.
- `modality`: the measurement family, such as transcriptomics, OLINK, proteomics, genotyping, or imaging.
- `data_type`: the value shape, such as raw counts, relative abundance, protein abundance, allele dosage, or DICOM-derived measurements.
- `feature_namespace`: the feature identifier system, such as Ensembl gene IDs, protein symbols, UniProt-backed protein IDs, dbSNP rsIDs, or DICOM standard tags.
- `level`: whether analysis is patient-level or sample-level.

Transcriptomics raw-count matrices are the active assay modality for the current curated Analysis tools. OLINK, proteomics, genotyping, and DICOM-standard imaging metadata matrices are included as scaffold fixtures so the UI and catalog can reason about multimodal assays consistently.

## Patient and sample linkage

Assay columns use sample IDs. In the synthetic fixtures, sample IDs follow the `patient:visit` pattern, which lets the workspace derive patient and timepoint linkage for sample-level analyses. Cohort tools can therefore check whether a selected assay overlaps the current workspace scope, Cohort A, and Cohort B.

## DICOM imaging

Imaging assays must use the DICOM standard. The current fixture represents imaging as DICOM-derived measurement matrices keyed by DICOM tag identifiers such as `DICOM:0018,0087_MagneticFieldStrength` and `DICOM:0028,0030_PixelSpacingRow`.

Raw DICOM object storage, DICOMweb retrieval, and pixel-data processing are not implemented in this refactor. Those should be added as DICOM-native resources rather than as generic image files.

## Analysis requirements

Curated Analysis tools declare their assay capabilities explicitly. For example, transcriptomics differential expression requires:

- transcriptomics modality;
- raw-count data;
- sample-level analysis;
- compare mode with Cohort A and Cohort B;
- one selected compatible assay dataset.

The Analysis Catalog surfaces these requirements as capability labels so users can distinguish clinical-only tools from assay-specific tools before configuring a run.
