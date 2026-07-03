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

M4 — HITL Gate (Human-in-the-Loop FSM review gate between Node 2 and Node 3)

---

## Current File

*No active implementation file. M4 is the next milestone to implement.*

---

## Last Completed Step

M3 (Hash Chain Utility) is complete:
- `backend/app/utils/hash_chain.py` — `compute_hash`, `link`, `verify_chain`, `build_chain` (fully implemented in M0)
- `backend/tests/test_hash_chain.py` — 20 tests: hashing, linking, verification, tamper detection (modified data, broken links, reordering), 1000+ links, JSON roundtrip
- `backend/tests/test_models.py` — hash chain tests migrated out to dedicated file
- 157 tests passing (70 M0 + 35 M1 + 34 M2 + 20 M3)

All memory files updated. M0, M1, M2, M3 marked complete in project_roadmap.md.

---

## Next Immediate Task

Begin implementing M4 — HITL Gate. Start with:
1. `backend/app/models/locked_fsm.py` — `LockedFSM` schema with hash chain integration
2. `backend/app/pipeline/nodes/hitl_gate.py` — conditional routing logic
3. `backend/app/api/routes/pipeline.py` — HITL review endpoints

---

## Files To Open Next

1. `memory/project_roadmap.md` — M4 completion criteria (line 188)
2. `backend/app/models/scoreboard.py` — `HashLink`, `HashChain` models (needed for LockedFSM)
3. `backend/app/utils/hash_chain.py` — `link()`, `verify_chain()` (needed for FSM locking)
4. `backend/app/models/fsm.py` — `HybridFSM` model (wrapped by LockedFSM)
5. `backend/app/pipeline/state.py` — `CompliancePipelineState` (HITL status fields)
6. `backend/app/pipeline/nodes/hitl_gate.py` — scaffold TODO (create from scratch)

## Commands To Run

```bash
cd backend && source .venv/bin/activate && python -m pytest tests/ -v
```

---

## Known Issues

- `backend/app/pipeline/nodes/hitl_gate.py` does not exist yet — needs to be created.
- `backend/app/api/routes/pipeline.py` is a scaffold TODO.
- `backend/data/locked_fsms/` directory does not exist yet — needs `.gitignore` entry.

---

## Warnings

- HITL gate is a hard requirement — human must review FSMs before Node 3 executes.
- Locked FSMs must be hash-chained using the M3 utility.
- Locked FSM data stored in `backend/data/locked_fsms/` must be gitignored (production data).
- Node 3 (Assertion Evaluator) must never call an LLM — this is a hard architectural constraint.
