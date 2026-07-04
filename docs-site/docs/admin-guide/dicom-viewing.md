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
BRN_OHIF_HOST_PORT=3000
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

The generator reads each dataset's `assays/imaging/dicom_studies.json` manifest
and writes matching `.dcm` files under `assays/imaging/dicom/`. The bundled
fixtures use pydicom's visible `MR_small.dcm` test image as a source image, then
assign BRN-specific Study/Series/SOP Instance UIDs, patient IDs, sample IDs,
study descriptions, and synthetic profile metadata.

The default fixture intentionally contains two kinds of studies:

- `synthetic-mri-syn001-week0`: a stable DICOM viewer smoke-test study. Its
  StudyInstanceUID is `1.2.826.0.1.3680043.10.54321.1.1`, and it should remain
  available for automated OHIF rendering checks.
- `synthetic-ms-brain-syn011-week0` and `synthetic-ms-brain-syn012-week0`:
  synthetic multiple-sclerosis brain MRI examples linked to fixture patients
  that carry `Multiple Sclerosis` clinical diagnoses. They are still derived
  test fixtures, not medically realistic MR simulations, but their pixel data is
  deliberately non-flat and patient-specific so OHIF rendering failures are
  easier to catch.

:::warning Synthetic pixels
The bundled MS brain MRI examples use MS-like metadata, but their pixels are
derived from pydicom test data. They are for OHIF/metadata smoke testing only
and are not realistic MS lesion images.
:::

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
      "label": "DICOM viewer smoke test MRI",
      "patient_id": "SYN001",
      "sample_id": "SYN001:week_0",
      "timepoint": "week_0",
      "modality": "MR",
      "synthetic_profile": "smoke_test",
      "study_instance_uid": "1.2.826.0.1.3680043.10.54321.1.1",
      "study_description": "Synthetic DICOM viewer smoke test MRI",
      "series": [
        {
          "series_instance_uid": "1.2.826.0.1.3680043.10.54321.1.1.1",
          "series_description": "Synthetic axial T1 smoke test",
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

For synthetic MS examples, `body_part` is set to `BRAIN` and
`synthetic_profile` is set to a profile such as `ms_brain_mild` or
`ms_brain_moderate`. These fields are fixture-generation hints. Real datasets
do not need `synthetic_profile`; they should describe the real study and point
to UIDs that already exist in the DICOMweb archive.

## Open a study

In BRN:

1. Load a dataset.
2. Open `Dashboard`.
3. Open the `Assays` dashboard view.
4. Find `DICOM imaging`.
5. Click `Open in OHIF`.

BRN only lists studies from datasets the current user can access. OHIF then loads pixels through the configured DICOMweb endpoint.

In the bundled Docker setup, OHIF proxies `/dicom-web/` and `/wado` to Orthanc
inside Docker. Browser requests therefore stay on the OHIF origin and avoid
local CORS failures.

## Run BRN from source with Docker DICOM services

For local development, run only Orthanc and OHIF in Docker and run BRN from the source checkout.

Start the DICOM services:

```bash
docker compose -f docker/docker-compose.yml --env-file docker/.env --profile dicom up -d orthanc ohif
```

Generate and import the bundled synthetic DICOM files:

```bash
PYTHONPATH=.deps python3 scripts/dicom/generate_synthetic_dicom.py
python3 scripts/dicom/import_to_orthanc.py default_dataset/assays/imaging/dicom --orthanc-url http://127.0.0.1:8042
```

Start BRN from source:

```bash
export BRN_AUTH_MODE=local
export BRN_SESSION_SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"

export BRN_DICOM_ENABLED=true
export BRN_OHIF_PUBLIC_URL=http://127.0.0.1:3000
export BRN_DICOMWEB_PUBLIC_URL=http://127.0.0.1:8042/dicom-web
export BRN_ORTHANC_INTERNAL_URL=http://127.0.0.1:8042

PYTHONPATH=.deps uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

When BRN runs from source on the host, `BRN_ORTHANC_INTERNAL_URL` must point to
`http://127.0.0.1:8042`. Use `http://orthanc:8042` only when BRN itself is
running inside the Docker Compose network.

Open `http://127.0.0.1:8000`, then go to `Dashboard -> Assays -> DICOM imaging`.

To verify that OHIF is rendering pixels instead of a black/blank viewport:

```bash
PYTHONPATH=.deps python3 scripts/dicom/check_ohif_render.py \
  "http://127.0.0.1:3001/viewer?StudyInstanceUIDs=1.2.826.0.1.3680043.10.54321.1.1"
```

The URL above uses the smoke-test StudyInstanceUID. If OHIF is exposed on port
`3000`, replace `3001` with `3000`. The check captures the largest OHIF canvas
and fails when the viewport is effectively black or when browser console errors
are emitted.

## OHIF port conflict

If Docker reports an error like:

```text
failed to bind host port for 0.0.0.0:3000: address already in use
```

another process is using host port `3000`. Choose another host port for OHIF,
for example `3001`.

Edit `docker/.env`:

```bash
BRN_OHIF_HOST_PORT=3001
BRN_OHIF_PUBLIC_URL=http://127.0.0.1:3001
```

Restart OHIF:

```bash
docker compose -f docker/docker-compose.yml --env-file docker/.env --profile dicom up -d ohif
```

If BRN is running from source, export the same OHIF URL before starting
`uvicorn`:

```bash
export BRN_OHIF_PUBLIC_URL=http://127.0.0.1:3001
```

## Real DICOM data

For real data:

1. Import `.dcm` files into Orthanc or make sure they are available through an institutional DICOMweb endpoint.
2. Extract the Study/Series/SOP Instance UIDs.
3. Add those UIDs to `assays/imaging/dicom_studies.json`.
4. Link each study to the BRN `patient_id`, `sample_id`, and `timepoint`.
5. Add modality/body-part descriptions where useful, for example `modality: "MR"` and `body_part: "BRAIN"` for MS brain MRI.
6. Load the dataset in BRN and open the Assays dashboard.

For multiple-sclerosis projects, keep raw pixels in the DICOMweb archive and use
BRN metadata to connect each study to the patient visit and downstream derived
features. Typical useful study labels are sequence-aware, for example
`Baseline brain MRI FLAIR`, `Follow-up brain MRI T2`, or `Post-contrast T1`.
Derived lesion counts, lesion volumes, scanner parameters, and segmentation
outputs can live in the imaging assay matrix while OHIF remains the pixel
viewer.

## Troubleshooting

- No studies in BRN: check that `dicom_studies.json` exists under the dataset root and that the user has access to that dataset.
- `Open in OHIF` is disabled: set `BRN_DICOM_ENABLED=true`.
- OHIF opens but shows no pixels: confirm the same StudyInstanceUID exists in Orthanc and that OHIF can reach `BRN_DICOMWEB_PUBLIC_URL`.
- Orthanc is unreachable from BRN: check `BRN_ORTHANC_INTERNAL_URL=http://orthanc:8042` when using Docker Compose.
- Browser CORS errors: keep OHIF and Orthanc behind the same local deployment or reverse proxy, or update Orthanc CORS settings for the deployment.
