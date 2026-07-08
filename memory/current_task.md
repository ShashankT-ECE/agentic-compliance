# Current Task — Exact Resume Point

---

## Developer

Brad (Friend — Windows + WSL2)

## Date

2026-07-08

## Branch

`dev`

## Latest Commit

`401b659` — `feat(v1.0.2): improve audit report explanations and evaluation flow`

## Repository State

- **Working tree clean** — all V1.0.2 changes committed and pushed to `origin/dev`.
- **410 tests pass, 0 fail.**
- **Frontend builds clean** (52 modules, zero errors).
- **V1 is frozen.**

---

## Current Feature

**V2 Planning — Regulatory Intelligence Platform**

The V2 roadmap (`docs/v2_roadmap.md`) defines 10 milestones (M1–M10) evolving the
platform from single-circular compliance checking into a production-grade regulatory
intelligence platform with RAG architecture, vector search, multi-circular support,
diff agent, and full production deployment.

---

## V1.0.2 — COMPLETE ✅ (FROZEN)

All V1.0.2 work committed as `401b659` and pushed. V1 frozen — no further changes
except critical bug fixes.

---

## What Was Done

### V1.0.2 — Final Demo Polish + Evaluator Fix + Explanation UX

All completed, committed, and pushed (`401b659`):

- Dashboard state sync fix (`pipeline.py`)
- Linear workflow diagram redesign (`FSMViewer/index.tsx`)
- Terminology cleanup — FSM → Obligation, State → Status (`hitl.tsx`)
- `determine_compliance_status()` fix — trusts `self._current_state` (`state_machine.py`)
- Report `compliance_pct` formula fix — matches scoreboard (`reports.py`)
- Overdue transition integration — `transition_to()` + evaluator wiring (`state_machine.py`, `evaluator.py`)
- 6 new tests (transition_to unit + overdue integration) (`test_evaluator.py`)
- Explanation column — deterministic `_derive_explanation()` + frontend column (`reports.py`, `AuditReport/index.tsx`, `client.ts`)

### Verified end-to-end with official SEBI circular

- Circular: `SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/57` (April 28, 2025)
- Trigger → HITL → Resume → Evaluation → Scoreboard → Report
- 4 verdicts: 2 NON_COMPLIANT (LATE), 2 PENDING
- Explanation column populated for all rows — no "—" fallbacks
- State/Status consistency: resolved
- Hash chain: verified

---

## V1 Freeze — Final State

V1.0.2 is frozen. No further changes to V1 pipeline, models, evaluator, or API.

The following known items are deferred to V2:
- 11 diagnostic `console.log()` calls in `AuditReport/index.tsx` (non-functional, cosmetic only)
- In-memory stores (lost on restart)
- No authentication
- Frontend test suite (Vitest + React Testing Library)
- Docker Compose full-stack
- `docs/architecture.pdf` (ASCII placeholder)
- `poppler-utils` not installed

---

## Next Milestone

**M1 — Regulatory RAG Architecture** (see `docs/v2_roadmap.md` for full plan)

---

## Exact Next Task

1. **Ratify V2 roadmap** — review `docs/v2_roadmap.md` with both developers.
2. **Ratify proposed ADRs** — vector DB (pgvector), chunking strategy, embedding model, hybrid retrieval weights, conflict resolution.
3. **Begin M1 implementation** after roadmap and ADRs are approved.

---

## Remaining Known Issues

- **Console.log diagnostics** — ✅ Removed (2026-07-08).
- **3 of 4 verdicts PENDING in demo** — fixture lacks events matching `bye_laws_amended`, `dissemination_completed`, `margin_collected`, `circular_issued`. Fixture coverage gap — not a bug.
- **HITL queue accumulates historical runs** — stale directories from test runs; cleanup needed.
- `docs/architecture.pdf` broken (ASCII placeholder) — V2.
- `poppler-utils` not installed — V2.
- In-memory stores (lost on restart) — V2 (PostgreSQL).
- No authentication — V2.
- Docker Compose incomplete — V2 (M10).
- Frontend tests — V2 (M10).
- Large-document support (399-page Master Circular) — V2 (M1-M6).

---

## Files Most Likely Needed Next

1. `frontend/src/components/AuditReport/index.tsx` — console.log cleanup
2. `backend/app/utils/llm_client.py` — max_tokens tuning for large documents
3. `backend/app/pipeline/nodes/parser.py` — chunked parsing design
4. `memory/progress.md` — V2 planning
5. `docs/architecture.md` — V2 architecture

---

## Warnings

- Node 3 (Assertion Evaluator) must never call an LLM — hard architectural constraint.
- The 6 Node 3 safety gate tests + AST-level verification must always pass.
- `docs/architecture.pdf` is the canonical source of truth (broken — fix in V2).
- Do not redesign M0–M9 — all milestones are independently verified.
- V2 must be planned and approved before any implementation begins.
- `backup-m5` branch has early-development stubs — do NOT merge into it.
- Server must be restarted after any backend code change.
- **Do NOT modify V1 pipeline, models, evaluator, or API** — V1 is frozen.
