# API Reference

## Base URL

`http://localhost:8000/api`

## Endpoints

### Pipeline

| Method | Path | Description |
|--------|------|-------------|
| POST   | /pipeline/trigger | Trigger a compliance pipeline run |
| GET    | /pipeline/status/:id | Check pipeline run status |
| GET    | /pipeline/result/:id | Retrieve pipeline run results |

### Telemetry

| Method | Path | Description |
|--------|------|-------------|
| POST   | /telemetry/ingest | Ingest broker telemetry records |
| GET    | /telemetry/query | Query telemetry data |

### Reports

| Method | Path | Description |
|--------|------|-------------|
| GET    | /reports/generate | Generate a compliance report |
| GET    | /reports/:id | Retrieve a specific report |

## Authentication

TODO: Document auth scheme (API key / JWT).
