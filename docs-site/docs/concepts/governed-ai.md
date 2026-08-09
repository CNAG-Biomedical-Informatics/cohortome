# Governed AI

A language model can help a researcher express a question or understand a
result. BRN checks what data may be used, limits what may be sent, and remains
responsible for running the requested operation.

## Supported roles

BRN uses approved models to assist with:

- translating natural-language research intent into inspectable query or
  analysis plans
- explaining available data, overlap, and missingness
- interpreting deterministic or curated analysis results
- suggesting follow-up questions without silently expanding the data scope

A deployment may disable model access, and a dataset may block it. This is an
expected governed state, not an application failure.

## Execution modes

| Mode | Role |
| --- | --- |
| Deterministic | Structured application logic queries data or computes a known result directly. |
| LLM planner | A model interprets intent and proposes a structured operation that BRN executes within its allowed contract. |
| LLM interpretation | A model explains bounded context or outputs produced by deterministic or curated methods. |
| Curated runner | Reviewed backend code launches a declared statistical or workflow implementation. |

The interface should report the mode used. An unavailable or disallowed model
must not be hidden by silently switching to an unrelated mode.

## Provider and disclosure policy

Administrators define approved OpenAI-compatible endpoints. Users choose among
those endpoints; they cannot supply an arbitrary model URL.

Each dataset contributes two relevant ceilings:

- in-application disclosure: detailed or summary
- AI-provider access: detailed allowed, safe summary, or blocked

For a workspace containing several datasets, the strictest selected policy
wins. Provider health never overrides dataset policy.

<picture>
  <source media="(max-width: 700px)" srcSet="/img/brn-governed-ai-mobile.svg" />
  <img
    src="/img/brn-governed-ai.svg"
    alt="BRN checks access, works with or without an approved language model, runs the operation itself, and keeps the result with its history."
  />
</picture>

## What models do not receive

- unrestricted access to every registered dataset
- records outside the current authorized workspace
- detailed identifiers when policy permits summaries only
- arbitrary shell or notebook execution
- authority to diagnose, prescribe, or make autonomous clinical decisions

## Evaluation contract

The PRECISESADS demonstrator should evaluate model-assisted tasks against
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
claim. Any connector must inherit BRN authorization, disclosure, scope, and
audit rules rather than bypassing them.
