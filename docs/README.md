# Forecast Platform — current-state documentation

This folder is the **current-state reference** for the codebase: what exists,
how it works, and how to extend it. It is written for both a human engineer
picking the project up and a coding agent working in it — every claim here was
verified against the source at the time of writing, and each doc names the
files it describes so drift is easy to detect and fix.

How this folder relates to the root-level documents:

- The root guides (`forecast-platform-project-guide.md`, `01`–`05`) are the
  **design history**: the product rationale, the original build specification,
  and the decision records. They explain *why* the system has this shape.
  A few of their implementation details have since been superseded (each file
  carries a note where that happened); when a root guide and a `docs/` file
  disagree about the code, `docs/` is right.
- `CLAUDE.md` at the root is the terse operating card for agents (commands,
  gotchas). This folder is the depth behind it.

## Reading order

New to the project (human or agent):

1. [architecture.md](architecture.md) — the system in one pass: services,
   the provider seam, and every end-to-end flow.
2. [ml.md](ml.md) — the forecasting core in full detail. This is the product's
   actual value; read it before touching anything under `services/ml/`.
3. [worker.md](worker.md) — the scheduler/poller/dispatch/relay process.
4. [api.md](api.md) — the HTTP surface and its patterns.
5. [connectors-and-agent.md](connectors-and-agent.md) — how data sources are
   defined, polled, pushed, and (via the self-hosted agent) kept
   credential-safe. This is the main extension surface.
6. [frontend.md](frontend.md) — the Next.js app.
7. [development.md](development.md) — environment setup, tests, migrations,
   golden files, and the gotchas that actually bite.

Task-directed entry points:

| You want to… | Read |
|---|---|
| Add a new data source | [connectors-and-agent.md](connectors-and-agent.md) §"Adding a connector" |
| Change model selection / thresholds | [ml.md](ml.md) §"Policy lives in three files" |
| Add an API endpoint | [api.md](api.md) §"Patterns to follow" |
| Add a background job | [worker.md](worker.md) §"Adding work to the worker" |
| Add a screen or component | [frontend.md](frontend.md) |
| Run the stack / the tests | [development.md](development.md) |
| Understand a flow end to end | [architecture.md](architecture.md) §"The flows" |

## Scope boundary (important)

The **local/open-source product is complete**; production deployment
(Supabase providers, Kafka/SQS, container hosting — `02-deploy-production.md`)
is **intentionally not started**. The production provider branches exist in
`shared/factory.py` and raise `NotImplementedError` by design. Do not begin
doc 02 work unless explicitly asked.

## Keeping these docs true

After a change that alters behavior described here, update the relevant file
in the same commit — these docs are part of the codebase, not an artifact.
The test suites are the enforcement layer for most claims (golden files pin
ml behavior; api/worker tests pin the flows); the docs are the explanation
layer on top.
