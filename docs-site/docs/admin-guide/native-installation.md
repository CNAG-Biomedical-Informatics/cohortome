---
title: Native Uvicorn (advanced)
---

# Native Uvicorn installation

Use this only when managing Python, Perl, R and Redis on the host yourself.
For the standard web setup, use [Docker](./starting-and-stopping).

The native launcher starts Uvicorn and one RQ worker in the same terminal.
Redis remains a separate machine service. This launcher supports Linux and
macOS; use Docker or WSL on Windows.

Install the Python dependencies in your active environment, then copy the
template once from the repository root:

```bash
python3 -m pip install -e .
cp native.env.example native.env
chmod 600 native.env
```

Edit `native.env`. It is ignored by Git and must be readable only by its owner.
For an existing installation, retain its runtime, secret, login settings,
and executable locations. Copy any OIDC and provider settings too. Container
hostnames and executable paths from `docker/.env` usually need changing for
native use. The launcher does not read `docker/.env`.

For a new installation, create a runtime directory explicitly and set its
absolute path as `COHORTOME_RUNTIME_ROOT`. Generate a session secret once with
`python3 -c 'import secrets; print(secrets.token_urlsafe(32))'`. Save that value
as `COHORTOME_SESSION_SECRET`; do not regenerate it at each startup. Configure
the initial administrator as described in [authentication and groups](./local-auth-and-groups).

The file is parsed as literal dotenv data; do not use `source`, shell commands,
`~`, or `$VARIABLE` substitutions in its values. Both processes receive the same
environment. Application settings in the shell (`COHORTOME_*`, `LM_STUDIO_*`,
and `UVICORN_*`) are ignored, so old exports cannot silently change the runtime
or authentication mode. Other shell settings, including R and Perl library
paths, are retained unless replaced in the file. The conventional user-local
`perl5` library is added automatically when `PERL5LIB` is not set in the file.

Start Redis using your machine's service manager. On a systemd Linux host:

```bash
sudo systemctl start redis-server
```

Check the configuration and start:

```bash
make doctor
make start
```

`make start` repeats the checks. Invalid core settings or unavailable Redis
block startup. Missing R packages or Pheno-Ranker dependencies produce warnings;
they do not block browsing. These checks do not validate every external runner
or perform an analysis. The launcher never imports or prepares datasets.

Wait for Uvicorn's startup-complete message and the RQ worker's listening
message. Logs from both processes appear in the terminal. Keep that terminal
open. In another terminal:

```bash
make status
make stop
```

`status` reports whether the managed processes are alive, not whether a job is
running or the worker can still reach Redis. The app's worker indicator checks
RQ availability. `stop` requests graceful shutdown; watch the start terminal
for completion. Active queued jobs may delay shutdown. `Ctrl+C` in the start
terminal has the same effect. Redis is left running. Independently started
Uvicorn processes and systemd services are not managed by these commands.

Open `http://127.0.0.1:8001`. To reach a Linux guest from its macOS host, use
`COHORTOME_HOST=0.0.0.0` in the file and the guest's IP address. Use
`COHORTOME_PORT` to change the port, and keep `COHORTOME_PUBLIC_BASE_URL` and
OIDC redirect settings consistent with the URL users open. Network binding
without authentication is rejected.

Stop before editing the configuration, particularly the runtime directory.
Then run `make start` again. To keep the configuration outside the checkout,
use `make start NATIVE_CONFIG=/absolute/path/native.env` and the same option
for `doctor`, `status`, and `stop`. Use `PYTHON=/path/to/venv/bin/python` when
needed. The checkout's `.deps` directory is also supported.

`make worker` starts only an additional foreground worker using this same file.
It no longer reads `docker/.env`. Stop that standalone worker with `Ctrl+C` in
its own terminal; it is not managed by `make stop`.
