# Connectors and the self-hosted agent

Connectors are how data enters the platform; the agent is the
credential-isolation variant of pulling. This is the primary extension surface
of the product — designed so that adding a new source is **one YAML file, and
only rarely any code**.

## Connectors are data

A connector *definition* is a YAML seed file in `/connectors`, loaded into the
`connector_definitions` table at api startup (`api/definitions.py`). The
shipped catalog: `generic_rest`, `braze`, `coingecko`, `open_meteo`,
`frankfurter`.

```yaml
# connectors/generic_rest.yaml (abridged)
key: generic_rest
name: Generic REST API
supports_pull: true
supports_push: false
supports_agent: true
config_schema:            # JSON Schema — load-bearing in three places at once
  type: object
  required: [base_url, value_path]
  properties:
    base_url:       { type: string, format: uri }
    auth_header:    { type: string, default: "Authorization" }
    auth_scheme:    { type: string, default: "Bearer", enum: [Bearer, Basic, raw] }
    value_path:     { type: string }   # JSONPath to the numeric value
    timestamp_path: { type: string }   # optional JSONPath to the timestamp
```

The single `config_schema` drives the frontend wizard form (RJSF renders it),
server-side validation of submitted config, and documentation for
contributors. A source-specific connector (e.g. `braze.yaml`) is the same file
with pinned defaults and different `supports_*` flags.

A connector *instance* (`connectors` table) is a tenant's configured copy:
non-sensitive `config` JSON, an `ingestion_method` (`pull` | `push` | `agent`),
a `schedule_cron` for pull, a `webhook_token` for push, and a `secret_ref` —
an opaque pointer into the `SecretsProvider`; **the secret itself is
structurally absent from the database**.

## The three ingestion methods

| Method | Who fetches | Credential custody | Entry point |
|---|---|---|---|
| `pull` | the worker, on a cron | stored via `SecretsProvider`, referenced by `secret_ref` | `worker/poller.py` |
| `push` | the source pushes | none — the platform never sees a source credential | `POST /webhooks/{token}` |
| `agent` | the user's own agent | never leaves the user's machine | `POST /ingest` (bearer token) |

All three converge on `shared/db/ingest.upsert_points` (idempotent upsert +
outbox in one transaction), so downstream code never knows the route.

## Extractors (`worker/extractors.py`)

The only *code* in the connector story. An `Extractor` is a Protocol with one
method: `fetch(config, secret, cadence) -> list[Point]`. Extractors are
registered by definition `key`; the poller looks the extractor up by the
connector's definition key and calls it.

`GenericRestExtractor` — the one implementation, shared by **all five**
shipped connectors (each is "GET a URL, JSONPath out a number"):

- Injects the secret into the configured auth header at request time; the
  secret is never stored or logged.
- Extracts `value_path` (required) and `timestamp_path` (optional) via
  JSONPath.
- **When the source provides no timestamp**, the point is stamped with `now()`
  **quantized to the connector's cron cadence bucket** (`worker/cadence.py`,
  croniter's previous fire) — not raw `now()`. Without this, a retried poll
  seconds later would mint a different timestamp and the
  `(metric_id, timestamp)` upsert would create a near-duplicate instead of
  deduping. Quantization is what keeps the timestamp-absent path idempotent.

### The SSRF guard (`worker/ssrf.py`)

`base_url` is tenant-controlled free text, so without a guard any org member
could point the worker at internal services (`ml:8100`, Postgres), a cloud
metadata endpoint (`169.254.169.254`), or another tenant's box and read the
response back as "their metric". `assert_public_url` enforces: http(s) only,
and **every** IP the host resolves to must be globally routable.

`CONNECTOR_ALLOW_PRIVATE_HOSTS` opts out — it defaults **true when
`APP_EDITION=local`** (a trusted self-hosted install whose bundled demo
connector polls this api's own localhost endpoint) and **false otherwise**; an
explicit env value always wins (`shared/settings.py` model validator). Known
residual: httpx re-resolves DNS on connect, so a host that flips its record
between check and connect isn't fully defeated; pinning the checked IP into
the connection would close that gap.

## Adding a connector — the checklist

1. **Write the YAML** in `/connectors/<key>.yaml`: `key`, `name`,
   `description`, `supports_pull/push/agent`, and a `config_schema` whose
   fields are exactly what a user must supply. Restart the api (or run a seed)
   to load it.
2. **Reuse `GenericRestExtractor`** if the pull path is "GET one URL, JSONPath
   one value" — just add the key to the registry list in
   `worker/extractors.default_registry`. Write a bespoke extractor **only** if
   the source pages/windows its API; register it under the same key.
3. The frontend needs **no changes** — the wizard renders from
   `config_schema`. That loop staying closed is the point of the design.
4. Add a test beside `services/worker/tests/test_extractor.py` /
   `test_live_connectors.py` if there's new extractor code.

## The self-hosted agent (`agent/`)

For pull-only sources whose credentials the user refuses (rightly) to hand
over: the agent runs on the **user's** infrastructure, polls the source there,
and forwards only normalized numeric points to the core. It is a deliberately
auditable, standalone subtree — one file
(`agent/src/forecast_agent/agent.py`), three dependencies (httpx, PyYAML,
jsonpath-ng), its own README and Dockerfile, **outside** the uv workspace.

Trust properties (guide §7.7) and where they live in the code:

- **Credential isolation** — the source secret is read from an env var on the
  user's machine (`secret_env` in `agent.config.yaml`) and attached only to
  requests to the *source*; requests to the core carry only the agent's own
  ingestion token.
- **Outbound-only** — the agent never listens on a port.
- **Bounded local buffering** — polled payloads queue in a
  `deque(maxlen=10_000)` and are flushed oldest-first; delivery stops at the
  first transient failure so order is preserved and the rest retry next tick.
  Terminal rejections (401 revoked token, 404 unknown metric, 409 unbound
  agent) drop that payload rather than blocking the queue forever.
- **Timestamp quantization** — same idempotency trick as the worker: points
  without a source timestamp are bucketed to the polling interval so re-polls
  dedupe server-side.
- **Heartbeats** — an explicit `POST /agents/heartbeat` every
  `heartbeat_seconds` (60), and every accepted ingest counts as one. The
  worker flips agents silent for >5 minutes to `stale` and notifies; the next
  successful contact flips them back.

Lifecycle: register through the UI/`POST /agents` (bound to a connector) → the
api returns the **one-time raw token** (only the sha256 hash is stored) and a
pre-filled `docker-compose.agent.yml` → the user adds their source API key to
the compose environment and runs it. Revocation (`POST /agents/{id}/revoke`)
invalidates the token; the agent's deliveries then 401 and are dropped as
terminal.

Config shape (`agent/agent.config.example.yaml`): `heartbeat_seconds` plus a
list of `sources`, each `{metric_key, base_url, value_path, interval_seconds,
timestamp_path?, auth_header?, auth_scheme?, secret_env?}`. `metric_key`
resolves server-side through the bound connector's metrics
(`UNIQUE (connector_id, key)`), so a payload maps to exactly one metric.

The agent's main loop is a 1-second `tick()`: poll due sources into the
buffer → flush → heartbeat when due. A failing source is logged and skipped —
it must never kill the agent. Tests: `agent/tests/test_agent.py`.
