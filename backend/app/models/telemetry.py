"""
Telemetry data models.

Defines Pydantic schemas for broker telemetry events ingested into the
compliance pipeline. Events represent discrete timestamped records from
broker operational systems.

These are external inputs to the pipeline — consumed by Node 3 (Evaluator).
"""

from datetime import datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class BrokerInfo(BaseModel):
    """Identifying information for a registered stock broker."""

    broker_id: str = Field(
        ...,
        description="Unique broker identifier (e.g., 'B-12345')",
        pattern=r"^[A-Za-z0-9\-_]+$",
    )
    name: str = Field(
        ...,
        min_length=1,
        description="Registered name of the broker entity",
    )
    registration_number: str = Field(
        ...,
        min_length=1,
        description="SEBI registration number",
    )


class TelemetryEvent(BaseModel):
    """A single timestamped event from a broker's operational systems.

    Events are processed chronologically by the Evaluator (Node 3).
    Each event has a type that may trigger FSM transitions.
    """

    event_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique event identifier (auto-generated UUID v4 if not provided)",
    )
    broker_id: str = Field(
        ...,
        description="Broker identifier — must match a known BrokerInfo.broker_id",
        pattern=r"^[A-Za-z0-9\-_]+$",
    )
    event_type: str = Field(
        ...,
        min_length=1,
        description="Event type (e.g., 'trade_settled', 'margin_report_filed', 'client_onboarded')",
    )
    timestamp: datetime = Field(
        ...,
        description="UTC timestamp of the event occurrence",
    )
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary event-specific data (e.g., trade details, report metadata)",
    )
