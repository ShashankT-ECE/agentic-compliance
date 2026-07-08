# Decision Log

> **Purpose**: Permanent record of architectural decisions. Never store temporary notes or task tracking here.
> **Updated**: Only when an architectural decision is made, changed, or reversed.
> **Priority**: Level 4 in the canonical source hierarchy.

---

## Decision Records

### 2026-07-01 — Repository scaffold with pipeline-oriented architecture

- **Decision**: Create the canonical directory layout with Python backend (FastAPI + LangGraph), TypeScript/React frontend (Vite), docs, scripts, and memory.
- **Rationale**: Clean separation of concerns with a pipeline-oriented backend architecture and modern frontend toolchain. Enables asynchronous parallel development.
- **Alternatives considered**: Monolithic structure, separate repos for frontend/backend.
- **Impact**: Clear ownership boundaries. Frontend and backend can be developed independently. LangGraph provides the orchestration framework for the pipeline DAG.
- **Status**: Implemented.

### 2026-07-01 — Four-node compliance pipeline

- **Decision**: Structure the pipeline as four sequential nodes: PDF Parser (Node 1), FSM Extractor (Node 2), Assertion Evaluator (Node 3), Scoreboard Generator (Node 4), with a HITL gate between Node 2 and Node 3.
- **Rationale**: Each node has a single responsibility with clear inputs and outputs. LLM usage can be tightly controlled per node. Node 3 is isolated for deterministic-only execution. HITL gate inserted where LLM output must be human-verified before deterministic evaluation.
- **Alternatives considered**: Two-node design, monolithic evaluator, post-evaluation review.
- **Impact**: Node 3's strict no-LLM constraint is naturally enforced by the architecture. Clear HITL insertion point before Node 3.
- **Status**: Implemented (5 nodes with conditional HITL branch in M7).

### 2026-07-03 — Timeline-based obligation for V1

- **Decision**: Target timeline-based SEBI circulars for V1 (reporting/submission deadlines with T+1, T+3 day offsets).
- **Rationale**: Deadline compliance is the most common pattern in SEBI circulars. Timeline logic is naturally testable with synthetic event streams.
- **Alternatives considered**: Threshold-based (position limits), process compliance.
- **Status**: Accepted.

### 2026-07-03 — Hybrid FSM model (state machine + timeline conditions)

- **Decision**: Model compliance obligations as hybrid FSMs with embedded timeline conditions.
- **Rationale**: Pure state machines cannot elegantly express time-based obligations. Pure rule engines lose auditability. Hybrid approach supports both.
- **Impact**: FSM schema is more complex. Evaluator must interpret both state transitions and timeline conditions.
- **Status**: Accepted.

### 2026-07-03 — Event-based telemetry with production schema

- **Decision**: Telemetry is event-based (discrete timestamped events from broker systems). Pipeline consumes production schema from Day 1.
- **Rationale**: Event logs are the standard format for broker operational data. Designing for real schema prevents rework.
- **Status**: Accepted.

### 2026-07-03 — HITL gate reviews FSMs before evaluation

- **Decision**: Human-in-the-loop gate occurs after Node 2 and before Node 3. Human reviews extracted FSMs for correctness.
- **Rationale**: LLMs may misinterpret regulatory text. HITL catches extraction errors before they propagate into compliance verdicts.
- **Status**: Accepted.

### 2026-07-03 — Hash chain required for V1 demo

- **Decision**: Hash-chain integrity system operational alongside core pipeline for V1 demo.
- **Rationale**: Verifiable audit trails are a core differentiator for the TechSprint demo.
- **Status**: Accepted.

### 2026-07-03 — Depth-first implementation strategy

- **Decision**: Build end-to-end depth first (one circular, one broker, full pipeline) rather than horizontal breadth.
- **Rationale**: A complete working pipeline through all nodes demonstrates the full value proposition.
- **Status**: Accepted.

### 2026-07-03 — Canonical V1 regulatory source

- **Decision**: Canonical V1 regulatory source is **SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/57** (28 April 2025), subject *"Timelines for collection of Margins other than Upfront Margins."*
- **Rationale**: Contains timeline-based obligations (T+1, advance-of-trade) that map cleanly to the HybridFSM model.
- **Status**: Accepted. Validated end-to-end against official PDF on 2026-07-08.

### 2026-07-03 — Deterministic FSM execution: first-match transition resolution

- **Decision**: When multiple transitions from current state match the same event trigger, take the first matching transition.
- **Rationale**: Must be fully deterministic. First-match provides a clear, reproducible rule.
- **Status**: Implemented in `state_machine.py`.

### 2026-07-03 — Timeline reference time: earliest event timestamp

- **Decision**: Use the earliest telemetry event's timestamp as the reference point for deadline computation when no explicit reference_time is provided.
- **Rationale**: Earliest event timestamp is the best available proxy for T+0. It's deterministic and always available.
- **Consequence**: Single-event scenarios always appear on-time. Meaningful late detection requires ≥2 events.
- **Status**: Implemented in `timeline_evaluator.py`.

### 2026-07-03 — End-of-trading-day deadline semantics

- **Decision**: T+N deadlines compute to 23:59:59 UTC on the target calendar date, not N×24 hours from reference.
- **Rationale**: SEBI circulars define deadlines as end-of-trading-day. Matches regulatory interpretation.
- **Status**: Implemented in `timeline_evaluator.py`.

### 2026-07-03 — Error-isolated FSM evaluation

- **Decision**: One malformed FSM produces an error verdict — remaining FSMs continue evaluating independently.
- **Rationale**: A single corrupt definition must not block the entire compliance run.
- **Status**: Implemented in `evaluator.py`.

### 2026-07-03 — Event-counted evidence trail with 1:1 telemetry mapping

- **Decision**: Evidence trail contains exactly one entry per telemetry event per FSM, with a `matched` boolean.
- **Rationale**: Auditors can trace every event against every obligation. Complete and independently verifiable.
- **Status**: Implemented in `evaluator.py`.

### 2026-07-03 — Compliance scoring rubric

- **Decision**: Five-tier scoring: COMPLIANT=1.0, DUE=0.75, PENDING=0.5, LATE=0.5, NON_COMPLIANT=0.0.
- **Rationale**: Distinguishes "nothing happened yet" (PENDING, 0.5) from "actively failing" (NON_COMPLIANT, 0.0).
- **Status**: Implemented in `evaluator.py`.

### 2026-07-04 — LangGraph + FastAPI as M7 orchestration layer

- **Decision**: Wire the pipeline via LangGraph's `StateGraph` using `CompliancePipelineState` (Pydantic model) as the shared state. Expose operations through FastAPI REST endpoints.
- **Rationale**: LangGraph provides the DAG structure and conditional routing. FastAPI provides the HTTP API. Manual sequential execution supports async LLM calls and HITL pause/resume.
- **Alternatives considered**: Full LangGraph invoke with async node support, Celery task queue, hand-rolled orchestrator.
- **Status**: Implemented in M7.

### 2026-07-04 — Pydantic state ↔ dict bridge for node compatibility

- **Decision**: LangGraph graph uses `CompliancePipelineState` (Pydantic model). Node wrapper functions convert to dict manually before calling pre-M7 node functions.
- **Rationale**: M1-M4 node functions were written before M7 and expect `dict.get()` access. Converting at the graph boundary avoids modifying all existing node functions.
- **Status**: Implemented in `graph.py` (`_state_to_dict()` — fixed in M9).

### 2026-07-04 — In-memory stores for V1 (database in V2)

- **Decision**: Pipeline run state, telemetry events, and reports use in-memory stores for V1. Replace with PostgreSQL via SQLAlchemy in V2.
- **Rationale**: In-memory stores enable fast iteration during development. Store accessor pattern makes the swap mechanical.
- **Status**: Implemented. V2 migration planned.

### 2026-07-04 — Frontend stack: React 19 + TypeScript strict + Vite + Zustand + native fetch

- **Decision**: Frontend uses React 19 with TypeScript strict mode, Vite for build, Zustand for state management, and native `fetch` for HTTP.
- **Rationale**: Zustand is lightweight and idiomatic for React 19. Native fetch avoids an extra dependency. CSS custom properties provide theming.
- **Alternatives considered**: Axios, Redux, Tailwind CSS, Next.js.
- **Status**: Implemented in M8.

### 2026-07-04 — Demo mode: MockLLMClient with canned responses

- **Decision**: The demo script and integration tests use `MockLLMClient` / `MultiMockLLMClient` with canned JSON responses. No real LLM API key required.
- **Rationale**: Demos must run reliably without depending on external API availability. Canned responses exercise the exact same code paths.
- **Status**: Implemented in M9.

### 2026-07-04 — Integration test strategy: in-process PipelineRunner

- **Decision**: Integration tests call `PipelineRunner` directly (in-process) rather than through FastAPI HTTP. Telemetry/report endpoints tested via `TestClient`.
- **Rationale**: Pipeline execution is the primary integration concern. HTTP layer is independently tested in `test_orchestration.py` (53 tests).
- **Status**: Implemented in `test_integration.py` (37 tests).

### 2026-07-06 — Disk-authoritative HITL list

- **Decision**: `list_hitl_runs()` reads exclusively from disk (`data/locked_fsms/`) rather than in-memory `_run_store`.
- **Rationale**: In-memory store is volatile. Disk is durable and verifiable. Prior dual-source approach leaked stale runs.
- **Status**: Implemented in `pipeline.py`.

### 2026-07-06 — Truncated JSON array recovery in parser

- **Decision**: Added "Attempt 4" to `_extract_json_from_response()` — character-by-character depth tracking to recover complete top-level JSON objects from truncated LLM responses.
- **Rationale**: Real LLM APIs can truncate responses when `max_tokens` is exceeded. Recovering partial results is better than losing everything.
- **Status**: Implemented in `parser.py`. 4 regression tests added. Verified recovering 53 clauses from 399-page master circular output.

### 2026-07-06 — Data path resolution: `backend/data/` not `backend/app/data/`

- **Decision**: All `__file__`-based data path constants use 4× `.parent` (reaching `backend/`).
- **Rationale**: The `.gitignore` was written for `backend/data/` — fixing code rather than `.gitignore` preserves original intent.
- **Status**: Implemented in `hitl_gate.py`, `fsm_extractor.py`, `pipeline.py`.

### 2026-07-06 — Enterprise UI design system

- **Decision**: Frontend CSS redesigned with enterprise palette (blue brand #2563eb, slate neutrals). FSM terminology replaced with "Compliance Obligation" in presentation layer.
- **Rationale**: Target audience is SEBI compliance officers — UI must feel like a professional regulatory tool.
- **Status**: Implemented in V1.0.1. Additional polish in V1.0.2.

### 2026-07-06 — Fixed-position SVG workflow diagram (linear layout)

- **Decision**: Replaced dynamic grid-based SVG with fixed-position linear layout: PENDING → DUE → LATE → NON_COMPLIANT, with COMPLIANT as a branch node.
- **Rationale**: Grid layout produced overlapping curved arrows. Fixed layout matching the business workflow is clearer.
- **Status**: Implemented in `FSMViewer/index.tsx`.

### 2026-07-07 — determine_compliance_status() trusts FSM current state

- **Decision**: `StateMachine.determine_compliance_status()` returns `self._current_state` as the canonical status rather than re-deriving from structural properties.
- **Rationale**: Old logic ignored the FSM's actual current state. When the FSM reached LATE, the method saw "non-terminal + has transitions" and returned DUE → PENDING.
- **Impact**: Verdicts now correctly show `non_compliant` when FSM reaches LATE. State/Status consistency resolved.
- **Status**: Implemented in `state_machine.py`.

### 2026-07-07 — Report compliance percentage matches scoreboard formula

- **Decision**: Report `compliance_pct` uses `compliant / (total - pending) * 100` (same as scoreboard's `compliance_rate`).
- **Rationale**: Old formula `compliant / total * 100` counted pending verdicts in denominator, producing 0% when nothing had been evaluated. Inconsistent with scoreboard.
- **Status**: Implemented in `reports.py`.

### 2026-07-08 — Timeline overdue_transition applied to StateMachine before verdict construction

- **Decision**: `StateMachine.transition_to(target_state, reason)` synthetically advances the FSM for timeline-driven transitions. Evaluator applies `overdue_transition` for every timeline rule with `deadline_met=False`.
- **Rationale**: `deadline_met=False` forced canonical status to LATE but `sm.current_state` remained PENDING — created a `State=PENDING / Status=NON_COMPLIANT` split. The `overdue_transition` field was designed for this purpose.
- **Impact**: `current_state` and `status` now consistent. Evidence trail records `trigger="timeline_overdue"` for auditability.
- **Status**: Implemented in `state_machine.py` and `evaluator.py`. 6 new tests.

### 2026-07-08 — Deterministic explanation column for audit reports

- **Decision**: Each verdict carries a human-readable `explanation` field derived from the existing `evidence` object via `_derive_explanation()` — pure function, no LLM. Displayed as 7th column in audit report.
- **Rationale**: PENDING verdicts gave no indication why — users couldn't distinguish bugs from correct behavior. Makes the report self-explanatory.
- **Alternatives considered**: Expandable detail rows, tooltip on status badge, separate diagnostics section.
- **Status**: Implemented in `reports.py`, `client.ts`, `AuditReport/index.tsx`. Browser-verified — all rows show correct explanations.

### 2026-07-08 — V1 Freeze

- **Decision**: Freeze V1 pipeline, models, evaluator, and API. No further changes to V1 components. All remaining issues deferred to V2.
- **Rationale**: V1.0.2 is functionally complete — 410 tests pass, frontend builds clean, explanation column verified, official SEBI circular validated end-to-end. Further changes risk regression without corresponding value for the current demo.
- **Impact**: V1 is immutable. V2 must be planned and approved before any implementation begins. V2 scope includes large-document support, PostgreSQL persistence, PDF upload UX, authentication, CI/CD, and production hardening.
- **Status**: Accepted (2026-07-08).

---

## V2 Proposed Decisions (from `docs/v2_roadmap.md`)

### 2026-07-08 — V2 Vector Database: Chroma (dev) → pgvector (production)

- **Decision**: Use Chroma as the development/embedded vector store, migrate to pgvector colocated with PostgreSQL for production.
- **Rationale**: Chroma requires zero infrastructure (pip install, in-process). pgvector eliminates a separate vector DB service — single PostgreSQL instance for relational + vector data. Migration is a config change via the `VectorStore` abstraction.
- **Alternatives considered**: Qdrant (separate service, operational overhead), LanceDB (newer, smaller community), FAISS (no metadata filtering), Pinecone (vendor lock-in, data leaves environment).
- **Impact**: M4 delivers both implementations. Dev loop stays fast (Chroma). Production gets single-DB simplicity (pgvector).
- **Status**: Proposed — ratify before M4.

### 2026-07-08 — V2 Chunking: Section-boundary-aware with overlap

- **Decision**: Chunk regulatory PDFs at section/paragraph boundaries with configurable context overlap. Never split mid-paragraph.
- **Rationale**: Regulatory meaning is defined by section/paragraph structure. Splitting "39.1.2 ... TMs/CMs will have time till settlement day [CHUNK BREAK] to collect margins" destroys obligation semantics. Fixed-size sliding windows are designed for prose, not legal text.
- **Alternatives considered**: Recursive character splitting (LangChain default — breaks legal text), semantic chunking via embedding similarity (too expensive for initial chunking, better as post-process), agentic chunking (overkill for structured documents).
- **Impact**: Chunks preserve legal integrity. Retrieval accuracy improves because each chunk is a self-contained regulatory unit. Cross-reference resolution (M7) benefits from clean section boundaries.
- **Status**: Proposed — ratify before M2.

### 2026-07-08 — V2 Embedding Model: bge-large-en-v1.5 (local default), text-embedding-3-small (optional)

- **Decision**: `BAAI/bge-large-en-v1.5` (1024-dim) as the default embedding model running locally via sentence-transformers. `text-embedding-3-small` (1536-dim) as an opt-in alternative via API.
- **Rationale**: BGE-large leads the MTEB retrieval benchmark for English text, handles legal/regulatory vocabulary well, and runs locally — no API cost, no data leaving the environment. Critical for compliance platforms where regulatory text may be sensitive. OpenAI option for higher quality when budget and data policies permit.
- **Alternatives considered**: all-MiniLM-L6-v2 (384-dim, smaller/faster but weaker on legal text), voyage-law-2 (best legal embeddings but API-only, US-hosted — regulatory data sovereignty concern), text-embedding-3-large (highest quality OpenAI but 2× cost of small).
- **Status**: Proposed — ratify before M4.

### 2026-07-08 — V2 Hybrid Retrieval: RRF with BM25=0.4, Vector=0.6

- **Decision**: Default reciprocal rank fusion weights of 0.4 (BM25) and 0.6 (vector), with per-query-type auto-detection and re-weighting.
- **Rationale**: BM25 excels at exact references ("Para 39.1.2", "CIR/2025/57", "Section 11(1)"). Vector search excels at semantic queries ("margin collection deadline", "client onboarding requirements"). Most user queries are semantic, hence vector-weighted. Exact-reference queries are auto-detected (regex match on known reference patterns) and re-weighted to favor BM25.
- **Alternatives considered**: BM25-only (misses semantic matches), vector-only (misses exact references), learning-to-rank (requires training data we don't have yet — V3 candidate).
- **Status**: Proposed — ratify before M5.

### 2026-07-08 — V2 Conflict Resolution: Detect automatically, resolve manually

- **Decision**: Cross-circular obligation conflicts are detected and flagged automatically. Resolution (which obligation takes precedence) is always a human decision.
- **Rationale**: Regulatory interpretation is inherently a legal determination. The platform can identify that Circular A says "T+2" and Circular B says "T+1" for the same obligation, but deciding which applies requires understanding of effective dates, rescission clauses, and regulatory intent — all of which require human judgment. Automatic resolution risks incorrect compliance verdicts with legal consequences.
- **Alternatives considered**: Heuristic resolution (latest circular wins — too simplistic, ignores partial rescissions), LLM-based resolution (not deterministic, hard to audit — violates P1), always-flag (chosen approach).
- **Status**: Proposed — ratify before M9.

---

## Template for New Entries

```markdown
### YYYY-MM-DD — Title

- **Decision**: What was decided.
- **Rationale**: Why this decision was made.
- **Alternatives considered**: Other options that were evaluated.
- **Impact**: Consequences of this decision (positive and negative).
- **Status**: Proposed / Accepted / Deprecated / Reversed.
```
