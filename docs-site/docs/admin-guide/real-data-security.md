# Real-Data Security

:::danger[Do not use the development stack for unrestricted patient data]
The bundled configuration is designed for synthetic local development. Real
PRECISESADS, 3TR, or DICOM data requires an institutionally reviewed deployment
with protected services and approved data handling.
:::

## Trust boundaries

COHORTome authorization protects application routes and controls which datasets are
available in a user's workspace. Every external data or model service must also
enforce an appropriate boundary:

- reverse proxy or network gateway
- institutional identity and authorization
- encrypted transport
- protected persistent volumes or managed storage
- backup and retention policy
- access and analysis logging

Application login alone does not secure a directly exposed database, DICOMweb
archive, model server, Redis instance, or filesystem mount.

## Before registering real datasets

1. Confirm the legal basis, data-use agreement, and approved user population.
2. Keep source data outside Git and outside public container images.
3. Map project identifiers to the minimum identifiers needed by COHORTome.
4. Validate patient, sample, visit, time-point, and assay linkage.
5. Configure dataset groups, disclosure level, and AI-provider policy.
6. Protect prepared stores, generated artifacts, backups, and logs.
7. Test access with an authorized user and a deliberately unauthorized user.
8. Define deletion, retention, and incident-response procedures.

## DICOM warning

The repository's Orthanc configuration enables remote access, disables Orthanc
authentication, and exposes development ports through Docker Compose. This is
appropriate only for the public synthetic smoke fixtures.

For real imaging:

- prefer an approved institutional PACS or authenticated DICOMweb service
- otherwise place Orthanc and OHIF behind an authenticated reverse proxy
- do not publish DICOM or DICOMweb ports directly
- de-identify headers and pixel data according to the approved protocol
- audit pixel access independently of COHORTome metadata access
- verify that an OHIF URL cannot retrieve a study outside the user's allowed
  data scope

See [DICOM Viewing](./dicom-viewing) for the local development workflow.

## LLM and model servers

- expose only administrator-approved endpoints
- prefer local or institutionally controlled providers for restricted data
- use dataset `safe_summary` or `blocked` policy when detailed context is not
  approved
- keep secrets outside provider JSON committed to Git
- record provider/model identity for evaluated or published outputs
- test behavior when the provider is unavailable or policy changes

## Redis, workers, and artifacts

Redis and workers participate in the analysis trust boundary. Restrict their
network access and protect job payloads. Generated bundles may contain cohort
IDs, clinical tables, assay matrices, logs, or plots and must follow the same
classification and retention policy as their source data.

## Repository safety

Never commit:

- restricted PRECISESADS or 3TR exports
- real patient records or DICOM pixels
- passwords, session secrets, OIDC client secrets, or model API keys
- prepared stores or run bundles containing restricted material
- local user databases or password-reset tokens
