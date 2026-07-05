"""Root pytest fixtures shared across services.

DB-touching tests (`api` / `worker` / the `shared` round-trip) run against a
real Postgres (plan 05 §2.6 — the compose stack IS the environment, no
testcontainers). They are skipped when TEST_DATABASE_URL is unset so the pure
suites (`ml`, `shared` providers) always run anywhere.

The schema is migrated once per session and tables are truncated between tests.
"""

import os
from collections.abc import Iterator

import pytest

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

# Tables truncated between tests — every mutable table the app writes.
_TRUNCATE_TABLES = [
    "forecast_points",
    "forecast_runs",
    "data_points",
    "connector_runs",
    "outbox_events",
    "export_jobs",
    "metrics",
    "connectors",
    "connector_definitions",
    "organization_members",
    "organizations",
    "auth.users",
]


def _run_migrations(database_url: str) -> None:
    from alembic import command
    from alembic.config import Config

    root = os.path.dirname(__file__)
    cfg = Config(os.path.join(root, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(root, "migrations"))
    os.environ["DATABASE_URL"] = database_url
    command.upgrade(cfg, "head")


@pytest.fixture(scope="session")
def db_url() -> str:
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL not set; skipping DB-backed test")
    return TEST_DATABASE_URL


@pytest.fixture(scope="session")
def _migrated_db(db_url: str) -> str:
    _run_migrations(db_url)
    return db_url


@pytest.fixture
def db_session(_migrated_db: str) -> Iterator[object]:
    from sqlalchemy import text

    from shared.db import session as session_mod
    from shared.settings import Settings

    settings = Settings(_env_file=None, database_url=_migrated_db)  # type: ignore[call-arg]
    session_mod.reset_engine()
    factory = session_mod.get_session_factory(settings)
    sess = factory()
    try:
        yield sess
    finally:
        sess.rollback()
        with session_mod.get_engine(settings).begin() as conn:
            conn.execute(
                text("TRUNCATE " + ", ".join(_TRUNCATE_TABLES) + " RESTART IDENTITY CASCADE")
            )
        sess.close()
