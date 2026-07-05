"""api test fixtures: a TestClient wired to the migrated test DB with the
connector catalog loaded and the implicit org/user seeded."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api import deps
from api.app import create_app
from api.definitions import load_connector_definitions
from shared.constants import LOCAL_ORG_ID, LOCAL_USER_ID
from shared.db.models import AuthUser, Organization

CONNECTORS_DIR = Path(__file__).resolve().parents[3] / "connectors"


@pytest.fixture
def client(db_session: Session, tmp_path: Path) -> Iterator[TestClient]:
    # Seed the implicit tenant the LocalAuthProvider returns.
    db_session.add(AuthUser(id=uuid.UUID(LOCAL_USER_ID), email="local@forecast.local"))
    db_session.add(Organization(id=uuid.UUID(LOCAL_ORG_ID), name="Local Organization"))
    db_session.flush()
    load_connector_definitions(db_session, CONNECTORS_DIR)

    app = create_app()

    def _override_db() -> Iterator[Session]:
        # Reuse the single test session so flushed rows are visible across
        # requests; the fixture teardown handles rollback + truncate.
        yield db_session

    from shared.providers.blob_store import LocalBlobStore

    app.dependency_overrides[deps.get_db] = _override_db
    app.dependency_overrides[deps._blob_store] = lambda: LocalBlobStore(
        tmp_path / "exports", api_url="http://localhost:8000"
    )
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()
