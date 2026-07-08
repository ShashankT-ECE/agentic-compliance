# V2 Roadmap — Regulatory Intelligence Platform

> **Version**: 1.0 — 2026-07-08
> **Status**: Planning — awaiting approval before any implementation
> **Canonical source of truth** for V2 architecture decisions

---

## V2 Vision

Evolve from a single-circular compliance checker into a **production-grade regulatory
intelligence platform** that ingests the full SEBI regulatory corpus (master circulars,
amending circulars, regulations, and cross-referenced statutes), extracts obligations
at scale, tracks regulatory change over time, and evaluates broker compliance with
deterministic, auditable, and explainable verdicts.

---

## Architectural Principles (carried forward from V1)

| # | Principle | Constraint |
|---|-----------|------------|
| P1 | Deterministic evaluation | Node 3 must never call an LLM, make HTTP requests, or perform non-deterministic operations |
| P2 | Human-in-the-loop | Human approval required before any FSM enters the evaluator |
| P3 | Full audit trail | Every compliance finding must be traceable to the originating regulation text |
| P4 | Explainability | Every verdict must be explainable from the FSM + telemetry alone |
| P5 | Backward compatibility | V1 API surface preserved; all 410 tests continue to pass |
| P6 | Incremental delivery | Each milestone produces a working, testable increment |

## V2 Target Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                     REGULATORY INGESTION LAYER                       │
│                                                                     │
│  ┌──────────┐   ┌───────────┐   ┌──────────────┐   ┌────────────┐  │
│  │  PDF     │ → │ Chunking  │ → │  Embedding   │ → │  Vector    │  │
│  │ Ingestion│   │ Engine    │   │  Pipeline    │   │  Database  │  │
│  └──────────┘   └───────────┘   └──────────────┘   └────────────┘  │
│       │                                                │            │
│       ▼                                                ▼            │
│  ┌──────────┐                                   ┌──────────┐       │
│  │ Metadata │                                   │ Hybrid   │       │
│  │ Extract. │                                   │ Retrieval│       │
│  └──────────┘                                   └──────────┘       │
│       │                                                │            │
└───────┼────────────────────────────────────────────────┼────────────┘
        │                                                │
        ▼                                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     OBLIGATION EXTRACTION LAYER                      │
│                                                                     │
│  ┌──────────┐   ┌───────────┐   ┌──────────┐   ┌────────────┐     │
│  │ RAG-     │ → │ Multi-    │ → │ Cross-   │ → │ Diff       │     │
│  │ Assisted │   │ Obligation│   │ Reference│   │ Agent      │     │
│  │ Parser   │   │ Extractor │   │ Resolver │   │            │     │
│  └──────────┘   └───────────┘   └──────────┘   └────────────┘     │
│                                                                     │
└──────────────────────────────────┬──────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   V1 PIPELINE (preserved)                            │
│                                                                     │
│  ┌──────────┐   ┌───────────┐   ┌──────────┐   ┌────────────┐     │
│  │ FSM      │ → │ HITL      │ → │ Eval     │ → │ Scoreboard │     │
│  │ Extractor│   │ Gate      │   │ (Node 3) │   │ (Node 4)  │     │
│  └──────────┘   └───────────┘   └──────────┘   └────────────┘     │
│                                                                     │
└──────────────────────────────────┬──────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     PRODUCTION INFRASTRUCTURE                        │
│  PostgreSQL + pgvector  |  Docker Compose  |  CI/CD  |  Auth        │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Milestone Map

```
M10: Production Deploy
 │
M9:  Multi-Circular Support
 │
M8:  Diff Agent
 │
M7:  Cross-Reference Resolution
 │
M6:  Multi-Obligation Extraction
 │
M5:  Hybrid Retrieval (BM25 + Vector)
 │
M4:  Vector Database
 │
M3:  Metadata Extraction
 │
M2:  PDF Chunking Strategy
 │
M1:  Regulatory RAG Architecture
 │
V1.0.2 (frozen baseline)
```

---

## M1 — Regulatory RAG Architecture

**Objective**: Design and implement the Retrieval-Augmented Generation foundation
that replaces the V1 "stuff-entire-PDF-into-the-prompt" approach with a modular
retrieval pipeline. This milestone defines the RAG subsystem architecture, implements
the document store abstraction, and builds the retrieval interface that future
milestones plug into.

### Deliverables

1. **Document Store abstraction** — pluggable backend interface (`DocumentStore`)
   supporting CRUD for regulatory documents with metadata.
2. **Circular Registry** — SQLAlchemy model tracking every ingested circular
   (circular_number, date, title, department, status, parent_circular, superseded_by).
3. **Retrieval Pipeline** — `RetrievalPipeline` class that orchestrates: query →
   pre-retrieval (metadata filter) → retrieval → post-retrieval (rerank/deduplicate).
4. **RAG-augmented parser adapter** — wraps the V1 `parse_circular()` to accept
   retrieved context chunks instead of raw full-text. V1 path preserved as fallback.
5. **Configuration system** — YAML-based config for RAG parameters (chunk size,
   top-k, embedding model, retrieval weights).

### Files to Create

| File | Purpose |
|------|---------|
| `backend/app/rag/__init__.py` | RAG subsystem package |
| `backend/app/rag/document_store.py` | `DocumentStore` abstract base + in-memory impl |
| `backend/app/rag/retrieval.py` | `RetrievalPipeline` — orchestration |
| `backend/app/rag/config.py` | RAG configuration (Pydantic model + YAML loader) |
| `backend/app/models/circular.py` | `CircularRecord` SQLAlchemy model |
| `backend/config/rag.yaml` | Default RAG configuration |
| `backend/tests/test_rag_document_store.py` | Document store unit tests |
| `backend/tests/test_rag_retrieval.py` | Retrieval pipeline tests |

### Files to Modify

| File | Change |
|------|--------|
| `backend/app/models/__init__.py` | Export `CircularRecord` |
| `backend/app/pipeline/nodes/parser.py` | Add RAG-assisted parse path (fallback to V1) |
| `backend/pyproject.toml` | Add `pyyaml` dependency |

### Acceptance Criteria

- [ ] `DocumentStore` can ingest the 399-page master circular and the 2-page amendment
- [ ] `CircularRegistry` records metadata for all 3 circulars in `data/circulars/`
- [ ] `RetrievalPipeline` returns top-k relevant text chunks for a query
- [ ] In-memory `DocumentStore` passes all CRUD tests
- [ ] V1 parser path still works unchanged (410 tests pass)
- [ ] RAG config loaded from YAML with sensible defaults

### Tests

- `test_rag_document_store.py`: 12 tests — CRUD operations, metadata filtering, empty store edge cases
- `test_rag_retrieval.py`: 8 tests — top-k retrieval, empty query, duplicate handling
- `test_rag_config.py`: 4 tests — YAML loading, Pydantic validation, defaults

**New tests**: 24 | **Total**: 434

### Risks

| Risk | Mitigation |
|------|-----------|
| RAG abstraction too generic | Design for regulatory text specifically — don't over-abstract |
| Circular registry schema too narrow | Include extensible `metadata JSONB` field from day 1 |
| Breaking V1 parser path | Run full V1 test suite after every change to `parser.py` |

### Dependencies

- **None** (M1 is the foundation — depends only on V1.0.2 frozen baseline)

---

## M2 — PDF Chunking Strategy

**Objective**: Implement a domain-aware chunking engine for SEBI regulatory PDFs.
Unlike generic text chunking, regulatory documents have structural markers
(Chapters, Sections, Paras, Sub-paras, Annexures) that must be preserved for
accurate retrieval and cross-referencing.

### Deliverables

1. **Document Structure Parser** — extracts the table of contents, section hierarchy,
   and paragraph numbering from regulatory PDFs. Produces a `DocumentTree`.
2. **Semantic Chunker** — chunks text at section/paragraph boundaries with
   configurable overlap. Never splits mid-paragraph. Minimum chunk size enforced
   by merging adjacent small sections.
3. **Chunk Metadata Annotator** — attaches hierarchical metadata to every chunk:
   `section_path` (e.g., "III.A.39.1.2"), `circular_ref`, `parent_chunk_id`,
   `entity_type` (obligation, definition, procedure, reference).
4. **Chunk Overlap Strategy** — configurable sliding window with
   `prepend_context` (N chars from previous chunk) and `append_context`
   (N chars from next chunk) for retrieval continuity.
5. **Chunking Report** — statistics: total chunks, avg chunk size, chunk size
   distribution, orphaned sections, structural anomalies.

### Files to Create

| File | Purpose |
|------|---------|
| `backend/app/rag/chunking/__init__.py` | Chunking subsystem package |
| `backend/app/rag/chunking/structure_parser.py` | `DocumentStructureParser` — TOC extraction, hierarchy |
| `backend/app/rag/chunking/semantic_chunker.py` | `SemanticChunker` — boundary-aware chunking |
| `backend/app/rag/chunking/metadata.py` | `ChunkMetadata` model + annotator |
| `backend/app/rag/chunking/report.py` | `ChunkingReport` — statistics generator |
| `backend/config/chunking.yaml` | Chunking configuration |
| `backend/tests/test_chunking_structure.py` | Structure parser tests |
| `backend/tests/test_chunking_semantic.py` | Semantic chunker tests |
| `backend/tests/test_chunking_integration.py` | End-to-end chunking tests |

### Files to Modify

| File | Change |
|------|--------|
| `backend/app/rag/document_store.py` | Add `add_chunks()` method accepting chunked documents |

### Acceptance Criteria

- [ ] 399-page master circular chunked into < 500 chunks (avg ~1500 chars)
- [ ] All 10 sections (I–X) correctly identified as top-level structure
- [ ] Para 39.1.2 text appears in exactly one chunk (no mid-paragraph splits)
- [ ] Every chunk has `section_path` metadata populated
- [ ] Table of contents extracted with ≥ 95% accuracy
- [ ] Chunk overlap correctly prepends/appends context from adjacent chunks

### Tests

- `test_chunking_structure.py`: 15 tests — TOC parsing, hierarchy extraction, edge cases (missing TOC, single-page, image-only pages)
- `test_chunking_semantic.py`: 12 tests — boundary detection, overlap generation, min-chunk merging, empty sections
- `test_chunking_integration.py`: 6 tests — full pipeline on 2-page circular, 399-page master circular, multi-circular batch

**New tests**: 33 | **Total**: 467

### Risks

| Risk | Mitigation |
|------|-----------|
| Inconsistent paragraph numbering across circulars | Heuristic-based fallback: detect numbering patterns (roman, decimal, alphanumeric) |
| Annexures and forms break structural parsing | Treat annexures as leaf sections — chunk by page with low-priority metadata |
| Table of contents page(s) may be scanned images | Fall back to text-based section header detection if TOC extraction fails |

### Dependencies

- **M1** (RAG document store for storing chunked documents)

---

## M3 — Metadata Extraction

**Objective**: Extract structured metadata from SEBI circulars to power filtering,
search, and cross-referencing. Metadata includes circular identity (number, date,
department, signatory), subject classification, entity targeting, effective dates,
and supersession chains.

### Deliverables

1. **Circular Identity Extractor** — regex + LLM hybrid: extracts circular number,
   date, department code, issuing officer, subject line with ≥ 99% accuracy.
2. **Entity Classifier** — classifies each obligation's target entities from a
   controlled vocabulary: `trading_member`, `clearing_member`, `stock_broker`,
   `recognized_stock_exchange`, `clearing_corporation`, `depository`,
   `depository_participant`, `investor`.
3. **Supersession Chain Builder** — parses rescission/rescinded-by clauses to build
   a directed graph of circular relationships (supersedes/superseded_by).
4. **Effective Date Resolver** — extracts effective dates, phased implementation
   dates, and grace periods. Handles "from the date of issuance", "within 90 days",
   "by June 1st of the subsequent year".
5. **Subject Taxonomy Tagger** — maps circular text to a predefined taxonomy:
   margin_requirements, client_onboarding, KYC, technology_compliance,
   investor_grievance, registration, supervision, reporting.
6. **Metadata API endpoint** — `GET /api/circulars/{circular_id}/metadata`

### Files to Create

| File | Purpose |
|------|---------|
| `backend/app/rag/metadata/__init__.py` | Metadata extraction package |
| `backend/app/rag/metadata/identity.py` | Circular identity extraction |
| `backend/app/rag/metadata/entities.py` | Entity classifier + controlled vocabulary |
| `backend/app/rag/metadata/supersession.py` | Supersession chain builder + graph |
| `backend/app/rag/metadata/dates.py` | Effective date resolver |
| `backend/app/rag/metadata/taxonomy.py` | Subject taxonomy tagger |
| `backend/app/models/circular_metadata.py` | `CircularMetadata` Pydantic + SQLAlchemy model |
| `backend/app/api/routes/circulars.py` | Circular metadata API endpoints |
| `backend/tests/test_metadata_identity.py` | Identity extraction tests |
| `backend/tests/test_metadata_entities.py` | Entity classifier tests |
| `backend/tests/test_metadata_supersession.py` | Supersession chain tests |
| `backend/tests/test_metadata_dates.py` | Date resolution tests |

### Files to Modify

| File | Change |
|------|--------|
| `backend/app/api/routes/__init__.py` | Register circulars router |
| `backend/app/main.py` | Mount circulars router |

### Acceptance Criteria

- [ ] Circular number extracted correctly for all 3 circulars in `data/circulars/`
- [ ] Entity classifier achieves ≥ 90% precision on 399-page master circular
- [ ] Supersession chain correctly identifies CIR/2025/90 supersedes the Aug 2024 circular
- [ ] Effective dates extracted for all timeline-bearing obligations
- [ ] Subject taxonomy assigns ≥ 1 category to every obligation
- [ ] `GET /api/circulars/{id}/metadata` returns complete metadata JSON

### Tests

- `test_metadata_identity.py`: 10 tests — regex extraction, date parsing, edge cases
- `test_metadata_entities.py`: 8 tests — classifier accuracy, controlled vocabulary validation
- `test_metadata_supersession.py`: 7 tests — chain building, circular graphs, cycles
- `test_metadata_dates.py`: 9 tests — relative dates, phased dates, grace periods

**New tests**: 34 | **Total**: 501

### Risks

| Risk | Mitigation |
|------|-----------|
| LLM hallucination on metadata fields | Identity fields use regex first; LLM only for ambiguous cases with confidence scores |
| Taxonomy drift over time | Taxonomy is config-driven (YAML), not hardcoded; updated without code changes |
| Supersession chains reference unresolvable circulars | External references stored with "unresolved" flag; resolved lazily when circular is ingested |

### Dependencies

- **M1** (Circular Registry, document store)
- **M2** (Chunk metadata for section-level entity classification)

---

## M4 — Vector Database

**Objective**: Select, integrate, and operationalize a vector database for storing
and querying regulatory text embeddings. Start with a lightweight embedded database
for development, with a clear migration path to production infrastructure.

### Deliverables

1. **Vector DB Selection Report** — evaluation of Chroma, pgvector, LanceDB, Qdrant
   against criteria: Python integration, zero-infra dev mode, production scalability,
   metadata filtering, hybrid search support, community health.
2. **Embedding Pipeline** — `EmbeddingPipeline` that takes chunked documents, generates
   embeddings via the configured model, and indexes them in the vector store.
3. **Embedding Model Integration** — abstraction over embedding providers:
   - `LocalEmbedder` (sentence-transformers / bge-large-en-v1.5) — zero-cost, offline
   - `OpenAIEmbedder` (text-embedding-3-small) — higher quality, API cost
   - Config-driven provider selection
4. **Vector Store Adapter** — `VectorStore` abstract base with implementations:
   - `ChromaVectorStore` — development (no infra, in-process)
   - `PGVectorStore` — production (colocated with app DB)
5. **Batch Indexing** — `index_circular(circular_id)` — chunk → embed → store pipeline
   for a single circular. `index_all()` for bulk re-indexing.
6. **CLI tool** — `python -m app.cli index --circular-id=X` for manual indexing.

### Files to Create

| File | Purpose |
|------|---------|
| `backend/app/rag/vector_store/__init__.py` | Vector store package |
| `backend/app/rag/vector_store/base.py` | `VectorStore` abstract base class |
| `backend/app/rag/vector_store/chroma_store.py` | Chroma implementation |
| `backend/app/rag/vector_store/pgvector_store.py` | pgvector implementation |
| `backend/app/rag/embedding/__init__.py` | Embedding package |
| `backend/app/rag/embedding/base.py` | `Embedder` abstract base |
| `backend/app/rag/embedding/local_embedder.py` | Sentence-transformers wrapper |
| `backend/app/rag/embedding/openai_embedder.py` | OpenAI embeddings wrapper |
| `backend/app/rag/embedding/pipeline.py` | `EmbeddingPipeline` — chunk → embed → index |
| `backend/app/cli.py` | CLI entry point (index, search, stats) |
| `backend/tests/test_vector_store.py` | Vector store interface tests |
| `backend/tests/test_embedding.py` | Embedding pipeline tests |
| `docs/v2_vector_db_selection.md` | Selection report |

### Files to Modify

| File | Change |
|------|--------|
| `backend/pyproject.toml` | Add `chromadb`, `sentence-transformers`, optional `pgvector` |
| `backend/config/rag.yaml` | Add embedding and vector store configuration sections |

### Acceptance Criteria

- [ ] Chroma in-process store indexes 399-page master circular in < 30 seconds
- [ ] Embedding dimension is 1024 (bge-large) or 1536 (OpenAI)
- [ ] `EmbeddingPipeline` correctly maps chunks → embeddings → vector store
- [ ] Vector search returns semantically relevant chunks for regulatory queries
- [ ] `LocalEmbedder` works offline (no API key required)
- [ ] Abstract interfaces allow swapping Chroma → pgvector without RAG logic changes
- [ ] CLI `index` command completes successfully

### Tests

- `test_vector_store.py`: 14 tests — CRUD, metadata filtering, batch operations, empty store
- `test_embedding.py`: 10 tests — embedding generation, dimension consistency, provider switching, error handling

**New tests**: 24 | **Total**: 525

### Risks

| Risk | Mitigation |
|------|-----------|
| Chroma not suitable for production | PGVector implementation built concurrently; swap is a config change |
| Local embedding model too large for deployment | Use ONNX-quantized variant (~500 MB vs 1.3 GB) |
| Embedding cost at scale (OpenAI) | Local embedder is the default; OpenAI is opt-in via config |

### Dependencies

- **M1** (document store for chunk storage)
- **M2** (chunked documents to embed)

---

## M5 — Hybrid Retrieval (BM25 + Vector)

**Objective**: Implement a hybrid retrieval system combining sparse (BM25) and dense
(vector embedding) retrieval for regulatory search. BM25 excels at exact keyword
matches (circular numbers, legal terms), while vector search captures semantic
similarity ("margin collection timeline" ≈ "deadline for collecting margins").

### Deliverables

1. **BM25 Index** — per-circular BM25 index built from chunked text using
   `rank_bm25` or PostgreSQL's `ts_rank`. Tokenized with legal-domain stop words.
2. **Reciprocal Rank Fusion (RRF)** — merges BM25 and vector result sets with
   configurable weighting. Default: 0.4 BM25 + 0.6 vector.
3. **HybridRetriever** — `HybridRetriever` class implementing:
   - `retrieve(query, top_k, filters)` → fused results with provenance
   - Per-result scores (BM25 score, vector similarity, RRF score)
   - Metadata-filtered retrieval (e.g., "only chunks from Section III")
4. **Re-ranking** — lightweight cross-encoder re-ranker (optional, config-driven):
   `CrossEncoderReRanker` using `ms-marco-MiniLM` or similar.
5. **Retrieval Evaluation** — `RetrievalEvaluator` with:
   - 20 curated regulatory queries with ground-truth relevant chunks
   - Metrics: MRR@10, NDCG@10, Recall@10
   - Regression benchmark run on every commit

### Files to Create

| File | Purpose |
|------|---------|
| `backend/app/rag/retrieval/bm25_index.py` | BM25 index builder + searcher |
| `backend/app/rag/retrieval/hybrid_retriever.py` | `HybridRetriever` + RRF fusion |
| `backend/app/rag/retrieval/reranker.py` | `CrossEncoderReRanker` |
| `backend/app/rag/retrieval/evaluator.py` | `RetrievalEvaluator` + benchmark queries |
| `backend/data/benchmarks/retrieval_queries.json` | Curated query set with relevance judgments |
| `backend/tests/test_bm25.py` | BM25 index tests |
| `backend/tests/test_hybrid_retrieval.py` | Hybrid retrieval tests |
| `backend/tests/test_reranker.py` | Re-ranker tests |
| `backend/tests/test_retrieval_evaluator.py` | Evaluator tests + benchmark regression |

### Files to Modify

| File | Change |
|------|--------|
| `backend/app/rag/retrieval.py` | Integrate `HybridRetriever` into `RetrievalPipeline` |
| `backend/config/rag.yaml` | Add retrieval weights, reranker config, benchmark path |

### Acceptance Criteria

- [ ] Hybrid retrieval beats BM25-only and vector-only on ≥ 80% of benchmark queries
- [ ] MRR@10 ≥ 0.75 on benchmark set
- [ ] Query "margin collection timeline by settlement day" returns Para 39.1.2 in top 3
- [ ] Metadata-filtered retrieval correctly restricts to specified sections
- [ ] Re-ranker improves NDCG@10 by ≥ 5% when enabled
- [ ] Benchmark evaluation runs in < 60 seconds

### Tests

- `test_bm25.py`: 10 tests — indexing, tokenization, search, empty index
- `test_hybrid_retrieval.py`: 12 tests — RRF fusion, weight configuration, metadata filtering, edge cases
- `test_reranker.py`: 6 tests — re-ranking improves order, no-op when disabled
- `test_retrieval_evaluator.py`: 8 tests — metric calculation, benchmark regression, result persistence

**New tests**: 36 | **Total**: 561

### Risks

| Risk | Mitigation |
|------|-----------|
| BM25 + vector disagree wildly (low agreement) | RRF handles this gracefully; log divergence for tuning |
| Legal stop words differ from general English | Curate domain stop word list from SEBI corpus statistics |
| Benchmark queries become stale as corpus grows | Version benchmark alongside corpus; update quarterly |

### Dependencies

- **M4** (vector database — vector side of hybrid retrieval)

---

## M6 — Multi-Obligation Extraction

**Objective**: Scale obligation extraction from "one prompt → ~4 clauses" to handling
the 399-page master circular's 130+ obligation-bearing provisions. Uses the RAG
pipeline to extract obligations per section, then deduplicate and merge.

### Deliverables

1. **Section-by-Section Extractor** — iterates over document sections (from M2
   structure parser), retrieves the most relevant chunks, and extracts obligations
   per section. Significantly reduces per-call token load.
2. **Obligation Deduplicator** — detects near-duplicate obligations extracted from
   adjacent/overlapping sections. Uses Jaccard similarity on normalized text +
   clause_id conflict resolution.
3. **Obligation Merger** — merges partial obligations from different sections into
   complete clause objects. Handles cross-section obligations (e.g., an obligation
   defined in III.39.1.2 with penalty in III.39.1.5).
4. **Extraction Progress Tracker** — `ExtractionJob` model tracking: sections
   processed, obligations extracted, failures, retries. Resumable.
5. **Extraction Quality Report** — compares extracted obligations against a
   manually curated "gold set" for the 2-page circular (known: 4 obligations).
   Precision/recall metrics.

### Files to Create

| File | Purpose |
|------|---------|
| `backend/app/rag/extraction/__init__.py` | Extraction package |
| `backend/app/rag/extraction/section_extractor.py` | Section-by-section extraction |
| `backend/app/rag/extraction/deduplicator.py` | Obligation deduplication |
| `backend/app/rag/extraction/merger.py` | Cross-section obligation merging |
| `backend/app/rag/extraction/job_tracker.py` | `ExtractionJob` — progress tracking, resumability |
| `backend/app/rag/extraction/quality.py` | Quality report generation |
| `backend/data/benchmarks/gold_obligations.json` | Gold-standard obligations for known circulars |
| `backend/tests/test_section_extractor.py` | Section extractor tests |
| `backend/tests/test_deduplicator.py` | Deduplication tests |
| `backend/tests/test_merger.py` | Merger tests |
| `backend/tests/test_extraction_quality.py` | Quality evaluation tests |

### Files to Modify

| File | Change |
|------|--------|
| `backend/app/pipeline/nodes/parser.py` | Integrate section-by-section extraction path |
| `backend/config/rag.yaml` | Add extraction config (sections per batch, dedup threshold) |

### Acceptance Criteria

- [ ] 399-page master circular: ≥ 40 obligations extracted (V1 did 53 from single call)
- [ ] 2-page amendment: 4 obligations extracted, matches gold set with 100% precision
- [ ] No duplicate obligations (same clause_id) in final output
- [ ] Cross-section obligations correctly merged (e.g., CL-02 obligation + penalty clause)
- [ ] Extraction job resumable after interruption
- [ ] Single-section extraction latency < 10s per section

### Tests

- `test_section_extractor.py`: 14 tests — per-section extraction, empty sections, LLM failure recovery, progress tracking
- `test_deduplicator.py`: 10 tests — exact duplicates, near-duplicates, boundary cases
- `test_merger.py`: 8 tests — cross-section merging, conflict resolution, completeness checks
- `test_extraction_quality.py`: 8 tests — precision, recall, F1 against gold sets, regression benchmark

**New tests**: 40 | **Total**: 601

### Risks

| Risk | Mitigation |
|------|-----------|
| Extraction quality varies by section complexity | Confidence scores per extraction; low-confidence sections flagged for human review |
| LLM cost scales linearly with sections | Batch small sections together; cache LLM responses for regression testing |
| Deduplication misses semantically identical obligations | Two-pass dedup: clause_id first (exact), then embedding similarity (semantic) |

### Dependencies

- **M2** (document structure for section-by-section iteration)
- **M5** (hybrid retrieval for per-section context retrieval)

---

## M7 — Cross-Reference Resolution

**Objective**: Build a cross-reference resolver that parses and resolves references
within and across regulatory documents. SEBI circulars cite other circulars, specific
paragraphs, regulations, and sections of the SEBI Act. Resolving these is critical
for building a complete regulatory graph and understanding obligation scope.

### Deliverables

1. **Reference Parser** — NLP + regex hybrid that extracts typed references from text:
   - `CircularRef(circular_no="SEBI/HO/MIRSD/.../2025/57")`
   - `ParaRef(para="39.1.2", parent_section="III")`
   - `RegulationRef(regulation="Regulation 30", act="SEBI (Stock Brokers) Regulations, 1992")`
   - `SectionRef(section="Section 11(1)", chapter="Chapter IV", act="SEBI Act, 1992")`
2. **Reference Graph** — NetworkX directed graph linking every parsed reference to its
   resolved target (document, section, or external reference). Supports traversal:
   "find all obligations that reference Regulation 30".
3. **Lazy Resolver** — resolves references on demand. Unresolvable external references
   (e.g., circulars not yet ingested) stored as "pending" with a resolution queue.
4. **Citation Completeness Checker** — reports unreferenced circulars, broken chains,
   and orphaned paragraphs.
5. **Reference API** — `GET /api/circulars/{id}/references` — returns all inbound
   and outbound references for a circular.

### Files to Create

| File | Purpose |
|------|---------|
| `backend/app/rag/references/__init__.py` | Cross-reference package |
| `backend/app/rag/references/parser.py` | `ReferenceParser` — typed reference extraction |
| `backend/app/rag/references/graph.py` | `ReferenceGraph` — NetworkX graph builder |
| `backend/app/rag/references/resolver.py` | `ReferenceResolver` — lazy resolution engine |
| `backend/app/rag/references/models.py` | Reference Pydantic models (`CircularRef`, `ParaRef`, etc.) |
| `backend/app/rag/references/completeness.py` | Citation completeness checker |
| `backend/app/api/routes/references.py` | Reference API endpoints |
| `backend/tests/test_reference_parser.py` | Reference extraction tests |
| `backend/tests/test_reference_graph.py` | Graph traversal tests |
| `backend/tests/test_reference_resolver.py` | Resolution engine tests |

### Files to Modify

| File | Change |
|------|--------|
| `backend/app/api/routes/circulars.py` | Add reference-related endpoints |

### Acceptance Criteria

- [ ] Parses ≥ 95% of references in the 399-page master circular
- [ ] Reference types correctly classified (circular, para, regulation, section)
- [ ] All 130 rescinded circular references from the master circular appendix captured
- [ ] Reference graph correctly links CIR/2025/57 as superseded_by CIR/2025/90
- [ ] Unresolved external references marked with "pending" status
- [ ] `GET /api/circulars/{id}/references` returns complete reference tree

### Tests

- `test_reference_parser.py`: 14 tests — all reference types, edge cases (roman numerals, multi-line refs), false positives
- `test_reference_graph.py`: 10 tests — graph construction, traversal, cycle detection
- `test_reference_resolver.py`: 8 tests — resolution success, pending marking, circular resolution

**New tests**: 32 | **Total**: 633

### Risks

| Risk | Mitigation |
|------|-----------|
| Reference formats vary across circulars and over time | Rule-based parser with fallback LLM extraction for ambiguous cases |
| Resolving all 130+ circulars requires ingesting them all | Lazy resolution — only resolve when queried; bulk resolve as circulars are ingested |
| Reference graph grows very large | Graph is per-circular; global graph built lazily and cached |

### Dependencies

- **M3** (metadata extraction — circular identity for resolving references)

---

## M8 — Diff Agent for Regulatory Changes

**Objective**: Build an agent that compares two versions of a master circular (or a
circular and its amendment), identifies changed/added/removed obligations, and produces
a structured change report. This is the foundation for regulatory change monitoring.

### Deliverables

1. **Circular Differ** — `CircularDiffer` that compares two circulars at three levels:
   - **Structural**: sections added/removed/reordered (from M2 structure trees)
   - **Textual**: paragraph-level diff with semantic change classification
   - **Obligation-level**: extracted obligations compared for addition/modification/removal
2. **Change Classifier** — classifies each change as:
   - `OBLIGATION_ADDED` — new compliance requirement
   - `OBLIGATION_REMOVED` — requirement rescinded
   - `OBLIGATION_MODIFIED` — scope/entity/timeline changed
   - `CLARIFICATION` — wording change, no obligation impact
   - `ADMINISTRATIVE` — formatting, numbering, metadata only
3. **Impact Assessor** — for each obligation-level change, estimates impact: which
   brokers are affected, which obligations need re-evaluation, which verdicts
   may change.
4. **Diff Report Generator** — produces a structured markdown + JSON report with
   executive summary, detailed change log, and impacted obligation inventory.
5. **Change Alert API** — `POST /api/diff/compare` — compare two circulars and
   return structured diff. `GET /api/diff/history` — change history for a circular.

### Files to Create

| File | Purpose |
|------|---------|
| `backend/app/rag/diff/__init__.py` | Diff agent package |
| `backend/app/rag/diff/differ.py` | `CircularDiffer` — three-level comparison |
| `backend/app/rag/diff/classifier.py` | `ChangeClassifier` — change type taxonomy |
| `backend/app/rag/diff/impact.py` | `ImpactAssessor` — obligation-level impact |
| `backend/app/rag/diff/report.py` | Diff report generator (markdown + JSON) |
| `backend/app/rag/diff/models.py` | Diff Pydantic models (`CircularDiff`, `ChangeRecord`) |
| `backend/app/api/routes/diff.py` | Diff API endpoints |
| `backend/tests/test_diff_differ.py` | Differ tests |
| `backend/tests/test_diff_classifier.py` | Classifier tests |
| `backend/tests/test_diff_impact.py` | Impact assessment tests |
| `backend/data/fixtures/circular_v1_aug2024.txt` | Previous master circular text (for diff testing) |

### Files to Modify

| File | Change |
|------|--------|
| `backend/app/api/routes/__init__.py` | Register diff router |

### Acceptance Criteria

- [ ] Comparing the Aug 2024 master circular with the Jun 2025 master circular:
  - Identifies ≥ 90% of new/changed obligations
  - Classifies changes with ≥ 85% accuracy (validated manually on 20 samples)
- [ ] Structural diff correctly identifies new/removed/reordered sections
- [ ] Impact assessment correctly flags brokers affected by margin timeline changes
- [ ] Diff report is human-readable (executive summary + detail)
- [ ] API returns structured diff in < 30 seconds for 399-page comparison

### Tests

- `test_diff_differ.py`: 12 tests — structural diff, textual diff, obligation diff, identical circulars
- `test_diff_classifier.py`: 10 tests — all 5 change types, edge cases, confidence scoring
- `test_diff_impact.py`: 8 tests — impact scope, affected entities, verdict re-evaluation flags

**New tests**: 30 | **Total**: 663

### Risks

| Risk | Mitigation |
|------|-----------|
| False positives in obligation-level diff | Classification confidence scores; low-confidence changes flagged for HITL review |
| Aug 2024 circular text may not be available digitally | Use PDF extraction (identical pipeline); if unavailable, mark as limitation |
| LLM hallucination on change classification | Classifier is primarily rule-based; LLM used only for ambiguous cases with explicit confidence |

### Dependencies

- **M2** (structure trees for structural diff)
- **M6** (obligation extraction for obligation-level diff)

---

## M9 — Multi-Circular Support

**Objective**: Scale the platform from single-circular to multi-circular operation.
Support simultaneous evaluation of obligations extracted from multiple circulars,
cross-circular obligation conflict detection, and unified compliance scoreboards.

### Deliverables

1. **Circular Set** — `CircularSet` model grouping related circulars for joint
   evaluation (e.g., "Master Circular + all amending circulars since last review").
2. **Cross-Circular Obligation Index** — unified index of all obligations across
   all ingested circulars, keyed by entity type + obligation category. Powers
   queries like "all margin-related obligations for trading members".
3. **Obligation Conflict Detector** — detects when two circulars impose conflicting
   or redundant obligations on the same entity. Classifies as:
   - `CONFLICT` — contradictory requirements (e.g., T+2 vs T+1 deadline)
   - `REDUNDANT` — duplicate obligation (superseded)
   - `REFINEMENT` — newer circular tightens/expands an existing obligation
4. **Multi-Circular Pipeline** — `MultiCircularRunner` that evaluates a `CircularSet`
   against broker telemetry, producing per-circular verdicts with cross-circular
   conflict annotations.
5. **Unified Scoreboard** — aggregates verdicts across circulars. Shows per-circular
   and cross-circular compliance rates. Flags conflict-affected verdicts.
6. **Circular Set API** — `POST /api/circular-sets` (create set), `POST /api/pipeline/trigger-set` (trigger multi-circular run), `GET /api/circular-sets/{id}/scoreboard`.

### Files to Create

| File | Purpose |
|------|---------|
| `backend/app/models/circular_set.py` | `CircularSet` + `CircularSetMembership` models |
| `backend/app/rag/cross_circular/__init__.py` | Cross-circular package |
| `backend/app/rag/cross_circular/index.py` | `CrossCircularObligationIndex` |
| `backend/app/rag/cross_circular/conflict.py` | Obligation conflict detector |
| `backend/app/pipeline/multi_runner.py` | `MultiCircularRunner` |
| `backend/app/api/routes/circular_sets.py` | Circular set API |
| `backend/app/api/routes/multi_pipeline.py` | Multi-circular pipeline endpoints |
| `backend/tests/test_cross_circular_index.py` | Obligation index tests |
| `backend/tests/test_conflict_detector.py` | Conflict detection tests |
| `backend/tests/test_multi_runner.py` | Multi-circular pipeline tests |
| `backend/tests/test_circular_sets_api.py` | Circular set API tests |

### Files to Modify

| File | Change |
|------|--------|
| `backend/app/api/routes/__init__.py` | Register new routers |
| `backend/app/pipeline/runner.py` | Add multi-circular support to runner |

### Acceptance Criteria

- [ ] Circular set with 3 circulars (master + 2 amendments) evaluated in single run
- [ ] Conflict detector correctly identifies CIR/2025/57 obligations as REDUNDANT
      when CIR/2025/90 supersedes them
- [ ] Unified scoreboard shows per-circular and cross-circular compliance
- [ ] Cross-circular obligation index supports entity-type + category queries
- [ ] Multi-circular pipeline returns results in < 5 minutes for 3-circular set
- [ ] All 410 V1 tests continue to pass (single-circular path unchanged)

### Tests

- `test_cross_circular_index.py`: 12 tests — indexing, multi-entity query, category filtering
- `test_conflict_detector.py`: 10 tests — CONFLICT, REDUNDANT, REFINEMENT detection
- `test_multi_runner.py`: 14 tests — multi-circular execution, error isolation, partial failures
- `test_circular_sets_api.py`: 8 tests — CRUD, membership management, trigger

**New tests**: 44 | **Total**: 707

### Risks

| Risk | Mitigation |
|------|-----------|
| Conflict detection produces false positives | Human review step before conflicts are surfaced in reports |
| Multi-circular pipeline latency grows with circular count | Parallelize per-circular extraction; evaluator is already per-FSM parallel |
| Conflicting obligations produce contradictory verdicts | Flag conflicts in report; do not resolve automatically — defer to human reviewer |

### Dependencies

- **M6** (obligation extraction for per-circular obligations)
- **M7** (cross-reference resolution for supersession chain awareness)
- **M8** (diff agent for change awareness)

---

## M10 — Production Deployment

**Objective**: Harden the platform for production deployment. Migrate from in-memory
stores to PostgreSQL, add authentication, containerize the full stack, set up CI/CD,
and implement observability.

### Deliverables

1. **PostgreSQL Migration** — replace all in-memory stores with SQLAlchemy + Alembic:
   - `PipelineRun` — pipeline state persistence (survives restart)
   - `CircularRecord` — circular registry (from M1)
   - `TelemetryEvent` — broker telemetry (from M0)
   - `ComplianceReport` — audit reports (from M7)
   - `LockedFSM` — HITL state (from M4)
2. **pgvector Integration** — migrate vector store from Chroma to pgvector (from M4).
   Single PostgreSQL instance for both relational and vector data.
3. **Authentication** — JWT-based API authentication with:
   - `POST /auth/login` — username/password → JWT
   - `POST /auth/refresh` — refresh token rotation
   - Role-based access: `admin`, `compliance_officer`, `auditor`, `readonly`
   - API key option for machine-to-machine access
4. **Docker Compose Full-Stack** — single `docker-compose up`:
   - `backend` — FastAPI + Uvicorn (multi-worker)
   - `frontend` — Nginx serving React build
   - `db` — PostgreSQL 16 + pgvector
   - `redis` — session cache + rate limiting
5. **CI/CD Pipeline** — GitHub Actions:
   - Lint (ruff, eslint, prettier)
   - Type check (mypy, tsc)
   - Test suite (707 tests)
   - Retrieval benchmark regression
   - Build containers
   - Deploy to staging
6. **Observability** — structured logging (structlog), Prometheus metrics, health
   check endpoints, Sentry error tracking (optional).
7. **Rate Limiting** — per-endpoint, per-user rate limiting via slowapi + Redis.
8. **Frontend Test Suite** — Vitest + React Testing Library for all components.

### Files to Create

| File | Purpose |
|------|---------|
| `backend/app/db/__init__.py` | Database package |
| `backend/app/db/session.py` | SQLAlchemy async session factory |
| `backend/app/db/base.py` | Declarative base |
| `backend/app/db/migrations/` | Alembic migrations |
| `backend/app/auth/__init__.py` | Authentication package |
| `backend/app/auth/jwt.py` | JWT encode/decode/refresh |
| `backend/app/auth/dependencies.py` | FastAPI auth dependencies |
| `backend/app/auth/models.py` | User + API key models |
| `backend/app/middleware/rate_limit.py` | Rate limiting middleware |
| `backend/app/middleware/logging.py` | Structured logging middleware |
| `docker-compose.yml` | Full-stack compose file |
| `docker/Dockerfile.backend` | Backend container |
| `docker/Dockerfile.frontend` | Frontend container |
| `docker/nginx.conf` | Nginx config |
| `.github/workflows/ci.yml` | CI pipeline |
| `.github/workflows/deploy.yml` | Deploy pipeline |
| `frontend/src/**/*.test.tsx` | Component tests (~40 files) |
| `backend/tests/test_auth.py` | Auth tests |
| `backend/tests/test_db_migration.py` | Migration tests |

### Files to Modify

| File | Change |
|------|--------|
| `backend/app/pipeline/runner.py` | Replace `_get_store()` / `_set_store()` with DB-backed store |
| `backend/app/api/routes/reports.py` | Replace `_report_store` with DB |
| `backend/app/api/routes/pipeline.py` | Replace in-memory run store with DB |
| `backend/app/models/*.py` | Add SQLAlchemy mappings |
| `backend/app/main.py` | Add auth middleware, rate limiting, CORS hardening |
| `backend/pyproject.toml` | Add production dependencies |
| `backend/config/rag.yaml` | Add production database connection string |

### Acceptance Criteria

- [ ] `docker-compose up` starts all 4 services, frontend accessible at `localhost:80`
- [ ] Pipeline state survives backend restart (PostgreSQL-backed)
- [ ] Unauthenticated requests to `/api/*` return 401
- [ ] JWT login flow works end-to-end
- [ ] Rate limiting returns 429 after threshold exceeded
- [ ] CI pipeline runs on every PR: lint → type-check → 707 tests → benchmark
- [ ] Retrieval benchmark does not regress from M5 baseline
- [ ] Frontend test suite covers all components (≥ 40 test files)
- [ ] Health check endpoint returns PostgreSQL + Redis status
- [ ] Structured logs emitted in JSON format

### Tests

(Counted in frontend test suite + auth/migration tests above — estimated 60 new backend + 80 frontend)

**New tests**: ~140 | **Total**: ~847

### Risks

| Risk | Mitigation |
|------|-----------|
| Database migration breaks V1 test data assumptions | Run full test suite against migrated DB; keep in-memory store for unit tests |
| Docker Compose complexity | Single `docker-compose.yml` with health checks and dependency ordering |
| JWT secret management in production | Documented as requiring environment variable; never committed to repo |
| CI costs at scale | Rust-based linters (ruff) for speed; cache Python/Node dependencies |

### Dependencies

- **M4** (pgvector for production vector DB)
- **M9** (multi-circular pipeline — production deployment target)

---

## Test Summary

| Milestone | New Tests | Cumulative |
|-----------|-----------|------------|
| V1.0.2 (baseline) | — | 410 |
| M1: RAG Architecture | 24 | 434 |
| M2: PDF Chunking | 33 | 467 |
| M3: Metadata Extraction | 34 | 501 |
| M4: Vector Database | 24 | 525 |
| M5: Hybrid Retrieval | 36 | 561 |
| M6: Multi-Obligation Extraction | 40 | 601 |
| M7: Cross-Reference Resolution | 32 | 633 |
| M8: Diff Agent | 30 | 663 |
| M9: Multi-Circular Support | 44 | 707 |
| M10: Production Deployment | ~140 | ~847 |

---

## Dependency Graph

```
M1 ────────┐
           ├──→ M2 ──→ M3
           │         │
           │         ├──→ M7
           │         │
           ├──→ M4 ──┤
           │         │
           └──→ M5 ──┤
                     │
                     ├──→ M6 ──→ M8
                     │              │
                     └──────────────┼──→ M9 ──→ M10
                                    │
                              M3 ───┘
```

## Critical Path

**M1 → M2 → M6 → M8 → M9 → M10** (6 milestones, longest chain)

Estimated time at normal pace: ~8-12 weeks for a solo developer; ~4-6 weeks for two developers working asynchronously.

## Architecture Decision Records (to be ratified)

### ADR-V2-01: Vector Database Selection

- **Decision**: Use Chroma for development, pgvector for production.
- **Rationale**: Chroma requires zero infrastructure (pip install, in-process). pgvector
  colocated with PostgreSQL eliminates a separate vector DB service. Migration is a
  config change.
- **Alternatives considered**: Qdrant (separate service, operational overhead), LanceDB
  (newer, smaller community), FAISS (no metadata filtering).
- **Status**: Proposed — ratify before M4.

### ADR-V2-02: Chunking Strategy

- **Decision**: Section-boundary-aware chunking with overlap, not fixed-size sliding window.
- **Rationale**: Regulatory text meaning is defined by section/paragraph boundaries.
  Splitting mid-paragraph ("39.1.2 ... TMs/CMs will have time till settlement day
  [CHUNK BREAK] to collect margins") destroys obligation semantics.
- **Alternatives considered**: Recursive character splitting (LangChain default), semantic
  chunking via embedding similarity, agentic chunking.
- **Status**: Proposed — ratify before M2.

### ADR-V2-03: Embedding Model

- **Decision**: `BAAI/bge-large-en-v1.5` as default (local), `text-embedding-3-small`
  as opt-in (API). 1024 dimensions.
- **Rationale**: BGE-large tops the MTEB leaderboard for retrieval tasks, runs locally
  (no API cost, no data leaving the environment), and handles legal/regulatory
  vocabulary well. OpenAI option for higher quality when budget allows.
- **Alternatives considered**: all-MiniLM-L6-v2 (smaller, faster, weaker on legal text),
  voyage-law-2 (best legal embeddings but API-only).
- **Status**: Proposed — ratify before M4.

### ADR-V2-04: Hybrid Retrieval Weights

- **Decision**: Default RRF weights: BM25=0.4, Vector=0.6, with per-query-type override.
- **Rationale**: BM25 excels at exact references ("Para 39.1.2", "CIR/2025/57").
  Vector excels at semantic queries ("margin collection deadline"). Most user queries
  are semantic, hence vector-weighted. Exact-reference queries auto-detect and
  re-weight BM25 higher.
- **Status**: Proposed — ratify before M5.

### ADR-V2-05: Multi-Circular Conflict Resolution

- **Decision**: Conflicts are detected automatically but resolved only by human review.
- **Rationale**: Regulatory interpretation is a legal determination. The platform
  flags conflicts; the compliance officer decides which obligation takes precedence.
  Automatic resolution risks incorrect compliance verdicts.
- **Status**: Proposed — ratify before M9.

---

## V1 Preservation Guarantees

| Guarantee | Enforcement |
|-----------|-------------|
| Node 3 deterministic | AST-level verification in CI (carried forward) |
| HITL gate preserved | No code removal from `hitl_gate.py` |
| 410 V1 tests pass | Run on every commit; fail = block merge |
| V1 API backward compatible | Existing 13 endpoints unchanged; new endpoints are additive |
| V1 demo script works | `scripts/run_demo.sh` verified on every M1-M10 release |

---

*This roadmap is a living document. Each milestone should be reviewed and potentially
adjusted based on findings from the previous milestone. The ADRs marked "Proposed" must
be formally ratified in `decision_log.md` before their respective milestones begin.*
