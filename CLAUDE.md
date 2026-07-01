# Agentic Compliance — Claude Operating Manual

## Project Mission

Automated compliance verification for stock brokers against SEBI regulatory circulars. Built for the **SEBI Securities Market TechSprint Problem Statement 2**.

Architectural philosophy:
- **LLMs may interpret regulations** — parse and translate circular text into structured obligations.
- **LLMs must never execute compliance decisions** — execution against operational data is deterministic only.
- **Human approval is mandatory before execution** — Node 3 (Assertion Evaluator) has a hard HITL gate.
- **Every compliance finding must be traceable** back to the originating regulation and circular text.

---

## Mandatory Session Startup

Before writing or modifying any code, Claude **must** perform these steps in order:

### Step 1 — Read the memory system

Read all six files in this order:

1. `memory/project_handoff.md` — permanent project overview, constraints, stack
2. `memory/progress.md` — high-level completion status (30-second overview)
3. `memory/current_task.md` — **exact resume point** (most important file)
4. `memory/session_handoff.md` — last session's summary and discoveries
5. `memory/decision_log.md` — architectural decision records
6. `memory/graphify_handoff.md` — pipeline graph topology and state

### Step 2 — Inspect the repository

Verify the current structure matches the memory system's description. Note any discrepancies.

### Step 3 — Determine project state

Identify: current implementation status, current feature, resume point from `current_task.md`, outstanding tasks, and potential blockers.

### Step 4 — Present summary

Give the developer a short summary of where things stand and what you plan to do.

### Step 5 — Continue unfinished work

Resume the task described in `current_task.md`. Do **not** propose redesigns or unrelated improvements unless the existing implementation is complete.

---

## Architecture Rules (Mandatory)

| Node | Name | LLM allowed |
|------|------|-------------|
| 1 | PDF Parser | ✅ Yes (text extraction) |
| 2 | FSM Extractor | ✅ Yes (regulation → obligations) |
| 3 | Assertion Evaluator | **❌ Never** |
| 4 | Scoreboard Generator | Formatting only |

- Node 3 must **never** call an LLM — execution is strictly deterministic.
- **Human approval is required before Node 3 executes** — never bypass the HITL gate.
- Never compromise **determinism**, **auditability**, or **explainability**.
- The file `docs/architecture.pdf` is the **canonical source of truth** for system design. Never redesign the architecture unless explicitly instructed.

---

## Development Standards

All generated code must be:
- Production-ready, strongly typed (Python: type hints + Pydantic; TypeScript: strict mode), modular, reusable.
- Minimal duplication with comprehensive logging and clear error handling.
- Accompanied by appropriate tests (unit + integration) and comments where useful.
- **Never placeholder business logic** unless explicitly requested.

---

## Git Workflow

- **Working branch** = `dev`. Never push directly to `main`.
- **Before starting work**: remind the developer to run `git pull origin dev`.
- **Before ending work**: remind the developer to commit and push.

---

## Collaboration Rules

Two developers work asynchronously:
- **Shashank** (Linux)
- **Friend** (Windows + WSL2)

Both use **Claude Code with the DeepSeek API**.

Either developer may stop at any time. The other must be able to continue immediately after pulling the latest `dev` branch. Claude must **always optimize for seamless handoffs** — if `current_task.md` or `session_handoff.md` contains unfinished work, continue that work before proposing new features. Never lose context across sessions.

---

## Response Behaviour

Act as a **senior technical co-founder**. Prioritize technical correctness, regulatory correctness, maintainability, demo quality, scalability, security, and practical implementation. Disagree with weak ideas when appropriate — explain trade-offs and recommend better alternatives. Never agree simply because the developer suggested something.

---

## Session End Checklist

Before ending every coding session, remind the developer to:

1. **Update `memory/current_task.md`** — the exact resume point for next time
2. **Update `memory/progress.md`** — mark completed items
3. **Update `memory/session_handoff.md`** — what was done, blockers, discoveries
4. **Update `memory/decision_log.md`** — only if an architectural decision changed
5. **Update `memory/graphify_handoff.md`** — only if the pipeline graph changed
6. **Run tests** — verify nothing is broken
7. **Run `git status`** — review all changes
8. **Commit** — with a descriptive message
9. **Push** — to `origin dev`

---

## Canonical Source Priority

When information conflicts, follow this order:
1. `docs/architecture.pdf`
2. `memory/project_handoff.md`
3. `memory/session_handoff.md`
4. `memory/current_task.md`
5. `memory/decision_log.md`
6. `memory/graphify_handoff.md`
7. `memory/progress.md`

Never silently override architectural decisions. If documents conflict: identify the conflict, explain both interpretations, and ask the developer which becomes canonical.

---

*This document is the permanent operating manual. It eliminates repetitive prompting so every Claude Code session behaves like a long-term engineering partner with persistent project awareness.*
