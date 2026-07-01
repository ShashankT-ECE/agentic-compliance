# Project Handoff

## Overview

Agentic Compliance is a SEBI Securities Market TechSprint project that
automates compliance verification for stock brokers using AI-driven
pipeline processing of regulatory circulars.

## Key Goals

- Parse SEBI circular PDFs to extract compliance obligations.
- Model obligations as finite state machines (FSMs).
- Evaluate broker telemetry data against FSMs.
- Generate verifiable audit scoreboards with hash-chain integrity.

## Architecture

- **Backend**: FastAPI + Python pipeline (parser → FSM extractor → evaluator → scoreboard)
- **Frontend**: React + TypeScript + Vite + Zustand
- **Data**: PostgreSQL (async via SQLAlchemy)
- **Deployment**: Docker Compose / GitHub Actions

## Getting Started

Refer to `scripts/setup_wsl.sh` or `scripts/setup_windows.ps1` for
environment setup instructions.

## Repository Structure

See the project README.md for the full directory layout.
