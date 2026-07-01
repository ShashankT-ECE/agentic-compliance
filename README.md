# Agentic Compliance

SEBI Securities Market TechSprint — Automated compliance verification
for stock brokers using AI-driven pipeline processing.

## Architecture

```
┌─────────────┐   ┌──────────────┐   ┌───────────┐   ┌────────────┐
│  PDF Parser  │ → │ FSM Extractor│ → │ Evaluator │ → │ Scoreboard  │
│  (circulars) │   │ (obligations)│   │ (telemetry)│   │ (audit)    │
└─────────────┘   └──────────────┘   └───────────┘   └────────────┘
```

- **Backend**: FastAPI (Python) — pipeline orchestration, data models, API
- **Frontend**: React + TypeScript + Vite — dashboard, FSM viewer, reports
- **Data**: PostgreSQL — circulars, extracted FSMs, telemetry, scoreboard
- **Integrity**: Hash-chain locking for FSM snapshots and audit trails

## Getting Started

### Prerequisites

- Python 3.12+
- Node.js 22+
- Docker & Docker Compose (optional, for full stack)

### Setup

**Linux / WSL:**
```bash
chmod +x scripts/setup_wsl.sh && ./scripts/setup_wsl.sh
```

**Windows:**
```powershell
.\scripts\setup_windows.ps1
```

### Run

```bash
# Full stack (Docker)
docker compose up

# Backend only
uvicorn backend.app.main:app --reload

# Frontend only
cd frontend && npm run dev
```

## Repository Structure

See the project directory tree at the top level for a complete
file-by-file layout description.

## License

SEBI Securities Market TechSprint — All rights reserved.
