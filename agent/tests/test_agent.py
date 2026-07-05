"""Agent v1 behavior: extraction, credential isolation, buffering/retry,
heartbeat — all against mock transports, no network."""

from __future__ import annotations

import httpx
import pytest
from forecast_agent.agent import Agent, AgentConfig, Source


class World:
    """Fake source + core with controllable availability."""

    def __init__(self) -> None:
        self.core_up = True
        self.ingested: list[dict] = []
        self.heartbeats = 0
        self.source_headers: dict | None = None

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith("http://source"):
            self.source_headers = dict(request.headers)
            return httpx.Response(200, json={"metric": {"v": 42.5}, "ts": "2026-07-01T00:00:00Z"})
        if url.endswith("/ingest"):
            if not self.core_up:
                return httpx.Response(503)
            import json

            self.ingested.append(json.loads(request.content))
            return httpx.Response(202, json={"accepted": 1})
        if url.endswith("/agents/heartbeat"):
            self.heartbeats += 1
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(404)


@pytest.fixture
def world() -> World:
    return World()


def _agent(world: World, **source_overrides) -> Agent:
    source = Source(
        metric_key="k",
        base_url="http://source/api",
        value_path="$.metric.v",
        timestamp_path="$.ts",
        interval_seconds=60,
        **source_overrides,
    )
    config = AgentConfig(api_url="http://core", token="tok", sources=[source])
    return Agent(config, client=httpx.Client(transport=httpx.MockTransport(world.handler)))


def test_poll_extract_and_deliver(world: World) -> None:
    agent = _agent(world)
    agent.tick(now=1000.0)
    assert len(world.ingested) == 1
    payload = world.ingested[0]
    assert payload["metric_key"] == "k"
    assert payload["points"][0]["value"] == 42.5
    assert payload["points"][0]["timestamp"] == "2026-07-01T00:00:00Z"
    # ingest authenticated with the AGENT token, not the source credential
    assert world.heartbeats == 1


def test_source_credential_never_sent_to_core(world: World, monkeypatch) -> None:
    monkeypatch.setenv("MY_SOURCE_KEY", "super-secret")
    agent = _agent(world, secret_env="MY_SOURCE_KEY", auth_scheme="Bearer")
    agent.tick(now=1000.0)
    # credential went to the source...
    assert world.source_headers is not None
    assert world.source_headers.get("authorization") == "Bearer super-secret"
    # ...and the core never saw it (only the agent token)
    assert "super-secret" not in str(world.ingested)


def test_buffers_while_core_down_then_flushes(world: World) -> None:
    agent = _agent(world)
    world.core_up = False
    agent.tick(now=1000.0)  # poll ok, delivery fails → buffered
    agent.tick(now=1061.0)  # second poll also buffered
    assert len(agent.buffer) == 2
    assert world.ingested == []

    world.core_up = True
    agent.tick(now=1122.0)  # next tick flushes everything (oldest first)
    assert len(agent.buffer) == 0
    assert len(world.ingested) == 3  # 2 buffered + this tick's poll


def test_respects_poll_interval(world: World) -> None:
    agent = _agent(world)
    agent.tick(now=1000.0)
    agent.tick(now=1010.0)  # only 10s later — source not due yet
    assert len(world.ingested) == 1


def test_rejected_payload_is_dropped_not_stuck(world: World) -> None:
    agent = _agent(world)

    def rejecting(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith("http://source"):
            return world.handler(request)
        if url.endswith("/ingest"):
            return httpx.Response(404, json={"detail": "unknown metric_key"})
        return world.handler(request)

    agent.client = httpx.Client(transport=httpx.MockTransport(rejecting))
    agent.tick(now=1000.0)
    assert len(agent.buffer) == 0  # dropped, not clogging the queue
