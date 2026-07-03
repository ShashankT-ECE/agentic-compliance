"""
Data models for the Agentic Compliance pipeline.

All models use Pydantic v2 for validation and serialization.
Types are designed to flow through the 4-node pipeline:
  Node 1 (PDF Parser) → Node 2 (FSM Extractor) → HITL Gate → Node 3 (Evaluator) → Node 4 (Scoreboard)
"""

from app.models.obligation import ObligationClause, ObligationType, TimelineParams
from app.models.telemetry import BrokerInfo, TelemetryEvent
from app.models.fsm import FSMState, FSMTransition, HybridFSM, TimelineRule
from app.models.verdict import ComplianceVerdict, VerdictStatus
from app.models.scoreboard import BrokerScore, ObligationResult, Scoreboard

__all__ = [
    # Obligation
    "ObligationType",
    "TimelineParams",
    "ObligationClause",
    # Telemetry
    "TelemetryEvent",
    "BrokerInfo",
    # FSM
    "FSMState",
    "FSMTransition",
    "TimelineRule",
    "HybridFSM",
    # Verdict
    "VerdictStatus",
    "ComplianceVerdict",
    # Scoreboard
    "ObligationResult",
    "BrokerScore",
    "Scoreboard",
]
