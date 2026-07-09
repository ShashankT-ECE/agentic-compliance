# V2.0 End-to-End Verification Plan

> **Date**: 2026-07-09
> **Purpose**: Validates the complete Agentic Compliance V2.0 system — Regulatory Knowledge Layer, Pipeline Execution, Evidence Engine, and Persistence Layer.
> **Baseline**: 642 backend tests passing. Frontend builds clean (93 modules). V1 frozen.

---

## Pre-Flight Checklist

Before beginning any functional verification:

- [ ] **P0.1** — 642 backend tests pass
  ```bash
  cd backend && source .venv/bin/activate && python -m pytest tests/ -q
  ```
  Expected: `642 passed, 1 warning in ~200s`

- [ ] **P0.2** — Frontend builds
  ```bash
  cd frontend && npm run build
  ```
  Expected: `✓ built in ~5s`, 93 modules, zero TypeScript errors

- [ ] **P0.3** — Kill any stale processes
  ```bash
  fuser -k 8000/tcp 2>/dev/null
  fuser -k 5173/tcp 2>/dev/null
  ```

- [ ] **P0.4** — Environment variables
  ```bash
  echo $DEEPSEEK_API_KEY | head -c 8
  ```
  Expected: Returns the first 8 chars of the API key (non-empty)

---

## Phase 1 — Environment Startup

### 1.1 PostgreSQL

- [ ] **P1.1.1** — Start PostgreSQL
  ```bash
  cd /home/bradha/agentic-compliance
  docker-compose up -d db
  ```
  Expected: Container starts. `docker ps` shows `postgres:16-alpine` healthy.

- [ ] **P1.1.2** — Verify connectivity
  ```bash
  docker exec -it $(docker ps -q -f name=db) pg_isready -U compliance -d compliance_db
  ```
  Expected: `/var/run/postgresql:5432 - accepting connections`

- [ ] **P1.1.3** — Apply schema migration
  ```bash
  cd backend && source .venv/bin/activate && alembic upgrade head
  ```
  Expected: `INFO  [alembic.runtime.migration] Running upgrade -> 001`

- [ ] **P1.1.4** — Verify tables exist
  ```bash
  docker exec -it $(docker ps -q -f name=db) psql -U compliance -d compliance_db -c "\dt"
  ```
  Expected: 9 tables listed (`circular_records`, `pipeline_runs`, `verdicts`, `locked_fsms`, `hitl_review_log`, `reports`, `evidence_references`, `rag_chunks`, `telemetry_events`)

- [ ] **P1.1.5** — Confirm empty tables
  ```bash
  docker exec -it $(docker ps -q -f name=db) psql -U compliance -d compliance_db -c "SELECT count(*) FROM pipeline_runs; SELECT count(*) FROM circular_records; SELECT count(*) FROM rag_chunks;"
  ```
  Expected: All return `0`

### 1.2 Backend

- [ ] **P1.2.1** — Start backend
  ```bash
  cd backend && source .venv/bin/activate && uvicorn app.main:app --host 0.0.0.0 --port 8000 &
  ```
  Expected: Log shows `Database tables initialised`, no errors.

- [ ] **P1.2.2** — Health check
  ```bash
  curl -s http://localhost:8000/health | python -m json.tool
  ```
  Expected: `{"status": "healthy", "version": "1.0.0"}`

- [ ] **P1.2.3** — OpenAPI schema
  ```bash
  curl -s http://localhost:8000/openapi.json | python -c "import json,sys; s=json.load(sys.stdin); print('Paths:', len(s['paths'])); print([p for p in s['paths'] if 'evidence' in p])"
  ```
  Expected: Evidence paths include `/api/evidence/{verdict_id}`, `/api/evidence/fsm/{locked_fsm_id}`, `/api/chunks/{chunk_id}/positions`, `/api/circulars/{circular_ref}/pdf`

### 1.3 Frontend

- [ ] **P1.3.1** — Start frontend dev server
  ```bash
  cd frontend && npm run dev &
  ```
  Expected: Vite dev server at `http://localhost:5173`

- [ ] **P1.3.2** — Dashboard loads
  Open `http://localhost:5173` in browser.
  Expected: Dashboard page renders with header, no JavaScript console errors.

---

## Phase 2 — PostgreSQL Verification

- [ ] **P2.1** — Backend uses PG for circular registry
  Look for in backend startup logs.
  Expected: `Using PostgreSQL-backed circular registry` (not `Using JSON-file circular registry`)

- [ ] **P2.2** — PG survives restart test
  ```bash
  # Kill and restart backend
  fuser -k 8000/tcp 2>/dev/null
  cd backend && source .venv/bin/activate && uvicorn app.main:app --host 0.0.0.0 --port 8000 &
  ```
  Expected: Backend starts. Health check passes.

---

## Phase 3 — Chroma Verification

- [ ] **P3.1** — Chroma collection exists
  ```bash
  cd backend && source .venv/bin/activate && python -c "
  from app.rag.vector_store import ChromaVectorStore
  store = ChromaVectorStore()
  print('Collection:', store._get_collection().name)
  print('Count:', store.count())
  "
  ```
  Expected: Collection name `sebi_circulars`, count `0` (before indexing)

---

## Phase 4 — Multi-Circular Indexing

### 4.1 Single circular index via CLI

- [ ] **P4.1.1** — Index the 2-page SEBI amendment circular
  ```bash
  cd backend && source .venv/bin/activate && python -m app.cli index \
    --pdf-path data/circulars/SEBI-HO-MIRSD-MIRSD-PoD-P-CIR-2025-57.pdf \
    --circular-ref "SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/57"
  ```
  Expected:
  - `Chunks created: <N>` where N >= 1
  - `Embeddings: <N> vectors, dim=384`
  - `Indexed: <N> chunks in Chroma`
  - `PG: <N> chunk(s) saved to rag_chunks`
  - `Total collection size: <N>`
  - `Done.`

- [ ] **P4.1.2** — Index the 399-page Master Circular
  ```bash
  cd backend && source .venv/bin/activate && python -m app.cli index \
    --pdf-path data/circulars/SEBI-Master-Circular-Stock-Brokers-2025-06-17.pdf \
    --circular-ref "SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/Master"
  ```
  Expected:
  - `Chunks created: ~200` (approximately 200 chunks)
  - `Indexed: ~200 chunks in Chroma`
  - `PG: ~200 chunk(s) saved to rag_chunks`

- [ ] **P4.1.3** — Index the official signed circular
  ```bash
  cd backend && source .venv/bin/activate && python -m app.cli index \
    --pdf-path data/circulars/SEBI-HO-MIRSD-MIRSD-PoD-P-CIR-2025-57-official.pdf \
    --circular-ref "SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/57-official"
  ```
  Expected: Similar output to P4.1.1

### 4.2 Verify PostgreSQL chunk storage

- [ ] **P4.2.1** — Chunks in `rag_chunks` table
  ```bash
  docker exec -it $(docker ps -q -f name=db) psql -U compliance -d compliance_db -c "
  SELECT circular_ref, count(*) FROM rag_chunks GROUP BY circular_ref ORDER BY circular_ref;
  "
  ```
  Expected: 3 rows showing chunk counts for each indexed circular

- [ ] **P4.2.2** — Chunk metadata integrity
  ```bash
  docker exec -it $(docker ps -q -f name=db) psql -U compliance -d compliance_db -c "
  SELECT chunk_id, circular_ref, char_length(text) as text_len,
         chunk_metadata->>'section_path' as path,
         chunk_metadata->>'start_page' as sp,
         chunk_metadata->>'end_page' as ep
  FROM rag_chunks ORDER BY circular_ref LIMIT 10;
  "
  ```
  Expected: Each row has a valid `chunk_id`, positive `text_len`, non-empty `section_path`, `start_page >= 1`, `end_page >= start_page`

- [ ] **P4.2.3** — Circular registry in PG
  ```bash
  docker exec -it $(docker ps -q -f name=db) psql -U compliance -d compliance_db -c "
  SELECT circular_ref, chunk_count, char_count, document_hash, index_version FROM circular_records ORDER BY circular_ref;
  "
  ```
  Expected: 3 rows with matching `chunk_count` values. `document_hash` is a 64-char hex string. `index_version` is `v2-m2`.

### 4.3 List indexed circulars

- [ ] **P4.3.1** — CLI list
  ```bash
  cd backend && source .venv/bin/activate && python -m app.cli list
  ```
  Expected: Table showing 3 circulars with refs, chunk counts, "Yes" for Indexed, and titles

- [ ] **P4.3.2** — API list
  ```bash
  curl -s http://localhost:8000/api/rag/circulars | python -m json.tool
  ```
  Expected: `total: 3`, each circular has `indexed: true`

- [ ] **P4.3.3** — API status
  ```bash
  curl -s "http://localhost:8000/api/rag/status/SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/57" | python -m json.tool
  ```
  Expected: `indexed: true`, `chunk_count >= 1`

---

## Phase 5 — Retrieval

- [ ] **P5.1** — Semantic search via CLI
  ```bash
  cd backend && source .venv/bin/activate && python -m app.cli search \
    --query "margin collection deadline timeline" --top-k 5
  ```
  Expected: 5 results, each with a score and section path. At least one result references "margin" or "collection."

- [ ] **P5.2** — Filtered search
  ```bash
  cd backend && source .venv/bin/activate && python -m app.cli search \
    --query "margin collection deadline" \
    --circular-ref "SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/57" --top-k 5
  ```
  Expected: Results only from the specified circular. Verify all metadata `circular_ref` matches.

- [ ] **P5.3** — Semantic search via API
  ```bash
  curl -s -X POST http://localhost:8000/api/rag/query \
    -H "Content-Type: application/json" \
    -d '{"query": "margin collection deadline", "top_k": 5}' \
    | python -m json.tool | head -30
  ```
  Expected: Results with `chunk_id`, `text`, `score`, `metadata`

- [ ] **P5.4** — Cross-circular filter
  ```bash
  curl -s -X POST http://localhost:8000/api/rag/query \
    -H "Content-Type: application/json" \
    -d '{"query": "registration of stock brokers", "top_k": 5, "circular_ref": "SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/Master"}' \
    | python -m json.tool | head -20
  ```
  Expected: Results filtered to Master circular. `total_chunks_searched` reflects Master circular's chunk count.

---

## Phase 6 — Parser & FSM (full pipeline via API)

### 6.1 Trigger pipeline with RAG

- [ ] **P6.1.1** — Trigger pipeline
  ```bash
  curl -s -X POST http://localhost:8000/api/pipeline/trigger \
    -H "Content-Type: application/json" \
    -d '{
      "circular_path": "data/circulars/SEBI-HO-MIRSD-MIRSD-PoD-P-CIR-2025-57.pdf",
      "circular_id": "SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/57",
      "use_rag": true
    }' | python -m json.tool
  ```
  Expected:
  - `run_id` starts with `run-`
  - `status`: `"awaiting_approval"`
  - `message`: `"Pipeline started. FSM extraction complete — awaiting human review at HITL gate."`

- [ ] **P6.1.2** — Save run_id
  ```bash
  RUN_ID=$(curl -s -X POST http://localhost:8000/api/pipeline/trigger \
    -H "Content-Type: application/json" \
    -d '{"circular_path": "data/circulars/SEBI-HO-MIRSD-MIRSD-PoD-P-CIR-2025-57.pdf", "circular_id": "SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/57", "use_rag": true}' \
    | python -c "import json,sys; print(json.load(sys.stdin)['run_id'])")
  echo "RUN_ID=$RUN_ID"
  ```
  Expected: Prints `RUN_ID=run-<hex>`

### 6.2 Verify pipeline checkpoints in PG

- [ ] **P6.2.1** — Pipeline run in `pipeline_runs`
  ```bash
  docker exec -it $(docker ps -q -f name=db) psql -U compliance -d compliance_db -c "
  SELECT run_id, status, circular_id FROM pipeline_runs WHERE run_id = '<YOUR_RUN_ID>';
  "
  ```
  Expected: One row with `status = 'awaiting_approval'`, `circular_id` matches

- [ ] **P6.2.2** — Checkpoint has state_blob
  ```bash
  docker exec -it $(docker ps -q -f name=db) psql -U compliance -d compliance_db -c "
  SELECT run_id, char_length(state_blob::text) as blob_size FROM pipeline_runs WHERE run_id = '<YOUR_RUN_ID>';
  "
  ```
  Expected: `blob_size > 0` (contains serialized pipeline state)

### 6.3 Check pipeline status

- [ ] **P6.3.1** — API status
  ```bash
  curl -s http://localhost:8000/api/pipeline/status/$RUN_ID | python -m json.tool
  ```
  Expected: `status: "awaiting_approval"`, `total_fsms >= 1`, `pending > 0`

- [ ] **P6.3.2** — List FSMs
  ```bash
  curl -s "http://localhost:8000/api/pipeline/$RUN_ID/fsms" | python -m json.tool | head -30
  ```
  Expected: List of pending FSMs with `locked_fsm_id`, `obligation_ref`, `status: "pending_review"`

---

## Phase 7 — HITL Pause/Resume

### 7.1 Verify Locked FSMs in PG

- [ ] **P7.1.1** — Locked FSMs in `locked_fsms`
  ```bash
  docker exec -it $(docker ps -q -f name=db) psql -U compliance -d compliance_db -c "
  SELECT locked_fsm_id, fsm_id, obligation_ref, status, pipeline_run_id
  FROM locked_fsms WHERE pipeline_run_id = '<YOUR_RUN_ID>';
  "
  ```
  Expected: Rows matching the count from P6.3.2. All `status = 'pending_review'`.

### 7.2 Approve FSMs

- [ ] **P7.2.1** — Approve all FSMs
  ```bash
  for FSM_ID in $(curl -s "http://localhost:8000/api/pipeline/$RUN_ID/fsms" | python -c "import json,sys; data=json.load(sys.stdin); [print(f['locked_fsm_id']) for f in data['fsms']]"); do
    echo "Approving $FSM_ID..."
    curl -s -X POST "http://localhost:8000/api/pipeline/$RUN_ID/fsms/$FSM_ID/approve" \
      -H "Content-Type: application/json" \
      -d '{"reviewer": "Compliance Officer", "review_comments": "Verified against circular text."}' \
      | python -c "import json,sys; d=json.load(sys.stdin); print(f'  Status: {d[\"status\"]}')"
  done
  ```
  Expected: Each FSM transitions to `status: "approved"`

- [ ] **P7.2.2** — Verify HITL audit log in PG
  ```bash
  docker exec -it $(docker ps -q -f name=db) psql -U compliance -d compliance_db -c "
  SELECT action, reviewer, locked_fsm_id, created_at FROM hitl_review_log WHERE pipeline_run_id = '<YOUR_RUN_ID>' ORDER BY created_at;
  "
  ```
  Expected: One row per approval with `action = 'approved'`, `reviewer = 'Compliance Officer'`

- [ ] **P7.2.3** — Locked FSM status updated in PG
  ```bash
  docker exec -it $(docker ps -q -f name=db) psql -U compliance -d compliance_db -c "
  SELECT locked_fsm_id, status, reviewer, integrity_hash FROM locked_fsms WHERE pipeline_run_id = '<YOUR_RUN_ID>';
  "
  ```
  Expected: All statuses now `approved`, `reviewer = 'Compliance Officer'`, `integrity_hash` is a 64-char hex string

### 7.3 Resume pipeline

- [ ] **P7.3.1** — Resume
  ```bash
  curl -s -X POST http://localhost:8000/api/pipeline/$RUN_ID/resume | python -m json.tool
  ```
  Expected: `status: "completed"`, `verdict_count >= 1`, `scoreboard_id` starts with `SB-`

- [ ] **P7.3.2** — Completed run in PG
  ```bash
  docker exec -it $(docker ps -q -f name=db) psql -U compliance -d compliance_db -c "
  SELECT status, completed_at FROM pipeline_runs WHERE run_id = '<YOUR_RUN_ID>';
  "
  ```
  Expected: `status = 'completed'`, `completed_at` is a non-null timestamp

---

## Phase 8 — Deterministic Evaluation

- [ ] **P8.1** — Verdicts in PG
  ```bash
  docker exec -it $(docker ps -q -f name=db) psql -U compliance -d compliance_db -c "
  SELECT verdict_id, obligation_ref, broker_id, status, current_state FROM verdicts WHERE pipeline_run_id = '<YOUR_RUN_ID>';
  "
  ```
  Expected: One row per obligation × broker. Statuses are `compliant`, `non_compliant`, or `pending`.

- [ ] **P8.2** — Pipeline result via API
  ```bash
  curl -s http://localhost:8000/api/pipeline/result/$RUN_ID | python -m json.tool | head -40
  ```
  Expected: `status: "completed"`, verdicts list populated, scoreboard present

- [ ] **P8.3** — Scoreboard contains broker summaries
  Look for `broker_summaries` in the scoreboard output.
  Expected: At least one broker. `total_obligations`, `compliant`, `non_compliant`, `pending` counts. `compliance_rate` between 0.0 and 1.0.

- [ ] **P8.4** — Hash chain integrity
  Look for `hash_chain` in the scoreboard.
  Expected: `root_hash` is a 64-char hex string. `chain` is a non-empty list of links.

---

## Phase 9 — Evidence Generation

- [ ] **P9.1** — Evidence references in PG
  ```bash
  docker exec -it $(docker ps -q -f name=db) psql -U compliance -d compliance_db -c "
  SELECT evidence_id, verdict_id, attribution_method, char_length(fsm_provenance::text) as prov_size
  FROM evidence_references WHERE pipeline_run_id = '<YOUR_RUN_ID>';
  "
  ```
  Expected: One row per verdict. `attribution_method = 'conservative'`. `prov_size > 0`.

- [ ] **P9.2** — Evidence API for a verdict
  ```bash
  VERDICT_ID=$(curl -s http://localhost:8000/api/pipeline/result/$RUN_ID | python -c "import json,sys; print(json.load(sys.stdin)['verdicts'][0]['verdict_id'])")
  curl -s "http://localhost:8000/api/evidence/$VERDICT_ID" | python -m json.tool | head -40
  ```
  Expected:
  - `evidence_id` starts with `EV-`
  - `verdict_id` matches
  - `fsm_provenance.obligation_source.source_chunks` is a non-empty list
  - each source chunk has `chunk_id`, `citation_text`, `page_range`
  - `attribution_method`: `"conservative"`

- [ ] **P9.3** — Evidence FSM endpoint
  Pick a locked_fsm_id from P7.2.1.
  ```bash
  curl -s "http://localhost:8000/api/evidence/fsm/LOCKED-<your_id>" | python -m json.tool
  ```
  Expected: Returns `fsm_id`, `obligation_ref`, `source_chunks` list, `review_status: "approved"`

- [ ] **P9.4** — Chunk positions
  Pick a chunk_id from P9.2 output.
  ```bash
  curl -s "http://localhost:8000/api/chunks/<chunk_id>/positions?circular_ref=SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/57" | python -m json.tool
  ```
  Expected: `status: "complete"` or `"unavailable"`. `page_range` matches the chunk's metadata. If `complete`, `regions` is a non-empty list with `page_number` and `rectangles`.

---

## Phase 10 — Evidence Viewer (Frontend)

- [ ] **P10.1** — Generate audit report
  ```bash
  curl -s "http://localhost:8000/api/reports/generate/$RUN_ID" | python -m json.tool
  ```
  Expected: `report_id` starts with `RPT-`. `circular_id` matches.

- [ ] **P10.2** — Report page loads
  Open `http://localhost:5173/report` in browser.
  Expected: Reports page. Enter the run_id, click "View Report." The Audit Report renders with summary stats, broker breakdown, verdicts table with "View Sources" buttons.

- [ ] **P10.3** — Click "View Sources"
  Click the "View Sources" button on any verdict row.
  Expected: Navigates to `/evidence?verdictId=<id>&circularRef=<ref>&runId=<run>`. Evidence page loads with PDF viewer on the left and Evidence Panel on the right.

- [ ] **P10.4** — PDF viewer renders
  Expected: PDF viewer displays the circular PDF. Navigation buttons (<prev | Page X of Y | next>) work. PDF content is readable.

- [ ] **P10.5** — Evidence Panel shows provenance
  Expected: Shows Verdict ID, FSM ID, Obligation reference, and list of Source Chunks. Each chunk shows its page range. Clicking a chunk navigates the PDF to that page.

- [ ] **P10.6** — Click chunk → page navigation
  Expected: PDF viewer navigates to the correct page. Highlights appear if bounding boxes were extracted (may show "unavailable" if bbox extraction hasn't run or text matching failed).

---

## Phase 11 — PostgreSQL Persistence Verification

### 11.1 Server restart resilience

- [ ] **P11.1.1** — Kill backend
  ```bash
  fuser -k 8000/tcp 2>/dev/null
  ```

- [ ] **P11.1.2** — Restart backend
  ```bash
  cd backend && source .venv/bin/activate && uvicorn app.main:app --host 0.0.0.0 --port 8000 &
  ```

- [ ] **P11.1.3** — Pipeline state survives restart
  ```bash
  curl -s http://localhost:8000/api/pipeline/status/$RUN_ID | python -m json.tool
  ```
  Expected: Returns pipeline status and counts (reconstructed from PG). Note: verdict_count may show 0 if the in-memory state was lost — this is expected from the in-memory path.

- [ ] **P11.1.4** — Evidence survives restart
  ```bash
  curl -s "http://localhost:8000/api/evidence/$VERDICT_ID" | python -m json.tool
  ```
  Expected: Returns evidence data if the verdict existed in the PG evidence_references table.

- [ ] **P11.1.5** — Circulars survive restart
  ```bash
  curl -s http://localhost:8000/api/rag/circulars | python -m json.tool | head -20
  ```
  Expected: All 3 circulars still listed, with correct chunk counts.

- [ ] **P11.1.6** — Chroma survives restart independently
  Verify Chroma directory still exists and holds data:
  ```bash
  cd backend && source .venv/bin/activate && python -c "
  from app.rag.vector_store import ChromaVectorStore
  store = ChromaVectorStore()
  print('Chunks:', store.count())
  print('Circulars:', store.list_circulars())
  "
  ```
  Expected: Non-zero count matching P4.1.

### 11.2 Transaction integrity

- [ ] **P11.2.1** — No orphaned verdicts
  ```bash
  docker exec -it $(docker ps -q -f name=db) psql -U compliance -d compliance_db -c "
  SELECT v.verdict_id FROM verdicts v
  LEFT JOIN pipeline_runs pr ON v.pipeline_run_id = pr.run_id
  WHERE pr.run_id IS NULL;
  "
  ```
  Expected: `0 rows` — no verdicts without a parent pipeline run.

- [ ] **P11.2.2** — No orphaned evidence
  ```bash
  docker exec -it $(docker ps -q -f name=db) psql -U compliance -d compliance_db -c "
  SELECT er.evidence_id FROM evidence_references er
  LEFT JOIN verdicts v ON er.verdict_id = v.verdict_id
  WHERE v.verdict_id IS NULL;
  "
  ```
  Expected: `0 rows` — no evidence without a parent verdict.

- [ ] **P11.2.3** — FK relationships intact
  ```bash
  docker exec -it $(docker ps -q -f name=db) psql -U compliance -d compliance_db -c "
  SELECT
    (SELECT count(*) FROM rag_chunks WHERE circular_ref NOT IN (SELECT circular_ref FROM circular_records)) as orphan_chunks,
    (SELECT count(*) FROM locked_fsms WHERE pipeline_run_id NOT IN (SELECT run_id FROM pipeline_runs)) as orphan_fsms;
  "
  ```
  Expected: `orphan_chunks: 0`, `orphan_fsms: 0`

---

## Phase 12 — Failure Scenarios

### 12.1 PostgreSQL unavailable

- [ ] **P12.1.1** — Stop PostgreSQL
  ```bash
  docker-compose stop db
  ```

- [ ] **P12.1.2** — Restart backend
  ```bash
  fuser -k 8000/tcp 2>/dev/null
  cd backend && source .venv/bin/activate && uvicorn app.main:app --host 0.0.0.0 --port 8000 &
  ```
  Expected: Startup log shows `PostgreSQL not available — running with in-memory stores and JSON-file registry as fallback`

- [ ] **P12.1.3** — Health check still passes
  ```bash
  curl -s http://localhost:8000/health
  ```
  Expected: `{"status": "healthy", "version": "1.0.0"}`

- [ ] **P12.1.4** — CLI still works
  ```bash
  cd backend && source .venv/bin/activate && python -m app.cli list
  ```
  Expected: Lists circulars from Chroma (since PG is down). Warning about PG may appear.

- [ ] **P12.1.5** — Search still works (Chroma-only)
  ```bash
  cd backend && source .venv/bin/activate && python -m app.cli search --query "margin" --top-k 3
  ```
  Expected: Returns results from Chroma ANN search.

- [ ] **P12.1.6** — Restart PostgreSQL
  ```bash
  docker-compose start db
  sleep 3
  docker exec -it $(docker ps -q -f name=db) pg_isready -U compliance -d compliance_db
  ```

- [ ] **P12.1.7** — Restart backend with PG
  ```bash
  fuser -k 8000/tcp 2>/dev/null
  cd backend && source .venv/bin/activate && uvicorn app.main:app --host 0.0.0.0 --port 8000 &
  ```
  Expected: `Using PostgreSQL-backed circular registry`

### 12.2 V1 path works (use_rag=False)

- [ ] **P12.2.1** — Trigger V1 pipeline
  ```bash
  curl -s -X POST http://localhost:8000/api/pipeline/trigger \
    -H "Content-Type: application/json" \
    -d '{
      "circular_path": "data/circulars/SEBI-HO-MIRSD-MIRSD-PoD-P-CIR-2025-57.pdf",
      "circular_id": "SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/57",
      "use_rag": false
    }' | python -m json.tool
  ```
  Expected: Pipeline triggers successfully (full PDF extraction path). Same response shape as P6.1.1.

- [ ] **P12.2.2** — V1 run produces verdicts
  Complete a full HITL review + resume cycle for this V1 run.
  Expected: Verdicts produced. Evidence assembly skipped (no chunk_objects) — logged as `Skipping evidence assembly ... no chunk objects`.

### 12.3 Delete and re-index

- [ ] **P12.3.1** — Delete a circular
  ```bash
  curl -s -X DELETE "http://localhost:8000/api/rag/circular/SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/57-official" | python -m json.tool
  ```
  Expected: `deleted_chunks > 0`, `deregistered: true`

- [ ] **P12.3.2** — PG chunks deleted
  ```bash
  docker exec -it $(docker ps -q -f name=db) psql -U compliance -d compliance_db -c "
  SELECT count(*) FROM rag_chunks WHERE circular_ref = 'SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/57-official';
  "
  ```
  Expected: `count: 0`

- [ ] **P12.3.3** — Chroma chunks deleted
  ```bash
  cd backend && source .venv/bin/activate && python -c "
  from app.rag.vector_store import ChromaVectorStore
  store = ChromaVectorStore()
  print(store.count_by_circular('SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/57-official'))
  "
  ```
  Expected: `0`

- [ ] **P12.3.4** — Re-index the circular
  ```bash
  cd backend && source .venv/bin/activate && python -m app.cli index \
    --pdf-path data/circulars/SEBI-HO-MIRSD-MIRSD-PoD-P-CIR-2025-57-official.pdf \
    --circular-ref "SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/57-official"
  ```
  Expected: Chunks re-created, re-indexed in both PG and Chroma.

---

## Phase 13 — Performance Observations

Record the following metrics during verification. These are not pass/fail — they establish a baseline for future optimization.

| Step | Operation | Observed Time | Notes |
|------|-----------|--------------|-------|
| P4.1.1 | Index 2-page circular | ___s | Should be < 30s |
| P4.1.2 | Index 399-page master | ___s | Should be < 5 min (embedding time dominates) |
| P6.1.1 | Pipeline trigger (RAG) | ___s | Parser + FSM extraction LLM calls |
| P7.3.1 | Pipeline resume | ___s | Evaluator + scoreboard generation |
| P10.3 | Evidence page load | ___s | PDF loading time depends on PDF size |
| P11.1.6 | Chroma query after restart | ___s | Should be instant (< 1s) |
| — | Backend memory after indexing 3 circulars | ___MB | Establish baseline |
| — | Chroma DB file size | ___MB | `du -h data/chroma_db/chroma.sqlite3` |
| — | PG DB size after verification | ___MB | `docker exec ... psql -c "SELECT pg_database_size('compliance_db')"` |

---

## Phase 14 — Cleanup

- [ ] **P14.1** — Kill backend and frontend
  ```bash
  fuser -k 8000/tcp 2>/dev/null
  fuser -k 5173/tcp 2>/dev/null
  ```

- [ ] **P14.2** — Stop PostgreSQL
  ```bash
  docker-compose stop db
  ```

- [ ] **P14.3** — Run tests one final time
  ```bash
  cd backend && source .venv/bin/activate && python -m pytest tests/ -q
  ```
  Expected: 642 passed

- [ ] **P14.4** — Frontend final build
  ```bash
  cd frontend && npm run build
  ```
  Expected: Clean build, zero errors

---

## Summary

| Phase | Coverage | Status |
|-------|----------|--------|
| P0 | Pre-flight (tests, build, env) | ☐ |
| P1 | Environment Startup | ☐ |
| P2 | PostgreSQL Verification | ☐ |
| P3 | Chroma Verification | ☐ |
| P4 | Multi-Circular Indexing | ☐ |
| P5 | Retrieval | ☐ |
| P6 | Parser & FSM | ☐ |
| P7 | HITL Pause/Resume | ☐ |
| P8 | Deterministic Evaluation | ☐ |
| P9 | Evidence Generation | ☐ |
| P10 | Evidence Viewer (Frontend) | ☐ |
| P11 | PostgreSQL Persistence | ☐ |
| P12 | Failure Scenarios | ☐ |
| P13 | Performance Observations | ☐ |
| P14 | Cleanup | ☐ |

**Total verification steps: 66**
**Estimated execution time: 30–45 minutes** (excluding LLM API call latency)

---

*Execute this checklist manually. Mark each item ☑ as you complete it. Record any unexpected behavior, warnings, or errors. This document becomes the V2.0 release baseline.*
