# COHORTome Docker Deployment

This directory contains the pilot Docker deployment path for COHORTome.

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

- replace `COHORTOME_SESSION_SECRET`
- decide whether to keep the bootstrap users
- configure `LM_STUDIO_*` or `COHORTOME_LLM_PROVIDERS_JSON` if an LLM endpoint is available

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

The Compose file mounts one mutable host directory into the containers:

- `runtime/` -> local users, settings, dataset registry, DuckDB stores, and generated runs
- `default_dataset/`, `private_dataset/`, `dataset-large/` -> read-only datasets

Back up:

```text
runtime/
```

Inside the container, `COHORTOME_RUNTIME_ROOT=/var/lib/cohortome`. Both the web
process and worker use that same root.

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

Override `COHORTOME_PHENO_RANKER_BIN` only if you build a custom image or mount a
different binary for development.

## DICOM Viewing

DICOM viewing is optional. Enable it in `docker/.env`:

```bash
COHORTOME_DICOM_ENABLED=true
COHORTOME_OHIF_HOST_PORT=3000
COHORTOME_OHIF_PUBLIC_URL=http://127.0.0.1:3000
COHORTOME_DICOMWEB_PUBLIC_URL=http://127.0.0.1:8042/dicom-web
COHORTOME_ORTHANC_INTERNAL_URL=http://orthanc:8042
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

Dataset roots expose studies to COHORTome through
`assays/imaging/dicom_studies.json`. The file stores Study/Series/SOP Instance
UIDs and sample linkage only; DICOM pixels stay in Orthanc or another DICOMweb
service.

The OHIF container proxies `/dicom-web/` and `/wado` to the Orthanc service
inside Docker. OHIF therefore loads pixels through its own origin, avoiding
browser CORS problems during local development.

### Source app with Docker DICOM services

During source development, run only the DICOM services in Docker and run COHORTome
with `uvicorn` on the host:

```bash
docker compose -f docker/docker-compose.yml --env-file docker/.env --profile dicom up -d orthanc ohif
```

Generate and import the bundled synthetic DICOM files:

```bash
PYTHONPATH=.deps python3 scripts/dicom/generate_synthetic_dicom.py
python3 scripts/dicom/import_to_orthanc.py default_dataset/assays/imaging/dicom --orthanc-url http://127.0.0.1:8042
```

Start COHORTome from source. Because COHORTome is running on the host, use
`127.0.0.1` for Orthanc instead of the Docker service name `orthanc`:

```bash
export COHORTOME_AUTH_MODE=local
export COHORTOME_SESSION_SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
export COHORTOME_RUNTIME_ROOT="$PWD/runtime"

export COHORTOME_DICOM_ENABLED=true
export COHORTOME_OHIF_PUBLIC_URL=http://127.0.0.1:3000
export COHORTOME_DICOMWEB_PUBLIC_URL=http://127.0.0.1:8042/dicom-web
export COHORTOME_ORTHANC_INTERNAL_URL=http://127.0.0.1:8042

PYTHONPATH=.deps uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Open `http://127.0.0.1:8000`, then go to `Dashboard -> Assays -> DICOM imaging`.

To verify that OHIF is rendering pixels instead of a black/blank viewport:

```bash
PYTHONPATH=.deps python3 scripts/dicom/check_ohif_render.py \
  "http://127.0.0.1:3001/viewer?StudyInstanceUIDs=1.2.826.0.1.3680043.10.54321.1.1"
```

### OHIF port already in use

If Docker reports:

```text
failed to bind host port for 0.0.0.0:3000: address already in use
```

another process is already using host port `3000`. Use another host port for
OHIF, for example `3001`.

Edit `docker/.env`:

```bash
COHORTOME_OHIF_HOST_PORT=3001
COHORTOME_OHIF_PUBLIC_URL=http://127.0.0.1:3001
```

Restart OHIF:

```bash
docker compose -f docker/docker-compose.yml --env-file docker/.env --profile dicom up -d ohif
```

If COHORTome is running from source, export the matching OHIF URL before starting
`uvicorn`:

```bash
export COHORTOME_OHIF_PUBLIC_URL=http://127.0.0.1:3001
```

## LLM Providers

For one local OpenAI-compatible endpoint:

```bash
LM_STUDIO_ENABLED=true
LM_STUDIO_BASE_URL=http://host.docker.internal:1234/v1
LM_STUDIO_MODEL=openai/gpt-oss-120b
```

For several approved endpoints, use `COHORTOME_LLM_PROVIDERS_JSON` or
`COHORTOME_LLM_PROVIDERS_FILE`. Users can then choose an approved provider in Settings.
Dataset policy still controls whether clinical context can be sent to a model.

## Local Auth

The first boot can seed users from `COHORTOME_LOCAL_USERS_JSON`.

After `runtime/state/auth/users.json` exists, that file is the source of truth.
Manage users in the `Users` admin tab.

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
