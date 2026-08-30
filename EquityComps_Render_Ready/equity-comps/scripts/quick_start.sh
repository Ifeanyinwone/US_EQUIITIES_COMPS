#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
# quick_start.sh  —  Local dev setup without Docker
# Run from the project root: bash scripts/quick_start.sh
# ─────────────────────────────────────────────────────────────────────
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║         EquityComps — Quick Start Setup          ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

# ── PostgreSQL check ──────────────────────────────────────────────
echo "▶  Checking PostgreSQL..."
if ! command -v psql &>/dev/null; then
    echo "   ⚠  psql not found. Install PostgreSQL 14+ and ensure it's running."
    echo "      macOS: brew install postgresql && brew services start postgresql"
    echo "      Ubuntu: sudo apt install postgresql && sudo service postgresql start"
    exit 1
fi

# Create DB if needed
psql -U postgres -tc "SELECT 1 FROM pg_database WHERE datname='equity_comps'" | grep -q 1 \
    || psql -U postgres -c "CREATE DATABASE equity_comps;" \
    && echo "   ✓  Database equity_comps ready"

# ── Python backend ────────────────────────────────────────────────
echo ""
echo "▶  Setting up Python backend..."
cd "$ROOT/backend"

if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    echo "   Created virtual environment"
fi

source .venv/bin/activate
pip install -q -r requirements.txt
echo "   ✓  Python dependencies installed"

# Copy env file if missing
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "   ✓  Created .env from .env.example (edit if needed)"
fi

# ── Seed data ─────────────────────────────────────────────────────
echo ""
echo "▶  Seeding database (this will take ~5–10 minutes)..."
echo "   Fetching company info, market prices, and SEC EDGAR financials..."
cd "$ROOT"
python scripts/seed.py

# ── Start backend ─────────────────────────────────────────────────
echo ""
echo "▶  Starting FastAPI backend on http://localhost:8000..."
cd "$ROOT/backend"
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!
echo "   Backend PID: $BACKEND_PID"

# ── Frontend ──────────────────────────────────────────────────────
echo ""
echo "▶  Setting up React frontend..."
cd "$ROOT/frontend"

if [ ! -d "node_modules" ]; then
    npm install
    echo "   ✓  Node dependencies installed"
fi

echo ""
echo "▶  Starting Vite dev server on http://localhost:3000..."
npm run dev &
FRONTEND_PID=$!
echo "   Frontend PID: $FRONTEND_PID"

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║  ✅  EquityComps is running!                     ║"
echo "║                                                   ║"
echo "║  Dashboard:  http://localhost:3000               ║"
echo "║  API docs:   http://localhost:8000/docs          ║"
echo "║                                                   ║"
echo "║  Press Ctrl+C to stop both servers              ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

# Keep running until Ctrl+C
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; echo 'Servers stopped.'; exit 0" INT TERM
wait
