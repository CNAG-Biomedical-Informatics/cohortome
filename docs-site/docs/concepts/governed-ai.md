# Governed AI

Here, governance means the rules for who can use a model and what data it may receive.

A language model can help a researcher express a question or understand a
result. COHORTome checks what data may be used, limits what may be sent, and remains
responsible for running the requested operation.

## Supported roles

COHORTome uses approved models to assist with:

- turning a research question into a query or analysis plan you can inspect
- explaining available data, overlap, and missingness
- interpreting deterministic or curated analysis results
- suggesting follow-up questions without silently expanding the data scope
- answering explicitly selected general-knowledge questions without attaching
  workspace context

A deployment or dataset may disable model access. Supported deterministic
queries and analyses remain available.

## Execution modes

| Mode | Role |
| --- | --- |
| Deterministic | Structured application logic queries data or computes a known result directly. |
| LLM planner | A model turns the question into a supported operation. COHORTome checks the operation and runs it. |
| LLM interpretation | A model explains bounded context or outputs produced by deterministic or curated methods. |
| Curated runner | Reviewed backend code launches a declared statistical or workflow implementation. |

The interface should report the mode used. An unavailable or disallowed model
must not be hidden by silently switching to an unrelated mode.

## Workspace and General question contexts

The user chooses the model context before sending a question:

| Context | What COHORTome sends |
| --- | --- |
| Workspace | Only the authorized workspace context allowed by dataset and provider policy, plus the question. |
| General question | The question and recent General-question history only. No active dataset, patients, assays, results, or workspace metadata. |

The histories are separate. A failed or unsupported Workspace request is never
silently retried as a General question, because the text may itself contain
private study information. General responses are labeled `No workspace
context` rather than with workspace disclosure badges.

## Provider and disclosure policy

Administrators define approved OpenAI-compatible endpoints. Users choose among
those endpoints; they cannot supply an arbitrary model URL.

The decision uses three independent controls:

- dataset visibility: which users may work with the data
- data classification: public or private
- AI-provider access: detailed allowed, safe summary, or blocked

The selected provider is also marked `local` or `external`. Private dataset
context may reach a local provider when the dataset permits it. It never
reaches an external provider. Public datasets continue to follow their
configured AI-provider access level for either provider boundary.

General-question mode does not attach dataset context, so it can use any
approved provider that the administrator has enabled. The question itself is
still sent to that provider. Users must not paste confidential or patient-level
content into an external model.

For a workspace containing several datasets, the strictest selected policy
wins, and one private dataset blocks the entire workspace from an external
provider. Provider health never overrides dataset policy.

The result provenance keeps two outputs explicit: `Response detail` is the
detail visible to the authorized user in COHORTome, while `Model context` is
the context actually supplied to a model. This avoids suggesting that a
detailed local response was also sent to the provider.

<picture>
  <source media="(max-width: 700px)" srcSet="/img/cohortome-governed-ai-mobile.svg" />
  <img
    src="/img/cohortome-governed-ai.svg"
    alt="COHORTome checks access, works with or without an approved language model, runs the operation itself, and keeps the result with its history."
  />
</picture>

## What models do not receive

- unrestricted access to every registered dataset
- records outside the current authorized workspace
- detailed identifiers when policy permits summaries only
- arbitrary shell or notebook execution
- authority to diagnose, prescribe, or make autonomous clinical decisions

## How model responses will be evaluated

Evaluation should compare model-assisted tasks against
reviewed reference outcomes. Relevant measures include:

- fidelity of patient and sample scope
- correctness of structured cohort criteria
- agreement with deterministic reference queries
- unsupported or ungrounded assertions
- adherence to disclosure and provider policy
- consistency across repeated runs and provider unavailability
- usefulness to clinical and translational researchers

Model evaluation must identify the provider, model, configuration, prompt or
task template, dataset snapshot, execution mode, and reference answer. A fluent
response alone is not evidence of correctness.

## Future tool integration

Model Context Protocol integrations may later expose approved metadata or
analysis tools. MCP is an extension point, not a currently validated scientific
claim. Any connector must inherit COHORTome authorization, disclosure, scope, and
audit rules rather than bypassing them.
