"""
Agentic Compliance — FastAPI application entry point (M7).

Initialises the web server, registers middleware and API routes,
and exposes the ASGI entry for Uvicorn / production servers.

Routes:
  /api/pipeline/*   — pipeline trigger, status, result, HITL review
  /api/telemetry/*  — telemetry ingest and query
  /api/reports/*    — compliance report generation and retrieval
  /health           — health check (no auth)
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import pipeline, reports, telemetry

logger = logging.getLogger(__name__)


# =========================================================================
# Lifespan
# =========================================================================


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup / shutdown handler.

    On startup: initialises the LLM client and pipeline runner.
    On shutdown: no special cleanup needed (V1 in-memory stores).
    """
    logger.info("Starting Agentic Compliance API...")
    # Trigger lazy initialisation of shared dependencies
    from app.api.deps import get_llm_client, get_runner

    llm = get_llm_client()
    runner = get_runner()
    logger.info("LLM client: %s", type(llm).__name__)
    logger.info("Pipeline runner: ready")

    yield

    logger.info("Shutting down Agentic Compliance API...")


# =========================================================================
# FastAPI app
# =========================================================================


app = FastAPI(
    title="Agentic Compliance API",
    description="Automated compliance verification for stock brokers against SEBI regulatory circulars.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow frontend dev server and any local access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------------------------------------------------
# Router registration
# -------------------------------------------------------------------------

app.include_router(pipeline.router)
app.include_router(telemetry.router)
app.include_router(reports.router)


# -------------------------------------------------------------------------
# Health check
# -------------------------------------------------------------------------


@app.get("/health", tags=["health"])
async def health_check() -> dict[str, str]:
    """Basic health check — no authentication required."""
    return {"status": "healthy", "version": "1.0.0"}
