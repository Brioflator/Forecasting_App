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

    def __init__(self, client: httpx.Client | None = None):
        self._client = client or httpx.Client(timeout=15.0)

    def _auth_headers(self, config: dict, secret: str | None) -> dict[str, str]:
        if not secret:
            return {}
        header = config.get("auth_header", "Authorization")
        scheme = config.get("auth_scheme", "Bearer")
        value = secret if scheme == "raw" else f"{scheme} {secret}"
        return {header: value}

    def fetch(self, config: dict, secret: str | None, cadence: str | None) -> list[Point]:
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
    if "generic_rest" not in _REGISTRY:
        register_extractor("generic_rest", GenericRestExtractor())
    if "braze" not in _REGISTRY:
        # Braze's pull path is REST + JSONPath — the generic extractor with
        # braze.yaml's defaults covers it; a bespoke extractor is only needed
        # if pagination/windowing ever gets added.
        register_extractor("braze", GenericRestExtractor())
    return _REGISTRY
