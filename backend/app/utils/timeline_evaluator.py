"""
Timeline evaluation utility for compliance obligations.

Provides deterministic deadline computation, parsing, and checking against
trading-day offsets (T+0, T+1, T+3) and arbitrary time windows.

CRITICAL: This module is 100% deterministic. No LLM, no randomness, no
external API calls. Every method is a pure function of its inputs.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any


class DeadlineType(Enum):
    """Canonical deadline types for SEBI compliance timelines."""

    T0 = "T"       # same trading day
    T1 = "T+1"     # next trading day
    T2 = "T+2"     # T+2
    T3 = "T+3"     # T+3
    CUSTOM = "custom"  # arbitrary day offset


class TimelineEvaluator:
    """Deterministic timeline and deadline evaluation engine.

    Computes absolute deadlines from descriptor strings or canonical
    offsets, checks whether events occurred within deadlines, and
    produces detailed timeline evaluation reports for audit trails.

    All methods are pure functions — identical inputs always produce
    identical outputs. No external state, no network calls, no LLM.
    """

    # Canonical deadline string → (DeadlineType, offset_days)
    _DEADLINE_MAP: dict[str, tuple[DeadlineType, int]] = {
        "T":   (DeadlineType.T0, 0),
        "T+0": (DeadlineType.T0, 0),
        "T+1": (DeadlineType.T1, 1),
        "T+2": (DeadlineType.T2, 2),
        "T+3": (DeadlineType.T3, 3),
    }

    # ── Deadline parsing ─────────────────────────────────────────────

    @staticmethod
    def parse_deadline(deadline_str: str) -> tuple[DeadlineType, int]:
        """Parse a deadline descriptor into (DeadlineType, offset_days).

        Supported formats:
            "T"      → same trading day (end-of-day)
            "T+0"    → same trading day
            "T+1"    → next trading day
            "T+2"    → T+2
            "T+3"    → T+3
            "T+N"    → arbitrary N-day offset

        Args:
            deadline_str: Deadline descriptor string.

        Returns:
            Tuple of (DeadlineType, offset_days). Defaults to (T0, 0)
            for unrecognised inputs.
        """
        cleaned = deadline_str.strip()

        # Canonical map lookup
        if cleaned in TimelineEvaluator._DEADLINE_MAP:
            return TimelineEvaluator._DEADLINE_MAP[cleaned]

        # T+N pattern (case-insensitive)
        upper = cleaned.upper()
        if upper.startswith("T+") or upper.startswith("T-"):
            try:
                offset = int(cleaned[2:])
                sign = 1 if "+" in cleaned else -1
                return (DeadlineType.CUSTOM, sign * abs(offset))
            except ValueError:
                pass

        # Fallback: treat as same-day (T)
        return (DeadlineType.T0, 0)

    @staticmethod
    def parse_offset_days(deadline_str: str) -> int:
        """Extract the number of days from a deadline descriptor.

        Convenience wrapper around parse_deadline — returns the offset
        in days directly.

        Args:
            deadline_str: Deadline descriptor (e.g. 'T+3').

        Returns:
            Integer number of days offset.
        """
        _, offset = TimelineEvaluator.parse_deadline(deadline_str)
        return offset

    # ── Deadline computation ─────────────────────────────────────────

    @staticmethod
    def compute_deadline(
        reference_time: datetime,
        deadline_str: str,
        grace_minutes: int = 0,
    ) -> datetime:
        """Compute the absolute deadline timestamp from a reference time.

        For T+N deadlines the deadline falls at 23:59:59 UTC on the
        target calendar date (end-of-trading-day semantics).

        Args:
            reference_time: The timestamp from which the deadline is
                measured (typically trade date or rule start event).
            deadline_str: Deadline descriptor (e.g. 'T', 'T+2').
            grace_minutes: Optional grace window in minutes added to
                the deadline.

        Returns:
            Absolute UTC-aware deadline datetime.
        """
        deadline_type, offset_days = TimelineEvaluator.parse_deadline(deadline_str)

        # Ensure reference is timezone-aware (assume UTC if naive)
        ref = _ensure_utc(reference_time)

        # T+N: deadline is end of trading day on the target date
        target_date = ref.date() + timedelta(days=offset_days)
        deadline = datetime(
            target_date.year,
            target_date.month,
            target_date.day,
            23, 59, 59,
            tzinfo=timezone.utc,
        )

        if grace_minutes:
            deadline += timedelta(minutes=grace_minutes)

        return deadline

    @staticmethod
    def compute_deadline_from_offset(
        reference_time: datetime,
        offset_days: int,
        grace_days: int = 0,
    ) -> datetime:
        """Compute the absolute deadline from an explicit day offset.

        Args:
            reference_time: The reference timestamp.
            offset_days: Number of calendar days from reference.
            grace_days: Additional grace days added to deadline.

        Returns:
            Absolute UTC-aware deadline datetime (end-of-day on target date).
        """
        ref = _ensure_utc(reference_time)
        total_days = offset_days + grace_days
        target_date = ref.date() + timedelta(days=total_days)
        return datetime(
            target_date.year,
            target_date.month,
            target_date.day,
            23, 59, 59,
            tzinfo=timezone.utc,
        )

    # ── Deadline checking ────────────────────────────────────────────

    @staticmethod
    def is_within_deadline(
        event_time: datetime,
        deadline: datetime,
    ) -> bool:
        """Check whether an event occurred on or before the deadline.

        Args:
            event_time: The event timestamp.
            deadline: The deadline timestamp.

        Returns:
            True if event_time <= deadline.
        """
        return _ensure_utc(event_time) <= _ensure_utc(deadline)

    @staticmethod
    def is_expired(
        deadline: datetime,
        as_of: datetime | None = None,
    ) -> bool:
        """Check whether a deadline has passed.

        Args:
            deadline: The deadline timestamp.
            as_of: Reference time (defaults to now UTC if None).

        Returns:
            True if as_of > deadline.
        """
        if as_of is None:
            as_of = datetime.now(timezone.utc)
        return _ensure_utc(as_of) > _ensure_utc(deadline)

    # ── Timeline evaluation ──────────────────────────────────────────

    @staticmethod
    def evaluate_timeline(
        events: list[dict[str, Any]],
        deadline_str: str,
        reference_time: datetime | None = None,
        grace_minutes: int = 0,
    ) -> dict[str, Any]:
        """Evaluate a sequence of events against a timeline obligation.

        Produces a detailed evaluation including the computed deadline,
        which events were on-time vs late, and whether the deadline was met.

        Args:
            events: Chronologically sorted event dicts, each with a
                'timestamp' key (ISO-8601 string or datetime).
            deadline_str: Deadline descriptor (e.g. 'T', 'T+2').
            reference_time: Reference timestamp for deadline computation.
                Defaults to earliest event timestamp.
            grace_minutes: Optional grace window in minutes.

        Returns:
            Timeline evaluation dict with keys:
                deadline_str, deadline, reference_time, deadline_met,
                late_events, on_time_events, grace_minutes.
        """
        if not events:
            return {
                "deadline_str": deadline_str,
                "deadline": None,
                "reference_time": None,
                "deadline_met": None,
                "late_events": [],
                "on_time_events": [],
                "grace_minutes": grace_minutes,
            }

        # Use earliest event as reference if none provided
        if reference_time is None:
            reference_time = _parse_timestamp(events[0]["timestamp"])

        deadline = TimelineEvaluator.compute_deadline(
            reference_time, deadline_str, grace_minutes
        )

        on_time: list[dict[str, Any]] = []
        late: list[dict[str, Any]] = []

        for event in events:
            event_time = _parse_timestamp(event["timestamp"])
            if TimelineEvaluator.is_within_deadline(event_time, deadline):
                on_time.append(event)
            else:
                late.append(event)

        return {
            "deadline_str": deadline_str,
            "deadline": deadline.isoformat(),
            "reference_time": _ensure_utc(reference_time).isoformat(),
            "deadline_met": len(late) == 0,
            "late_events": late,
            "on_time_events": on_time,
            "grace_minutes": grace_minutes,
        }

    @staticmethod
    def evaluate_timeline_rule(
        events: list[dict[str, Any]],
        rule: Any,  # TimelineRule (import would be circular; duck-typed)
    ) -> dict[str, Any]:
        """Evaluate a single HybridFSM TimelineRule against telemetry events.

        Finds the event matching the rule's start_event, computes the
        deadline from its timestamp, then checks whether all other events
        occurred within that deadline.

        Args:
            events: Chronologically sorted telemetry event dicts.
            rule: A TimelineRule-like object with attributes:
                start_event, deadline_offset, grace_period, time_unit,
                overdue_transition.

        Returns:
            Evaluation dict with: start_event_matched, start_timestamp,
            deadline, deadline_met, late_events, overdue_transition.
        """
        # Find the start event
        start_timestamp: datetime | None = None
        for event in events:
            if event.get("event_type") == rule.start_event:
                start_timestamp = _parse_timestamp(event["timestamp"])
                break

        if start_timestamp is None:
            return {
                "start_event": rule.start_event,
                "start_event_matched": False,
                "start_timestamp": None,
                "deadline": None,
                "deadline_met": None,
                "late_events": [],
                "overdue_transition": rule.overdue_transition,
            }

        # Compute deadline: start_time + offset + grace
        deadline = TimelineEvaluator.compute_deadline_from_offset(
            reference_time=start_timestamp,
            offset_days=rule.deadline_offset,
            grace_days=rule.grace_period,
        )

        # Check which events are late
        late: list[dict[str, Any]] = []
        for event in events:
            event_time = _parse_timestamp(event["timestamp"])
            if not TimelineEvaluator.is_within_deadline(event_time, deadline):
                late.append(event)

        return {
            "start_event": rule.start_event,
            "start_event_matched": True,
            "start_timestamp": start_timestamp.isoformat(),
            "deadline": deadline.isoformat(),
            "deadline_met": len(late) == 0,
            "late_events": late,
            "overdue_transition": rule.overdue_transition,
        }


# ── Internal helpers ──────────────────────────────────────────────────


def _parse_timestamp(ts: object) -> datetime:
    """Parse a timestamp value to a UTC-aware datetime.

    Accepts ISO-8601 strings and datetime objects. Naive datetimes
    are treated as UTC.
    """
    if isinstance(ts, datetime):
        return _ensure_utc(ts)
    if isinstance(ts, str):
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return _ensure_utc(dt)
    raise TypeError(f"Cannot parse timestamp of type {type(ts).__name__}: {ts!r}")


def _ensure_utc(dt: datetime) -> datetime:
    """Ensure a datetime is UTC-aware. Naive datetimes are treated as UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt
