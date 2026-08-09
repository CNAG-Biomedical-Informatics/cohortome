# Development Dex Provider

This directory contains a local Dex OpenID Connect provider for COHORTome
development.

Start Dex from the repository root:

```bash
docker compose -f scripts/dev/docker-compose.dex.yml up
```

Then start COHORTome with OIDC auth:

```bash
export COHORTOME_AUTH_MODE=oidc
export COHORTOME_OIDC_PROVIDER_NAME=Dex
export COHORTOME_OIDC_ISSUER=http://127.0.0.1:5556/dex
export COHORTOME_OIDC_CLIENT_ID=cohortome
export COHORTOME_OIDC_CLIENT_SECRET=cohortome-secret
export COHORTOME_OIDC_REDIRECT_URI=http://127.0.0.1:8000/auth/oidc/callback
export COHORTOME_AUTH_LOCAL_FALLBACK=true
export COHORTOME_SESSION_SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
PYTHONPATH=.deps uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Dev login:

- email: `manuel.rueda@cnag.eu`
- password: `password`

COHORTome still uses `state/auth/users.json` for authorization. The Dex
email must match an enabled local COHORTome user email, or the login is
rejected after the OIDC callback.
