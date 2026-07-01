# Current Task — Exact Resume Point

---

## Developer

Shashank

## Date

2026-07-01

## Branch

`dev`

---

## Current Feature

Memory system redesign — persistent memory workflow for async development.

---

## Current File

*No active implementation file. Memory system is fully scaffolded.*

---

## Last Completed Step

Rewrote the entire memory system (6 files) and CLAUDE.md as the permanent operating manual. The project remains at scaffold stage — no pipeline logic has been implemented.

---

## Current Work

Memory system redesign is complete. No active development in progress.

---

## Next Immediate Task

Begin implementing the backend pipeline. Suggested starting point: `backend/app/pipeline/state.py` — define the pipeline state schema that flows through all four nodes.

---

## Files To Open Next

1. `backend/app/pipeline/state.py` — define pipeline state
2. `backend/app/pipeline/nodes/parser.py` — implement PDF parsing
3. `backend/app/models/obligation.py` — define obligation data models

---

## Commands To Run

```bash
cd backend && python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
```

---

## Known Issues

- All source files are scaffold-only with TODO docstrings — nothing is implemented.
- Test files are empty placeholders.
- No database migrations exist yet.

---

## Warnings

- Node 3 (Assertion Evaluator) must never call an LLM — this is a hard architectural constraint.
- HITL gate before Node 3 must be respected in all designs.
