"""Domain vocabulary — the enumerated string values the app writes and compares.

One authoritative definition per set of allowed values, so a status or method
is never retyped as a bare literal in a route or worker loop. Every member is a
`StrEnum`, so its value equals the plain string the database stores and the API
serialises — assigning `connector.status = ConnectorStatus.ACTIVE` persists
exactly `"active"`, and `body.model in ModelType` accepts exactly the strings
the DB CheckConstraints allow.

These mirror the CheckConstraints in `shared/db/models.py` (themselves a
verbatim mirror of the migration SQL, which remains the schema authority). Keep
the members — names, values, and order — in lockstep with those constraints.
"""

from __future__ import annotations

from enum import StrEnum


class IngestionMethod(StrEnum):
    PUSH = "push"
    PULL = "pull"
    AGENT = "agent"


class ConnectorStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    ERROR = "error"


class AgentStatus(StrEnum):
    ACTIVE = "active"
    STALE = "stale"
    REVOKED = "revoked"


class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ModelType(StrEnum):
    AUTO = "auto"
    SARIMA = "sarima"
    ETS = "ets"
    PROPHET = "prophet"


class PointSource(StrEnum):
    POLL = "poll"
    WEBHOOK = "webhook"
    AGENT = "agent"
    BACKFILL = "backfill"
