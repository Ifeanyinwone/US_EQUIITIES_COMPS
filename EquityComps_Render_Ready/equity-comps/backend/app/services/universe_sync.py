"""
Dynamic S&P 500 universe synchronization service.

Fetches the live S&P 500 constituent list from the datasets/s-and-p-500-companies
GitHub repository (raw CSV, always accessible), compares against the database,
inserts new companies, and marks removed companies as inactive.

Never deletes historical records.

Sector/industry metadata priority:
  1. Live GitHub CSV (most current GICS classification)
  2. SP500_METADATA from universe.py (static authoritative fallback)
  3. yfinance (for Nasdaq-100 only tickers not in S&P 500)

Failure isolation: if GitHub is unreachable, the static SP500_METADATA
is used instead. The existing universe in the DB is never corrupted.
"""
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Set
import urllib.request
import io
import csv

from app.core.universe import SP500_TICKERS, NASDAQ100_TICKERS, SP500_METADATA

logger = logging.getLogger(__name__)
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="universe_worker")

SP500_CSV_URL = (
    "https://raw.githubusercontent.com/datasets/s-and-p-500-companies"
    "/main/data/constituents.csv"
)


# ── Live constituent fetch ────────────────────────────────────────────────

def _fetch_sp500_github_sync() -> Optional[List[Dict]]:
    """
    Fetch S&P 500 constituents from the datasets GitHub repo CSV.
    Returns list of dicts with {ticker, name, sector, sub_industry, cik}.
    Returns None on failure — caller uses static SP500_METADATA fallback.
    """
    try:
        req = urllib.request.Request(
            SP500_CSV_URL,
            headers={"User-Agent": "EquityComps/2.0 contact@equitycomps.example.com"},
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            content = r.read().decode("utf-8")
        reader = csv.DictReader(io.StringIO(content))
        rows = list(reader)
        if len(rows) < 400:
            logger.warning(f"[universe_sync] CSV only {len(rows)} rows — suspiciously small, ignoring")
            return None
        constituents = []
        for row in rows:
            ticker = row.get("Symbol", "").strip().replace(".", "-")
            if not ticker:
                continue
            constituents.append({
                "ticker":       ticker,
                "name":         row.get("Security", "").strip(),
                "sector":       row.get("GICS Sector", "").strip(),
                "sub_industry": row.get("GICS Sub-Industry", "").strip(),
                "cik":          row.get("CIK", "").strip().zfill(10) or None,
            })
        logger.info(f"[universe_sync] GitHub CSV returned {len(constituents)} S&P 500 constituents")
        return constituents
    except Exception as e:
        logger.warning(f"[universe_sync] GitHub CSV fetch failed: {e}")
        return None


async def fetch_sp500_constituents() -> List[Dict]:
    """
    Fetch live S&P 500 constituents. Falls back to SP500_METADATA if GitHub
    is unreachable. Always returns a usable list.
    """
    loop = asyncio.get_event_loop()
    live = await loop.run_in_executor(_executor, _fetch_sp500_github_sync)
    if live:
        return live
    # Static fallback from SP500_METADATA (complete, authoritative)
    logger.info("[universe_sync] Using static SP500_METADATA as fallback")
    return [
        {
            "ticker":       t,
            "name":         SP500_METADATA.get(t, {}).get("name") or t,
            "sector":       SP500_METADATA.get(t, {}).get("sector") or "",
            "sub_industry": SP500_METADATA.get(t, {}).get("sub_industry") or "",
            "cik":          SP500_METADATA.get(t, {}).get("cik") or None,
        }
        for t in SP500_TICKERS
    ]


def _fetch_yfinance_metadata_sync(ticker: str) -> Dict:
    """
    Fetch metadata from yfinance for Nasdaq-100-only tickers (not in S&P 500).
    Returns partial dict — all fields may be None if yfinance unavailable.
    """
    try:
        import yfinance as yf
        info = yf.Ticker(ticker).info or {}
        return {
            "name":     info.get("longName") or info.get("shortName") or ticker,
            "sector":   info.get("sector"),
            "industry": info.get("industry"),
            "exchange": info.get("exchange"),
        }
    except Exception as e:
        logger.debug(f"[universe_sync] yfinance metadata failed for {ticker}: {e}")
        return {"name": ticker, "sector": None, "industry": None, "exchange": None}


async def fetch_company_metadata(ticker: str) -> Dict:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, _fetch_yfinance_metadata_sync, ticker)


# ── Main sync function ────────────────────────────────────────────────────

async def sync_sp500_universe(db) -> Dict:
    """
    Synchronize the S&P 500 + Nasdaq-100 universe with the database:
      1. Fetch live S&P 500 constituents from GitHub CSV (with static fallback)
      2. Compare against active companies in DB
      3. Insert new companies with authoritative GICS sector/name data
      4. Update sector/name for companies with 'Unknown' metadata
      5. Mark removed S&P 500 companies as in_sp500=False
      6. Add Nasdaq-100 only tickers not already in DB

    Never deletes any record.
    Returns summary dict.
    """
    from sqlalchemy import select, update
    from app.models.models import Company
    from app.db.crud import upsert_company

    nasdaq100_set = set(NASDAQ100_TICKERS)

    # Fetch live S&P 500 list
    sp500_constituents = await fetch_sp500_constituents()
    sp500_tickers_live = {c["ticker"] for c in sp500_constituents}
    ticker_to_sp500_meta = {c["ticker"]: c for c in sp500_constituents}

    # Get current DB state
    result = await db.execute(
        select(Company.ticker, Company.in_sp500, Company.is_active,
               Company.sector, Company.name)
    )
    db_rows = result.all()
    db_companies: Dict[str, Dict] = {
        row.ticker: {
            "in_sp500":  row.in_sp500,
            "is_active": row.is_active,
            "sector":    row.sector,
            "name":      row.name,
        }
        for row in db_rows
    }

    db_active_sp500 = {t for t, c in db_companies.items() if c["in_sp500"] and c["is_active"]}

    # All tickers that should be in DB
    all_target = sp500_tickers_live | nasdaq100_set

    to_add        = all_target - set(db_companies.keys())
    to_reactivate = (all_target & set(db_companies.keys())) - db_active_sp500
    to_deactivate = db_active_sp500 - sp500_tickers_live

    added = deactivated = reactivated = metadata_fixed = 0

    # Insert new companies
    for ticker in sorted(to_add):
        try:
            in_sp500 = ticker in sp500_tickers_live
            meta = ticker_to_sp500_meta.get(ticker, {})

            if in_sp500 and meta.get("sector"):
                name     = meta["name"] or ticker
                sector   = meta["sector"]
                industry = meta.get("sub_industry") or meta["sector"]
                exchange = None
            else:
                # Nasdaq-100 only — try yfinance
                yf_meta  = await fetch_company_metadata(ticker)
                name     = yf_meta.get("name") or ticker
                sector   = yf_meta.get("sector") or SP500_METADATA.get(ticker, {}).get("sector")
                industry = yf_meta.get("industry") or SP500_METADATA.get(ticker, {}).get("sub_industry")
                exchange = yf_meta.get("exchange")
                await asyncio.sleep(0.3)

            await upsert_company(db, ticker, {
                "name":         name,
                "sector":       sector,
                "industry":     industry,
                "exchange":     exchange,
                "in_sp500":     in_sp500,
                "in_nasdaq100": ticker in nasdaq100_set,
                "is_active":    True,
                "cik":          meta.get("cik"),
            })
            added += 1
        except Exception as e:
            logger.warning(f"[universe_sync] Failed to add {ticker}: {e}")

    # Re-activate and fix sector for existing companies with bad metadata
    for ticker in sorted(set(db_companies.keys()) & all_target):
        company = db_companies[ticker]
        updates: Dict = {}

        # Fix membership flags
        should_be_sp500 = ticker in sp500_tickers_live
        if bool(company["in_sp500"]) != should_be_sp500:
            updates["in_sp500"] = should_be_sp500

        # Fix missing sector/name from authoritative SP500_METADATA
        meta = ticker_to_sp500_meta.get(ticker) or SP500_METADATA.get(ticker, {})
        if meta.get("sector") and (not company["sector"] or company["sector"] == "Unknown"):
            updates["sector"]   = meta["sector"]
            updates["industry"] = meta.get("sub_industry") or meta["sector"]
        if meta.get("name") and (not company["name"] or company["name"] == ticker):
            updates["name"] = meta["name"]

        # CIK from CSV (important for EDGAR queries)
        if meta.get("cik"):
            updates["cik"] = meta["cik"]

        if updates:
            try:
                await db.execute(
                    update(Company).where(Company.ticker == ticker).values(**updates)
                )
                metadata_fixed += 1
            except Exception as e:
                logger.warning(f"[universe_sync] Failed to update {ticker}: {e}")

    # Deactivate removed S&P 500 members — keep all historical data
    for ticker in sorted(to_deactivate):
        try:
            await db.execute(
                update(Company)
                .where(Company.ticker == ticker)
                .values(in_sp500=False)
                # is_active stays True — data is preserved for research
            )
            deactivated += 1
        except Exception as e:
            logger.warning(f"[universe_sync] Failed to deactivate {ticker}: {e}")

    await db.commit()

    summary = {
        "source":          "GitHub CSV" if sp500_constituents else "static",
        "total_sp500":     len(sp500_tickers_live),
        "total_nasdaq100": len(nasdaq100_set),
        "added":           added,
        "reactivated":     reactivated,
        "deactivated":     deactivated,
        "metadata_fixed":  metadata_fixed,
    }
    logger.info(
        f"[universe_sync] Universe sync complete: "
        f"added={added} deactivated={deactivated} metadata_fixed={metadata_fixed} "
        f"sp500={len(sp500_tickers_live)} nasdaq100={len(nasdaq100_set)}"
    )
    return summary


# ── Live constituent fetch ────────────────────────────────────────────────

def _fetch_sp500_wikipedia_sync() -> Optional[List[Dict]]:
    """
    Fetch S&P 500 constituents from Wikipedia via pandas read_html.
    Returns a list of dicts with {ticker, name, sector, sub_industry}.
    Returns None on failure — caller falls back to static list.
    """
    try:
        import pandas as pd
        tables = pd.read_html(
            "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
            attrs={"id": "constituents"},
        )
        if not tables:
            return None
        df = tables[0]
        # Column names vary slightly — normalize
        col_map = {
            "Symbol": "ticker",
            "Security": "name",
            "GICS Sector": "sector",
            "GICS Sub-Industry": "sub_industry",
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
        required = {"ticker", "name", "sector"}
        if not required.issubset(df.columns):
            logger.warning("[universe_sync] Wikipedia table missing expected columns")
            return None

        constituents = []
        for _, row in df.iterrows():
            ticker = str(row.get("ticker", "")).strip().replace(".", "-")
            if not ticker:
                continue
            constituents.append({
                "ticker":       ticker,
                "name":         str(row.get("name", "")).strip(),
                "sector":       str(row.get("sector", "")).strip(),
                "sub_industry": str(row.get("sub_industry", "")).strip() if "sub_industry" in df.columns else None,
            })
        logger.info(f"[universe_sync] Wikipedia returned {len(constituents)} S&P 500 constituents")
        return constituents
    except Exception as e:
        logger.warning(f"[universe_sync] Wikipedia fetch failed: {e}")
        return None




def _fetch_company_metadata_sync(ticker: str) -> Dict:
    """
    Fetch company name, sector, industry from yfinance for a new constituent.
    Returns partial dict — all fields may be None if yfinance is unavailable.
    """
    try:
        import yfinance as yf
        info = yf.Ticker(ticker).info or {}
        return {
            "name":     info.get("longName") or info.get("shortName") or ticker,
            "sector":   info.get("sector"),
            "industry": info.get("industry"),
            "exchange": info.get("exchange"),
        }
    except Exception as e:
        logger.debug(f"[universe_sync] yfinance metadata failed for {ticker}: {e}")
        return {"name": ticker, "sector": None, "industry": None, "exchange": None}




# ── Static fallback universe ──────────────────────────────────────────────

def get_static_sp500_set() -> Set[str]:
    return set(SP500_TICKERS)


def get_static_nasdaq100_set() -> Set[str]:
    return set(NASDAQ100_TICKERS)


# ── Main sync function ────────────────────────────────────────────────────

