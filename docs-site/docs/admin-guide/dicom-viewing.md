---
sidebar_position: 4
---

# DICOM Viewing

COHORTome can launch DICOM studies in OHIF while keeping pixel storage in Orthanc or another DICOMweb service. This integration is optional and disabled by default.

:::danger Local development only
The bundled Orthanc configuration disables authentication and exposes
development ports. Use it only with the public synthetic fixtures. Before using
real patient images, read [Real-Data Security](./real-data-security) and deploy
an authenticated, network-restricted institutional DICOMweb service or reverse
proxy.
:::

## Runtime services

The Docker deployment includes an optional `dicom` profile:

- `orthanc`: DICOM storage and DICOMweb endpoint
- `ohif`: browser viewer
- `web`: COHORTome, which lists authorized studies and creates OHIF launch URLs

In this deployment mode, OHIF and Orthanc run as separate services.

## Bundled viewer prototype

The source app also has a local OHIF prototype for the bundled default synthetic
dataset. Prepare its browser assets once with:

```bash
python3 scripts/dicom/prepare_bundled_viewer.py
```

This extracts a pinned OHIF image into ignored `runtime/ohif`. Docker is needed
for this preparation step, not for viewing images afterwards. With these assets
present, Dashboard → Imaging offers **View images** for the default synthetic
studies. The viewer opens over the workspace; **Close viewer** returns to it.
Each study has one viewing action: it prefers the bundled viewer when available
for that study; otherwise it uses the enabled external OHIF configuration. It
does not automatically retry a failed local request against an external service.

Metadata and pixel requests use COHORTome's authentication, dataset authorization
and Detailed-access checks on every request. Patient responses are marked
`no-store`; the OHIF service worker is disabled and the viewer's network policy
blocks external connections. Previously displayed pixels cannot be recalled from
a user's screen when access is revoked. This prototype deliberately rejects
other dataset roots and is not ready for restricted images.

The extracted assets occupy about 115 MiB, including about 96 MiB under the ONNX
runtime directory. This is not an installer-size measurement. The current pinned
Docker build needs asset-path adaptation to run below `/local-viewer`; a release
should build OHIF for that path directly. Desktop WebKit rendering, installer
packaging, upstream licence and dependency notices, and additional imaging
formats still need verification before distribution. No optional-download
manager is being introduced.

## Enable local DICOM viewing

Edit `docker/.env`:

```bash
COHORTOME_DICOM_ENABLED=true
COHORTOME_OHIF_HOST_PORT=3000
COHORTOME_OHIF_PUBLIC_URL=http://127.0.0.1:3000
COHORTOME_DICOMWEB_PUBLIC_URL=http://127.0.0.1:8042/dicom-web
COHORTOME_ORTHANC_INTERNAL_URL=http://orthanc:8042
COHORTOME_ORTHANC_USERNAME=
COHORTOME_ORTHANC_PASSWORD=
```

Start the stack with the DICOM profile:

```bash
docker compose -f docker/docker-compose.yml --env-file docker/.env --profile dicom up -d --build
```

Open:

```text
COHORTome:     http://127.0.0.1:8000
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
assign COHORTome-specific Study/Series/SOP Instance UIDs, patient IDs, sample IDs,
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

Each dataset exposes DICOM studies to COHORTome through:

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

In COHORTome:

1. Load a dataset.
2. Open `Dashboard`.
3. Open the `Assays` dashboard view.
4. Find `DICOM imaging`.
5. Click `Open in OHIF`.

COHORTome only lists studies from datasets the current user can access. OHIF then loads pixels through the configured DICOMweb endpoint.

In the bundled Docker setup, OHIF proxies `/dicom-web/` and `/wado` to Orthanc
inside Docker. Browser requests therefore stay on the OHIF origin and avoid
local CORS failures.

## Run COHORTome from source with Docker DICOM services

For local development, run only Orthanc and OHIF in Docker and run COHORTome from the source checkout.

Start the DICOM services:

```bash
docker compose -f docker/docker-compose.yml --env-file docker/.env --profile dicom up -d orthanc ohif
```

Generate and import the bundled synthetic DICOM files:

```bash
PYTHONPATH=.deps python3 scripts/dicom/generate_synthetic_dicom.py
python3 scripts/dicom/import_to_orthanc.py default_dataset/assays/imaging/dicom --orthanc-url http://127.0.0.1:8042
```

Start COHORTome from source:

```bash
export COHORTOME_AUTH_MODE=local
export COHORTOME_SESSION_SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"

export COHORTOME_DICOM_ENABLED=true
export COHORTOME_OHIF_PUBLIC_URL=http://127.0.0.1:3000
export COHORTOME_DICOMWEB_PUBLIC_URL=http://127.0.0.1:8042/dicom-web
export COHORTOME_ORTHANC_INTERNAL_URL=http://127.0.0.1:8042

PYTHONPATH=.deps uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

When COHORTome runs from source on the host, `COHORTOME_ORTHANC_INTERNAL_URL` must point to
`http://127.0.0.1:8042`. Use `http://orthanc:8042` only when COHORTome itself is
running inside the Docker Compose network.

Open `http://127.0.0.1:8000`, then go to `Dashboard -> Imaging`.

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
COHORTOME_OHIF_HOST_PORT=3001
COHORTOME_OHIF_PUBLIC_URL=http://127.0.0.1:3001
```

Restart OHIF:

```bash
docker compose -f docker/docker-compose.yml --env-file docker/.env --profile dicom up -d ohif
```

If COHORTome is running from source, export the same OHIF URL before starting
`uvicorn`:

```bash
export COHORTOME_OHIF_PUBLIC_URL=http://127.0.0.1:3001
```

## Real DICOM data

The steps below describe linkage only. They do not make the bundled Docker
services suitable for restricted data. Complete the security controls in
[Real-Data Security](./real-data-security) first.

For an approved real-data deployment:

1. Import `.dcm` files into Orthanc or make sure they are available through an institutional DICOMweb endpoint.
2. Extract the Study/Series/SOP Instance UIDs.
3. Add those UIDs to `assays/imaging/dicom_studies.json`.
4. Link each study to the COHORTome `patient_id`, `sample_id`, and `timepoint`.
5. Add modality/body-part descriptions where useful, for example `modality: "MR"` and `body_part: "BRAIN"` for MS brain MRI.
6. Load the dataset in COHORTome and open the Assays dashboard.

For multiple-sclerosis projects, keep raw pixels in the DICOMweb archive and use
COHORTome metadata to connect each study to the patient visit and downstream derived
features. Typical useful study labels are sequence-aware, for example
`Baseline brain MRI FLAIR`, `Follow-up brain MRI T2`, or `Post-contrast T1`.
Derived lesion counts, lesion volumes, scanner parameters, and segmentation
outputs can live in the imaging assay matrix while OHIF remains the pixel
viewer.

## Troubleshooting

- No studies in COHORTome: check that `dicom_studies.json` exists under the dataset root and that the user has access to that dataset.
- `Open in OHIF` is disabled: set `COHORTOME_DICOM_ENABLED=true`.
- OHIF opens but shows no pixels: confirm the same StudyInstanceUID exists in Orthanc and that OHIF can reach `COHORTOME_DICOMWEB_PUBLIC_URL`.
- Orthanc is unreachable from COHORTome: check `COHORTOME_ORTHANC_INTERNAL_URL=http://orthanc:8042` when using Docker Compose.
- Browser CORS errors: keep OHIF and Orthanc behind the same local deployment or reverse proxy, or update Orthanc CORS settings for the deployment.
