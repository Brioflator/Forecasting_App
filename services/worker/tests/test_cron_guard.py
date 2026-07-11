"""A malformed schedule_cron must not crash worker startup.

sync_pull_jobs runs synchronously in main() before the dispatch/relay loops
start, so an exception out of it would crash-loop the whole worker (the bad row
persists across restarts). The guard skips the offending connector, flags it
'error', and schedules the rest.
"""

from __future__ import annotations

import pytest
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session

from shared.db.models import Connector
from shared.providers.secrets import DotenvSecretsProvider
from shared.settings import Settings
from worker.main import sync_pull_jobs


def _settings(db_session: Session, tmp_path) -> Settings:
    db_url = db_session.get_bind().engine.url.render_as_string(hide_password=False)
    from shared.db import session as session_mod

    session_mod.reset_engine()
    return Settings(  # type: ignore[call-arg]
        _env_file=None,
        database_url=db_url,
        secret_file=str(tmp_path / "s.env"),
    )


def test_bad_cron_is_skipped_and_flagged_not_crashing(
    seeded, db_session: Session, tmp_path
) -> None:
    # A second connector with a broken cron alongside the valid seeded one.
    bad = Connector(
        organization_id=seeded.org_id,
        connector_definition_id=seeded.connector.connector_definition_id,
        name="broken cron",
        ingestion_method="pull",
        schedule_cron="not a cron at all",
    )
    db_session.add(bad)
    db_session.commit()

    settings = _settings(db_session, tmp_path)
    secrets = DotenvSecretsProvider(tmp_path / "s.env")
    scheduler = BackgroundScheduler()

    # Must not raise — the whole point of the guard.
    added, removed = sync_pull_jobs(scheduler, settings, secrets)

    # The valid connector is scheduled; the broken one is not.
    assert scheduler.get_job(f"poll-{seeded.connector.id}") is not None
    assert scheduler.get_job(f"poll-{bad.id}") is None
    assert added == 1

    # The broken connector is flagged so it surfaces in the UI.
    db_session.expire_all()
    assert db_session.get(Connector, bad.id).status == "error"


@pytest.fixture(autouse=True)
def _restore_engine():
    """This module rebinds the shared engine to the test DB; restore afterwards."""
    yield
    from shared.db import session as session_mod

    session_mod.reset_engine()
