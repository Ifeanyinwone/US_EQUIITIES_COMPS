# EquityComps v2 — Deployment Guide

Complete instructions for running from a clean machine.

---

## Prerequisites

Install these before anything else:

| Tool | Version | Download |
|---|---|---|
| Python | 3.12+ | https://www.python.org/downloads |
| Node.js | 20 LTS | https://nodejs.org |
| PostgreSQL | 14+ | https://www.postgresql.org/download |

**Windows Python install:** tick **"Add Python to PATH"** during setup.

**Windows PostgreSQL install:** note the password you set — you will need it.

---

## Part 1 — Database Setup (do once)

### macOS
```bash
brew install postgresql@16
brew services start postgresql@16
createdb equity_comps
```

### Ubuntu / Debian
```bash
sudo apt install postgresql
sudo service postgresql start
sudo -u postgres createdb equity_comps
```

### Windows
Open **SQL Shell (psql)** from the Start menu, press Enter through all prompts,
type your password, then run:
```sql
CREATE DATABASE equity_comps;
\q
```

---

## Part 2 — Backend Setup

Open VS Code, press **Ctrl+`** to open the terminal.

### Step 1 — Enter backend folder and create virtual environment
```bash
cd backend

python -m venv venv
```

### Step 2 — Activate virtual environment

**Windows PowerShell:**
```powershell
venv\Scripts\Activate.ps1
```
If blocked by execution policy, run this first:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```
Then activate again.

**macOS / Linux:**
```bash
source venv/bin/activate
```

You will see `(venv)` at the start of your terminal prompt.

### Step 3 — Install Python dependencies
```bash
pip install -r requirements.txt
```

### Step 4 — Configure environment
```bash
cp .env.example .env
```

Open `backend/.env` and replace `YOUR_PASSWORD` with your PostgreSQL password:
```
DATABASE_URL=postgresql+asyncpg://postgres:YOUR_PASSWORD@localhost:5432/equity_comps
SYNC_DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@localhost:5432/equity_comps
```

**macOS Homebrew (no password):**
```
DATABASE_URL=postgresql+asyncpg://postgres@localhost:5432/equity_comps
SYNC_DATABASE_URL=postgresql://postgres@localhost:5432/equity_comps
```

### Step 5 — Run database migrations
```bash
alembic upgrade head
```

Expected output:
```
INFO  [alembic] Running upgrade  -> 001_initial, Initial schema
INFO  [alembic] Running upgrade 001_initial -> 002_upgrade, Add v2 columns
```

**If you see a "transaction is aborted" error**, run recovery instead:
```bash
cd ..
python scripts/fix_migration.py
cd backend
```

### Step 6 — Test with 5 tickers first
```bash
cd ..
python scripts/seed.py --limit 5
```

This should complete in about 10 seconds.
Open http://localhost:8000/health to confirm the API is running.

### Step 7 — Full seed (5–20 minutes)
```bash
python scripts/seed.py
```

Watch the progress. If it stops, just run it again — it is safe to re-run.
To resume from where it left off:
```bash
python scripts/seed.py --resume
```

---

## Part 3 — Start the Backend

Open a **new terminal tab** in VS Code (click the + button):

```bash
cd backend
venv\Scripts\Activate.ps1    # Windows
# OR
source venv/bin/activate      # macOS/Linux

uvicorn app.main:app --reload --port 8000
```

Expected output:
```
INFO | EquityComps API — Starting up
INFO | Database connection verified
INFO | Database schema verified
INFO | Background scheduler started
INFO | Startup complete — API is ready
INFO | Uvicorn running on http://0.0.0.0:8000
```

---

## Part 4 — Start the Frontend

Open **another new terminal tab**:

```bash
cd frontend
npm install
npm run dev
```

Expected output:
```
  VITE v5.x  ready in 400ms
  ➜  Local:   http://localhost:3000/
```

---

## Part 5 — Open the Dashboard

Go to: **http://localhost:3000**

---

## Startup Checklist

Run through this after a fresh install:

| Check | Command | Expected |
|---|---|---|
| Python version | `python --version` | 3.12.x |
| DB connection | `python scripts/fix_migration.py --check-only` | All columns ✓ |
| API health | visit http://localhost:8000/health | `{"status":"ok","db":"connected"}` |
| Quick seed | `python scripts/seed.py --limit 5` | `✅ SEED COMPLETE` |
| Dashboard | visit http://localhost:3000 | Table loads with data |

---

## Seed Script Options

```bash
# Test with 5 tickers (fast)
python scripts/seed.py --limit 5

# Test specific tickers
python scripts/seed.py --tickers AAPL,MSFT,NVDA,GOOGL,META

# Full seed (valuation + analyst + news sentiment — 20-30 min on first run)
python scripts/seed.py

# Fast valuation-only seed, skip sentiment entirely (a few minutes)
python scripts/seed.py --skip-sentiment

# Resume after interruption
python scripts/seed.py --resume

# Run only one step
python scripts/seed.py --step companies
python scripts/seed.py --step financials
python scripts/seed.py --step multiples
python scripts/seed.py --step analyst_sentiment
python scripts/seed.py --step news_sentiment
python scripts/seed.py --step peer_stats

# Slower delay if still hitting 429
python scripts/seed.py --delay 3.0

# Check migration state
python scripts/fix_migration.py --check-only

# Check sentiment integration status (Finnhub configured? FinBERT loaded?)
curl http://localhost:8000/api/v1/status/sentiment
```

---

## Setting Up Analyst Sentiment (Finnhub) — Optional

The app runs fully without this — analyst sentiment columns simply show N/A.
To enable it:

1. Sign up for a free key at **https://finnhub.io/register** (60 calls/min, no credit card)
2. Open `backend/.env` and set:
   ```
   FINNHUB_API_KEY=your_key_here
   ```
3. Re-run the analyst sentiment step:
   ```bash
   python scripts/seed.py --step analyst_sentiment
   python scripts/seed.py --step multiples   # recalculates Opportunity Score with the new data
   ```

The scheduled background job refreshes analyst sentiment nightly at `ANALYST_REFRESH_HOUR` (default 03:00 UTC) automatically once a key is set — no restart required, just edit `.env` and it picks it up on the next scheduled run (or restart the backend to pick it up sooner).

---

## News Sentiment (FinBERT) — First Run Timing

The first `news_sentiment` step downloads the FinBERT model (~440MB, one-time) and classifies headlines for the full universe — **expect 15–25 minutes**. Every subsequent run is much faster because of incremental refresh:

- Tickers refreshed within `NEWS_STALE_AFTER_HOURS` (default 20h) are skipped entirely
- Within tickers that are due for refresh, only headlines not already seen (by content hash) are sent through the model

If you want to skip this entirely for a quick demo:
```bash
python scripts/seed.py --skip-sentiment
```


---

## Troubleshooting

### "transaction is aborted" during alembic upgrade
```bash
python scripts/fix_migration.py
```

### "password authentication failed"
Edit `backend/.env` — fix the password in both DATABASE_URL lines.

### "connection refused" / PostgreSQL not running
```bash
# macOS
brew services start postgresql@16

# Ubuntu
sudo service postgresql start

# Windows — open Services app, start "postgresql-x64-16"
```

### "equity_comps database does not exist"
```bash
# macOS/Linux
createdb equity_comps

# Windows psql
CREATE DATABASE equity_comps;
```

### 429 Too Many Requests from Yahoo Finance
The seed script already includes 1.5s delays. If still hitting limits:
```bash
python scripts/seed.py --delay 3.0 --resume
```

### Venv deactivates unexpectedly
Re-run: `venv\Scripts\Activate.ps1` (Windows) or `source venv/bin/activate` (macOS)

### Port already in use
```bash
# Windows PowerShell
netstat -ano | findstr :8000
taskkill /PID <number> /F

# macOS/Linux
lsof -ti:8000 | xargs kill
```

---

## Useful URLs

| URL | Purpose |
|---|---|
| http://localhost:3000 | Dashboard |
| http://localhost:8000/health | API health + DB status |
| http://localhost:8000/docs | Swagger API documentation |

---

## Log Files

After seeding, check these files in the project root:

| File | Contents |
|---|---|
| `logs/seed.log` | Full seed run log |
| `logs/seed_failed.log` | Only failed tickers |
| `seed_progress.json` | Resume state (delete to restart fresh) |


# Render Deployment

This repository includes `render.yaml` for a Render Blueprint.

## Services

- `equity-comps-api`: FastAPI web service
- `equity-comps-frontend`: React/Vite static site
- `equity-comps-db`: Render PostgreSQL

## Deploy

1. Push this repository to GitHub.
2. In Render, choose **New → Blueprint** and select the repository.
3. Render creates the API, frontend, and PostgreSQL database.
4. After the API deploys, copy its `https://...onrender.com` URL.
5. Set `VITE_API_URL` on `equity-comps-frontend` to that API URL and redeploy the frontend.
6. Open the frontend URL and confirm `/health` on the API returns `status: ok`.

## Populate the production database

The database starts empty. After the API is live, open the API service's Render Shell and run:

```bash
python scripts/seed.py
```

The seed script creates the tables and loads the current universe, Yahoo market data, SEC EDGAR financials, and calculated multiples.

Run the audit afterwards:

```bash
python scripts/audit_data.py
```

Do not treat the deployment as production-ready until the audit has been reviewed.

## Important

The current project still contains known data-integrity issues from the existing local seed/audit. Render hosting does not correct those values automatically. This deployment makes the application accessible online; the financial-selection and price-refresh logic must still be validated separately.


## Recommended single-service Render deployment

The Blueprint deploys one web service that builds the React frontend and serves it from FastAPI, plus one Render PostgreSQL database. This avoids a production frontend/API URL configuration step.

The first deployment runs:

```bash
python scripts/seed.py
```

as the service's one-time `initialDeployHook`. This can take roughly the same amount of time as the local full seed because it calls Yahoo Finance and SEC EDGAR.

The web service exposes both:

- `/` — EquityComps dashboard
- `/api/v1/...` — API
- `/health` — database/application health

The Blueprint intentionally does not include a paid background worker. The existing scheduler code is therefore not automatically running in this free deployment. Price/financial refresh automation should be added later as a separate paid worker or cron service after the data-selection logic has been validated.
