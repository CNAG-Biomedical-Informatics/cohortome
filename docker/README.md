# Docker deployment

Compose runs the web app, one RQ worker and Redis. OHIF is embedded in the app;
the optional Orthanc service supplies image storage. The image includes both
synthetic demos, Python, R and Pheno-Ranker.

## Start

Install Docker with Compose. Clone the repository for its deployment files:

```bash
git clone https://github.com/CNAG-Biomedical-Informatics/cohortome.git
cd cohortome
cp docker/env.example docker/.env
```

Edit `docker/.env`: replace `COHORTOME_SESSION_SECRET`, review bootstrap users,
replace all example users/passwords, and configure any model endpoint. Keep this
file private. `COHORTOME_IMAGE` selects the Docker Hub version for web and worker.

```bash
docker compose -f docker/docker-compose.yml --env-file docker/.env pull web worker redis
docker compose -f docker/docker-compose.yml --env-file docker/.env up -d --no-build
```

Open <http://127.0.0.1:8000> and sign in as your administrator. Docker selects the
amd64 or arm64 image for the host. See the [web guide](../docs-site/docs/admin-guide/starting-and-stopping.md)
for dataset setup and HTTPS/network precautions before sharing the server.

## Operate

Check services and logs:

```bash
docker compose -f docker/docker-compose.yml --env-file docker/.env ps
docker compose -f docker/docker-compose.yml --env-file docker/.env logs -f web worker
```

To update, back up the runtime volume, change `COHORTOME_IMAGE` in `docker/.env`
to the desired version, then repeat the pull and start commands. To stop:

```bash
docker compose -f docker/docker-compose.yml --env-file docker/.env down
```

The default worker runs one background job at a time. After checking available
RAM and CPU, increase capacity with:

```bash
docker compose -f docker/docker-compose.yml --env-file docker/.env up -d --scale worker=2
```

## Persistent data

The `cohortome-runtime` named volume holds users, settings, registrations,
prepared stores and results at `/var/lib/cohortome`, shared by web and worker.
Stopping with `down` preserves it; **do not add `--volumes` unless deleting
that state is intentional**.

Back up the volume and source datasets. Restricted data must stay outside the
repository and Docker build context. Any replacement bind mount must use a
protected host location outside the checkout. Test-only fixtures are not installed.

## Build from source instead

Set `COHORTOME_IMAGE=cohortome:local` in `docker/.env`, then run:

```bash
docker compose -f docker/docker-compose.yml --env-file docker/.env build web
docker compose -f docker/docker-compose.yml --env-file docker/.env up -d --no-build
```

Both web and worker use that locally built image.

## Configuration guides

The manual **Test Docker deployment** Actions workflow builds on native Linux
amd64 and arm64 runners. It checks login, both synthetic stores, Pheno-Ranker,
a queued R analysis and settings persistence after restart. It does not publish images.

Run **Publish Docker release** manually with the same annotated tag as desktop.
Both native architectures must pass before the versioned image is published to
Docker Hub; no published GitHub release is required. Leave `update_latest` off
while testing. Enable it only for a published GitHub release to also update
`latest`. Pushing a Git tag alone does nothing.

- [Web deployment and runtime configuration](../docs-site/docs/admin-guide/starting-and-stopping.md)
- [Accounts and OIDC](../docs-site/docs/admin-guide/local-auth-and-groups.mdx)
- [Datasets and store preparation](../docs-site/docs/admin-guide/datasets-and-access.mdx)
- [Model endpoints and data boundaries](../docs-site/docs/admin-guide/model-providers.mdx)
- [DICOM setup, source-app integration and port conflicts](../docs-site/docs/admin-guide/dicom-viewing.md)
- [Restricted-data security](../docs-site/docs/admin-guide/real-data-security.md)

The bundled Orthanc configuration has authentication disabled. Do not expose it
publicly or use it for restricted images without securing it first.
