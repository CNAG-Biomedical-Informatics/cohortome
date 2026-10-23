---
title: Institutional sign-in (OIDC)
---

# Institutional sign-in (OIDC)

**Optional, Web only.** Use this when your institution requires single sign-on.
Otherwise, keep [local accounts](./local-auth-and-groups).

OIDC verifies identity. COHORTome still controls roles, groups and dataset
permissions. Users must already have enabled COHORTome accounts; provider login
does not automatically create them.

## Configure

Ask your identity-service administrator to register COHORTome as an OIDC client.
Add these settings to the deployment's private environment file:

```dotenv
COHORTOME_AUTH_MODE=oidc
COHORTOME_OIDC_PROVIDER_NAME=Institutional sign-in
COHORTOME_OIDC_ISSUER=https://identity.example.org
COHORTOME_OIDC_CLIENT_ID=your-client-id
COHORTOME_OIDC_CLIENT_SECRET=your-client-secret
COHORTOME_OIDC_REDIRECT_URI=https://cohortome.example.org/auth/oidc/callback
COHORTOME_PUBLIC_BASE_URL=https://cohortome.example.org
```

The callback must exactly match the URL registered with the provider.
Each COHORTome account must match the provider's identity by
`external_subject` or email. SAML or LDAP services need an OIDC bridge.

Apply the configuration to both web and worker services. With Docker, use
`docker compose ... up -d`, not just `restart`.

## Changing an existing installation

1. Back up the runtime and configuration.
2. Keep the runtime directory, session secret and existing usernames.
3. Check each account's email or external subject against the new provider.
4. If your policy permits, set `COHORTOME_AUTH_LOCAL_FALLBACK=true` temporarily
   and verify that an administrator has a working local password.
5. Test OIDC in a separate browser session. Confirm the username, dataset access
   and existing saved work before disabling temporary fallback.

Returning to local login requires a local password on the **same** account.
Editing bootstrap settings does not update an existing user database.

For local development only, see the
[Dex example](https://github.com/CNAG-Biomedical-Informatics/cohortome/blob/main/scripts/dev/README.md).
