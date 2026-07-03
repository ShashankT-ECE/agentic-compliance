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

- **Decision**: Structure the pipeline as four sequential nodes: PDF Parser (Node 1), FSM Extractor (Node 2), Assertion Evaluator (Node 3), Scoreboard Generator (Node 4).
- **Rationale**: Each node has a single responsibility with clear inputs and outputs. LLM usage can be tightly controlled per node. Node 3 is isolated for deterministic-only execution.
- **Alternatives considered**: Two-node design (parse+extract merged, evaluate+score merged), single monolithic evaluator.
- **Impact**: Node 3's strict no-LLM constraint is naturally enforced by the architecture. Clear HITL insertion point before Node 3.
- **Status**: Implemented.

### 2026-07-03 — Timeline-based obligation for V1

- **Decision**: Target a timeline-based SEBI circular for V1 (e.g., reporting/submission deadlines with T+1, T+3 day offsets).
- **Rationale**: Deadline compliance is the most common pattern in SEBI circulars, making it the highest-value demonstration. Timeline logic is naturally testable with synthetic event streams. Demonstrates the hybrid FSM model effectively.
- **Alternatives considered**: Threshold-based (position limits), process compliance (KYA procedures).
- **Impact**: Parser must extract time offsets and deadlines. FSM model must embed timeline conditions. Evaluator must compute time-based state transitions.
- **Status**: Accepted.

### 2026-07-03 — Hybrid FSM model (state machine + timeline conditions)

- **Decision**: Model compliance obligations as hybrid FSMs — a state machine wrapper (states: PENDING, DUE, COMPLIANT, LATE, NON_COMPLIANT) with embedded timeline conditions (deadlines, grace periods, event-triggered countdowns).
- **Rationale**: Pure state machines cannot elegantly express time-based obligations (deadlines vs event sequences). Pure rule engines lose auditability. The hybrid approach allows both: state transitions capture the compliance workflow, timeline conditions capture the time-sensitive constraints brokers must satisfy.
- **Alternatives considered**: Classic state machine only, timeline-only model, rule-based boolean conditions.
- **Impact**: FSM schema is more complex. FSM extractor (Node 2) must produce hybrid FSMs. Evaluator (Node 3) must interpret both state transitions and timeline conditions. Scoreboard must reflect both dimensions.
- **Status**: Accepted.

### 2026-07-03 — Event-based telemetry with production schema

- **Decision**: Telemetry is event-based (discrete timestamped events from broker systems). The pipeline consumes the production schema from Day 1 — no synthetic-only detour.
- **Rationale**: Event logs are the standard format for broker operational data. Designing for the real schema from the start prevents rework. Synthetic generators in `telemetry_gen.py` produce events matching the same schema.
- **Alternatives considered**: Snapshot-based telemetry (periodic state dumps), time-series data, mock-only schema.
- **Impact**: Telemetry model must reflect real broker event types. Evaluator must handle event ordering, missing events, and out-of-sequence events. Schema must be defined before Node 3 implementation.
- **Status**: Accepted.

### 2026-07-03 — HITL gate reviews FSMs before evaluation

- **Decision**: The human-in-the-loop gate occurs after Node 2 (FSM Extractor) and before Node 3 (Evaluator). The human reviews the extracted FSMs for correctness, approves or corrects them, and only then does deterministic evaluation proceed.
- **Rationale**: LLMs may misinterpret regulatory text. The HITL gate catches FSM extraction errors before they propagate into compliance verdicts. Once FSMs are locked, Node 3 runs deterministically with no further human involvement, preserving auditability.
- **Alternatives considered**: Review evaluation results before publishing, both gates.
- **Impact**: Pipeline state includes an "FSM review" phase. API must expose FSM review endpoints. Frontend needs an FSM approval UI. Conditional edge in LangGraph delays Node 3 until approval. Locked FSMs are stored in `backend/data/locked_fsms/`.
- **Status**: Accepted.

### 2026-07-03 — Hash chain required for V1 demo

- **Decision**: The hash-chain integrity system must be operational alongside the core pipeline for the V1 demo.
- **Rationale**: Verifiable audit trails are a core differentiator for the TechSprint demo. Building it after the pipeline would require retrofitting integrity hooks into every node, which is more expensive than designing for it from the start.
- **Alternatives considered**: Defer hash chain to V2.
- **Impact**: Every scoreboard entry and locked FSM snapshot must be hash-chained. The hash chain utility must be designed in M0 alongside data models. Scoreboard Generator (Node 4) must produce chained output.
- **Status**: Accepted.

### 2026-07-03 — Depth-first implementation strategy

- **Decision**: Build end-to-end depth first (one circular, one broker, full PDF → scoreboard pipeline) rather than horizontal breadth (multiple circulars at parser level only).
- **Rationale**: A complete working pipeline through all 4 nodes demonstrates the full value proposition. Breadth can be added later without architectural changes. A partial implementation at any stage is not demonstrable.
- **Alternatives considered**: Breadth-first (multi-circular parser/extractor), hybrid (two circulars deep).
- **Impact**: All milestones are ordered around the first end-to-end flow. Later circulars are additive, not structural.
- **Status**: Accepted.

### 2026-07-03 — Canonical V1 regulatory source

- **Decision**: The canonical V1 regulatory source for the entire project is **SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/57**, issued **28 April 2025**, subject *"Timelines for collection of Margins other than Upfront Margins – Alignment to settlement cycle."* All milestones (M1–M9) use this single circular as their regulatory input.
- **Rationale**: The depth-first implementation strategy requires exactly one real SEBI circular to build the complete end-to-end pipeline. This circular was selected because it contains timeline-based obligations (T+1 settlement day, advance-of-trade deadlines) that map cleanly to the V1 HybridFSM model, it has a clear effective date, it addresses specific regulated entities (Trading Members, Clearing Members, Recognized Stock Exchanges, Clearing Corporations), and its full text is publicly available on sebi.gov.in. Using a single canonical circular ensures every milestone is consistent — obligations extracted in M1 are the same ones modelled as FSMs in M2, reviewed at the HITL gate in M4, evaluated in M5, and scored in M6.
- **Alternatives considered**: Fabricated/test circulars (rejected — architecture constraint requires obligations always extracted from real SEBI circulars), selecting the circular at a later milestone (rejected — M1's parser and fixture must target the real circular from the start).
- **Impact**:
  - M1 parses obligations from this circular.
  - M2 generates HybridFSMs from obligations extracted from this circular.
  - M3 hash-chains FSMs derived from this circular.
  - M4 performs HITL review on FSMs derived from this circular.
  - M5 evaluates broker telemetry against obligations from this circular.
  - M6 generates compliance scoreboards for this circular.
  - M7 orchestrates the pipeline for this circular.
  - M8 visualises compliance results for this circular.
  - M9 demonstrates the complete end-to-end workflow using this circular.
  - Test fixtures, prompt templates, and mock data must reference this circular's actual content.
  - If the circular needs to be changed, this decision record must be updated and all milestones re-verified.
- **Status**: Accepted.

---

### 2026-07-03 — M1: Parser architecture

- **Decision**: The parser node (Node 1) uses a two-layer architecture: pdfplumber for deterministic PDF text extraction, LLM for structured obligation extraction. The LLM backend is abstracted behind an `LLMClient` ABC with a `DeepSeekClient` implementation, making the backend swappable without changing node logic.
- **Rationale**: Separation of deterministic I/O (PDF reading) from probabilistic extraction (LLM). The abstraction allows testing with `MockLLMClient` and swapping to different LLM providers without modifying parser logic.
- **Alternatives considered**: Inline LLM calls (rejected — not swappable), fully deterministic extraction (rejected — SEBI circulars use natural language with varying structure).
- **Impact**: `llm_client.py` is reusable by all LLM-using nodes (M1, M2). Prompt templates are stored as markdown files for easy iteration. JSON extraction uses a 3-pass parser (pure JSON, markdown fence, regex extraction) to handle diverse LLM output patterns.
- **Status**: Accepted.

### 2026-07-03 — M2: FSM extraction architecture

- **Decision**: FSM extraction uses the same `LLMClient` abstraction as M1. The extractor sends all obligation clauses in a single LLM call (batch extraction) rather than one call per clause. Pre-Pydantic validation enforces all 5 canonical states, minimum 3 transitions, and minimum 1 timeline rule before the full `HybridFSM` model validation runs.
- **Rationale**: Batch extraction gives the LLM context across multiple obligations from the same circular, improving consistency. Pre-Pydantic checks catch structural errors early with clear error messages before the model validator runs.
- **Alternatives considered**: Per-clause extraction (rejected — loses cross-clause context, more API calls).
- **Impact**: The `_extract_json_from_response` function in parser.py was extended to handle single JSON objects `{...}` in addition to arrays `[{...}]` — the FSM prompt may return single objects. Extracted FSMs are persisted to `data/extracted/{circular}/` with a `_index.json` manifest.
- **Status**: Accepted.

### 2026-07-03 — M3: Hash chain completion

- **Decision**: The hash chain utility (`compute_hash`, `link`, `verify_chain`, `build_chain`) was fully implemented in M0 (not just interface signatures) because downstream data structures depend on `HashLink`/`HashChain` types. M3 completed the remaining roadmap items: dedicated test file, 1000+ link chain test, and JSON serialization roundtrip test.
- **Rationale**: The `link()` function is needed by any code that creates `HashLink` instances — keeping it as a signature-only stub in M0 would have made M0 model tests meaningless. The 1000+ link test validates chain performance and correctness at scale.
- **Alternatives considered**: Deferring full implementation to M3 (rejected — would block M0 testing).
- **Impact**: Zero production code changes in M3. Tests migrated from `test_models.py` to dedicated `test_hash_chain.py`.
- **Status**: Accepted.

### 2026-07-03 — M4: HITL workflow

- **Decision**: The HITL gate sits between Node 2 and Node 3 as a synchronous checkpoint. After Node 2 extracts FSMs, `hitl_gate_node()` creates PENDING `LockedFSM` records and pauses the pipeline at `AWAITING_APPROVAL`. Human reviewers resolve each FSM individually via API (approve/reject/amend). The pipeline resumes when all FSMs are resolved.
- **Rationale**: LLMs may misinterpret regulatory text. The HITL gate catches FSM extraction errors before they propagate into deterministic compliance verdicts. Once FSMs are locked, Node 3 runs deterministically with no further human involvement.
- **Alternatives considered**: Review after evaluation (rejected — verdicts would be based on incorrect FSMs), automated validation only (rejected — cannot catch semantic errors in FSM extraction).
- **Impact**: Pipeline state includes `AWAITING_APPROVAL`, `APPROVED`, and `REJECTED` statuses. API exposes 6 HITL endpoints. Frontend (M8) needs FSM review UI. Locked FSMs stored in `data/locked_fsms/{run_id}/`.
- **Status**: Accepted.

### 2026-07-03 — M4: LockedFSM design

- **Decision**: Each locked FSM wraps a `HybridFSM` with approval metadata (`reviewer`, `reviewed_at`, `review_comments`), an `integrity_hash` (SHA-256 of the serialized FSM content), a `hash_link` (M3 chain anchor), and an `amendment_history` (ordered list of prior versions). Six Pydantic validators enforce state-dependent field requirements.
- **Rationale**: The `integrity_hash` enables post-hoc tamper detection — recomputing the hash from stored FSM content and comparing detects any modification. The `hash_link` anchors each locked FSM in the verifiable audit chain. `AmendmentRecord` preserves the full lifecycle of every FSM for auditability.
- **Alternatives considered**: Storing only the hash without the original FSM (rejected — Node 3 needs the FSM content for evaluation). Storing amendments as diffs (rejected — full snapshots are simpler and more auditable for V1 scale).
- **Impact**: `LockedFSM` is the input type for Node 3 (Evaluator). The `original_fsm` field holds the FSM content. Amendments version the LockedFSM rather than overwriting.
- **Status**: Accepted.

### 2026-07-03 — M4: Amendment versioning

- **Decision**: Amendments version the LockedFSM — the `version` field increments, the prior FSM is preserved in `amendment_history` as an `AmendmentRecord` with full `prior_fsm` snapshot, and a new `integrity_hash` and `hash_link` are computed for the corrected FSM.
- **Rationale**: Regulatory auditors must be able to reconstruct the full lifecycle of any FSM — who changed what, when, and why. Versioning preserves the complete history. The same `locked_fsm_id` is retained across versions so the amendment chain is traceable.
- **Alternatives considered**: Overwriting without history (rejected — loses audit trail). Creating new LockedFSM records per version (rejected — breaks the 1:1 relationship between obligation and locked record).
- **Impact**: `AmendmentRecord` stores `version`, `amended_by`, `amended_at`, `changes`, and `prior_fsm`. The amendment history is an ordered list. Node 3 always uses the current `original_fsm` (latest version).
- **Status**: Accepted.

### 2026-07-03 — M4: Pipeline pause/resume behaviour

- **Decision**: The pipeline pauses by setting `state["status"] = PipelineStatus.AWAITING_APPROVAL` and `state["locked_fsms"] = []` after persisting PENDING LockedFSM records. The API layer handles individual FSM resolution. The pipeline resumes when the conditional edge in M7 detects all FSMs are resolved (`APPROVED` or `AMENDED`).
- **Rationale**: The HITL gate does not block or poll — it's a synchronous checkpoint. The API and pipeline operate on the same persisted data (`data/locked_fsms/{run_id}/`), making the gate stateless from the pipeline's perspective.
- **Alternatives considered**: Pipeline blocks with a polling loop (rejected — wastes resources, couples API and pipeline). In-memory state only (rejected — not durable across restarts).
- **Impact**: The `hitl_gate_node()` function is a standalone callable (same pattern as `parser_node()` and `fsm_extractor_node()`). M7 will wire the conditional edge. Rejected FSMs route back to Node 2 via `PipelineStatus.REJECTED`.
- **Status**: Accepted.

### 2026-07-03 — M4: Zero-LLM rule for HITL

- **Decision**: The HITL gate must never call an LLM. All HITL logic — creating LockedFSM records, computing integrity hashes, creating hash chain links, validating amendments — is strictly deterministic.
- **Rationale**: The HITL gate is a security boundary. LLM calls at this stage could modify FSM content without human oversight, defeating the purpose of the gate. The gate's sole purpose is to enable human review of LLM-extracted content from upstream nodes.
- **Alternatives considered**: LLM-assisted review suggestions (rejected — violates the human-as-final-authority principle).
- **Impact**: `hitl_gate.py` imports from `hash_chain.py` (deterministic SHA-256) and `locked_fsm.py` (Pydantic models). No imports from `llm_client.py`. Verified by grep — zero LLM-related imports in any M4 file.
- **Status**: Accepted.

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
