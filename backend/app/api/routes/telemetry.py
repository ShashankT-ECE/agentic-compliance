"""
API routes for telemetry data (M7).

Endpoints for ingesting broker telemetry events and querying them.
Uses an in-memory store (V1 — replace with database in M9).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.models.telemetry import TelemetryEvent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/telemetry", tags=["telemetry"])

# In-memory telemetry store (V1)
_telemetry_store: dict[str, list[TelemetryEvent]] = {}


def _get_telemetry_store() -> dict[str, list[TelemetryEvent]]:
    """Return the telemetry store (overridable for testing)."""
    return _telemetry_store


def _set_telemetry_store(store: dict[str, list[TelemetryEvent]]) -> None:
    """Override the telemetry store (for testing)."""
    global _telemetry_store
    _telemetry_store = store


# =========================================================================
# Request / response models
# =========================================================================


class IngestRequest(BaseModel):
    """Request body for POST /telemetry/ingest."""

    events: list[dict[str, Any]] = Field(..., min_length=1, description="List of telemetry events to ingest")
    broker_id: str | None = Field(default=None, description="Default broker_id for events without one")


class IngestResponse(BaseModel):
    """Response for POST /telemetry/ingest."""

    ingested: int
    rejected: int
    errors: list[str]


class TelemetryQueryResponse(BaseModel):
    """Response for GET /telemetry/query."""

    total: int
    events: list[dict[str, Any]]


# =========================================================================
# POST /telemetry/ingest
# =========================================================================


@router.post("/ingest", response_model=IngestResponse, status_code=201)
def ingest_telemetry(request: IngestRequest) -> dict[str, Any]:
    """Ingest one or more telemetry events.

    Each event must have a broker_id and event_type at minimum.
    Invalid events are rejected individually — valid events are still ingested.
    """
    store = _get_telemetry_store()
    ingested: list[TelemetryEvent] = []
    errors: list[str] = []

    for i, raw in enumerate(request.events):
        # Apply default broker_id if missing
        if "broker_id" not in raw and request.broker_id:
            raw = {**raw, "broker_id": request.broker_id}

        try:
            event = TelemetryEvent.model_validate(raw)
            ingested.append(event)
        except Exception as exc:
            errors.append(f"Event {i}: {exc}")
            logger.warning("Rejected telemetry event %d: %s", i, exc)

    # Group ingested events by broker_id
    for event in ingested:
        store.setdefault(event.broker_id, []).append(event)

    logger.info("Telemetry ingest: %d accepted, %d rejected", len(ingested), len(errors))

    return {
        "ingested": len(ingested),
        "rejected": len(errors),
        "errors": errors,
    }


# =========================================================================
# GET /telemetry/query
# =========================================================================


@router.get("/query", response_model=TelemetryQueryResponse)
def query_telemetry(
    broker_id: str | None = Query(default=None, description="Filter by broker ID"),
    event_type: str | None = Query(default=None, description="Filter by event type"),
    limit: int = Query(default=100, ge=1, le=10000, description="Max events to return"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
) -> dict[str, Any]:
    """Query ingested telemetry events.

    Supports filtering by broker_id and event_type with pagination.
    Results are sorted by timestamp descending.
    """
    store = _get_telemetry_store()

    # Collect all matching events
    all_events: list[TelemetryEvent] = []
    for bid, events in store.items():
        if broker_id and bid != broker_id:
            continue
        all_events.extend(events)

    # Filter by event_type
    if event_type:
        all_events = [e for e in all_events if e.event_type == event_type]

    # Sort by timestamp descending
    all_events.sort(key=lambda e: e.timestamp, reverse=True)

    total = len(all_events)
    page = all_events[offset : offset + limit]

    return {
        "total": total,
        "events": [e.model_dump(mode="json", exclude_none=True) for e in page],
    }


# =========================================================================
# GET /telemetry/query/{run_id} — query telemetry for a specific run
# =========================================================================


@router.get("/query/{run_id}", response_model=TelemetryQueryResponse)
def query_run_telemetry(run_id: str) -> dict[str, Any]:
    """Get telemetry events for a specific pipeline run."""
    from app.pipeline.runner import get_run_state

    state = get_run_state(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Pipeline run '{run_id}' not found")

    events = state.telemetry_events

    return {
        "total": len(events),
        "events": [_serialize_event(e) for e in events],
    }


# =========================================================================
# Internal helpers
# =========================================================================


def _serialize_event(event: Any) -> dict[str, Any]:
    """Serialize a TelemetryEvent to a JSON-safe dict."""
    try:
        return event.model_dump(mode="json", exclude_none=True)
    except AttributeError:
        return dict(event)
