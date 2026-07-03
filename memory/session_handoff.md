# Session Handoff

---

## Session Overview

| Field | Value |
|-------|-------|
| **Date** | 2026-07-03 |
| **Developer** | Shashank |
| **Branch** | `dev` |
| **Duration** | ~2.5 hours |
| **Environment** | Linux |

## What Was Completed

### M2 — FSM Extractor (Node 2) ✅

Implemented the entire M2 milestone from `project_roadmap.md`:

**FSM extractor node (`backend/app/pipeline/nodes/fsm_extractor.py`):**
- `extract_fsms(clauses, circular_ref, llm_client)` — primary async entry point
- `load_fsm_prompt_template()` — loads markdown prompt from `app/prompts/fsm_extractor_prompt.md`
- `_parse_fsm_dict()` — dict-to-HybridFSM with pre-Pydantic checks:
  - Canonical states validation (all 5 required)
  - Minimum 3 transitions enforced
  - Minimum 1 timeline rule enforced
  - Initial state forced to PENDING
  - Nested Pydantic validation for FSMState, FSMTransition, TimelineRule
- `_validate_fsm_states()` — checks all 5 canonical states present before Pydantic
- `persist_fsms(fsms, circular_ref, output_dir)` — writes each FSM as individual JSON file + `_index.json` manifest under `data/extracted/{circular_ref_slug}/`
- `fsm_extractor_node(state, llm_client)` — LangGraph node function for M7 integration
- Reuses `_extract_json_from_response` from parser.py (Node 1)

**LLM prompt template (`backend/app/prompts/fsm_extractor_prompt.md`):**
- 200+ line markdown system prompt
- Complete HybridFSM schema definition with all 5 canonical states
- Field mapping from ObligationClause.timeline_params → TimelineRule
- 3 detailed examples using real SEBI circular obligations (CL-01 timeline T+1, CL-02 offset=0, CL-03 procedure)
- 5 edge case rules (missing timeline_params, offset=0, procedure type, multiple entities, ambiguous triggers)
- 7 output format rules

**JSON extraction fix (M1 utility):**
- `_extract_json_from_response` in `parser.py` updated to handle single JSON objects (not just arrays). Added 3 new extraction paths: raw single object, fenced single object, regex-extracted single object. Required for FSM extraction where the LLM may return `{...}` instead of `[{...}]`.

**Tests (`backend/tests/test_fsm.py`):**
- **34 tests, all passing**
- `TestValidateFsmStates` (5): all 5 canonical states present, missing states, missing single state, missing states key, non-list states
- `TestParseFsmDict` (10): valid timeline FSM, valid procedure FSM, circular_ref fill, initial_state override, too few transitions, missing timeline rules, missing states, invalid transition state, missing timeline fields, terminal state check
- `TestFsmPromptLoading` (2): load default, nonexistent path
- `TestExtractFsms` (12): successful 4-FSM extraction, empty clauses, empty LLM response, invalid JSON, LLM error propagation, partial valid survival, all-invalid raise, markdown-fenced response, single clause → single FSM, all 5 canonical states verification, deadline transition verification, unique FSM IDs
- `TestPersistFsms` (4): writes files + index, empty FSMs, roundtrip re-read + validate, obligation traceability
- `test_canonical_states_constant` (1): verify CANONICAL_STATES set

## M2 Completion Criteria Verification

| Criteria | Status |
|----------|--------|
| FSM extractor produces `List[HybridFSM]` from `List[ObligationClause]` | ✅ Done |
| FSMs correctly encode timeline-based obligations (deadlines relative to trigger events) | ✅ T+1 settlement, advance-of-trade, 90-day/30-day procedure fallbacks |
| FSMs include all states: PENDING, DUE, COMPLIANT, LATE, NON_COMPLIANT | ✅ Enforced by `_validate_fsm_states` |
| FSMs include at least one time-based transition (PENDING → LATE if deadline passes) | ✅ Enforced by min 1 timeline_rule check |
| FSM validation rejects malformed state machines | ✅ Missing states, too few transitions, missing timeline rules, invalid transition states — all tested |
| Extracted FSMs are persisted to `data/extracted/` as JSON | ✅ Individual FSM files + `_index.json` manifest |
| Tests pass with parser output fixtures | ✅ 4 real obligations from SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/57 |

## Files Changed (this session)

### New files:
- `backend/app/prompts/fsm_extractor_prompt.md` — LLM system prompt for FSM generation
- `backend/tests/test_fsm.py` — 34 comprehensive tests

### Rewritten files (were scaffold TODOs):
- `backend/app/pipeline/nodes/fsm_extractor.py` — Full FSM extractor node

### Modified files (required bug fix):
- `backend/app/pipeline/nodes/parser.py` — `_extract_json_from_response` now handles single JSON objects (3 new extraction paths). Required because FSM LLM responses may be single objects `{...}` not arrays `[{...}]`.
- `backend/tests/test_parser.py` — Updated `test_json_object_not_array` → `test_single_json_object_wrapped_in_list` to match new behavior

### Files NOT modified:
- All M0 model files (fsm.py, obligation.py, telemetry.py, verdict.py, scoreboard.py)
- Pipeline state, hash chain, database
- pdf_ingest.py, llm_client.py
- All existing tests pass (85 M0 + 35 M1)

## Blockers

None. M2 is self-contained. Ready for M3 (Hash Chain Utility) or M4 (HITL Gate), depending on chosen ordering.

## Important Discoveries

- The `_extract_json_from_response` function in parser.py needed to handle single JSON objects — the FSM prompt allows the LLM to return `{...}` for a single FSM, not just `[{...}]`. The fix added 3 extraction paths (raw, fenced, regex) for single objects. This is a legitimate shared-utility fix, not an M1 redesign.
- The FSM extractor enforces more pre-Pydantic checks than the parser (canonical states, min transitions, min timeline rules) because invalid FSMs are harder for the LLM to self-correct than invalid clauses. The extra validation catches structural errors early with clear messages.
- `persist_fsms` uses a directory-per-circular structure with a `_index.json` manifest — this makes it easy to find FSMs for a specific circular without scanning all files.
- The prompt instructs the LLM to generate a 90-day default deadline for procedure-type obligations — this is documented as a fallback with lower extraction confidence.

## Testing Performed

```bash
cd backend && source .venv/bin/activate
python -m pytest tests/ -v
# 154 passed in 0.17s
# 85 M0 + 35 M1 + 34 M2
```

## Environment Notes

- Linux, Python 3.10.12, Pydantic 2.x
- `data/extracted/` directory is created at runtime by `persist_fsms()` — no manual setup needed
- All packages in requirements.txt are installed in the venv

---

## Last Words For The Next Developer

M2 is done. The FSM extractor converts obligation clauses into validated HybridFSMs and persists them to disk. The next milestones:

Dependency chain:
```
M0 ✅ → M1 ✅ → M2 ✅ → M4 (HITL Gate) → M5 (Evaluator) → M6 (Scoreboard) → M7 (API) → M8 (Frontend) → M9 (E2E)
               M3 (Hash Chain) can run alongside M1/M2 (only depends on M0)
```

Key files to open for M3 or M4:
- `backend/app/utils/hash_chain.py` — hash chain utility (already implemented in M0, needs tests in M3)
- `backend/app/pipeline/nodes/hitl_gate.py` — HITL gate (current: not yet created)
- `backend/app/api/routes/pipeline.py` — HITL review endpoints (current: scaffold TODO)
- `backend/app/models/` — may need `locked_fsm.py` for M4

**NOTE: This session's changes have NOT been committed or pushed.** Per the developer's instruction: "Do not commit. Do not push."

---

## 2026-07-03 (Session 4) — M3 Hash Chain Utility ✅

### What was done
M3's hash chain implementation was already functionally complete from M0 (`hash_chain.py` — `compute_hash`, `link`, `verify_chain`, `build_chain`). This session completed the remaining roadmap deliverables:

- **Created `backend/tests/test_hash_chain.py`** — dedicated test file with 20 tests:
  - `TestComputeHash` (5): bytes, dict, deterministic, key-order-independent, invalid type
  - `TestLink` (2): genesis, chain
  - `TestVerifyChain` (10): valid, empty, single, tampered, broken, reordered, HashChain object, wrong genesis, **1000+ links**
  - `TestBuildChain` (2): build, empty
  - `TestJsonRoundtrip` (2): roundtrip, empty chain roundtrip
- **Removed** 17 hash chain tests from `test_models.py` (migrated to dedicated file)
- **Removed** hash chain import from `test_models.py`
- **Zero production code changes** — `hash_chain.py` unchanged

### New tests added (2)
- `test_1000_plus_links` — builds 1001-link chain, verifies, checks ordering, verifies tamper detection at scale
- `test_roundtrip` — `build_chain` → `model_dump_json` → `model_validate_json` → `verify_chain` == True, all link fields preserved

### M3 Completion Criteria

| Criteria | Status |
|----------|--------|
| `compute_hash`, `link`, `verify_chain` implemented and tested | ✅ (M0) |
| Chain verification detects tampering (modified data, broken link, reordered links) | ✅ |
| Hash chain can serialize/deserialize to JSON for storage | ✅ (new roundtrip test) |
| Edge cases: empty chain, single-link chain, chain with 1000+ links | ✅ (new 1000+ links test) |
| Tests pass with tampering scenarios | ✅ |
| Dedicated `test_hash_chain.py` file | ✅ |

### Test Results
```bash
157 passed in 0.21s
# 70 M0 models + 35 M1 parser + 34 M2 FSM + 20 M3 hash chain (17 migrated + 2 new + 1 reorganized)
```

**NOTE: This session's changes have NOT been committed or pushed.** Per the developer's instruction: "Do not commit. Do not push."

---

## 2026-07-03 (Session 5) — M4 HITL Gate ✅

### Files created
- `backend/app/models/locked_fsm.py` — `LockStatus` enum, `AmendmentRecord`, `LockedFSM` (6 Pydantic validators)
- `backend/app/pipeline/nodes/hitl_gate.py` — `create_locked_fsms`, `approve_fsm`, `reject_fsm`, `amend_fsm`, `verify_locked_fsm_integrity`, `build_hitl_hash_chain`, `persist_locked_fsms`, `load_locked_fsms`, `hitl_gate_node`
- `backend/tests/test_hitl.py` — 46 tests

### Files modified
- `backend/app/pipeline/state.py` — `locked_fsms` type: `list[HybridFSM]` → `list[LockedFSM]`
- `backend/app/api/routes/pipeline.py` — 6 HITL endpoints (list, get, approve, reject, amend, review history)
- `backend/tests/test_models.py` — updated `test_full_pipeline_state_roundtrip` for LockedFSM

### M4 Completion Criteria — all met
- Locked FSM includes hash chain link, approval metadata, and original FSM data
- Locked FSMs stored in `data/locked_fsms/{run_id}/` (individual JSON, pipeline state, review log, hash chain)
- 6 API endpoints with proper status codes (200, 400, 404, 409, 422, 500)
- Pipeline pause/resume: `AWAITING_APPROVAL` → `APPROVED` on all-resolved, `REJECTED` on any-rejected
- Hash chain verifies locked FSM integrity; tamper detection works
- 46 tests covering all HITL paths

### Test Results
```
203 passed, 1 warning in 0.83s
68 M0 + 35 M1 + 34 M2 + 20 M3 + 46 M4
```

**NOTE: This session's changes have NOT been committed or pushed.**
