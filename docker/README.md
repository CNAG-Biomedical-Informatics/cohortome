# Docker deployment

Compose runs the web app, one RQ worker and Redis. Optional Orthanc and OHIF
services provide DICOM viewing. The image includes both synthetic demos,
Python, R and Pheno-Ranker.

## Start

From the repository root:

```bash
cp docker/env.example docker/.env
```

Edit `docker/.env`: replace `COHORTOME_SESSION_SECRET`, review bootstrap users,
and configure any model endpoint. Keep this file private.

```bash
docker compose -f docker/docker-compose.yml --env-file docker/.env up -d --build
```

Open <http://127.0.0.1:8000>. Sign in as an administrator and prepare the selected
dataset's store in **Admin > Data** before loading it.

## Operate

Check services and logs:

```bash
docker compose -f docker/docker-compose.yml --env-file docker/.env ps
docker compose -f docker/docker-compose.yml --env-file docker/.env logs -f web worker
```

After updating the source, repeat the start command to rebuild. To stop:

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

## Configuration guides

The manual **Test Docker deployment** Actions workflow builds on native Linux
amd64 and arm64 runners. It checks login, both synthetic stores, a queued R
analysis and settings persistence after restart. It does not publish images.

- [Web deployment and runtime configuration](../docs-site/docs/admin-guide/starting-and-stopping.md)
- [Accounts and OIDC](../docs-site/docs/admin-guide/local-auth-and-groups.mdx)
- [Datasets and store preparation](../docs-site/docs/admin-guide/datasets-and-access.mdx)
- [Model endpoints and data boundaries](../docs-site/docs/admin-guide/model-providers.mdx)
- [DICOM setup, source-app integration and port conflicts](../docs-site/docs/admin-guide/dicom-viewing.md)
- [Restricted-data security](../docs-site/docs/admin-guide/real-data-security.md)

The bundled Orthanc configuration has authentication disabled. Do not expose it
publicly or use it for restricted images without securing it first.
