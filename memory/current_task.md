# Current Task — Exact Resume Point

---

## Developer

Brad (Friend — Windows + WSL2)

## Date

2026-07-07

## Branch

`dev`

## Latest Commit

`2bcc1ec` — `test: isolate runtime persistence during integration tests`

> Two commits have landed since the 2026-07-06 memory update:
> - `a1ee2ee` — `docs: synchronize project memory after V1.0.1 verification`
> - `2bcc1ec` — `test: isolate runtime persistence during integration tests`

## Repository State

- `dev` has 2 new commits since last memory sync (pushed by Shashank)
- Working tree has **5 modified files** — 3 V1.0.2 polish + 2 today's fixes
- All 5 files are **uncommitted**
- **404 tests pass, 0 fail**
- **Frontend builds clean** (52 modules, zero errors)

---

## Current Feature

**V1.0.2 — Final Demo Polish + Evaluator Fix**

### V1.0.2 polish (existing, uncommitted)

| File | Change |
|------|--------|
| `backend/app/api/routes/pipeline.py` | Dashboard state sync (fetchStatus on every HITL review) |
| `frontend/src/components/FSMViewer/index.tsx` | Linear workflow diagram (no overlapping arrows) |
| `frontend/src/pages/hitl.tsx` | onReviewed sync fix + terminology cleanup |

### Today's fixes (2026-07-07, uncommitted)

| File | Change |
|------|--------|
| `backend/app/utils/state_machine.py` | `determine_compliance_status()` now trusts `self._current_state` |
| `backend/app/api/routes/reports.py` | Report `compliance_pct` now matches scoreboard formula |

---

## What Was Done Today

### Phase 1 — Diagnostic Investigation

- Traced the "all PENDING" report bug through the full pipeline (trigger → evaluator → scoreboard → report → frontend)
- Called live API on the completed run and compared raw verdicts vs report
- **Finding**: report faithfully mirrors backend — backend already returns all-PENDING verdicts
- **Smoking gun**: VER-68C15CC86544 had `current_state="LATE"` but `status="pending"`

### Phase 2 — Root Cause Identification

**Bug in `StateMachine.determine_compliance_status()`** at `state_machine.py:164-202`:

The method re-derived canonical status from `(is_terminal, has_transitions, deadline_met)` but never read `self._current_state`. When the FSM transitioned to LATE (which has an outgoing `grace_expired → NON_COMPLIANT` transition), the method saw "non-terminal + has transitions" and returned `DUE`, which `_map_status` turned into `PENDING`.

Two decision points mattered:
1. `is_terminal` = whether current state has NO outgoing transitions. LATE had one → `False`.
2. `has_transitions` = whether any transition fired. One had → `True`.
3. Branch: `not terminal and has_transitions` → returns `DUE` → maps to `PENDING`.

**Contributing factor**: Report formula `compliant / total * 100` counted pending verdicts in the denominator, giving 0% even when nothing could be evaluated yet. Scoreboard correctly used `compliant / (total - pending)`.

### Phase 3 — Fix Implementation

**Fix 1 — `state_machine.py`** (lines 164-200):
- Rewrote `determine_compliance_status()` to trust `self._current_state` as the canonical status
- The FSM's transitions (including timeline-driven ones) are the source of truth
- `deadline_met=False` still overrides to LATE regardless of FSM state (regulatory requirement)
- Removed the faulty `(is_terminal, has_transitions)` branch logic

**Fix 2 — `reports.py`** (lines 96-106):
- Changed formula from `compliant / total * 100` to `compliant / (total - pending) * 100`
- When all are pending (evaluated=0), returns 100.0 (matches scoreboard: "nothing to fail yet")

### Phase 4 — Verification

| Check | Result |
|-------|--------|
| Backend test suite | **404 passed, 0 failed** |
| Frontend build | **52 modules, zero errors** |
| Live end-to-end demo | Pipeline triggered → 4 FSMs approved → resumed → completed |
| Verdict statuses | CL-02: `non_compliant` (was `pending` before fix) ✅ |
| | 3 others: `pending` (correct — no matching events in demo fixture) ✅ |
| Scoreboard compliance_rate | 0.0 (= 0/1 evaluated) ✅ |
| Report compliance_pct | 0.0 (= 0/1 evaluated, matches scoreboard) ✅ |

---

## Next Immediate Task

**Complete V1.0.2 and freeze V1** — when resuming:

1. Final manual browser end-to-end demo to confirm dashboard renders new verdicts.
2. Review the 3 remaining PENDING verdicts — decide whether to enrich demo fixture or accept as-is (they're correct given the fixture's event types).
3. Clean stale runtime data (cleanup script or manual `rm`).
4. Commit V1.0.2 (all 5 files).
5. Push to origin.
6. Declare V1 frozen.
7. Begin V2 planning.

---

## Remaining Known Issues

- **3 of 4 verdicts remain PENDING** — demo telemetry fixture has no events matching the FSM transition triggers (`bye_laws_amended`, `dissemination_completed`, `margin_collected`). Timeline start events (`circular_issued`, `margin_call_issued`) also absent. This is a **fixture coverage gap**, not an evaluator bug.
- **HITL queue accumulates historical runs** — ~74 stale directories from test runs; cleanup needed.
- **Dashboard browser workflow** not yet confirmed with the fixed verdict statuses.
- `docs/architecture.pdf` broken (ASCII placeholder) — V2.
- `poppler-utils` not installed — V2.
- In-memory stores (lost on restart) — V2 (PostgreSQL).
- No authentication — V2.
- Docker Compose incomplete — V2.
- Frontend tests — V2.

---

## Files Most Likely Needed Next

1. `CLAUDE.md` — operating manual
2. `memory/session_handoff.md` — today's session details
3. `memory/progress.md` — updated completion status
4. `frontend/src/pages/index.tsx` — dashboard rendering of verdicts
5. `frontend/src/components/AuditReport/index.tsx` — report display
6. `backend/tests/fixtures/sample_telemetry.json` — demo fixture (may need enrichment)
7. `scripts/run_demo.sh` — end-to-end demo script

---

## Warnings

- Node 3 (Assertion Evaluator) must never call an LLM — hard architectural constraint.
- The 6 Node 3 safety gate tests + AST-level verification must always pass.
- `docs/architecture.pdf` is the canonical source of truth (broken — fix in V2).
- Do not redesign M0–M9 — all milestones are independently verified.
- V2 must be planned and approved before any implementation begins.
- `backup-m5` branch has early-development stubs — do NOT merge into it.
- Server must be restarted after any backend code change.
- **Do NOT commit or push** until manual browser verification succeeds.
