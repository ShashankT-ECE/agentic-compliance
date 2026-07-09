# Decision Log

> **Purpose**: Permanent record of architectural decisions. Never store temporary notes or task tracking here.
> **Updated**: Only when an architectural decision is made, changed, or reversed.
> **Priority**: Level 4 in the canonical source hierarchy.

---

## Decision Records

### 2026-07-01 — Repository scaffold with pipeline-oriented architecture

- **Decision**: Create the canonical directory layout with Python backend (FastAPI + LangGraph), TypeScript/React frontend (Vite), docs, scripts, and memory.
- **Rationale**: Clean separation of concerns with a pipeline-oriented backend architecture.
- **Alternatives considered**: Monolithic structure, separate repos.
- **Status**: Implemented.

### 2026-07-01 — Four-node compliance pipeline

- **Decision**: Structure the pipeline as four sequential nodes with HITL gate between Node 2 and Node 3.
- **Rationale**: Each node has a single responsibility. Node 3 isolated for deterministic-only execution.
- **Status**: Implemented.

### 2026-07-03 — Timeline-based obligation for V1, Hybrid FSM model, event-based telemetry

- **Decision**: Target timeline-based SEBI circulars, model as hybrid FSMs, event-based telemetry.
- **Status**: Accepted.

### 2026-07-03 — HITL gate, hash chain, depth-first strategy, canonical V1 circular

- **Decision**: HITL reviews FSMs before evaluation. Hash chain required for V1 demo. Depth-first build.
- **Status**: Accepted.

### 2026-07-03 — Deterministic FSM execution, timeline reference time, deadline semantics, error isolation, evidence trail, scoring rubric

- **Decision**: First-match transition resolution, earliest event reference time, end-of-trading-day deadlines, error-isolated evaluation, 1:1 evidence mapping, five-tier scoring.
- **Status**: Implemented.

### 2026-07-04 — LangGraph + FastAPI orchestration, Pydantic state bridge, in-memory stores

- **Decision**: LangGraph StateGraph with manual sequential execution. In-memory stores for V1.
- **Status**: Implemented.

### 2026-07-04 — Frontend stack, demo mode, integration test strategy

- **Decision**: React 19 + TypeScript strict + Vite + Zustand. MockLLMClient for demos. In-process integration tests.
- **Status**: Implemented.

### 2026-07-06 — Disk-authoritative HITL, truncated JSON recovery, data path fix, enterprise UI, fixed-position SVG

- **Decision**: HITL reads from disk. Truncation recovery via depth-tracking. Data path corrected to `backend/data/`.
- **Status**: Implemented.

### 2026-07-07 — determine_compliance_status() trusts current state, report compliance matches scoreboard

- **Decision**: Status derived from `self._current_state`, not re-derived from structural properties.
- **Status**: Implemented.

### 2026-07-08 — Timeline overdue_transition integration, deterministic explanation column, V1 freeze

- **Decision**: `transition_to()` wires timeline results into FSM state. `_derive_explanation()` adds human-readable column. V1 frozen.
- **Status**: Accepted. All implemented.

---

## V2 Decisions

### 2026-07-09 — V2 M1: Topic-level chunking for regulatory PDFs

- **Decision**: Chunk regulatory PDFs at numbered topic boundaries (Level 2 in the document hierarchy) rather than sub-section or paragraph boundaries. Target ~1,500 chars per chunk, merge adjacent small chunks within same Roman section, split large chunks at paragraph boundaries.
- **Rationale**: The 399-page SEBI Master Circular has ~98 numbered topics averaging 4,733 chars each — well within a single LLM call. Sub-section-level chunking produces 1,800+ tiny fragments (avg 399 chars) that lose regulatory context. Topic-level chunking produces 200 semantically coherent chunks.
- **Alternatives considered**: Sub-section chunking (too fine-grained, 1,800+ chunks), recursive character splitting (loses legal structure), semantic chunking via embedding similarity (too complex for initial implementation).
- **Status**: Implemented in `rag/chunker.py` (V2 M1, `32149c8`).

### 2026-07-09 — V2 M1: bge-small-en-v1.5 as default embedding model

- **Decision**: `BAAI/bge-small-en-v1.5` (384-dim, 133 MB) as the default local embedding model with lazy loading.
- **Rationale**: Strong MTEB retrieval scores on legal/regulatory text. Small enough for fast iteration (133 MB vs 1.3 GB for large variant). Lazy loading avoids startup penalty when embeddings aren't needed. Upgrade path to bge-large (1024-dim) in M4 if quality requires it.
- **Alternatives considered**: all-MiniLM-L6-v2 (384-dim, 90 MB, weaker on legal text), bge-large-en-v1.5 (1024-dim, 1.3 GB, better quality but too large for dev iteration).
- **Status**: Implemented in `rag/embedder.py` (V2 M1, `32149c8`).

### 2026-07-09 — V2 M1: Chroma PersistentClient for development vector store

- **Decision**: Use Chroma's `PersistentClient` (disk-backed, in-process) as the development vector store. Abstracted behind a `ChromaVectorStore` class that can be replaced with pgvector in V2 M5.
- **Rationale**: Chroma requires zero infrastructure (`pip install chromadb`). Persistent mode survives server restarts. The `VectorStore` abstraction (add/search/delete/get_by_circular_ref) makes the swap to pgvector a config change.
- **Alternatives considered**: Qdrant (separate service, operational overhead for dev), LanceDB (newer, smaller community), FAISS (no metadata filtering, no persistence without manual serialization).
- **Status**: Implemented in `rag/vector_store.py` (V2 M1, `32149c8`).

### 2026-07-09 — V2 M1: RAG behind `use_rag` feature flag, V1 path preserved

- **Decision**: All RAG integration in the parser and pipeline is behind a `use_rag` boolean flag on `TriggerRequest`. Default is `False` — identical V1 behavior. When `True`, the pipeline retrieves chunks from Chroma and passes them to the parser. Graceful fallback to full PDF extraction if the circular is not indexed.
- **Rationale**: Zero risk to V1. The feature flag pattern allows RAG to be tested in production without affecting existing behavior. The fallback path ensures the pipeline never breaks if Chroma is unavailable or the circular hasn't been indexed.
- **Alternatives considered**: Always-on RAG (breaks V1 tests, risky), separate RAG pipeline endpoint (duplicates pipeline logic), chunk-first-with-fallback (chosen approach).
- **Status**: Implemented in `pipeline.py`, `parser.py`, `runner.py` (V2 M1, `32149c8`).

### 2026-07-09 — V2 M1: Section-boundary merge guard

- **Decision**: The chunker never merges chunks across Roman section boundaries, even when both chunks are below `min_chunk_size`. Each chunk's metadata records its originating Roman section, topic number, and section path independently.
- **Rationale**: Merging across section boundaries would produce chunks with misleading metadata (e.g., a chunk containing text from both Section III and Section IV would be cited incorrectly). Preserving section boundaries ensures citation accuracy.
- **Impact**: Some chunks are smaller than `min_chunk_size` but semantically complete within their section context. The metadata records `chunk_index`/`chunk_total` so retrieval can reassemble adjacent small chunks when needed.
- **Status**: Implemented in `rag/chunker.py:_apply_size_constraints()` (V2 M1, `32149c8`).

### 2026-07-09 — V2 M2: Circular Registry as a backend-agnostic Protocol

- **Decision**: Define a `CircularRegistryBackend` Protocol (4 methods: `register`, `deregister`, `get`, `list_all`) and implement `JsonCircularRegistry` as the initial concrete backend. The module-level `get_registry()` singleton returns the protocol type, not the concrete class. `build_record()` is a module-level factory function, not a classmethod.
- **Rationale**: The JSON-file registry is a development mechanism. PostgreSQL replaces it in M4. The protocol allows callers (API endpoints, CLI) to be completely agnostic to the storage backend. `build_record()` as a module-level function avoids coupling callers to `JsonCircularRegistry`.
- **Alternatives considered**: No abstraction (hard-coded JSON, rewrite callers in M4), ABC with inheritance (overkill for 4 methods, Protocol is simpler), classmethod on protocol (Protocol does support it but module-level function is cleaner for a factory that only uses data from the record model).
- **Status**: Implemented in `rag/circular_registry.py` (V2 M2).

### 2026-07-09 — V2 M2: document_hash and index_version on every registry record

- **Decision**: Every `CircularRecord` carries `document_hash` (SHA-256 of the PDF at index time) and `index_version` (e.g., "v2-m2").
- **Rationale**: `document_hash` enables incremental re-indexing (skip if hash unchanged) and tamper detection. `index_version` tracks which chunking/embedding pipeline version produced the index, enabling migration scripts ("re-index all circulars from v2-m2 to v2-m4").
- **Status**: Implemented in `rag/circular_registry.py:CircularRecord` (V2 M2).

### 2026-07-09 — V2 M2: {circular_ref:path} for URL parameters

- **Decision**: Use FastAPI's `:path` converter for all URL parameters containing SEBI circular references, which include slashes (e.g., `SEBI/HO/MIRSD/P/CIR/2025/57`).
- **Rationale**: Without `:path`, FastAPI splits on slashes and only captures the first segment. The `:path` converter matches the entire remaining URL path.
- **Status**: Implemented in `rag.py` endpoints (V2 M2).

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
