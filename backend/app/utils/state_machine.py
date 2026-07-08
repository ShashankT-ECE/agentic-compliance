"""
Deterministic finite-state-machine execution engine.

Executes FSM transitions based on telemetry event triggers against
HybridFSM definitions produced by Node 2 and approved at the HITL gate.

CRITICAL: 100% deterministic. No LLM, no randomness, no external calls.
Same FSM + same events always produces the same transition history.
"""

from __future__ import annotations

from typing import Any

from app.models.fsm import FSMTransition, HybridFSM


class StateMachine:
    """Deterministic FSM executor for compliance verification.

    Takes an approved HybridFSM and processes telemetry events against it.
    Every transition is recorded for the evidence trail.

    The FSM validates its definition on construction, builds an O(1)
    transition lookup from the HybridFSM model, and processes events
    in the order they are provided (the caller is responsible for
    chronological sorting).

    Canonical compliance statuses (from fsm.py CANONICAL_STATES):
        PENDING, DUE, COMPLIANT, LATE, NON_COMPLIANT
    """

    STATUS_PENDING = "PENDING"
    STATUS_DUE = "DUE"
    STATUS_COMPLIANT = "COMPLIANT"
    STATUS_LATE = "LATE"
    STATUS_NON_COMPLIANT = "NON_COMPLIANT"

    def __init__(self, fsm: HybridFSM) -> None:
        """Initialise the state machine from a HybridFSM.

        Args:
            fsm: An approved HybridFSM from Node 2 / HITL gate.

        Raises:
            ValueError: If the FSM definition is structurally invalid.
        """
        self.fsm = fsm
        self._current_state: str = fsm.initial_state
        self._history: list[dict[str, Any]] = []
        self._transition_count: int = 0
        self._event_count: int = 0

        # O(1) transition lookup: source_state → [(trigger_event, FSMTransition)]
        self._transition_map: dict[str, list[tuple[str, FSMTransition]]] = {}
        for t in fsm.transitions:
            self._transition_map.setdefault(t.from_state, []).append(
                (t.trigger_event, t)
            )

        # Build set of state names
        self._state_names: set[str] = {s.name for s in fsm.states}

    # ── Read-only properties ─────────────────────────────────────────

    @property
    def current_state(self) -> str:
        """The FSM's current state name."""
        return self._current_state

    @property
    def is_terminal(self) -> bool:
        """Whether the current state has no outgoing transitions."""
        return self._current_state not in self._transition_map

    @property
    def is_initial(self) -> bool:
        """Whether the FSM is still in its initial state (no transitions fired)."""
        return self._transition_count == 0

    @property
    def history(self) -> list[dict[str, Any]]:
        """A copy of the complete transition history."""
        return list(self._history)

    @property
    def transition_count(self) -> int:
        """How many transitions have been executed."""
        return self._transition_count

    @property
    def event_count(self) -> int:
        """How many events have been processed."""
        return self._event_count

    # ── Event processing ─────────────────────────────────────────────

    def apply_event(self, event: dict[str, Any]) -> tuple[bool, dict | None]:
        """Attempt to apply a telemetry event as a transition trigger.

        A transition fires when a transition exists whose from_state
        matches the current state AND whose trigger_event matches the
        event's ``event_type``.

        Only the *first* matching transition is taken (deterministic
        resolution — the caller must ensure FSM definitions are unambiguous).

        Args:
            event: Telemetry event dict with at minimum:
                ``event_type`` (str) — the event type name.
                ``timestamp`` — ISO-8601 string or datetime.
                ``event_id`` — optional unique ID.
                ``payload`` — optional dict of event-specific data.

        Returns:
            Tuple of ``(transitioned, record)``. ``record`` is None if
            no transition fired.
        """
        self._event_count += 1
        event_type = event.get("event_type", "")
        candidates = self._transition_map.get(self._current_state, [])

        for trigger, transition in candidates:
            if trigger == event_type:
                source = self._current_state
                target = transition.to_state
                self._current_state = target
                self._transition_count += 1

                record = {
                    "transition_index": self._transition_count,
                    "event_index": self._event_count,
                    "source": source,
                    "target": target,
                    "trigger": event_type,
                    "event_type": event_type,
                    "event_timestamp": event.get("timestamp"),
                    "event_id": event.get("event_id"),
                    "event_payload": event.get("payload", {}),
                }
                self._history.append(record)
                return (True, record)

        return (False, None)

    def apply_events(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Apply a chronologically sorted sequence of events.

        Events are processed in the order given — the caller is
        responsible for sorting by timestamp before calling.

        Args:
            events: Telemetry events sorted by timestamp ascending.

        Returns:
            The complete transition history after processing.
        """
        for event in events:
            self.apply_event(event)
        return self.history

    def transition_to(
        self,
        target_state: str,
        reason: str = "timeline_overdue",
    ) -> bool:
        """Synthetically advance to a target state (timeline-driven).

        Unlike :meth:`apply_event`, this does not require a matching
        event trigger.  It is called by the evaluator when a timeline
        rule's deadline has elapsed and the ``overdue_transition`` must
        be applied to the FSM.

        The transition is recorded in the history with ``reason`` as the
        trigger so the evidence trail shows that the timeline evaluator —
        not a telemetry event — advanced the state.

        Args:
            target_state: Canonical state to transition to (e.g. ``"LATE"``).
            reason: Identifier for the trigger in the evidence trail
                (default ``"timeline_overdue"``).

        Returns:
            ``True`` if the transition was applied, ``False`` if the FSM
            was already in *target_state* or the state is unknown.
        """
        if target_state == self._current_state:
            return False

        if target_state not in self._state_names:
            return False

        source = self._current_state
        self._current_state = target_state
        self._transition_count += 1

        record: dict[str, Any] = {
            "transition_index": self._transition_count,
            "event_index": self._event_count,
            "source": source,
            "target": target_state,
            "trigger": reason,
            "event_type": reason,
            "event_timestamp": None,
            "event_id": None,
            "event_payload": {"reason": reason},
        }
        self._history.append(record)
        return True

    # ── Compliance determination ─────────────────────────────────────

    def determine_compliance_status(
        self,
        deadline_met: bool | None = None,
    ) -> str:
        """Determine the canonical compliance status.

        Derives the status from the FSM's *actual current state* rather
        than re-deriving it from (is_terminal, has_transitions).  The FSM's
        transitions — including those driven by overdue timeline rules — are
        the source of truth for where the machine landed.

        The ``deadline_met`` parameter from the timeline evaluator is used
        as an override: a missed deadline escalates even a COMPLIANT
        terminal state to LATE (the action was completed, but too late).

        Args:
            deadline_met: Optional timeline evaluation result.
                None → deadline not considered (trust FSM state).
                True  → on time — trust FSM state.
                False → missed deadline — forces LATE regardless of FSM state.

        Returns:
            One of the five canonical status strings.
        """
        state = self._current_state

        # Timeline override: a missed deadline always means LATE, even if
        # the FSM reached COMPLIANT (the action happened, but after the
        # regulatory cutoff).
        if deadline_met is False:
            return self.STATUS_LATE

        # Otherwise trust the FSM: it already reflects the correct canonical
        # status (COMPLIANT, LATE, NON_COMPLIANT, DUE, or PENDING).
        return state

    # ── Lifecycle ────────────────────────────────────────────────────

    def reset(self) -> None:
        """Reset to initial state (enables replay verification)."""
        self._current_state = self.fsm.initial_state
        self._history = []
        self._transition_count = 0
        self._event_count = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize current machine state for audit trails."""
        return {
            "fsm_id": self.fsm.fsm_id,
            "obligation_ref": self.fsm.obligation_ref,
            "circular_ref": self.fsm.circular_ref,
            "initial_state": self.fsm.initial_state,
            "current_state": self._current_state,
            "is_terminal": self.is_terminal,
            "transition_count": self._transition_count,
            "event_count": self._event_count,
            "history": self._history,
        }
