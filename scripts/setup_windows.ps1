# Agentic Compliance — Windows setup script (PowerShell)
Write-Host "=== Agentic Compliance Setup (Windows) ===" -ForegroundColor Cyan

# Python
Write-Host "[1/3] Setting up Python virtual environment..."
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r backend/requirements.txt

# Node.js
Write-Host "[2/3] Installing frontend dependencies..."
Set-Location frontend
npm install
Set-Location ..

Write-Host "[3/3] Setup complete." -ForegroundColor Green
Write-Host ""
Write-Host "Run 'docker compose up' for full stack, or:"
Write-Host "  .\.venv\Scripts\Activate.ps1 ; uvicorn backend.app.main:app"
Write-Host "  cd frontend ; npm run dev"
