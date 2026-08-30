# EquityComps — Clean U.S. Equity Comparable Analysis

Production-focused comparable-analysis application for S&P 500 and Nasdaq-100 equities.

## What was corrected

### Market prices
- Scheduled refresh now uses genuine multi-ticker `yfinance.download()` batches.
- Current intraday `Close` is used during the regular NYSE session.
- Latest completed daily close is used outside the session.
- Previous close is always a different completed trading day.
- Yahoo MultiIndex layouts are handled explicitly; ambiguous ticker mappings are rejected.
- Prices must be finite and strictly positive.
- Individual price cache has a short TTL; scheduled batch prices are never served from cache.
- A failed Yahoo request never becomes zero or a fabricated price.
- Market refresh uses `America/New_York` session hours, so EST/EDT is handled correctly.
- Refreshed timestamps are explicitly updated on every successful database upsert.
- Current market cap is rebuilt from the fresh price and stored share count during refresh, preventing stale market cap from contaminating EV-based multiples.

### SEC EDGAR financials
- Flow facts are classified by actual `start`/`end` duration rather than trusting only XBRL `fp`.
- H1 and 9M cumulative facts are converted to standalone Q2/Q3.
- Q4 is constructed as FY minus 9M.
- TTM is the sum of four standalone quarters, not four cumulative facts.
- Prior revenue is selected on the same basis as current revenue.
- Annualization is applied only to interim flow periods.
- Balance-sheet fields are anchored to one common reporting date.
- Missing debt/cash/capex are not silently treated as zero.
- FCF is only calculated when both CFO and CapEx are available.
- Annualized EPS is derived from annualized net income and disclosed shares only when a reported TTM EPS is unavailable; cumulative EPS is never blindly multiplied by 2 or 4.

The SEC Company Facts API is the official source used for these financial facts. The SEC notes that Company Facts provides company concepts and that XBRL period/date information must be interpreted with the reporting period in mind. citeturn0search0turn0search22

### Valuation calculations
- Missing debt/cash no longer creates a false EV.
- Missing CapEx no longer creates a false FCF.
- `None` is not confused with valid zero.
- Price, EPS, EV/EBITDA, EV/Sales and P/B require economically meaningful denominators.
- P/E can derive EPS from the same selected net-income basis and share count when a suitable reported EPS is unavailable.
- Multiples record their financial basis.

### Database / scheduler
- Upserts explicitly refresh `refreshed_at`, `updated_at` and `calculated_at`.
- Market-price refresh uses one database transaction with per-ticker savepoints.
- Scheduler is timezone-aware and handles daylight saving time correctly.
- Scheduler starts the first market refresh immediately when it starts during market hours.
- The Docker Compose stack now includes the scheduler as a separate service.
- Obsolete analyst/news sentiment migrations are retained only as no-op compatibility nodes; they are no longer part of the active application.

## Local Windows startup

Open three VS Code terminals.

### Terminal 1 — Backend

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

### Terminal 2 — Scheduler

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m app.jobs.run_scheduler
```

### Terminal 3 — Frontend

```powershell
cd frontend
npm install
npm run dev
```

Open:

- Dashboard: http://localhost:3000
- API docs: http://localhost:8000/docs
- Health: http://localhost:8000/health

## Initial data load

If the database is empty:

```powershell
python scripts\seed.py
```

For a small test first:

```powershell
python scripts\seed.py --limit 10
```

For specific tickers:

```powershell
python scripts\seed.py --tickers AAPL,MSFT,ACN
```

Then calculate multiples again if needed:

```powershell
python scripts\seed.py --step multiples
```

## Data audit

After seeding or a major refresh:

```powershell
python scripts\audit_data.py
```

The audit checks:
- invalid/non-positive prices
- stale/missing price timestamps
- invalid financial values
- financial-basis coverage
- TTM/annualized consistency
- missing EV inputs
- multiple sanity conditions

## Docker

```bash
docker compose up -d
```

The stack contains PostgreSQL, API, scheduler and frontend.

## Important data-integrity policy

This application is intended for investment analysis. Missing data is displayed as unavailable rather than invented.

A stale existing database value may remain when a source is temporarily unavailable, but its `refreshed_at` timestamp is not advanced. This prevents the application from presenting an old price as freshly retrieved data.
