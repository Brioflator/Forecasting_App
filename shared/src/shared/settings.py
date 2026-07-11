"""The canonical configuration surface (plan 05 §2.3).

Every knob all three services and the seed/migration tooling read. Names are
pinned by the implementation plan; do not rename without updating .env.example
and the compose file.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ── Edition & providers (the seam selectors, doc 1 §2) ──
    app_edition: str = "local"  # local | production
    secrets_impl: str = "dotenv"  # dotenv | supabase_vault
    event_bus_impl: str = "inproc"  # inproc | redis | kafka
    blob_store_impl: str = "local"  # local | supabase
    auth_impl: str = "local"  # local | supabase
    multi_tenant: bool = False

    # ── Datastores ──
    database_url: str = "postgresql+psycopg://forecast:forecast@postgres:5432/forecast"
    redis_url: str = "redis://redis:6379/0"

    # ── Service wiring ──
    # Reject oversized request bodies by Content-Length before FastAPI parses
    # them (the per-delivery point cap only bounds what's persisted, not what's
    # parsed). ~8 MB comfortably fits a max 10k-point delivery.
    max_request_body_bytes: int = 8_000_000
    api_port: int = 8000
    ml_port: int = 8100
    ml_service_url: str = "http://ml:8100"
    api_url: str = "http://localhost:8000"
    cors_origins: str = "http://localhost:3000"
    log_level: str = "info"

    # ── Secrets / storage (local impls) ──
    secret_file: str = "/run/secrets/connectors.env"
    export_dir: str = "/data/exports"

    # ── worker knobs ──
    forecast_poll_interval_seconds: float = 2
    outbox_poll_interval_seconds: float = 2
    poll_batch_size: int = 20
    default_cadence_cron: str = "* * * * *"
    max_consecutive_failures: int = 5
    poll_retry_attempts: int = 3  # per-poll fetch retries with expo backoff (MVP ops)
    poll_retry_backoff_seconds: float = 1.0
    agent_stale_after_minutes: int = 5  # heartbeat age before an agent flips to 'stale'
    # auto-forecast-on-ingest consumer (plan 05 §4 "real event path"); 0 = off
    auto_forecast_min_interval_minutes: int = 15
    auto_forecast_horizon: int = 24
    # transport-level ml failures: exponential backoff, then terminal failure
    # (doc 1 §7 "ml failures are HTTP errors the worker retries with backoff")
    forecast_dispatch_max_attempts: int = 5
    forecast_dispatch_backoff_seconds: float = 5
    # cap on the series payload shipped to ml per forecast — the history grows
    # forever, the training window doesn't (ml caps again at MAX_FIT_POINTS)
    forecast_max_series_points: int = 5000
    # how often the worker re-syncs pull jobs against the connectors table, so
    # wizard-created connectors start polling without a restart
    connector_sync_interval_seconds: float = 30
    # SSRF guard: pull connectors may only fetch globally-routable hosts. Set
    # True only for trusted self-hosted deployments whose sources live on the
    # internal network (worker/ssrf.py).
    connector_allow_private_hosts: bool = False
    # anomaly detection (guide §5.7, v2.x pulled into the local product):
    # actuals outside the latest forecast's confidence band → anomalies rows
    anomaly_sweep_interval_seconds: float = 60  # 0 = disabled

    # ── ml knobs (doc 3 §4–§5) ──
    # statsforecast is the statistical backbone (revalidation guide §3);
    # "legacy" falls back to the statsmodels ladder (no ARIMA rung, no CV)
    # for machines where statsforecast/numba cannot install.
    forecast_engine: str = "statsforecast"  # statsforecast | legacy
    forecast_default_confidence: float = 0.95
    gap_fill_max_consecutive: int = 3
    gap_fill_max_fraction: float = 0.05
    # NOTE: AutoARIMA search bounds are NOT here — they live in
    # services/ml/src/ml/constants.py (AUTO_ARIMA_MAX_*), kept low for OOM
    # safety. A settings knob here would be dead config (nothing reads it) and
    # would tempt raising the bound past the safe ceiling.

    # ── production only (doc 2) — present but unused when APP_EDITION=local ──
    supabase_url: str | None = None
    supabase_anon_key: str | None = None
    supabase_service_role_key: str | None = None
    supabase_jwt_secret: str | None = None
    kafka_brokers: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
