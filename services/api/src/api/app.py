"""The api FastAPI app — the frontend's entire backend (doc 4 §0).

Assembles the routers, CORS, healthz, and (local edition) loads the connector
definition seeds at startup so the wizard has a catalog on first boot.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api import agents, connectors, dev, eda, forecasts, ingestion, metrics, notifications
from api.definitions import load_connector_definitions
from shared.db import session as session_mod
from shared.logging_setup import configure_logging
from shared.providers.auth import Unauthorized
from shared.settings import get_settings

# /connectors is mounted at repo root in the container; overridable for tests.
CONNECTORS_DIR = Path(__file__).resolve().parents[4] / "connectors"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    try:
        factory = session_mod.get_session_factory(settings)
        with factory() as session:
            load_connector_definitions(session, CONNECTORS_DIR)
    except Exception:  # noqa: BLE001 — a missing DB at boot shouldn't crash import in tests
        pass
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging("api", settings.log_level)
    app = FastAPI(title="Forecast API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    max_body = settings.max_request_body_bytes

    @app.middleware("http")
    async def _cap_body_size(request, call_next):
        # Reject by declared size before the body is read/parsed. The route-level
        # point-count check stays as the backstop for chunked/unlabelled bodies.
        from fastapi.responses import JSONResponse

        content_length = request.headers.get("content-length")
        if (
            content_length is not None
            and content_length.isdigit()
            and int(content_length) > max_body
        ):
            return JSONResponse(status_code=413, content={"detail": "request body too large"})
        return await call_next(request)

    @app.exception_handler(Unauthorized)
    async def _unauthorized(_request, exc: Unauthorized):
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=401, content={"detail": str(exc)})

    @app.get("/healthz", tags=["health"])
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(connectors.router)
    app.include_router(metrics.router)
    app.include_router(forecasts.router)
    app.include_router(ingestion.router)
    app.include_router(agents.router)
    app.include_router(eda.router)
    app.include_router(notifications.router)
    app.include_router(dev.router)
    return app


app = create_app()
