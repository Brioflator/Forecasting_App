"""FastAPI dependencies: settings, DB session, and the injected providers.

The implicit org/user is injected by the LocalAuthProvider (doc 1 §6.6); every
tenant-scoped query filters on principal.org_id so the same route code enforces
tenancy once RLS + real auth land (plan 05 §4).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.db import session as session_mod
from shared.db.models import Connector, ForecastRun, Metric
from shared.factory import make_auth_provider, make_blob_store
from shared.providers.auth import AuthProvider, Principal
from shared.providers.blob_store import BlobStore
from shared.settings import Settings, get_settings


@lru_cache
def _auth_provider() -> AuthProvider:
    return make_auth_provider(get_settings())


@lru_cache
def _blob_store() -> BlobStore:
    return make_blob_store(get_settings())


def get_db() -> Iterator[Session]:
    factory = session_mod.get_session_factory(get_settings())
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def current_principal(authorization: Annotated[str | None, Header()] = None) -> Principal:
    return _auth_provider().authenticate(authorization)


SettingsDep = Annotated[Settings, Depends(get_settings)]
DbDep = Annotated[Session, Depends(get_db)]
PrincipalDep = Annotated[Principal, Depends(current_principal)]
BlobDep = Annotated[BlobStore, Depends(_blob_store)]


def require_owned_connector(
    connector_id: uuid.UUID, db: DbDep, principal: PrincipalDep
) -> Connector:
    """Resolve `{connector_id}` to a connector the caller's org owns, or 404.

    A route that declares an `OwnedConnectorDep` states its need — an owned
    connector — instead of re-deriving the tenancy lookup in its body. This is
    the single place org-scoping is enforced for connector routes.
    """
    connector = db.scalar(
        select(Connector).where(
            Connector.id == connector_id,
            Connector.organization_id == uuid.UUID(principal.org_id),
        )
    )
    if connector is None:
        raise HTTPException(404, "connector not found")
    return connector


def require_owned_metric(metric_id: uuid.UUID, db: DbDep, principal: PrincipalDep) -> Metric:
    """Resolve `{metric_id}` to a metric the caller's org owns, or 404.

    The metric-route counterpart to `require_owned_connector`; the single place
    org-scoping is enforced for metric routes.
    """
    metric = db.scalar(
        select(Metric).where(
            Metric.id == metric_id,
            Metric.organization_id == uuid.UUID(principal.org_id),
        )
    )
    if metric is None:
        raise HTTPException(404, "metric not found")
    return metric


def require_owned_run(forecast_id: uuid.UUID, db: DbDep, principal: PrincipalDep) -> ForecastRun:
    """Resolve `{forecast_id}` to a forecast run the caller's org owns, or 404.

    The forecast-route counterpart to `require_owned_connector`; the single
    place org-scoping is enforced for forecast routes.
    """
    run = db.scalar(
        select(ForecastRun).where(
            ForecastRun.id == forecast_id,
            ForecastRun.organization_id == uuid.UUID(principal.org_id),
        )
    )
    if run is None:
        raise HTTPException(404, "forecast not found")
    return run


OwnedConnectorDep = Annotated[Connector, Depends(require_owned_connector)]
OwnedMetricDep = Annotated[Metric, Depends(require_owned_metric)]
OwnedRunDep = Annotated[ForecastRun, Depends(require_owned_run)]
