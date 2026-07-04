---
sidebar_position: 4
---

# DICOM Viewing

BRN can launch DICOM studies in OHIF while keeping pixel storage in Orthanc or another DICOMweb service. This integration is optional and disabled by default.

## Runtime services

The Docker deployment includes an optional `dicom` profile:

- `orthanc`: DICOM storage and DICOMweb endpoint
- `ohif`: browser viewer
- `web`: BRN, which lists authorized studies and creates OHIF launch URLs

BRN does not copy OHIF, Cornerstone, or Orthanc source code into the app. They run as separate services.

## Enable local DICOM viewing

Edit `docker/.env`:

```bash
BRN_DICOM_ENABLED=true
BRN_OHIF_PUBLIC_URL=http://127.0.0.1:3000
BRN_DICOMWEB_PUBLIC_URL=http://127.0.0.1:8042/dicom-web
BRN_ORTHANC_INTERNAL_URL=http://orthanc:8042
BRN_ORTHANC_USERNAME=
BRN_ORTHANC_PASSWORD=
```

Start the stack with the DICOM profile:

```bash
docker compose -f docker/docker-compose.yml --env-file docker/.env --profile dicom up -d --build
```

Open:

```text
BRN:     http://127.0.0.1:8000
OHIF:    http://127.0.0.1:3000
Orthanc: http://127.0.0.1:8042
```

## Synthetic fixtures

Generate the bundled tiny synthetic DICOM files:

```bash
PYTHONPATH=.deps python3 scripts/dicom/generate_synthetic_dicom.py
```

Import them into Orthanc:

```bash
python3 scripts/dicom/import_to_orthanc.py default_dataset/assays/imaging/dicom --orthanc-url http://127.0.0.1:8042
```

Optionally import the other bundled fixture datasets:

```bash
python3 scripts/dicom/import_to_orthanc.py dataset-large/assays/imaging/dicom --orthanc-url http://127.0.0.1:8042
python3 scripts/dicom/import_to_orthanc.py private_dataset/assays/imaging/dicom --orthanc-url http://127.0.0.1:8042
```

## Dataset metadata

Each dataset exposes DICOM studies to BRN through:

```text
dataset_root/
  assays/
    imaging/
      dicom_studies.json
```

The file stores study identity and sample linkage, not DICOM pixels or Orthanc credentials:

```json
{
  "version": 1,
  "source": "synthetic",
  "studies": [
    {
      "study_id": "synthetic-mri-syn001-week0",
      "label": "Synthetic MRI baseline SYN001",
      "patient_id": "SYN001",
      "sample_id": "SYN001:week_0",
      "timepoint": "week_0",
      "modality": "MR",
      "study_instance_uid": "1.2.826.0.1.3680043.10.54321.1.1",
      "study_description": "Synthetic baseline MRI",
      "series": [
        {
          "series_instance_uid": "1.2.826.0.1.3680043.10.54321.1.1.1",
          "series_description": "Synthetic axial T1",
          "instance_count": 1,
          "sop_instance_uids": [
            "1.2.826.0.1.3680043.10.54321.1.1.1.1"
          ]
        }
      ]
    }
  ]
}
```

## Open a study

In BRN:

1. Load a dataset.
2. Open `Dashboard`.
3. Open the `Assays` dashboard view.
4. Find `DICOM imaging`.
5. Click `Open in OHIF`.

BRN only lists studies from datasets the current user can access. OHIF then loads pixels through the configured DICOMweb endpoint.

## Real DICOM data

For real data:

1. Import `.dcm` files into Orthanc or make sure they are available through an institutional DICOMweb endpoint.
2. Extract the Study/Series/SOP Instance UIDs.
3. Add those UIDs to `assays/imaging/dicom_studies.json`.
4. Link each study to the BRN `patient_id`, `sample_id`, and `timepoint`.
5. Load the dataset in BRN and open the Assays dashboard.

## Troubleshooting

- No studies in BRN: check that `dicom_studies.json` exists under the dataset root and that the user has access to that dataset.
- `Open in OHIF` is disabled: set `BRN_DICOM_ENABLED=true`.
- OHIF opens but shows no pixels: confirm the same StudyInstanceUID exists in Orthanc and that OHIF can reach `BRN_DICOMWEB_PUBLIC_URL`.
- Orthanc is unreachable from BRN: check `BRN_ORTHANC_INTERNAL_URL=http://orthanc:8042` when using Docker Compose.
- Browser CORS errors: keep OHIF and Orthanc behind the same local deployment or reverse proxy, or update Orthanc CORS settings for the deployment.
