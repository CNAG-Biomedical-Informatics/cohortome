---
sidebar_position: 1
---

# Start the web app

Use Web for a shared server with accounts and dataset permissions. For one
person, use [Desktop](../getting-started/desktop).

## Deploy from Docker Hub

Install Docker with Compose. The prebuilt
[Docker Hub image](https://hub.docker.com/r/manuelrueda/cohortome) supports Linux
amd64 and arm64 and includes the application and analysis runtimes. No local
compilation is needed. Clone the repository for the Compose configuration:

```bash
git clone https://github.com/CNAG-Biomedical-Informatics/cohortome.git
cd cohortome
```

1. Copy the configuration:

   ```bash
   cp docker/env.example docker/.env
   ```

2. Edit `docker/.env` before starting:
   - Set `COHORTOME_IMAGE` to the version to deploy, for example
     `manuelrueda/cohortome:0.1.0`. Web and worker use the same image.
   - Set `COHORTOME_SESSION_SECRET` to a long random value and keep it unchanged.
   - Replace the example users in `COHORTOME_LOCAL_USERS_JSON` with your
     administrator account and a strong password.
   - Leave the LLM and DICOM settings disabled unless you need them.

   Keep this file private. To generate a secret without installing Python:

   ```bash
   docker run --rm python:3.11-slim python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

3. Download the images and start the app, Redis and one background worker:

   ```bash
   docker compose -f docker/docker-compose.yml --env-file docker/.env pull web worker redis
   docker compose -f docker/docker-compose.yml --env-file docker/.env up -d --no-build
   ```

4. Open [COHORTome](http://127.0.0.1:8000) and sign in with the administrator account.
   In **Admin > Data**, prepare a demo dataset's store. Select it in
   **Datasets** and apply the workspace.

:::warning[Before sharing the server]

Replace all example passwords. For access beyond a trusted local machine,
configure HTTPS and appropriate network restrictions; see
[deployment security](./real-data-security).
Compose publishes port 8000 on the host. Set `COHORTOME_PUBLIC_BASE_URL` to the
address users will open and put shared deployments behind an HTTPS reverse proxy.

:::

## Stop or update

Stop without deleting saved work:

```bash
docker compose -f docker/docker-compose.yml --env-file docker/.env down
```

To update, back up your data, change `COHORTOME_IMAGE` to the desired version,
then repeat the pull and start commands above. Prefer an explicit version over
`latest`. After editing `docker/.env`, use `up -d --no-build` again; `restart`
alone does not apply new settings. Keep the same checkout location/Compose
project name so the existing named volumes are reused.

The named volumes hold accounts, cohorts, chats, stores and results. Back them
up along with the source datasets. **Do not add `--volumes` or `-v` to
`down` unless you intend to delete this state.**

<details>
<summary>Check services and logs</summary>

```bash
docker compose -f docker/docker-compose.yml --env-file docker/.env ps
docker compose -f docker/docker-compose.yml --env-file docker/.env logs --tail=50 web worker redis
```

If workers show Offline, check that both Redis and the worker are running.
If saved work disappears, check that you are using the same runtime volume
and COHORTome account.

</details>

## Build from source instead

For development, set `COHORTOME_IMAGE=cohortome:local` in `docker/.env`:

```bash
docker compose -f docker/docker-compose.yml --env-file docker/.env build web
docker compose -f docker/docker-compose.yml --env-file docker/.env up -d --no-build
```

Web and worker share the resulting image. Repeat these commands after updating
the source.

## Next steps

- [Manage accounts](./local-auth-and-groups)
- [Add datasets and grant access](./datasets-and-access)
- [Connect an LLM](./model-providers)

OHIF is embedded in the app. **Orthanc storage is optional** and is not started
by the normal command. See [Imaging setup](./dicom-viewing) for local files or
the optional `dicom` storage profile.

[Native Uvicorn](./native-installation) and
[institutional sign-in (OIDC)](./institutional-sign-in) are alternative,
advanced setup guides—not prerequisites for Docker.
