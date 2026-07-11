"""Connector extractors — the only *code* a new connector needs (doc 1 §4.1).

Registered by connector-definition `key`; the poller looks up the extractor for
a connector's definition and calls `fetch()`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

import httpx
from jsonpath_ng import parse as jsonpath_parse

from shared.models import Point
from worker.cadence import quantize_to_cadence
from worker.ssrf import assert_public_url


class Extractor(Protocol):
    def fetch(self, config: dict, secret: str | None, cadence: str | None) -> list[Point]: ...


def _jsonpath_first(expr: str, data: object) -> object:
    matches = jsonpath_parse(expr).find(data)
    if not matches:
        raise ValueError(f"JSONPath matched nothing: {expr}")
    return matches[0].value


class GenericRestExtractor:
    """Poll any REST endpoint and pull a numeric value out of the JSON response.

    The secret is injected into the auth header here and never stored (guide §7).
    """

    def __init__(self, client: httpx.Client | None = None, *, allow_private_hosts: bool = False):
        self._client = client or httpx.Client(timeout=15.0)
        # The SSRF guard protects the real egress client. An injected client is a
        # test/programmatic seam that never touches the real network, so it
        # bypasses the guard; `allow_private_hosts` opts the real client out too,
        # for self-hosted deployments whose sources genuinely live on-network.
        self._guard_ssrf = client is None and not allow_private_hosts

    def _auth_headers(self, config: dict, secret: str | None) -> dict[str, str]:
        if not secret:
            return {}
        header = config.get("auth_header", "Authorization")
        scheme = config.get("auth_scheme", "Bearer")
        value = secret if scheme == "raw" else f"{scheme} {secret}"
        return {header: value}

    def fetch(self, config: dict, secret: str | None, cadence: str | None) -> list[Point]:
        if self._guard_ssrf:
            assert_public_url(config["base_url"])
        resp = self._client.get(config["base_url"], headers=self._auth_headers(config, secret))
        resp.raise_for_status()
        body = resp.json()

        raw_value = _jsonpath_first(config["value_path"], body)
        value = float(raw_value)  # type: ignore[arg-type]
        if config.get("timestamp_path"):
            raw_ts = _jsonpath_first(config["timestamp_path"], body)
            ts = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
        else:
            ts = quantize_to_cadence(datetime.now(tz=UTC), cadence)
        return [Point(timestamp=ts, value=value)]


# Registry keyed by connector-definition key.
_REGISTRY: dict[str, Extractor] = {}


def register_extractor(key: str, extractor: Extractor) -> None:
    _REGISTRY[key] = extractor


def get_extractor(key: str) -> Extractor:
    if key not in _REGISTRY:
        raise KeyError(f"no extractor registered for connector key: {key}")
    return _REGISTRY[key]


def default_registry() -> dict[str, Extractor]:
    # Every connector whose pull path is "GET a URL, pull a numeric value out of
    # the JSON by JSONPath" shares one GenericRestExtractor; the connector's YAML
    # supplies the URL and value_path. A bespoke extractor is only needed for a
    # source that pages/windows its API (none of these do).
    from shared.settings import get_settings

    shared = GenericRestExtractor(allow_private_hosts=get_settings().connector_allow_private_hosts)
    for key in ("generic_rest", "braze", "coingecko", "open_meteo", "frankfurter"):
        if key not in _REGISTRY:
            register_extractor(key, shared)
    return _REGISTRY
