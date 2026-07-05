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
    # how often the worker re-syncs pull jobs against the connectors table, so
    # wizard-created connectors start polling without a restart
    connector_sync_interval_seconds: float = 30
    # anomaly detection (guide §5.7, v2.x pulled into the local product):
    # actuals outside the latest forecast's confidence band → anomalies rows
    anomaly_sweep_interval_seconds: float = 60  # 0 = disabled

    # ── ml knobs (doc 3 §4–§5) ──
    forecast_default_confidence: float = 0.95
    gap_fill_max_consecutive: int = 3
    gap_fill_max_fraction: float = 0.05
    auto_arima_max_p: int = 5
    auto_arima_max_q: int = 5

    # ── production only (doc 2) — present but unused when APP_EDITION=local ──
    supabase_url: str | None = None
    supabase_anon_key: str | None = None
    supabase_service_role_key: str | None = None
    supabase_jwt_secret: str | None = None
    kafka_brokers: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
