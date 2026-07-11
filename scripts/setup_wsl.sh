#!/usr/bin/env bash
# RuleBridge — WSL / Linux setup script
set -euo pipefail

echo "=== RuleBridge Setup (WSL/Linux) ==="
echo ""

# Python backend
echo "[1/4] Setting up Python virtual environment..."
cd "$(dirname "$0")/../backend"

if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi

source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
echo "  Python dependencies installed."

# Download embedding model (cached for offline use)
echo ""
echo "[2/4] Pre-downloading embedding model (bge-small-en-v1.5)..."
python3 -c "
from sentence_transformers import SentenceTransformer
model = SentenceTransformer('BAAI/bge-small-en-v1.5')
print(f'  Model loaded: {model.get_sentence_embedding_dimension()}-dim embeddings')
" || echo "  ⚠ Model download failed — will download on first use."

# Node.js frontend
echo ""
echo "[3/4] Installing frontend dependencies..."
cd ../frontend
npm install
echo "  Frontend dependencies installed."

# Environment
echo ""
echo "[4/4] Setup complete!"
echo ""
echo "────────────────────────────────────────────────────────────"
echo "  NEXT STEPS:"
echo ""
echo "  1. Configure environment:"
echo "     cp backend/.env.example backend/.env"
echo "     # Edit backend/.env — add your DEEPSEEK_API_KEY"
echo ""
echo "  2. Start PostgreSQL (requires Docker):"
echo "     docker compose up -d db"
echo ""
echo "  3. Start backend:"
echo "     cd backend && source .venv/bin/activate"
echo "     uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
echo ""
echo "  4. Start frontend (new terminal):"
echo "     cd frontend && npm run dev"
echo ""
echo "  5. Open http://localhost:5173"
echo "────────────────────────────────────────────────────────────"
