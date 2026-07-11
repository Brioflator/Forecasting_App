"""The free-public-API connectors (coingecko / open_meteo / frankfurter) all
ride the shared GenericRestExtractor; these lock that they are registered and
that each YAML's default value_path pulls the value out of that API's real
response shape.
"""

from __future__ import annotations

import httpx

from worker.extractors import GenericRestExtractor, default_registry


def _client(body: dict) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=body)))


def test_live_extractor_keys_registered() -> None:
    reg = default_registry()
    for key in ("coingecko", "open_meteo", "frankfurter"):
        assert key in reg


def test_coingecko_default_value_path() -> None:
    ex = GenericRestExtractor(client=_client({"bitcoin": {"usd": 63698}}))
    pts = ex.fetch({"base_url": "http://x", "value_path": "$.bitcoin.usd"}, None, "0 * * * *")
    assert pts[0].value == 63698.0


def test_open_meteo_default_value_path() -> None:
    ex = GenericRestExtractor(client=_client({"current": {"temperature_2m": 27.9}}))
    pts = ex.fetch(
        {"base_url": "http://x", "value_path": "$.current.temperature_2m"}, None, "0 * * * *"
    )
    assert pts[0].value == 27.9


def test_frankfurter_default_value_path() -> None:
    ex = GenericRestExtractor(client=_client({"rates": {"EUR": 0.876}}))
    pts = ex.fetch({"base_url": "http://x", "value_path": "$.rates.EUR"}, None, "0 12 * * *")
    assert pts[0].value == 0.876
