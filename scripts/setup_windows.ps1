# RuleBridge — Windows setup script (PowerShell)
Write-Host "=== RuleBridge Setup (Windows) ===" -ForegroundColor Cyan
Write-Host ""

# Python backend
Write-Host "[1/4] Setting up Python virtual environment..." -ForegroundColor Yellow
Set-Location "$PSScriptRoot\..\backend"

if (-not (Test-Path ".venv")) {
    python -m venv .venv
}

.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Write-Host "  Python dependencies installed." -ForegroundColor Green

# Embedding model
Write-Host ""
Write-Host "[2/4] Pre-downloading embedding model (bge-small-en-v1.5)..." -ForegroundColor Yellow
try {
    python -c @"
from sentence_transformers import SentenceTransformer
model = SentenceTransformer('BAAI/bge-small-en-v1.5')
print(f'  Model loaded: {model.get_sentence_embedding_dimension()}-dim embeddings')
"@
} catch {
    Write-Host "  WARNING: Model download failed — will download on first use." -ForegroundColor Yellow
}

# Node.js frontend
Write-Host ""
Write-Host "[3/4] Installing frontend dependencies..." -ForegroundColor Yellow
Set-Location "$PSScriptRoot\..\frontend"
npm install
Write-Host "  Frontend dependencies installed." -ForegroundColor Green

# Done
Write-Host ""
Write-Host "[4/4] Setup complete!" -ForegroundColor Green
Write-Host ""
Write-Host "────────────────────────────────────────────────────────────"
Write-Host "  NEXT STEPS:"
Write-Host ""
Write-Host "  1. Configure environment:"
Write-Host "     copy backend\.env.example backend\.env"
Write-Host "     # Edit backend\.env — add your DEEPSEEK_API_KEY"
Write-Host ""
Write-Host "  2. Start PostgreSQL (requires Docker):"
Write-Host "     docker compose up -d db"
Write-Host ""
Write-Host "  3. Start backend:"
Write-Host "     cd backend && .\.venv\Scripts\Activate.ps1"
Write-Host "     uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
Write-Host ""
Write-Host "  4. Start frontend (new terminal):"
Write-Host "     cd frontend && npm run dev"
Write-Host ""
Write-Host "  5. Open http://localhost:5173"
Write-Host "────────────────────────────────────────────────────────────"

Set-Location "$PSScriptRoot\.."
