# API Reference

> **Base URL**: `http://localhost:8000`
> **Interactive docs**: `http://localhost:8000/docs` (Swagger UI)

---

## Health

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check — returns `{"status": "healthy", "version": "1.0.0"}` |

---

## Pipeline

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/pipeline/trigger` | Start a compliance pipeline run |
| `GET` | `/api/pipeline/status/{run_id}` | Get pipeline run status + FSM counts |
| `GET` | `/api/pipeline/result/{run_id}` | Get verdicts + scoreboard for a completed run |
| `POST` | `/api/pipeline/{run_id}/resume` | Resume pipeline after HITL review |

### Trigger Request

```json
{
  "circular_path": "data/circulars/SEBI-HO-...pdf",
  "circular_id": "SEBI/HO/MIRSD/.../2025/57",
  "telemetry": [],
  "use_rag": false
}
```

---

## HITL Review

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/pipeline/hitl` | List runs with pending HITL items |
| `POST` | `/api/pipeline/hitl/{fsm_id}/approve` | Approve an FSM |
| `POST` | `/api/pipeline/hitl/{fsm_id}/reject` | Reject an FSM (requires comments) |
| `POST` | `/api/pipeline/hitl/{fsm_id}/amend` | Amend an FSM (supply corrected FSM JSON) |
| `GET` | `/api/pipeline/{run_id}/fsms` | List all FSMs for a run |
| `GET` | `/api/pipeline/{run_id}/fsms/{locked_fsm_id}` | Get a single LockedFSM |
| `POST` | `/api/pipeline/{run_id}/fsms/{locked_fsm_id}/approve` | Approve by run + FSM ID |
| `POST` | `/api/pipeline/{run_id}/fsms/{locked_fsm_id}/reject` | Reject by run + FSM ID |
| `POST` | `/api/pipeline/{run_id}/fsms/{locked_fsm_id}/amend` | Amend by run + FSM ID |
| `GET` | `/api/pipeline/{run_id}/review-history` | Get review audit trail |

---

## RAG

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/rag/index` | Index a circular PDF (chunk → embed → store) |
| `POST` | `/api/rag/query` | Semantic search across indexed circulars |
| `GET` | `/api/rag/status/{circular_ref}` | Check index status for a circular |
| `GET` | `/api/rag/circulars` | List all indexed circulars |
| `POST` | `/api/rag/index-all` | Batch-index multiple circulars |
| `DELETE` | `/api/rag/circular/{circular_ref}` | Remove a circular from index + registry |

---

## Evidence

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/evidence/{verdict_id}` | Full evidence chain for a verdict |
| `GET` | `/api/evidence/fsm/{locked_fsm_id}` | Source chunks for a locked FSM |
| `GET` | `/api/chunks/{chunk_id}/positions` | Bounding-box positions for a chunk |
| `GET` | `/api/circulars/{circular_ref}/pdf` | Serve source PDF for PDF.js viewer |

---

## Telemetry

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/telemetry/ingest` | Ingest broker telemetry events |
| `GET` | `/api/telemetry/query` | Query telemetry with filters |
| `GET` | `/api/telemetry/query/{run_id}` | Get telemetry for a specific run |

---

## Reports

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/reports/generate/{run_id}` | Generate an audit report |
| `GET` | `/api/reports/{report_id}` | Retrieve a generated report |

---

## Status Codes

| Code | Meaning |
|------|---------|
| `200` | Success |
| `201` | Created (pipeline triggered) |
| `400` | Bad request (validation error) |
| `404` | Not found (run, verdict, report, etc.) |
| `500` | Internal server error |

---

## Authentication

> **Current**: No authentication (development/hackathon mode).
> **Planned**: API key or JWT-based authentication.

---

*For complete schema details, use the interactive Swagger UI at `/docs`.*
