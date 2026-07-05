"""The self-hosted polling agent (guide §7.7, plan 05 §4 agent v1).

Trust properties this file exists to make auditable:
- Your source credential is read from an environment variable on THIS machine
  (`secret_env` in agent.config.yaml) and is only ever sent to YOUR source API
  — never to the Forecast Platform core.
- Only normalized numeric points ({metric_key, [{timestamp, value}]}) are
  transmitted, authenticated by the agent's own ingestion token.
- Outbound-only networking: the agent calls out to your source and to the core
  /ingest endpoint; it never listens on a port.
- Points are buffered in memory and retried on network failure, so transient
  outages don't silently drop data.
"""

from __future__ import annotations

import logging
import os
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx
import yaml
from jsonpath_ng import parse as jsonpath_parse

log = logging.getLogger("forecast-agent")

MAX_BUFFERED_PAYLOADS = 10_000  # oldest dropped beyond this — bounded memory


@dataclass
class Source:
    metric_key: str
    base_url: str
    value_path: str
    interval_seconds: int = 60
    timestamp_path: str | None = None
    auth_header: str = "Authorization"
    auth_scheme: str = "Bearer"
    secret_env: str | None = None
    _next_due: float = field(default=0.0, repr=False)


@dataclass
class AgentConfig:
    api_url: str
    token: str
    sources: list[Source]
    heartbeat_seconds: int = 60

    @classmethod
    def load(cls, config_path: str) -> AgentConfig:
        api_url = os.environ.get("FORECAST_API_URL", "").rstrip("/")
        token = os.environ.get("FORECAST_AGENT_TOKEN", "")
        if not api_url or not token:
            raise SystemExit("FORECAST_API_URL and FORECAST_AGENT_TOKEN must be set")
        raw = yaml.safe_load(open(config_path, encoding="utf-8"))
        sources = [Source(**s) for s in raw.get("sources", [])]
        if not sources:
            raise SystemExit(f"no sources configured in {config_path}")
        return cls(
            api_url=api_url,
            token=token,
            sources=sources,
            heartbeat_seconds=int(raw.get("heartbeat_seconds", 60)),
        )


def _extract_first(expr: str, data: Any) -> Any:
    matches = jsonpath_parse(expr).find(data)
    if not matches:
        raise ValueError(f"JSONPath matched nothing: {expr}")
    return matches[0].value


class Agent:
    def __init__(self, config: AgentConfig, client: httpx.Client | None = None):
        self.config = config
        self.client = client or httpx.Client(timeout=15.0)
        # Buffer of ready-to-send ingest payloads (guide §7.7 local buffering).
        self.buffer: deque[dict] = deque(maxlen=MAX_BUFFERED_PAYLOADS)
        self._next_heartbeat = 0.0

    # ── polling ──────────────────────────────────────────────────────

    def poll_source(self, source: Source) -> dict | None:
        headers = {}
        if source.secret_env:
            secret = os.environ.get(source.secret_env)
            if not secret:
                log.warning("env var %s not set; polling unauthenticated", source.secret_env)
            elif source.auth_scheme == "raw":
                headers[source.auth_header] = secret
            else:
                headers[source.auth_header] = f"{source.auth_scheme} {secret}"

        resp = self.client.get(source.base_url, headers=headers)
        resp.raise_for_status()
        body = resp.json()
        value = float(_extract_first(source.value_path, body))
        if source.timestamp_path:
            ts = str(_extract_first(source.timestamp_path, body))
        else:
            # Quantize to the polling interval so re-polls dedupe server-side.
            now = datetime.now(tz=UTC)
            bucket = int(now.timestamp() // source.interval_seconds) * source.interval_seconds
            ts = datetime.fromtimestamp(bucket, tz=UTC).isoformat()
        return {"metric_key": source.metric_key, "points": [{"timestamp": ts, "value": value}]}

    # ── delivery ─────────────────────────────────────────────────────

    def flush(self) -> int:
        """Send buffered payloads oldest-first; stop at the first failure so
        order is preserved and the rest are retried next tick."""
        sent = 0
        while self.buffer:
            payload = self.buffer[0]
            try:
                resp = self.client.post(
                    f"{self.config.api_url}/ingest",
                    json=payload,
                    headers={"Authorization": f"Bearer {self.config.token}"},
                )
            except httpx.HTTPError as exc:
                log.warning("core unreachable, keeping %d buffered: %s", len(self.buffer), exc)
                break
            if resp.status_code in (401, 404, 409):
                # Terminal for this payload (revoked token / unknown metric) —
                # drop it rather than blocking the queue forever.
                log.error("payload rejected (%s): %s", resp.status_code, resp.text)
                self.buffer.popleft()
                continue
            if resp.status_code >= 400:
                log.warning("ingest failed (%s), will retry: %s", resp.status_code, resp.text)
                break
            self.buffer.popleft()
            sent += 1
        return sent

    def heartbeat(self) -> None:
        try:
            self.client.post(
                f"{self.config.api_url}/agents/heartbeat",
                headers={"Authorization": f"Bearer {self.config.token}"},
            )
        except httpx.HTTPError as exc:
            log.warning("heartbeat failed: %s", exc)

    # ── main loop ────────────────────────────────────────────────────

    def tick(self, now: float | None = None) -> None:
        """One scheduler pass: poll due sources into the buffer, flush, heartbeat."""
        now = now if now is not None else time.monotonic()
        for source in self.config.sources:
            if now >= source._next_due:
                source._next_due = now + source.interval_seconds
                try:
                    payload = self.poll_source(source)
                except Exception as exc:  # noqa: BLE001 — a bad source must not kill the agent
                    log.warning("poll failed for %s: %s", source.metric_key, exc)
                    continue
                if payload:
                    self.buffer.append(payload)
        self.flush()
        if now >= self._next_heartbeat:
            self._next_heartbeat = now + self.config.heartbeat_seconds
            self.heartbeat()

    def run_forever(self) -> None:  # pragma: no cover — thin loop over tick()
        log.info(
            "agent started: %d source(s), core=%s", len(self.config.sources), self.config.api_url
        )
        while True:
            self.tick()
            time.sleep(1)


def main() -> None:  # pragma: no cover
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    config = AgentConfig.load(os.environ.get("AGENT_CONFIG", "agent.config.yaml"))
    Agent(config).run_forever()


if __name__ == "__main__":
    main()
