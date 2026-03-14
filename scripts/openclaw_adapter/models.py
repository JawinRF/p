from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class InspectRequest(BaseModel):
    entry_id: str
    text: str
    ingestion_path: str
    source_type: str
    source_name: str
    session_id: str
    run_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class InspectResponse(BaseModel):
    verdict: str
    confidence: float
    reason: str
    layer_triggered: str
    normalized_text: str
    ticket_id: str | None
    placeholder: str | None
    audit: dict[str, Any]

