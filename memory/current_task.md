# Current Task — Exact Resume Point

---

## Developer

Shashank

## Date

2026-07-03

## Branch

`dev`

---

## Current Feature

**M5 — Assertion Evaluator (Node 3)**

Objective: Implement the deterministic compliance evaluator that matches broker telemetry events against approved LockedFSMs to produce `ComplianceVerdict` records.

---

## Current File

*No active implementation file. M5 is the next milestone to implement.*

---

## Last Completed Step

M4 (HITL Gate) is complete:
- `backend/app/models/locked_fsm.py` — `LockStatus`, `AmendmentRecord`, `LockedFSM` (6 Pydantic validators)
- `backend/app/pipeline/nodes/hitl_gate.py` — `create_locked_fsms`, `approve_fsm`, `reject_fsm`, `amend_fsm`, integrity verification, persistence, `hitl_gate_node`
- `backend/app/api/routes/pipeline.py` — 6 HITL endpoints (list, get, approve, reject, amend, review history)
- `backend/app/pipeline/state.py` — `locked_fsms` type changed to `list[LockedFSM]`
- `backend/tests/test_hitl.py` — 46 tests

M0-M4 are all complete. 203 tests passing. All memory files synchronized.

---

## Next Immediate Task

Begin implementing M5 — Assertion Evaluator (Node 3). Start with:

1. `backend/app/utils/state_machine.py` — FSM evaluation engine (process events, match transitions, execute state changes)
2. `backend/app/utils/timeline_evaluator.py` — deadline/offset computation (compute T+0, T+1, T+3 offsets from event timestamps)
3. `backend/app/pipeline/nodes/evaluator.py` — evaluator node function (deterministic, NO LLM)
4. `backend/tests/test_evaluator.py` — comprehensive evaluator tests
5. `backend/tests/fixtures/mock_telemetry.json` — realistic event sequences

---

## Files To Open Next

1. `memory/project_roadmap.md` — M5 completion criteria (line 222)
2. `backend/app/models/verdict.py` — `ComplianceVerdict`, `VerdictStatus` model (output target)
3. `backend/app/models/locked_fsm.py` — `LockedFSM` model (input: `original_fsm: HybridFSM`)
4. `backend/app/models/fsm.py` — `HybridFSM`, `FSMTransition`, `TimelineRule` (evaluation logic)
5. `backend/app/models/telemetry.py` — `TelemetryEvent` (input event stream)
6. `backend/app/pipeline/nodes/evaluator.py` — scaffold TODO (rewrite from scratch)
7. `backend/app/utils/state_machine.py` — does not exist yet (create new)
8. `backend/app/utils/timeline_evaluator.py` — does not exist yet (create new)

## Commands To Run

```bash
cd backend && source .venv/bin/activate && python -m pytest tests/ -v
# Expected: 203 passed (M0-M4)
```

---

## Known Issues

- `backend/app/pipeline/nodes/evaluator.py` is a scaffold TODO — needs full implementation.
- `backend/app/utils/state_machine.py` does not exist — needs creation.
- `backend/app/utils/timeline_evaluator.py` does not exist — needs creation.
- `backend/app/utils/telemetry_gen.py` is a scaffold TODO — synthetic telemetry generator needed for tests.
- `backend/tests/fixtures/mock_telemetry.json` is a placeholder — needs realistic event sequences.
- No telemetry data has been generated yet.

---

## Warnings

- Node 3 (Assertion Evaluator) must **never** call an LLM — this is the single most important architectural constraint in the entire project.
- The evaluator must be a pure function: same FSMs + same events → same verdicts. No randomness, no external API calls.
- Time computations must use event timestamps, not wall clock time.
- The evaluator receives `LockedFSM` instances (from M4), not raw `HybridFSM`. Unlock the `original_fsm` field for evaluation.
- Every verdict must include an evidence trail: which events were matched, timeline status, current state.
