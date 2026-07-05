"""Worker entrypoint: scheduler + poller + forecast dispatch + outbox relay.

Locally these are separate loops in one process (doc 1 §3); the module
boundaries keep the production split (separate replicas) a config change, not a
restructuring.
"""

from __future__ import annotations

import logging
import threading
import time

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select

from shared.db import session as session_mod
from shared.db.models import Connector
from shared.factory import make_event_bus, make_secrets_provider
from shared.logging_setup import configure_logging
from shared.settings import get_settings
from worker.consumers import register_consumers
from worker.dispatch import dispatch_pending_forecasts
from worker.extractors import default_registry
from worker.forecast_client import HttpForecastClient
from worker.poller import poll_connector
from worker.relay import relay_outbox

log = logging.getLogger("worker.main")


def _register_pull_jobs(scheduler: BackgroundScheduler, settings) -> None:
    from apscheduler.triggers.cron import CronTrigger

    secrets = make_secrets_provider(settings)
    factory = session_mod.get_session_factory(settings)
    with factory() as session:
        connectors = session.scalars(
            select(Connector).where(
                Connector.ingestion_method == "pull", Connector.status != "paused"
            )
        ).all()
        connector_ids = [
            (c.id, c.schedule_cron or settings.default_cadence_cron) for c in connectors
        ]

    def _make_poll(connector_id):
        def _job() -> None:
            with session_mod.get_session_factory(settings)() as s:
                connector = s.get(Connector, connector_id)
                if connector is not None:
                    poll_connector(s, connector, secrets, settings)

        return _job

    for connector_id, cron in connector_ids:
        scheduler.add_job(
            _make_poll(connector_id),
            CronTrigger.from_crontab(cron),
            id=f"poll-{connector_id}",
            replace_existing=True,
        )


def _dispatch_loop(settings, stop: threading.Event) -> None:
    client = HttpForecastClient(settings.ml_service_url)
    factory = session_mod.get_session_factory(settings)
    while not stop.is_set():
        try:
            with factory() as session:
                dispatch_pending_forecasts(session, client, settings.poll_batch_size)
        except Exception:  # noqa: BLE001 — keep the loop alive across transient errors
            log.exception("dispatch loop error")
        stop.wait(settings.forecast_poll_interval_seconds)


def _relay_loop(settings, bus, stop: threading.Event) -> None:
    factory = session_mod.get_session_factory(settings)
    while not stop.is_set():
        try:
            with factory() as session:
                relay_outbox(session, bus, settings.poll_batch_size)
        except Exception:  # noqa: BLE001
            log.exception("relay loop error")
        stop.wait(settings.outbox_poll_interval_seconds)


def _register_maintenance_jobs(scheduler: BackgroundScheduler, settings) -> None:
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger

    from worker.maintenance import ensure_partitions, mark_stale_agents

    factory = session_mod.get_session_factory(settings)

    def _partitions() -> None:
        with factory() as session:
            ensure_partitions(session)

    def _agents() -> None:
        with factory() as session:
            mark_stale_agents(session, settings)

    scheduler.add_job(_partitions, CronTrigger.from_crontab("30 2 * * *"), id="partition-maint")
    scheduler.add_job(_agents, IntervalTrigger(minutes=1), id="agent-staleness")


def main() -> None:
    settings = get_settings()
    configure_logging("worker", settings.log_level)
    default_registry()

    scheduler = BackgroundScheduler()
    _register_pull_jobs(scheduler, settings)
    _register_maintenance_jobs(scheduler, settings)
    scheduler.start()

    # One bus instance shared by the relay (publisher) and the consumers —
    # the auto-forecast-on-ingest subscriber exercises the real event path.
    bus = make_event_bus(settings)
    register_consumers(bus, session_mod.get_session_factory(settings), settings)

    stop = threading.Event()
    threads = [
        threading.Thread(
            target=_dispatch_loop, args=(settings, stop), daemon=True, name="dispatch"
        ),
        threading.Thread(target=_relay_loop, args=(settings, bus, stop), daemon=True, name="relay"),
    ]
    for t in threads:
        t.start()

    log.info("worker started (scheduler + dispatch + relay)")
    try:
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        stop.set()
        scheduler.shutdown()


if __name__ == "__main__":
    main()
