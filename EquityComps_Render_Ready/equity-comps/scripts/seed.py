#!/usr/bin/env python3
"""Seed the current EquityComps valuation database.

This project intentionally contains no analyst/news sentiment pipeline.
Seed steps:
1. create_tables
2. companies + Yahoo metadata/prices
3. SEC EDGAR financials
4. valuation multiples
5. peer statistics

Price policy: only valid positive finite Yahoo prices are stored.
Financial policy: only SEC facts selected on a like-for-like period basis are stored.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_DIR / "seed.log", mode="a", encoding="utf-8"),
    ],
)
logger = logging.getLogger("seed")


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int)
    parser.add_argument("--tickers")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--step",
        choices=["create_tables", "companies", "financials", "multiples", "peer_stats"],
    )
    parser.add_argument("--delay", type=float)
    parser.add_argument("--reset-progress", action="store_true")
    return parser.parse_args()


def progress_path() -> Path:
    from app.core.config import settings
    return ROOT / settings.SEED_PROGRESS_FILE


def load_progress() -> Dict[str, Any]:
    path = progress_path()
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            pass
    return {"completed_tickers": [], "started_at": None}


def save_progress(state: Dict[str, Any]) -> None:
    progress_path().write_text(json.dumps(state, indent=2))


def mark_done(state: Dict[str, Any], ticker: str) -> None:
    if ticker not in state["completed_tickers"]:
        state["completed_tickers"].append(ticker)
    save_progress(state)


async def step_create_tables() -> None:
    from app.db.database import engine, verify_db_connection
    from app.models.models import Base

    if not await verify_db_connection():
        raise RuntimeError("Database is not reachable")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("Database tables verified")


async def step_seed_companies(
    tickers: List[str],
    universe_map: Dict[str, Dict[str, Any]],
    cik_map: Dict[str, str],
    progress: Dict[str, Any],
    resume: bool,
) -> None:
    from app.core.universe import SP500_METADATA
    from app.db.crud import upsert_company, upsert_market_price
    from app.db.database import AsyncSessionLocal
    from app.services.market_data import clear_cache, fetch_market_data

    clear_cache()

    for i, ticker in enumerate(tickers, 1):
        if resume and ticker in progress["completed_tickers"]:
            continue

        try:
            data = await fetch_market_data(ticker)
            metadata = SP500_METADATA.get(ticker, {})
            flags = universe_map.get(ticker, {})

            company_data = {
                "name": data.get("name") or metadata.get("name") or ticker,
                "sector": data.get("sector") or metadata.get("sector"),
                "industry": (
                    data.get("industry")
                    or metadata.get("sub_industry")
                    or data.get("sector")
                    or metadata.get("sector")
                ),
                "cik": cik_map.get(ticker) or metadata.get("cik"),
                "exchange": data.get("exchange"),
                "currency": data.get("currency") or "USD",
                "in_sp500": bool(flags.get("in_sp500")),
                "in_nasdaq100": bool(flags.get("in_nasdaq100")),
                "is_active": True,
            }

            price_data = {
                key: data[key]
                for key in (
                    "price",
                    "prev_close",
                    "day_change_pct",
                    "market_cap",
                    "volume",
                    "avg_volume_30d",
                    "shares_outstanding",
                    "week_52_high",
                    "week_52_low",
                    "dividend_yield",
                )
                if data.get(key) is not None
            }

            async with AsyncSessionLocal() as db:
                await upsert_company(db, ticker, company_data, commit=False)
                if price_data:
                    await upsert_market_price(
                        db, ticker, price_data, commit=False
                    )
                await db.commit()

            mark_done(progress, ticker)
            logger.info(
                "[%d/%d] %-8s price=%s source=%s",
                i,
                len(tickers),
                ticker,
                data.get("price"),
                data.get("_source", "none"),
            )
        except Exception as exc:
            logger.exception("Company seed failed for %s: %s", ticker, exc)

        await asyncio.sleep(0.05)


async def step_seed_financials(
    tickers: List[str],
    cik_map: Dict[str, str],
) -> None:
    from app.db.crud import upsert_financial_statement
    from app.db.database import AsyncSessionLocal
    from app.services.edgar_service import extract_financials

    for i, ticker in enumerate(tickers, 1):
        cik = cik_map.get(ticker)
        if not cik:
            continue

        try:
            fins = await extract_financials(ticker, cik)
            if not fins:
                continue

            def integer(value):
                return int(value) if value is not None else None

            fs_data = {
                k: v
                for k, v in {
                    "revenue": integer(fins.get("revenue")),
                    "revenue_prior": integer(fins.get("revenue_prior")),
                    "gross_profit": integer(fins.get("gross_profit")),
                    "ebitda": integer(fins.get("ebitda")),
                    "ebit": integer(fins.get("ebit")),
                    "net_income": integer(fins.get("net_income")),
                    "eps_diluted": fins.get("eps_diluted"),
                    "free_cash_flow": integer(fins.get("free_cash_flow")),
                    "operating_cash_flow": integer(
                        fins.get("operating_cash_flow")
                    ),
                    "total_assets": integer(fins.get("total_assets")),
                    "total_debt": integer(fins.get("total_debt")),
                    "cash_and_equivalents": integer(
                        fins.get("cash_and_equivalents")
                    ),
                    "shareholders_equity": integer(
                        fins.get("shareholders_equity")
                    ),
                    "shares_outstanding_bs": integer(
                        fins.get("shares_outstanding_bs")
                    ),
                    "net_debt": integer(fins.get("net_debt")),
                    "filing_form": fins.get("filing_form"),
                    "fiscal_year": fins.get("fiscal_year"),
                    "fiscal_quarter": fins.get("fiscal_quarter"),
                    "period_end_date": fins.get("period_end_date"),
                    "filing_date": fins.get("filing_date"),
                    "financial_basis": fins.get("financial_basis"),
                    "interim_period_months": fins.get(
                        "interim_period_months"
                    ),
                    "data_source": "SEC_EDGAR",
                    "annualized_revenue": integer(
                        fins.get("annualized_revenue")
                    ),
                    "annualized_gross_profit": integer(
                        fins.get("annualized_gross_profit")
                    ),
                    "annualized_ebitda": integer(
                        fins.get("annualized_ebitda")
                    ),
                    "annualized_ebit": integer(
                        fins.get("annualized_ebit")
                    ),
                    "annualized_net_income": integer(
                        fins.get("annualized_net_income")
                    ),
                    "annualized_eps_diluted": fins.get(
                        "annualized_eps_diluted"
                    ),
                    "annualized_operating_cash_flow": integer(
                        fins.get("annualized_operating_cash_flow")
                    ),
                    "annualized_free_cash_flow": integer(
                        fins.get("annualized_free_cash_flow")
                    ),
                    "ttm_revenue": integer(fins.get("ttm_revenue")),
                    "ttm_gross_profit": integer(
                        fins.get("ttm_gross_profit")
                    ),
                    "ttm_ebitda": integer(fins.get("ttm_ebitda")),
                    "ttm_ebit": integer(fins.get("ttm_ebit")),
                    "ttm_net_income": integer(
                        fins.get("ttm_net_income")
                    ),
                    "ttm_eps_diluted": fins.get("ttm_eps_diluted"),
                    "ttm_operating_cash_flow": integer(
                        fins.get("ttm_operating_cash_flow")
                    ),
                    "ttm_free_cash_flow": integer(
                        fins.get("ttm_free_cash_flow")
                    ),
                }.items()
                if v is not None
            }

            async with AsyncSessionLocal() as db:
                await upsert_financial_statement(
                    db, ticker, fs_data, commit=False
                )
                await db.commit()

            if i % 25 == 0 or i == len(tickers):
                logger.info("Financials: %d/%d", i, len(tickers))
        except Exception as exc:
            logger.exception("Financial seed failed for %s: %s", ticker, exc)

        await asyncio.sleep(0.15)


async def step_calc_multiples(tickers: List[str]) -> None:
    from app.db.crud import recalculate_multiples_for_ticker
    from app.db.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        for ticker in tickers:
            try:
                await recalculate_multiples_for_ticker(
                    db, ticker, commit=False
                )
            except Exception:
                logger.exception("Multiple calculation failed for %s", ticker)
        await db.commit()


async def step_peer_stats() -> None:
    from app.db.crud import refresh_peer_statistics
    from app.db.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        await refresh_peer_statistics(db)


async def main():
    args = parse_args()

    from app.core.config import settings

    if args.delay is not None:
        settings.YF_REQUEST_DELAY = args.delay

    if args.reset_progress and progress_path().exists():
        progress_path().unlink()

    progress = load_progress()
    progress.setdefault("started_at", datetime.now(timezone.utc).isoformat())

    from app.core.universe import get_ticker_universe_map
    universe_map = get_ticker_universe_map()

    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    else:
        tickers = list(universe_map)

    if args.limit:
        tickers = tickers[:args.limit]

    from app.services.edgar_service import get_cik_map

    step = args.step
    cik_map = await get_cik_map() if step in (None, "companies", "financials") else {}

    started = time.time()
    logger.info("EquityComps clean valuation seed: %d tickers", len(tickers))

    if step in (None, "create_tables"):
        await step_create_tables()
    if step in (None, "companies"):
        await step_seed_companies(
            tickers, universe_map, cik_map, progress, args.resume
        )
    if step in (None, "financials"):
        await step_seed_financials(tickers, cik_map)
    if step in (None, "multiples"):
        await step_calc_multiples(tickers)
    if step in (None, "peer_stats"):
        await step_peer_stats()

    logger.info(
        "SEED COMPLETE in %.1f minutes",
        (time.time() - started) / 60.0,
    )


if __name__ == "__main__":
    asyncio.run(main())
