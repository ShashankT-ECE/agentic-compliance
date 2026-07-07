# Session Handoff

---

## Session Overview

| Field | Value |
|-------|-------|
| **Date** | 2026-07-07 |
| **Developer** | Brad (Friend — Windows + WSL2) |
| **Branch** | `dev` |
| **Latest Commit** | `2bcc1ec` — test: isolate runtime persistence during integration tests |
| **Repository State** | 5 files modified in working tree (3 V1.0.2 polish + 2 evaluator fixes). Nothing committed. |
| **Overall Status** | **V1.0.1 COMMITTED + PUSHED** — V1.0.2 fixes complete, uncommitted |

## What Was Done Today

### Phase 1 — Diagnostic Investigation

The user reported: generated report shows every verdict as `Status=PENDING`, `Compliance=0%`, even though FSM states changed during evaluation (one reached LATE).

Investigation traced the full pipeline:
1. Called `GET /api/pipeline/result/{run_id}` — all 4 verdicts had `status: "pending"` despite `current_state: "LATE"` on one.
2. Called `GET /api/reports/{report_id}` — identical verdicts. Report faithfully mirrors backend.
3. **Conclusion**: backend evaluator is the source — not the report or frontend.

**Smoking gun** (VER-68C15CC86544):
- `current_state: "LATE"` — FSM did transition (PENDING → LATE via `trade_executed`)
- `status: "pending"` — wrong, should be `non_compliant` per the LATE→NON_COMPLIANT mapping

### Phase 2 — Root Cause

**`StateMachine.determine_compliance_status()`** at `state_machine.py:164-202`:

```python
# OLD CODE (buggy)
def determine_compliance_status(self, deadline_met=None):
    terminal = self.is_terminal           # False (LATE has grace_expired→NON_COMPLIANT)
    has_transitions = self._transition_count > 0  # True

    if not terminal and not has_transitions:
        return "PENDING"
    if not terminal and has_transitions:
        return "DUE"                      # ← returned DUE, maps to PENDING
    ...
```

The method re-derived canonical status from `(is_terminal, has_transitions, deadline_met)` instead of reading the FSM's actual `self._current_state`. When the FSM was in `LATE` (non-terminal, has outgoing transitions), it returned `DUE`, which `_map_status` converted to `PENDING`.

The `_map_status` function itself was correct (`LATE → NON_COMPLIANT`) — it was just never given `LATE` as input.

### Phase 3 — Fixes Applied

**Fix 1: `backend/app/utils/state_machine.py`** — `determine_compliance_status()` rewritten to trust `self._current_state` as the canonical status. The FSM's transitions (including timeline-driven) are the source of truth. `deadline_met=False` still overrides to LATE regardless of FSM state (regulatory requirement: action completed after deadline counts as late).

**Fix 2: `backend/app/api/routes/reports.py`** — Report `compliance_pct` formula changed from `compliant / total * 100` to `compliant / (total - pending) * 100`, matching the scoreboard. When all are pending (evaluated=0), returns 100.0 ("nothing to fail yet").

### Phase 4 — Verification

| Check | Result |
|-------|--------|
| Backend test suite | **404 passed, 0 failed** |
| Frontend build | **52 modules, zero errors** |
| Live end-to-end demo | Trigger → approve 4 FSMs → resume → completed |
| Verdict CL-02 | `non_compliant` (was `pending` before fix) ✅ · timeline: start matched, deadline missed |
| Verdicts CL-01, CL-03, CL-04 | `pending` (correct — no matching events in demo fixture) ✅ |
| Scoreboard compliance_rate | 0.0 (= 0/1 evaluated) ✅ |
| Report compliance_pct | 0.0 (= 0/1 evaluated, matches scoreboard) ✅ |

### Remaining PENDING Verdicts (Fixture Gap)

3 of 4 verdicts remain PENDING because the demo telemetry fixture lacks events matching their FSM transition triggers:
- CL-01: trigger = `margin_collected` or `settlement_day_approaching` — fixture has neither; timeline start = `margin_call_issued` — not in fixture
- CL-03: trigger = `bye_laws_amended` or `amendment_process_started` — fixture has neither; timeline start = `circular_issued` — not in fixture
- CL-04: trigger = `dissemination_completed` or `dissemination_process_started` — fixture has neither; timeline start = `circular_issued` — not in fixture

This is a **test-fixture coverage gap**, not an evaluator bug. The LLM-generated FSMs reference obligation-specific triggers that the generic demo telemetry doesn't include.

## Uncommitted Working Tree

| File | Lines | Purpose |
|------|-------|---------|
| `backend/app/utils/state_machine.py` | +47/-? | `determine_compliance_status()` fix (today) |
| `backend/app/api/routes/reports.py` | +11/-? | Report formula alignment (today) |
| `backend/app/api/routes/pipeline.py` | +56/-? | V1.0.2 dashboard sync fix (previous session) |
| `frontend/src/components/FSMViewer/index.tsx` | ~483 changed | V1.0.2 linear workflow diagram (previous session) |
| `frontend/src/pages/hitl.tsx` | +19/-? | V1.0.2 onReviewed sync fix (previous session) |

## Remaining V1 Tasks (Before Freeze)

1. **Final manual browser demo** — confirm dashboard renders non-compliant verdicts correctly
2. **Decide on fixture gap** — enrich demo telemetry to trigger all FSMs, or document as known limitation
3. **Clean stale runtime data** — `rm -rf backend/data/locked_fsms/*`
4. **Commit V1.0.2** — all 5 files with descriptive message
5. **Push to origin**
6. **Declare V1 frozen**
7. **Begin V2 planning**

## Blockers

None. All V1 functional bugs are resolved. Remaining work is polish + fixture decisions.

## Next Milestone

**Freeze V1** → then **V2 — Production Hardening**

## Startup Instructions

```bash
cd /home/bradha/agentic-compliance
git checkout dev
git pull origin dev

# Kill any stale server
fuser -k 8000/tcp 2>/dev/null

# Verify
cd backend
source .venv/bin/activate
python -m pytest tests/ -v        # verify 404 tests pass
cd ../frontend
npm run build                      # verify build succeeds

# Start backend
cd ../backend && source .venv/bin/activate && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &

# Start frontend
cd ../frontend && npm run dev
```

Then read memory files in order:
1. `memory/project_handoff.md` — project overview
2. `memory/progress.md` — 30-second status
3. `memory/current_task.md` — exact resume point
4. `memory/decision_log.md` — architectural decisions
5. `memory/graphify_handoff.md` — pipeline graph topology
6. This file — session history

**CRITICAL RULES:**
- Do not redesign M0–M9 — all milestones are independently verified
- Propose and get V2 plan approved before any implementation
- All 404 tests must continue to pass
- Node 3 safety gate (no LLM) must never be violated
- Always restart the backend server after any code change
- **Do NOT commit or push** until manual browser verification succeeds
