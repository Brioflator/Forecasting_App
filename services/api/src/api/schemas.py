"""Request/response models for the api's own REST surface (distinct from the
shared inter-service DTOs). FastAPI turns these into the OpenAPI the frontend
codegens against (doc 4 §5)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ConnectorDefinitionOut(BaseModel):
    id: uuid.UUID
    key: str
    name: str
    description: str | None
    config_schema: dict[str, Any]
    supports_push: bool
    supports_pull: bool
    supports_agent: bool


class ConnectorCreate(BaseModel):
    connector_definition_key: str
    name: str
    config: dict[str, Any] = Field(default_factory=dict)
    ingestion_method: str = "pull"
    schedule_cron: str | None = None
    # Write-only: stored via the SecretsProvider under a generated secret_ref;
    # never persisted in the connectors row itself (guide §7.3).
    secret: str | None = None


class ConnectorUpdate(BaseModel):
    name: str | None = None
    config: dict[str, Any] | None = None
    schedule_cron: str | None = None
    status: str | None = None


class ConnectorOut(BaseModel):
    id: uuid.UUID
    connector_definition_id: uuid.UUID
    name: str
    config: dict[str, Any]
    ingestion_method: str
    schedule_cron: str | None
    webhook_token: str | None
    status: str


class MetricCreate(BaseModel):
    name: str
    key: str
    unit: str | None = None
    seasonal_period: int | None = None
    extraction_config: dict[str, Any] = Field(default_factory=dict)


class MetricOut(BaseModel):
    id: uuid.UUID
    connector_id: uuid.UUID
    name: str
    key: str
    unit: str | None
    seasonal_period: int | None


class MetricListItemOut(MetricOut):
    """Dataset-list shape (doc 4 §3): sparkline + freshness at a glance."""

    connector_name: str
    n_points: int
    last_updated: datetime | None
    spark: list[float]


class DataPointOut(BaseModel):
    timestamp: datetime
    value: float
    source: str


class MetricDataOut(BaseModel):
    metric_id: uuid.UUID
    points: list[DataPointOut]


class ForecastCreate(BaseModel):
    horizon: int = 24
    model: str = "auto"


class ForecastPointOut(BaseModel):
    timestamp: datetime
    predicted: float
    lower: float | None
    upper: float | None


class ForecastRunOut(BaseModel):
    id: uuid.UUID
    metric_id: uuid.UUID
    model_type: str
    model_params: dict[str, Any]
    horizon: int
    status: str
    requested_at: datetime
    completed_at: datetime | None
    error_message: str | None
    warning: str | None = None
    points: list[ForecastPointOut] = Field(default_factory=list)


class SampleMetricOut(BaseModel):
    value: float
    timestamp: datetime


class EdaReportOut(BaseModel):
    id: uuid.UUID
    metric_id: uuid.UUID
    generated_at: datetime
    stationarity: dict[str, Any]
    seasonality: dict[str, Any]
    acf_pacf: dict[str, Any]


class AgentRegisterIn(BaseModel):
    connector_id: uuid.UUID


class AgentOut(BaseModel):
    id: uuid.UUID
    connector_id: uuid.UUID | None
    status: str
    last_heartbeat_at: datetime | None
    created_at: datetime


class AgentRegisterOut(BaseModel):
    agent: AgentOut
    # Shown exactly once at registration (only the hash is stored, guide §5.2).
    ingestion_token: str
    compose_file: str
