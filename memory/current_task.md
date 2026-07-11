# Current Task — Exact Resume Point

---

## Developer

Brad (Friend — Windows + WSL2)

## Date

2026-07-11

## Branch

`dev`

## Latest Commit

`b71e86d` — `perf(fsm): batch extraction and configurable DeepSeek timeout`

## Repository State

- **Working tree has uncommitted changes** — Documentation polish and Docker improvements for hackathon submission.
- **642 tests pass, 0 fail**.
- **Frontend builds clean** (93 modules, zero errors).
- **V1 is frozen.** V2 M1–M4 are complete.

---

## Current Task

**Repository Polish for Hackathon Submission**

Preparing the repository for a national hackathon (SEBI TechSprint):
- README rewrite (professional, comprehensive)
- Docker configuration fixes (frontend service, health checks)
- Setup script fixes
- Documentation cleanup
- Memory file synchronization with actual repo state

---

## M3 — Evidence Traceability ✅ COMPLETE

Evidence pipeline: attribution → source mapping → bbox extraction → citations.
PDF.js viewer with highlighted passages. Full provenance chain API.

Committed as `1754c66`.

## M4 — PostgreSQL Migration ✅ COMPLETE

9 SQLAlchemy ORM models, 6 repositories, Alembic migration, graceful fallback.
Committed as `f231741`.

## M5–M6 — Pending

---

## Next Task

After hackathon submission polish is approved:
1. Review M5 design document.
2. Implement M5: Compliance Scenario Library.
3. Add scenario regression tests.

---

## Warnings

- Node 3 (Assertion Evaluator) must never call an LLM — hard architectural constraint.
- The 6 Node 3 safety gate tests + AST-level verification must always pass.
- Do not redesign M0–M4 — all milestones are independently verified.
- `backup-m5` branch has early-development stubs — do NOT merge into it.
- Server must be restarted after any backend code change.
- **Do NOT modify V1 pipeline, models, evaluator, or API** — V1 is frozen.
- **V1 backward compat preserved** — `use_rag=False` default, 410 V1 tests pass.
