#!/usr/bin/env bash
# Agentic Compliance — WSL / Linux setup script
set -euo pipefail

echo "=== Agentic Compliance Setup (WSL/Linux) ==="

# Python
echo "[1/3] Setting up Python virtual environment..."
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r backend/requirements.txt

# Node.js
echo "[2/3] Installing frontend dependencies..."
cd frontend
npm install
cd ..

# Docker (optional)
echo "[3/3] Setup complete."
echo ""
echo "Run 'docker compose up' for full stack, or:"
echo "  source .venv/bin/activate && uvicorn backend.app.main:app"
echo "  cd frontend && npm run dev"
