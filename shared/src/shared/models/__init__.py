"""Shared Pydantic DTOs — the inter-service contracts (plan 05 §2.2).

`ml` imports only these, never the DB mapping layer (doc 3 §0).
"""

from shared.models.dto import (
    CandidateScore,
    EdaRequest,
    EdaResponse,
    FoldScore,
    ForecastError,
    ForecastPoint,
    ForecastRequest,
    ForecastResponse,
    IngestPayload,
    Point,
)

__all__ = [
    "CandidateScore",
    "EdaRequest",
    "EdaResponse",
    "FoldScore",
    "ForecastError",
    "ForecastPoint",
    "ForecastRequest",
    "ForecastResponse",
    "IngestPayload",
    "Point",
]
