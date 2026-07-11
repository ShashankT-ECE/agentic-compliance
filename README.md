# RuleBridge — Explainable Regulatory Compliance Verification

<p align="center">
  <img src="https://img.shields.io/badge/status-hackathon--ready-brightgreen" alt="Hackathon Ready">
  <img src="https://img.shields.io/badge/python-3.11%2B-blue" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/typescript-5.7-blue" alt="TypeScript 5.7">
  <img src="https://img.shields.io/badge/react-19-61dafb" alt="React 19">
  <img src="https://img.shields.io/badge/fastapi-0.115-009688" alt="FastAPI">
  <img src="https://img.shields.io/badge/postgresql-16-336791" alt="PostgreSQL 16">
  <img src="https://img.shields.io/badge/tests-642%20passed-success" alt="642 Tests Passing">
  <img src="https://img.shields.io/badge/license-MIT-blue" alt="License MIT">
</p>

<p align="center">
  <a href="https://rulebridge.vercel.app"><strong>Live Dashboard</strong></a> &nbsp;·&nbsp;
  <a href="https://www.youtube.com/watch?v=79bXTBQX6X0"><strong>Demo Video</strong></a> &nbsp;·&nbsp;
  <a href="#documentation"><strong>Documentation</strong></a> &nbsp;·&nbsp;
  <a href="https://github.com/ShashankT-ECE/agentic-compliance"><strong>GitHub Repository</strong></a>
</p>

---

## Executive Summary

**RuleBridge** is an automated compliance verification platform that ingests SEBI
regulatory circulars, extracts structured obligations using LLMs, enforces a
mandatory Human-in-the-Loop (HITL) approval gate, and evaluates broker telemetry
against approved rules using a fully deterministic engine. Every compliance
decision is traceable to the exact passage of regulatory text that produced it,
with cryptographic integrity seals ensuring tamper-evident audit reports.

The platform was built for the **SEBI Securities Market TechSprint — Problem
Statement 2** and demonstrates a production-ready approach to regulatory
compliance automation that respects the operational boundaries required in
financial regulation: LLMs interpret regulations, humans approve interpretations,
and machines execute deterministic evaluations.

---

## Problem Statement

SEBI issues regulatory circulars that stock brokers are legally required to
comply with. Current compliance processes rely on manual review of circulars
spanning hundreds of pages and manual cross-referencing against operational
data. This approach presents several structural problems:

- **Scale**: Each new circular requires a full manual review cycle, creating
  unsustainable workloads for compliance teams.
- **Accuracy**: Obligations are missed or misinterpreted during manual reading,
  introducing regulatory risk.
- **Auditability**: There is no automated mechanism linking a compliance finding
  to the specific regulatory text that produced it.
- **Consistency**: Different compliance officers may interpret the same circular
  differently, leading to inconsistent enforcement.

RuleBridge addresses these problems by applying a pipeline architecture where
LLMs assist with the high-volume reading task, humans validate the machine output
through a mandatory approval gate, and a deterministic engine executes the
approved rules against operational data.

---

## Proposed Solution

RuleBridge implements a four-node compliance pipeline with a strict separation of
responsibilities:

| Node | Function | LLM Permitted | Deterministic |
|------|----------|:---:|:---:|
| **Node 1 — PDF Parser** | Extracts structured obligations from SEBI circular PDFs | Yes | No |
| **Node 2 — FSM Extractor** | Converts obligations into Hybrid Finite State Machines | Yes | No |
| **HITL Gate** | Human review: approve, reject, or amend each extracted FSM | No | No |
| **Node 3 — Assertion Evaluator** | Evaluates broker telemetry against approved FSMs | **Never** | **Yes** |
| **Node 4 — Scoreboard Generator** | Aggregates verdicts into audit scoreboards | No | Yes |

The architecture enforces three invariants:

1. **LLMs interpret regulations; they never make compliance decisions.**
2. **A human must approve every obligation before it enters evaluation.**
3. **Every compliance finding must be traceable to its originating regulatory
   text.**

An upstream **Regulatory Knowledge Layer** (RAG) indexes circulars into a vector
database with structural chunking, enabling semantic search and chunk-level
provenance tracking.

---

## Key Features

### Regulatory RAG (Retrieval-Augmented Generation)

Multi-circular indexing supports the full SEBI regulatory corpus. Circulars are
chunked at topic boundaries using a structure-aware parser that respects the
4-level hierarchy of SEBI Master Circulars (Roman sections, numbered topics,
sub-sections, sub-sub-sections). This produces semantically coherent chunks that
preserve regulatory context — critical for accurate obligation extraction.

- Embedding model: `BAAI/bge-small-en-v1.5` (384-dimensional vectors)
- Vector store: Chroma PersistentClient with cosine similarity search
- Cross-circular semantic search with metadata-provenance filtering
- Circular Registry with SHA-256 document hashing and index versioning
- Feature-flagged integration (`use_rag`) preserves backward compatibility with
  the V1 full-PDF extraction path

### Hybrid FSM Obligation Extraction

The DeepSeek LLM extracts compliance obligations as **Hybrid Finite State
Machines** — a model that combines event-driven state transitions with
timeline-based deadline rules. Each FSM encodes: the set of compliant and
non-compliant states, the events that trigger transitions, and the deadline
offsets (T+0 through T+3) that govern time-bound obligations.

Extraction is done in batches with configurable timeout parameters. LLM
responses are cached by prompt hash (SHA-256) to guarantee deterministic
re-extraction — identical inputs always produce identical outputs, regardless
of API-side variability.

### Human-in-the-Loop (HITL) Approval

Every extracted FSM passes through a mandatory human review gate before it
reaches the evaluator. A compliance officer must approve, reject, or amend each
FSM. The HITL gate enforces:

- **Immutable audit trail**: All review actions are logged to an INSERT-only
  table. No review record can be modified or deleted after the fact.
- **Amendment versioning**: Amended FSMs preserve the full history of prior
  versions, with reviewer identity and timestamps.
- **Hash-chain anchoring**: Each approved FSM is linked into a SHA-256 hash
  chain, making post-hoc tampering cryptographically detectable.
- **Hard gate enforcement**: The evaluator (Node 3) will not execute until all
  FSMs for a pipeline run have been resolved.

### Evidence Traceability

Every compliance verdict carries a complete provenance chain linking it to the
source regulatory text. The chain spans six levels: `Circular → Page → Chunk →
Obligation → FSM → Verdict`.

The platform uses a **conservative attribution strategy** (all input chunks
attributed to all output obligations) — the safest model for audit, as it asserts
the parser had access to the relevant source text. The attribution strategy is a
swappable Protocol, enabling finer-grained strategies in future releases.

Bounding-box extraction via pdfplumber provides word-level position data for
every cited passage. The frontend PDF.js viewer renders the source circular with
highlighted regions, allowing an auditor to verify a finding by reading the exact
text that produced it.

### Deterministic Compliance Evaluation

Node 3 (Assertion Evaluator) is the trust anchor of the system. It accepts
approved FSMs and broker telemetry events, and produces compliance verdicts
through a fully deterministic execution path:

- **State machine execution**: First-match transition resolution with
  chronological event replay.
- **Timeline evaluation**: Deadline computation with end-of-trading-day
  semantics (T+0, T+1, T+2, T+3).
- **Error isolation**: A failure in one FSM does not block evaluation of others.
- **Zero LLM calls, zero network access, zero randomness.**

Determinism is verified by six AST-level safety gate tests that statically
confirm Node 3 imports no LLM modules, makes no HTTP calls, and uses no
randomness sources.

### Audit Report Generation

Completed pipeline runs produce cryptographically sealed audit reports with
per-broker compliance scorecards. Each report includes: a compliance percentage
breakdown across a five-tier scoring rubric, per-obligation verdicts with
deterministic explanations, and a SHA-256 hash chain linking all verdicts to
enable tamper detection.

---

## System Architecture

```mermaid
graph TB
    subgraph RAG["Regulatory Knowledge Layer"]
        PDF["SEBI Circular PDFs"]
        Chunker["Document Chunker<br/>Topic-level chunking"]
        Embedder["Local Embedder<br/>bge-small-en-v1.5"]
        Chroma["Chroma Vector Store<br/>Persistent storage"]
        Registry["Circular Registry<br/>JSON / PostgreSQL"]
        Retrieval["Retrieval Pipeline<br/>Cross-circular search"]
    end

    subgraph Pipeline["Compliance Pipeline"]
        N1["Node 1: PDF Parser<br/>LLM-assisted extraction"]
        N2["Node 2: FSM Extractor<br/>LLM-assisted extraction"]
        HITL["HITL Gate<br/>Mandatory human review"]
        N3["Node 3: Evaluator<br/>Deterministic execution"]
        N4["Node 4: Scoreboard<br/>Report aggregation"]
    end

    subgraph Evidence["Evidence Layer"]
        Attribution["Attribution Strategy<br/>Chunk-to-obligation mapping"]
        BBox["Bounding Box Extractor<br/>pdfplumber coordinates"]
        EvidenceSvc["Evidence Service<br/>Provenance assembly"]
    end

    subgraph Frontend["React Dashboard"]
        Dash["Compliance Dashboard"]
        HITL_UI["HITL Review Interface"]
        Report["Audit Report Viewer"]
        Evidence_UI["Evidence Panel + PDF.js"]
    end

    PDF --> Chunker --> Embedder --> Chroma
    Chroma --> Retrieval
    Retrieval --> N1
    N1 --> N2 --> HITL
    HITL -->|"All approved"| N3
    HITL -->|"Amendments"| N2
    N3 --> N4
    N4 --> Report
    N4 --> EvidenceSvc
    Attribution --> EvidenceSvc
    BBox --> EvidenceSvc
    EvidenceSvc --> Evidence_UI
    Registry -.-> Retrieval

    style N3 fill:#dc3545,color:#fff
    style HITL fill:#ffc107,color:#333
    style N1 fill:#28a745,color:#fff
    style N2 fill:#28a745,color:#fff
```

### Architectural Principles

| Principle | Constraint |
|-----------|------------|
| Deterministic evaluation | Node 3 must not call an LLM, perform I/O, or use non-deterministic operations |
| Human-in-the-loop | Human approval is required before any FSM reaches the evaluator |
| Full audit trail | Every compliance finding must be traceable to its source regulatory text |
| Explainability | Every verdict must be explainable from the FSM structure and telemetry alone |
| Backward compatibility | V1 API surface and 410 V1 tests preserved; `use_rag` defaults to `false` |

---

## Project Workflow

### Pipeline Execution

```
[Circular PDF] -> [Node 1: Parser] -> [Node 2: FSM Extractor] -> [HITL Gate]
                                                                      |
                                                     ┌────────────────┼────────────────┐
                                                     v                v                v
                                               [Approve]         [Reject]          [Amend]
                                                     |                |                |
                                                     └────────────────┼────────────────┘
                                                                      |
                                             [Hash-Chain Anchoring] <-+
                                                                      |
                                             [Node 3: Evaluator] <----+
                                                                      |
                                             [Node 4: Scoreboard] <---+
                                                                      |
                                             [Evidence Assembly] <----+
                                                                      |
                                             [Audit Report]
```

### Evidence Provenance Chain

```
Circular PDF
  -> Chunker (structured chunks with page metadata)
    -> Parser (LLM extracts obligations from chunks)
      -> Attribution Strategy (conservative: all chunks map to all obligations)
        -> FSM Extractor (obligations converted to HybridFSMs)
          -> HITL Gate (human approval with hash-chain anchoring)
            -> Evaluator (deterministic verdict generation)
              -> Evidence Service (assembles full provenance)
                -> PDF.js Viewer (highlighted source passages)
```

---

## Technology Stack

| Category | Technology | Purpose |
|----------|-----------|---------|
| **Backend framework** | FastAPI 0.115+ | REST API with async request handling |
| **Pipeline orchestration** | LangGraph 1.0+ | StateGraph-based DAG execution |
| **LLM** | DeepSeek v4 Pro | Nodes 1 and 2: regulation parsing and FSM generation |
| **Vector database** | Chroma (PersistentClient) | Embedding storage and semantic search |
| **Embedding model** | BAAI/bge-small-en-v1.5 (384-dim) | Local embedding inference (133 MB) |
| **Database** | PostgreSQL 16 + asyncpg | Persistent storage for all domain entities |
| **ORM** | SQLAlchemy 2.0 (async) | Type-safe database operations |
| **Migrations** | Alembic 1.14+ | Version-controlled schema evolution |
| **PDF processing** | pdfplumber 0.11+ | Text extraction and bounding-box coordinates |
| **Data validation** | Pydantic 2.7+ | Schema validation and serialization |
| **Cryptographic integrity** | cryptography 42+ | SHA-256 hash-chain implementation |
| **Frontend framework** | React 19 + TypeScript 5.7 | Dashboard, reports, and evidence viewer |
| **PDF rendering** | PDF.js (pdfjs-dist 5.6) | In-browser circular viewing with passage highlighting |
| **State management** | Zustand 5 | Client-side state management |
| **Routing** | React Router 7 | Client-side navigation |
| **Build tool** | Vite 6 | Development server and production bundling |
| **Testing** | pytest 8.3+ | 642 backend tests |

---

## Repository Structure

```
agentic-compliance/
├── backend/                        # Python FastAPI backend
│   ├── app/
│   │   ├── api/                    # REST API layer
│   │   │   ├── deps.py             # Dependency injection
│   │   │   └── routes/             # Route modules
│   │   │       ├── pipeline.py     # Pipeline + HITL endpoints
│   │   │       ├── rag.py          # RAG endpoints
│   │   │       ├── evidence.py     # Evidence endpoints
│   │   │       ├── telemetry.py    # Telemetry ingestion and query
│   │   │       └── reports.py      # Report generation
│   │   ├── models/                 # Pydantic domain models
│   │   │   ├── fsm.py              # HybridFSM definition
│   │   │   ├── obligation.py       # ObligationClause schema
│   │   │   ├── telemetry.py        # TelemetryEvent schema
│   │   │   ├── verdict.py          # ComplianceVerdict schema
│   │   │   ├── scoreboard.py       # Scoreboard and HashLink definitions
│   │   │   ├── locked_fsm.py       # LockedFSM (HITL-reviewed)
│   │   │   └── evidence.py         # EvidenceReference provenance chain
│   │   ├── pipeline/               # Pipeline execution engine
│   │   │   ├── graph.py            # LangGraph StateGraph definition
│   │   │   ├── runner.py           # PipelineRunner orchestration
│   │   │   ├── state.py            # CompliancePipelineState
│   │   │   ├── evidence_service.py # Evidence assembly coordination
│   │   │   ├── attribution.py      # Chunk-to-obligation attribution strategy
│   │   │   └── nodes/              # Individual pipeline nodes
│   │   │       ├── parser.py       # Node 1: PDF Parser
│   │   │       ├── fsm_extractor.py# Node 2: FSM Extractor
│   │   │       ├── hitl_gate.py    # HITL Gate
│   │   │       ├── evaluator.py    # Node 3: Assertion Evaluator
│   │   │       └── scoreboard.py   # Node 4: Scoreboard Generator
│   │   ├── rag/                    # RAG subsystem
│   │   │   ├── chunker.py          # DocumentChunker
│   │   │   ├── embedder.py         # LocalEmbedder
│   │   │   ├── vector_store.py     # ChromaVectorStore
│   │   │   ├── retrieval.py        # RetrievalPipeline
│   │   │   ├── circular_registry.py# CircularRegistry
│   │   │   ├── schemas.py          # Shared RAG data structures
│   │   │   └── config.py           # YAML configuration loader
│   │   ├── db/                     # PostgreSQL persistence layer
│   │   │   ├── models.py           # 9 SQLAlchemy ORM models
│   │   │   └── repos/              # Repository pattern implementations
│   │   ├── utils/                  # Shared utilities
│   │   │   ├── llm_client.py       # LLM abstraction (DeepSeekClient)
│   │   │   ├── pdf_ingest.py       # PDF text extraction
│   │   │   ├── hash_chain.py       # SHA-256 hash chain
│   │   │   ├── state_machine.py    # Deterministic FSM executor
│   │   │   ├── timeline_evaluator.py# Deadline computation
│   │   │   ├── telemetry_gen.py    # Synthetic telemetry generators
│   │   │   └── bbox_extractor.py   # PDF bounding-box extraction
│   │   ├── cli.py                  # Command-line interface (6 commands)
│   │   ├── main.py                 # FastAPI application entry point
│   │   └── database.py             # Async SQLAlchemy configuration
│   ├── config/
│   │   └── rag.yaml                # RAG configuration
│   ├── alembic/                    # Database migrations
│   │   ├── env.py
│   │   └── versions/
│   │       └── 001_initial_schema.py
│   ├── tests/                      # 642 tests across 24 test files
│   ├── data/                       # Runtime data (gitignored)
│   │   ├── circulars/              # SEBI circular PDFs
│   │   ├── chroma_db/              # Chroma persistent storage
│   │   ├── circular_registry.json  # Registry data
│   │   ├── extracted/              # Extracted FSMs
│   │   └── locked_fsms/            # HITL-reviewed FSMs
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
├── frontend/                       # React + TypeScript frontend
│   ├── src/
│   │   ├── App.tsx                 # Router and layout
│   │   ├── App.css                 # Design system
│   │   ├── api/client.ts           # Typed API client
│   │   ├── store/                  # Zustand state management
│   │   ├── pages/                  # Page components
│   │   │   ├── index.tsx           # Dashboard
│   │   │   ├── hitl.tsx            # HITL Review
│   │   │   ├── report.tsx          # Audit Reports
│   │   │   └── evidence.tsx        # Evidence Viewer
│   │   └── components/             # Reusable UI components
│   │       ├── CircularPanel/      # Pipeline trigger
│   │       ├── FSMViewer/          # SVG state diagrams
│   │       ├── AuditReport/        # Compliance scorecards
│   │       ├── EvidencePanel/      # Provenance chain display
│   │       ├── PDFViewer/          # PDF.js with passage highlighting
│   │       └── TelemetryTable/     # Event browser
│   ├── Dockerfile                  # Multi-stage Node 22 + Nginx
│   ├── nginx.conf                  # SPA fallback + API proxy
│   ├── package.json
│   ├── tsconfig.json
│   └── vite.config.ts
├── docs/
│   ├── v2_roadmap.md               # V2 milestone plan
│   ├── v2_verification_plan.md     # End-to-end verification plan
│   └── api_reference.md            # API reference documentation
├── scripts/
│   ├── setup_wsl.sh               # WSL/Linux setup script
│   └── setup_windows.ps1          # Windows setup script
├── memory/                         # Project context persistence
├── docker-compose.yml
├── LICENSE
└── README.md
```

---

## Installation

### Prerequisites

- Python 3.11 or later with `pip`
- Node.js 22 or later with `npm`
- Docker and Docker Compose (for PostgreSQL)
- DeepSeek API key (for LLM-dependent features in Nodes 1 and 2)

### Setup

```bash
git clone https://github.com/ShashankT-ECE/agentic-compliance.git
cd agentic-compliance

# Linux / WSL
chmod +x scripts/setup_wsl.sh && ./scripts/setup_wsl.sh

# Windows (PowerShell)
.\scripts\setup_windows.ps1
```

### Environment Configuration

```bash
cp backend/.env.example backend/.env
```

Edit `backend/.env` and set the following required variables:

| Variable | Description |
|----------|-------------|
| `DEEPSEEK_API_KEY` | DeepSeek API key for LLM operations (required for Nodes 1 and 2) |
| `DATABASE_URL` | PostgreSQL connection string (default: `postgresql+asyncpg://compliance:compliance@localhost:5432/compliance_db`) |
| `SECRET_KEY` | Application secret key (change from the default placeholder) |

---

## Quick Start

### Step 1 — Start PostgreSQL

```bash
docker compose up -d db
```

### Step 2 — Start Backend

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

The backend API is now available at `http://localhost:8000`. Interactive API
documentation (Swagger UI) is at `http://localhost:8000/docs`.

### Step 3 — Start Frontend

```bash
cd frontend
npm run dev
```

The dashboard is now available at `http://localhost:5173`.

### Step 4 — Index a Circular

```bash
cd backend
source .venv/bin/activate

python -m app.cli index \
  --pdf-path data/circulars/SEBI-HO-MIRSD-MIRSD-PoD-P-CIR-2025-57-official.pdf \
  --circular-ref "SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/57"
```

### Step 5 — Run a Compliance Pipeline

Open the dashboard at `http://localhost:5173`. Trigger a pipeline run by
entering the circular reference. Review extracted FSMs in the HITL interface.
Approve, reject, or amend each obligation. After all FSMs are resolved, resume
the pipeline to generate verdicts and the audit report.

---

## Docker Deployment

Three deployment modes are supported:

### Development Mode

```bash
# Start PostgreSQL
docker compose up -d db

# Run backend with hot reload (on host machine)
cd backend && source .venv/bin/activate && uvicorn app.main:app --reload

# Run frontend with HMR (on host machine)
cd frontend && npm run dev
```

### Backend + Database (Docker Compose)

```bash
docker compose up --build
```

Services:
- Backend: `http://localhost:8000`
- PostgreSQL: `localhost:5432`

### Full Stack (Backend + Frontend + Database)

```bash
docker compose --profile fullstack up --build
```

Services:
- Backend: `http://localhost:8000`
- Frontend: `http://localhost:3000`
- PostgreSQL: `localhost:5432`

The full-stack profile uses a multi-stage frontend Dockerfile that compiles the
React application and serves it via Nginx with API proxying to the backend.

---

## API Reference

The platform exposes 22 REST endpoints across the following groups. Full schema
details are available in the interactive Swagger UI at `http://localhost:8000/docs`.

### Pipeline

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/pipeline/trigger` | Start a compliance pipeline run |
| `GET` | `/api/pipeline/status/{run_id}` | Get pipeline run status and FSM counts |
| `GET` | `/api/pipeline/result/{run_id}` | Get verdicts and scoreboard for a completed run |
| `POST` | `/api/pipeline/{run_id}/resume` | Resume pipeline after HITL review |

### Human-in-the-Loop Review

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/pipeline/hitl` | List pipeline runs with pending HITL items |
| `POST` | `/api/pipeline/hitl/{fsm_id}/approve` | Approve an FSM (seals it into the hash chain) |
| `POST` | `/api/pipeline/hitl/{fsm_id}/reject` | Reject an FSM (requires reviewer comments) |
| `POST` | `/api/pipeline/hitl/{fsm_id}/amend` | Amend an FSM with a corrected specification |

### RAG (Regulatory Knowledge Layer)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/rag/index` | Index a circular PDF (chunk, embed, store) |
| `POST` | `/api/rag/query` | Semantic search across indexed circulars |
| `GET` | `/api/rag/status/{circular_ref}` | Check whether a circular is indexed |
| `GET` | `/api/rag/circulars` | List all indexed circulars |
| `POST` | `/api/rag/index-all` | Batch-index multiple circulars |
| `DELETE` | `/api/rag/circular/{circular_ref}` | Remove a circular from index and registry |

### Evidence

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/evidence/{verdict_id}` | Full evidence chain for a compliance verdict |
| `GET` | `/api/evidence/fsm/{locked_fsm_id}` | Source chunks and obligation for a locked FSM |
| `GET` | `/api/chunks/{chunk_id}/positions` | Bounding-box regions for a chunk in the source PDF |
| `GET` | `/api/circulars/{circular_ref}/pdf` | Serve the source PDF for the PDF.js viewer |

### Telemetry and Reports

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/telemetry/ingest` | Ingest broker telemetry events |
| `GET` | `/api/telemetry/query` | Query telemetry with optional filters |
| `GET` | `/api/reports/generate/{run_id}` | Generate a cryptographically sealed audit report |
| `GET` | `/api/reports/{report_id}` | Retrieve a previously generated report |

---

## Dashboard

The React dashboard provides a centralized interface for compliance operations:

| Page | Route | Purpose |
|------|-------|---------|
| **Dashboard** | `/` | Pipeline trigger, run status overview, telemetry statistics |
| **HITL Review** | `/hitl/:runId` | Approve, reject, or amend extracted FSMs |
| **Audit Reports** | `/report/:reportId?` | Generate and view cryptographically sealed reports |
| **Evidence Viewer** | `/evidence` | Side-by-side PDF viewer with provenance chain display |

---

## Live Dashboard

A deployed instance of RuleBridge is available at:

**[https://rulebridge.vercel.app](https://rulebridge.vercel.app)**

The dashboard provides interactive access to the compliance pipeline, including
circular indexing, HITL review, evidence traceability, and audit report
generation with sample data.

---

## Documentation

| Document | Description |
|----------|-------------|
| [V2 Roadmap](docs/v2_roadmap.md) | Detailed V2 milestone plan with architectural decisions |
| [V2 Verification Plan](docs/v2_verification_plan.md) | End-to-end verification plan (14 phases, 66 steps) |
| [API Reference](docs/api_reference.md) | Exhaustive API documentation with request/response schemas |
| [Swagger UI](http://localhost:8000/docs) | Interactive API documentation (available when backend is running) |

---

## Demo Video

A walkthrough of the complete compliance verification pipeline, covering
circular indexing, FSM extraction, HITL review, verdict generation, evidence
traceability, and audit report generation.

**[Watch on YouTube](https://www.youtube.com/watch?v=79bXTBQX6X0)**

---

## Knowledge Graph (Graphify)

RuleBridge integrates with **Graphify**, a persistent knowledge graph that
captures the system's topology and code relationships:

- Pipeline graph: node definitions, state transitions, conditional edges
- Code structure: file dependencies, import graphs, module relationships
- Architecture mapping: component hierarchy and cross-layer connections

Graphify enables semantic queries over the codebase and community detection for
architectural analysis. Run `/graphify` in the repository to generate or update
the knowledge graph.

---

## Testing

```bash
cd backend
source .venv/bin/activate

# Full test suite
python -m pytest tests/ -v

# Run a specific test module
python -m pytest tests/test_evaluator.py -v

# Run with coverage report
python -m pytest tests/ --cov=app --cov-report=html
```

The test suite consists of 642 tests across 24 test files covering models,
pipeline nodes, RAG components, database repositories, evidence attribution,
bounding-box extraction, API endpoints, and end-to-end integration. All tests
pass with zero failures.

---

## Team

| Member | Role |
|--------|------|
| Amrutha Abulusu | Full-Stack Development |
| Shashank T | Backend Engineering and Infrastructure |

---

## Future Enhancements

Planned milestones are documented in detail at [docs/v2_roadmap.md](docs/v2_roadmap.md).

| Milestone | Status | Description |
|-----------|--------|-------------|
| V2 M1 — RAG Architecture | Complete | Chroma vector store, bge-small embeddings, topic-level chunking, retrieval API |
| V2 M2 — Multi-Circular Retrieval | Complete | Circular registry, cross-circular search, batch indexing |
| V2 M3 — Evidence Traceability | Complete | Attribution strategy, bounding-box extraction, PDF.js viewer |
| V2 M4 — PostgreSQL Migration | Complete | SQLAlchemy ORM, Alembic migrations, repository pattern, graceful degradation |
| V2 M5 — Compliance Scenario Library | Planned | Reusable regression scenarios covering clean pass, clean fail, boundary cases, and edge conditions |
| V2 M6 — Tamper-Evident Audit Log | Planned | Merkle tree over verdicts with incremental proof generation |

---

## License

MIT License — see the [LICENSE](LICENSE) file for details.

---

## Acknowledgements

- **SEBI** for organizing the Securities Market TechSprint
- **DeepSeek** for the LLM API used in regulatory text extraction
- **BAAI** for the bge-small-en-v1.5 embedding model
- **Chroma** for the open-source vector database
- **pdfplumber** for PDF text and coordinate extraction utilities
