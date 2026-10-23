---
sidebar_position: 4
title: Imaging setup
---

# Imaging setup

**OHIF displays images. Orthanc stores images.** COHORTome links studies to
dataset patients and checks access before serving metadata or pixels.
Images are not stored in DuckDB.

| Deployment | Image sources |
| --- | --- |
| Desktop | Local DICOM files |
| Web | Server-side DICOM files, or a configured Orthanc/DICOMweb archive |

OHIF opens inside COHORTome. A separate OHIF container is not required.

## Link a DICOM folder

1. Load the dataset containing the patients.
2. Open **Admin > Data** (**Data** in Desktop), expand the dataset and choose
   **Imaging > Link folder**. Browse the linked studies under **Dashboard > Imaging**.
3. Choose the dataset and folder. Desktop provides a native folder picker;
   Web requires a path accessible to the server.
4. Choose **Validate and link**, then **View images** beside a study.

DICOM `PatientID` must exactly match the dataset's patient ID. Unmatched
patients, duplicate instance UIDs and symbolic links are rejected. COHORTome
does not guess patient mappings or anonymize files.

Files remain in their original folder. The protected runtime stores an index,
not a copy of the images. Linking another folder replaces the previous links
for that dataset without deleting files. If files change or move, relink them.
Back up both the original image folder and the COHORTome runtime.

This path requires Detailed dataset access; only the desktop owner or a Web
administrator can link folders. The runtime must be outside the source checkout.
For Docker, mount any image directory read-only at a server path before linking it.

## Web: use Orthanc instead

If an institution already has an archive, use it rather than creating another
copy. The current embedded integration requires DICOMweb metadata and WADO-URI
image retrieval, both provided by Orthanc.

For the optional local Orthanc service, edit `docker/.env`:

```dotenv
COHORTOME_DICOM_ENABLED=true
COHORTOME_ORTHANC_INTERNAL_URL=http://orthanc:8042
```

Then start the storage profile:

```bash
docker compose -f docker/docker-compose.yml --env-file docker/.env --profile dicom up -d --build
```

The profile adds **Orthanc only**. Its named volume keeps the image archive.
The host ports bind to loopback. Do not delete the volume when stopping.

:::warning[Configure security before using restricted images]

The supplied Orthanc configuration has authentication disabled for local
synthetic testing. Configure authentication, HTTPS where applicable, restricted
network access and backups before using real data. Do not expose its API or
DICOM ports publicly. See [deployment security](./real-data-security).

:::

For an existing archive, configure its server-accessible URL and credentials:

```dotenv
COHORTOME_DICOM_ENABLED=true
COHORTOME_DICOMWEB_INTERNAL_URL=https://archive.example.org/dicom-web
COHORTOME_WADO_INTERNAL_URL=https://archive.example.org/wado
COHORTOME_ORTHANC_USERNAME=your-service-account
COHORTOME_ORTHANC_PASSWORD=your-service-password
```

Credentials stay on the backend. COHORTome checks Detailed dataset access on
every image request, and verifies the archive's patient/study identifiers.
Desktop does not enable remote archive access.

<details>
<summary>Link archive studies to a dataset</summary>

Supply `assays/imaging/dicom_studies.json` in the dataset package:

```json
{
  "version": 1,
  "studies": [{
    "study_id": "baseline-mri",
    "patient_id": "P001",
    "timepoint": "Baseline",
    "modality": "MR",
    "study_instance_uid": "1.2.3.4",
    "label": "Baseline brain MRI"
  }]
}
```

Use actual archive identifiers and a matching patient ID; the values above are
illustrative. Optional `series` entries provide `series_instance_uid`,
`instance_count` and `sop_instance_uids` for the dashboard inventory.
A linked local folder takes precedence over the archive for that dataset.

</details>

## Viewer assets and current limits

The Docker image includes pinned OHIF static assets. For a source preview,
prepare them once:

```bash
python3 scripts/dicom/prepare_bundled_viewer.py
```

That development script uses Docker to extract the assets, not to run the
viewer. Desktop packaging accepts `--ohif-assets /path/to/reviewed/assets`.
Existing test bundles without those assets do not gain a viewer automatically.

Local and remote metadata/pixel requests are marked `no-store`, and offline
viewer caching is disabled. Previously displayed pixels cannot be recalled
from a user's screen.

The local path has been tested with a synthetic multi-instance MR series in
Linux WebKitGTK. This is not validation of every DICOM object type, transfer
syntax, 3D tool or operating system. Linux Desktop uses software rendering;
clinical interpretation and anonymization are outside COHORTome's scope.
