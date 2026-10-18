---
title: Query disclosure
---

# Query disclosure

Two policies apply independently: what a user can see in COHORTome, and what
context a model can receive. For a workspace with several datasets, the most
restrictive selected policy applies.

## Results shown to the user

| Response detail | Available results and actions |
| --- | --- |
| Summary | Counts, boolean answers, and permitted grouped summaries; no patient IDs or record rows |
| Detailed | Patient/record tables and, when available, cohort, export, and analysis actions |

Dataset policy sets the level. Query displays it as read-only state.
Summary responses remove row-level payloads and disable patient lookup,
cohort saving, ID transfer, and previous-result scope.

Detailed access still requires authorization for the dataset. A count answer
does not include member IDs or cohort actions simply because Detailed access
is allowed.

## Context sent to a model

| Model policy | Behaviour |
| --- | --- |
| Detailed allowed | Permitted dataset context may be sent |
| Safe summary | Only structural, non-clinical context; no patient-derived summaries |
| Blocked | No workspace context is sent |

:::note[Safe summary is not an aggregate clinical summary]

In Query, this mode skips semantic planning and excludes diseases, treatments,
counts, and top terms from provider context.

:::

Private dataset context is blocked for external providers, regardless of the
configured context ceiling. With a local provider, the dataset's model policy
applies. See [Model configuration](../admin-guide/model-providers.mdx).

A reply can therefore show **Response detail: Detailed** and
**Model context: Safe summary**: the user saw local record detail that was not
sent to the model. These labels are separate from **Deterministic** or
**LLM-planned**, which describe how the operation ran.

## General questions

**General question** calls `POST /llm/general` with the prompt and recent
general-question history. It does not resolve or attach the active workspace,
and cannot return cohort actions. The UI shows **No workspace context**.

The text the user types is still sent to the selected provider.

## Result actions and pagination

The backend supplies available actions; the frontend does not infer membership
from the reply text.

Detailed lists return one page and an opaque, user-scoped result handle.
The complete ordered membership stays server-side. Paging and transfer actions
recheck dataset authorization, workspace/source fingerprints, and Detailed access.

- Default page: 50 rows; API maximum: 100.
- Result lifetime: one hour, unless invalidated by a workspace or source change.
- **Save cohort**, **Open in Analysis**, and previous-result scope use the handle,
  not a client-supplied bulk ID list.

<details>
<summary>Response fields</summary>

| Field | Meaning |
| --- | --- |
| `granularity_requested` | Level derived from workspace policy |
| `granularity_applied` | Level applied to this result |
| `available_actions` | Backend-authorized actions |
| `ai_provider_access` | Effective model-context policy |
| `ai_provider_context_granularity` | Allowed context level for a provider call |
| `external_llm_allowed` | Whether the response permits external model use |

See the [OpenAPI reference](/api/) for endpoint schemas.

</details>
