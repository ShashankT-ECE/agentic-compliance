"""
Synthetic telemetry record generator.

Produces deterministic telemetry sequences for testing the compliance
evaluator across various scenarios (compliant, non-compliant, missing
events, duplicates, out-of-order, multi-broker).

All generation methods are pure functions — same arguments always
produce the same records.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any


class TelemetryGenerator:
    """Generates synthetic broker telemetry records for testing.

    Every method returns a list of telemetry dicts conforming to the
    TelemetryEvent schema. Sequences are deterministic — calling any
    method with the same arguments always produces identical output.
    """

    # ── Record factory ───────────────────────────────────────────────

    @staticmethod
    def record(
        broker_id: str,
        timestamp: datetime,
        event_type: str,
        payload: dict[str, Any] | None = None,
        event_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a single telemetry record.

        Args:
            broker_id: Broker identifier.
            timestamp: UTC-aware datetime for the event.
            event_type: Event type string (e.g. 'margin_report_filed').
            payload: Optional event-specific payload.
            event_id: Optional unique event ID (auto-generated if None).

        Returns:
            Telemetry event dict compatible with TelemetryEvent model.
        """
        ts = timestamp if timestamp.tzinfo else timestamp.replace(tzinfo=timezone.utc)
        return {
            "broker_id": broker_id,
            "timestamp": ts,
            "event_type": event_type,
            "payload": payload or {},
            "event_id": event_id or "",
        }

    # ── Sequence generators ──────────────────────────────────────────

    @staticmethod
    def compliant_sequence(
        broker_id: str = "BROKER001",
        base_time: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Generate a fully compliant telemetry sequence.

        Events arrive in chronological order and all required triggers
        are present. Suitable for verifying a well-formed FSM reaches
        a terminal COMPLIANT state.

        Sequence: margin_report_filed at T0+2h.
        """
        t0 = _resolve_base(base_time)
        return [
            TelemetryGenerator.record(
                broker_id, t0 + timedelta(hours=2),
                "margin_report_filed",
                {"report_id": "RPT-001", "exchange": "NSE"},
            ),
        ]

    @staticmethod
    def non_compliant_sequence(
        broker_id: str = "BROKER001",
        base_time: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Generate a non-compliant telemetry sequence.

        Key events are missing — the FSM will not reach a terminal
        state. Useful for verifying NON_COMPLIANT / PENDING verdicts.

        Sequence: no relevant events.
        """
        return []

    @staticmethod
    def late_sequence(
        broker_id: str = "BROKER001",
        base_time: datetime | None = None,
        late_days: int = 5,
    ) -> list[dict[str, Any]]:
        """Generate a sequence where the required event is late.

        The event occurs after a typical T+3 deadline.

        Sequence: margin_report_filed at T0 + late_days.
        """
        t0 = _resolve_base(base_time)
        return [
            TelemetryGenerator.record(
                broker_id, t0 + timedelta(days=late_days),
                "margin_report_filed",
                {"report_id": "RPT-001", "exchange": "NSE"},
            ),
        ]

    @staticmethod
    def missing_event_sequence(
        broker_id: str = "BROKER001",
        base_time: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Generate a sequence with a gap — a required intermediate event
        is missing. The FSM expects a trigger that never arrives.

        Sequence: irrelevant event only (does not match any trigger).
        """
        t0 = _resolve_base(base_time)
        return [
            TelemetryGenerator.record(
                broker_id, t0 + timedelta(hours=1),
                "irrelevant_event",
                {"note": "does not match any trigger"},
            ),
        ]

    @staticmethod
    def duplicate_event_sequence(
        broker_id: str = "BROKER001",
        base_time: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Generate a sequence with duplicate events.

        The same event_type appears twice. The first triggers a
        transition; the second is a no-op (FSM already in the next
        state). Verifies idempotent duplicate handling.

        Sequence: margin_report_filed, margin_report_filed (dup).
        """
        t0 = _resolve_base(base_time)
        return [
            TelemetryGenerator.record(
                broker_id, t0 + timedelta(hours=1),
                "margin_report_filed",
                {"report_id": "RPT-001", "exchange": "NSE"},
            ),
            TelemetryGenerator.record(
                broker_id, t0 + timedelta(hours=3),
                "margin_report_filed",
                {"report_id": "RPT-001-dup", "exchange": "NSE"},
            ),
        ]

    @staticmethod
    def out_of_order_sequence(
        broker_id: str = "BROKER001",
        base_time: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Generate a sequence with out-of-order timestamps.

        Events are in reverse chronological order — the evaluator
        must sort before processing.

        Sequence (as returned): event_B (T+3h), event_A (T+1h).
        """
        t0 = _resolve_base(base_time)
        return [
            TelemetryGenerator.record(
                broker_id, t0 + timedelta(hours=3),
                "margin_report_filed",
                {"report_id": "RPT-002", "exchange": "BSE"},
            ),
            TelemetryGenerator.record(
                broker_id, t0 + timedelta(hours=1),
                "margin_report_filed",
                {"report_id": "RPT-001", "exchange": "NSE"},
            ),
        ]

    @staticmethod
    def multi_event_compliant(
        broker_id: str = "BROKER001",
        base_time: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Generate a multi-step compliant sequence.

        Sequence: trade_executed (T0) → margin_report_filed (T0+2h).
        Suitable for FSMs requiring a start_event trigger followed by
        the compliance action within the deadline.
        """
        t0 = _resolve_base(base_time)
        return [
            TelemetryGenerator.record(
                broker_id, t0,
                "trade_executed",
                {"trade_id": "T-001", "amount": 500000.0},
            ),
            TelemetryGenerator.record(
                broker_id, t0 + timedelta(hours=2),
                "margin_report_filed",
                {"report_id": "RPT-001", "exchange": "NSE"},
            ),
        ]

    @staticmethod
    def multi_event_late(
        broker_id: str = "BROKER001",
        base_time: datetime | None = None,
        late_days: int = 5,
    ) -> list[dict[str, Any]]:
        """Generate a multi-step sequence where the second event is late.

        Sequence: trade_executed (T0) → margin_report_filed (T0+late_days).
        """
        t0 = _resolve_base(base_time)
        return [
            TelemetryGenerator.record(
                broker_id, t0,
                "trade_executed",
                {"trade_id": "T-001", "amount": 500000.0},
            ),
            TelemetryGenerator.record(
                broker_id, t0 + timedelta(days=late_days),
                "margin_report_filed",
                {"report_id": "RPT-001", "exchange": "NSE"},
            ),
        ]

    @staticmethod
    def empty_sequence() -> list[dict[str, Any]]:
        """Return an empty telemetry sequence."""
        return []

    @staticmethod
    def custom_sequence(
        events_spec: list[dict[str, Any]],
        broker_id: str = "BROKER001",
        base_time: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Generate a sequence from a declarative spec.

        Each spec dict must have:
            event_type: str
            offset_minutes: int (from base_time)

        Example::

            TelemetryGenerator.custom_sequence([
                {"event_type": "trade_executed", "offset_minutes": 0},
                {"event_type": "margin_report_filed", "offset_minutes": 120},
            ])

        Args:
            events_spec: List of {event_type, offset_minutes, payload?} dicts.
            broker_id: Broker identifier.
            base_time: Reference timestamp.

        Returns:
            List of telemetry records in spec order.
        """
        t0 = _resolve_base(base_time)
        records: list[dict[str, Any]] = []
        for spec in events_spec:
            event_time = t0 + timedelta(minutes=spec["offset_minutes"])
            records.append(
                TelemetryGenerator.record(
                    broker_id=broker_id,
                    timestamp=event_time,
                    event_type=spec["event_type"],
                    payload=spec.get("payload"),
                )
            )
        return records


# ── Internal helpers ──────────────────────────────────────────────────


def _resolve_base(base_time: datetime | None) -> datetime:
    """Return base_time if given, otherwise a fixed deterministic default."""
    if base_time is not None:
        if base_time.tzinfo is None:
            return base_time.replace(tzinfo=timezone.utc)
        return base_time
    # Fixed reference: 2026-06-01T09:00:00Z (deterministic default)
    return datetime(2026, 6, 1, 9, 0, 0, tzinfo=timezone.utc)
