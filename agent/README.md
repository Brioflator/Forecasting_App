# Forecast Platform — self-hosted agent

Polls your source APIs on **your** infrastructure and forwards only normalized
numeric points to the Forecast Platform core. Your source credentials never
leave this machine (guide §7): they live in this compose file's environment,
are attached only to requests to your source, and the agent authenticates to
the core with its own ingestion token instead.

## Security posture

- **Open source, single file** — [`src/forecast_agent/agent.py`](src/forecast_agent/agent.py)
  is the entire program; audit it in five minutes.
- **Outbound-only** — the agent never listens on a port.
- **Non-root container**, minimal base image, three dependencies.
- **Local buffering** — points queue in memory and retry when the core is
  unreachable, so transient outages don't drop data.
- The core tracks the agent's heartbeat and shows "agent unreachable" in the
  dashboard when it goes quiet.

## Running it

1. In the app, open your connector and register an agent — you get a one-time
   ingestion token and a pre-filled `docker-compose.agent.yml`.
2. Copy `agent.config.example.yaml` → `agent.config.yaml`; set your source
   URL, JSONPath, and (if needed) `secret_env` pointing at the env var that
   holds your source API key.
3. Put that key in `docker-compose.agent.yml`'s environment.
4. `docker compose -f docker-compose.agent.yml up -d`

Data appears under the connector's metrics within one polling interval.
