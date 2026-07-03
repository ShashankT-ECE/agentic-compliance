"""
Obligation data models.

Defines Pydantic schemas for compliance obligations extracted from SEBI circulars.
These are the output of Node 1 (PDF Parser) and the input to Node 2 (FSM Extractor).
"""

from datetime import date
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator


class ObligationType(str, Enum):
    """Classification of compliance obligations extracted from circulars.

    V1 targets TIMELINE only (deadline-based: T+1, T+3, etc.).
    THRESHOLD and PROCEDURE are reserved for future milestones.
    """

    TIMELINE = "timeline"
    THRESHOLD = "threshold"
    PROCEDURE = "procedure"


class TimelineParams(BaseModel):
    """Time-based parameters for timeline obligations.

    Describes a deadline relative to a triggering event.
    Example: "Report must be filed within T+1 day" →
        offset=1, grace_period=0, unit="days"
    """

    offset: Annotated[int, Field(ge=0, description="Number of time units from the triggering event")]
    grace_period: Annotated[int, Field(ge=0, description="Additional grace period in the same unit", default=0)]
    unit: Literal["days", "hours", "months"] = Field(
        default="days",
        description="Time unit for offset and grace period",
    )


class ObligationClause(BaseModel):
    """A single compliance obligation extracted from a SEBI circular.

    Represents one atomic requirement that a broker must satisfy.
    Each clause is traceable back to the source circular text.
    """

    clause_id: str = Field(
        ...,
        description="Unique identifier for this clause (e.g., 'CIRC-2024-001-CL-03')",
        pattern=r"^[A-Z0-9\-_]+$",
    )
    circular_ref: str = Field(
        ...,
        description="Reference to the source SEBI circular (e.g., 'SEBI/HO/MIRSD/MIRSD-PoD-1/P/CIR/2024/001')",
    )
    clause_text: str = Field(
        ...,
        min_length=10,
        description="Verbatim or lightly-normalized text of the obligation clause",
    )
    obligation_type: ObligationType = Field(
        ...,
        description="Type of obligation (timeline, threshold, or procedure)",
    )
    timeline_params: TimelineParams | None = Field(
        default=None,
        description="Time-based parameters; required when obligation_type is TIMELINE",
    )
    effective_date: date | None = Field(
        default=None,
        description="Date from which this obligation takes effect",
    )
    applicable_entities: list[str] = Field(
        default_factory=list,
        description="List of broker/entity types this obligation applies to (e.g., ['stock_broker', 'clearing_member'])",
    )

    @model_validator(mode="after")
    def validate_timeline_params_required(self) -> "ObligationClause":
        """Ensure timeline obligations have timeline_params."""
        if self.obligation_type == ObligationType.TIMELINE and self.timeline_params is None:
            raise ValueError(
                f"Clause {self.clause_id}: timeline_params is required when obligation_type is TIMELINE"
            )
        return self

    @model_validator(mode="after")
    def validate_circular_ref_format(self) -> "ObligationClause":
        """Ensure circular_ref is not empty or whitespace-only."""
        if not self.circular_ref.strip():
            raise ValueError("circular_ref must not be empty or whitespace-only")
        return self
