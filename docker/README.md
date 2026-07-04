# Biomedical Research Navigator Docker Deployment

This directory contains the pilot Docker deployment path for Biomedical Research Navigator.

It is intended for a single VM with synthetic data and a small group of test
users. It runs:

- FastAPI web app
- one RQ analysis worker
- Redis for background jobs
- optional Orthanc and OHIF services for DICOM viewing

## Files

- `Dockerfile` builds the app image with Python, R, and the R packages needed by
  the molecular workflows.
- `docker-compose.yml` runs `web`, `worker`, and `redis`.
- `env.example` documents the runtime configuration.
- `orthanc/orthanc.json` and `ohif/app-config.js` configure optional DICOM
  services when the `dicom` Compose profile is enabled.

## First Run

From the repository root:

```bash
cp docker/env.example docker/.env
```

Edit `docker/.env` before starting:

- replace `BRN_SESSION_SECRET`
- decide whether to keep the bootstrap users
- configure `LM_STUDIO_*` or `BRN_LLM_PROVIDERS_JSON` if an LLM endpoint is available

Start the stack:

```bash
docker compose -f docker/docker-compose.yml --env-file docker/.env up --build
```

Open:

```text
http://127.0.0.1:8000
```

Run in the background:

```bash
docker compose -f docker/docker-compose.yml --env-file docker/.env up -d --build
```

Stop:

```bash
docker compose -f docker/docker-compose.yml --env-file docker/.env down
```

## Persistent Paths

The Compose file mounts these host paths into the containers:

- `state/` -> local users, settings, saved cohorts, jobs, dataset registry
- `.cache/` -> DuckDB query stores
- `runs/` -> generated Pheno-Ranker and analysis artifacts
- `default_dataset/`, `private_dataset/`, `dataset-large/` -> read-only datasets

Back up at least:

```text
state/
.cache/query-store/
runs/
```

## Dataset Stores

User workspace loading expects selected dataset stores to be prepared. For the
pilot, sign in as an admin and prepare stores from `Data Administration`.

The default dataset should be prepared before users test the app. Large datasets
can be prepared later if the pilot includes molecular timing or workflow tests.

## Background Jobs

The `worker` service processes the `analysis` queue:

```bash
docker compose -f docker/docker-compose.yml --env-file docker/.env logs -f worker
```

The pilot default is one worker. That means several users can submit jobs, but
heavy workflows run one at a time. Increase worker replicas only after measuring
RAM and CPU usage:

```bash
docker compose -f docker/docker-compose.yml --env-file docker/.env up -d --scale worker=2
```

## Pheno-Ranker

Pheno-Ranker is installed in the image from CPAN as `Pheno::Ranker`. The
container expects:

```text
/usr/local/bin/pheno-ranker
```

Override `BRN_PHENO_RANKER_BIN` only if you build a custom image or mount a
different binary for development.

## DICOM Viewing

DICOM viewing is optional. Enable it in `docker/.env`:

```bash
BRN_DICOM_ENABLED=true
BRN_OHIF_PUBLIC_URL=http://127.0.0.1:3000
BRN_DICOMWEB_PUBLIC_URL=http://127.0.0.1:8042/dicom-web
BRN_ORTHANC_INTERNAL_URL=http://orthanc:8042
```

Start the DICOM services with the Compose profile:

```bash
docker compose -f docker/docker-compose.yml --env-file docker/.env --profile dicom up -d --build
```

Import local DICOM files into Orthanc:

```bash
PYTHONPATH=.deps python3 scripts/dicom/generate_synthetic_dicom.py
python3 scripts/dicom/import_to_orthanc.py default_dataset/assays/imaging/dicom --orthanc-url http://127.0.0.1:8042
```

Dataset roots expose studies to BRN through
`assays/imaging/dicom_studies.json`. The file stores Study/Series/SOP Instance
UIDs and sample linkage only; DICOM pixels stay in Orthanc or another DICOMweb
service.

## LLM Providers

For one local OpenAI-compatible endpoint:

```bash
LM_STUDIO_ENABLED=true
LM_STUDIO_BASE_URL=http://host.docker.internal:1234/v1
LM_STUDIO_MODEL=openai/gpt-oss-120b
```

For several approved endpoints, use `BRN_LLM_PROVIDERS_JSON` or
`BRN_LLM_PROVIDERS_FILE`. Users can then choose an approved provider in Settings.
Dataset policy still controls whether clinical context can be sent to a model.

## Local Auth

The first boot can seed users from `BRN_LOCAL_USERS_JSON`.

After `state/auth/users.json` exists, that file is the source of truth. Manage
users in the `Users` admin tab.

For a controlled synthetic-data pilot, local auth is simpler than OIDC. Add OIDC
only when you need institutional identity integration.

## Updating

```bash
git pull
docker compose -f docker/docker-compose.yml --env-file docker/.env up -d --build
```

## Troubleshooting

Check service state:

```bash
docker compose -f docker/docker-compose.yml --env-file docker/.env ps
```

Read web logs:

```bash
docker compose -f docker/docker-compose.yml --env-file docker/.env logs -f web
```

Read Redis logs:

```bash
docker compose -f docker/docker-compose.yml --env-file docker/.env logs -f redis
```

If the app says a dataset store is stale or not ready, sign in as admin and use
`Data Administration` to prepare or rebuild the store.
