---
title: Security configuration
---

import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

# Security configuration

COHORTome controls access through its application routes. Files and connected
services also need their own access controls.

## Installation access

<Tabs>
<TabItem value="desktop" label="Desktop" default>

Desktop has one local owner and no application login. Use operating-system
accounts, file permissions, and storage encryption to control access to datasets
and saved work. The backend listens on loopback and uses a per-launch cookie.

</TabItem>
<TabItem value="web" label="Web">

For centralized, multi-user deployments:

- Configure [local or OIDC authentication](local-auth-and-groups.mdx).
- Assign dataset access through groups or individual permissions.
- Use HTTPS for browser connections and keep the session secret stable.
- Restrict direct access to storage, Redis, workers, and connected data services.
- Check access using accounts with different dataset permissions.

Application login does not protect services that can be reached independently
of COHORTome.

</TabItem>
</Tabs>

## Dataset and model policies

Dataset visibility determines who can open a dataset. Model-context policy
determines what may be sent to a configured provider.

| Setting | Purpose |
| --- | --- |
| Dataset visibility, groups, and users | Access within a shared Web installation |
| Public/private classification | Whether dataset context may reach an external provider |
| Model-context policy | Detailed context, safe summary, or no dataset context |
| Provider boundary | Whether the endpoint is local or external |

Private dataset context is blocked for external providers. A local provider
can receive it only when dataset policy permits. Set the boundary to match the
actual service; a label does not change where inference runs.

**General question** does not attach workspace records, but sends the user's
question and recent general-question history to the provider.

See [model configuration](model-providers.mdx) for endpoints and policies.

## Files, exports, and backups

Prepared stores, chats, run outputs, exports, and project files can contain
patient information. Apply the source dataset's access and retention rules to
these files and their backups.

Keep research data, runtime state, credentials, and API keys out of source
repositories and public container images. Back up runtime state and source
data separately from application code. A saved project references local data
and results; it is not a backup.

## DICOM services

:::warning[Bundled Orthanc has authentication disabled]

The example Orthanc configuration exposes development ports without
authentication. Use an authenticated, network-restricted DICOMweb service or
proxy before loading restricted images.

:::

COHORTome permissions do not protect a DICOM service exposed through a separate
URL. Configure access on that service and check that direct study requests
respect the intended permissions. Image de-identification and pixel review are
handled outside COHORTome.

See [imaging setup](dicom-viewing.md).

## Background workers

Web workers and Redis may handle sensitive job inputs. Keep them on a protected
network and restrict access to the runtime and job files.

Desktop uses its local queue and does not require Redis. The same file-access
rules apply to its generated results.
