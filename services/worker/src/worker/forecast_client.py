"""HTTP client to the stateless `ml` service (doc 1 §3.1).

`worker` talks to `ml` only over this REST contract — it never imports the ml
package, which is what keeps ml independently deployable/scalable. Tests drive
the same client through an ASGI transport so the real serialization path runs
without a network server.
"""

from __future__ import annotations

from typing import Any, Protocol

import httpx

from shared.models import ForecastRequest


class ForecastFailed(Exception):
    """A structured refusal from ml (insufficient/invalid data) — terminal."""

    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(detail)


class ForecastClient(Protocol):
    def forecast(self, request: ForecastRequest) -> dict[str, Any]: ...


class HttpForecastClient:
    def __init__(self, base_url: str, client: httpx.Client | None = None):
        self._base_url = base_url.rstrip("/")
        # Generous read timeout: a bounded fit takes tens of seconds (ml caps
        # the training window and search space); timing out mid-fit only to
        # retry the same fit is how work used to pile up on the ml service.
        self._client = client or httpx.Client(timeout=httpx.Timeout(120.0, connect=10.0))

    def forecast(self, request: ForecastRequest) -> dict[str, Any]:
        resp = self._client.post(f"{self._base_url}/forecast", json=request.model_dump(mode="json"))
        if resp.status_code == 422:
            body = resp.json()
            # A structured refusal (insufficient_data / invalid_request) is
            # terminal — the run should be marked failed, not retried.
            raise ForecastFailed(body.get("detail", "forecast refused"))
        resp.raise_for_status()
        return resp.json()
