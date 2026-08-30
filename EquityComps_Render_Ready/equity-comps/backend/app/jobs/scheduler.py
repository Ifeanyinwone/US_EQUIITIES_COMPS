"""Background jobs for market prices, SEC financials and universe sync."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, time
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select

from app.core.config import settings
from app.core.universe import get_full_universe
from app.db.crud import (
    recalculate_multiples_for_ticker,
    refresh_peer_statistics,
    upsert_financial_statement,
    upsert_market_price,
)
from app.db.database import AsyncSessionLocal
from app.models.models import MarketPrice
from app.services.edgar_service import extract_financials, get_cik_map
from app.services.market_data import fetch_batch_prices
from app.services.universe_sync import sync_sp500_universe

logger = logging.getLogger(__name__)

NY_TZ = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")
scheduler = AsyncIOScheduler(timezone=UTC)


def is_market_hours(now: datetime | None = None) -> bool:
    """NYSE regular session: Monday-Friday, 09:30-16:00 New York time."""
    current = now.astimezone(NY_TZ) if now else datetime.now(NY_TZ)
    if current.weekday() >= 5:
        return False
    return time(9, 30) <= current.time() <= time(16, 0)


async def refresh_market_prices_job() -> None:
    if not is_market_hours():
        logger.debug("Market refresh skipped: outside NYSE regular hours")
        return

    tickers = get_full_universe()
    logger.info("Market price refresh starting: %d tickers", len(tickers))

    market_data = await fetch_batch_prices(tickers, batch_size=50)

    async with AsyncSessionLocal() as db:
        existing = {
            row.ticker: row
            for row in (
                await db.scalars(
                    select(MarketPrice).where(
                        MarketPrice.ticker.in_(tickers)
                    )
                )
            ).all()
        }

        updated = 0
        failed = 0

        for ticker, data in market_data.items():
            price = data.get("price")
            if price is None or price <= 0:
                continue

            try:
                # Save only fresh values returned by Yahoo. If Yahoo did not
                # return a field, preserve the existing DB value rather than
                # replacing it with an invented value.
                price_data = {
                    "price": price,
                    "prev_close": data.get("prev_close"),
                    "day_change_pct": data.get("day_change_pct"),
                }

                current = existing.get(ticker)
                if current and current.shares_outstanding:
                    market_cap = int(
                        float(price) * int(current.shares_outstanding)
                    )
                    if market_cap > 0:
                        price_data["market_cap"] = market_cap

                # Savepoint isolates a bad ticker without rolling back the
                # entire refresh transaction.
                async with db.begin_nested():
                    await upsert_market_price(
                        db, ticker, price_data, commit=False
                    )
                    await recalculate_multiples_for_ticker(
                        db, ticker, commit=False
                    )

                updated += 1
            except Exception as exc:
                failed += 1
                logger.exception(
                    "Market update failed for %s: %s", ticker, exc
                )

        await db.commit()

        try:
            await refresh_peer_statistics(db)
        except Exception as exc:
            logger.error("Peer stats refresh failed: %s", exc)

    logger.info(
        "Market refresh done: %d/%d updated, %d failed",
        updated, len(tickers), failed,
    )


async def refresh_financial_statements_job() -> None:
    logger.info("Nightly financials refresh starting...")
    tickers = get_full_universe()
    cik_map = await get_cik_map()
    ok = failed = skipped = 0

    for ticker in tickers:
        cik = cik_map.get(ticker)
        if not cik:
            skipped += 1
            continue

        try:
            fins = await extract_financials(ticker, cik)
            if not fins:
                skipped += 1
                continue

            def _int(value):
                return int(value) if value is not None else None

            fs_data = {
                k: v
                for k, v in {
                    "revenue": _int(fins.get("revenue")),
                    "revenue_prior": _int(fins.get("revenue_prior")),
                    "gross_profit": _int(fins.get("gross_profit")),
                    "ebitda": _int(fins.get("ebitda")),
                    "ebit": _int(fins.get("ebit")),
                    "net_income": _int(fins.get("net_income")),
                    "eps_diluted": fins.get("eps_diluted"),
                    "free_cash_flow": _int(fins.get("free_cash_flow")),
                    "operating_cash_flow": _int(
                        fins.get("operating_cash_flow")
                    ),
                    "total_assets": _int(fins.get("total_assets")),
                    "total_debt": _int(fins.get("total_debt")),
                    "cash_and_equivalents": _int(
                        fins.get("cash_and_equivalents")
                    ),
                    "shareholders_equity": _int(
                        fins.get("shareholders_equity")
                    ),
                    "shares_outstanding_bs": _int(
                        fins.get("shares_outstanding_bs")
                    ),
                    "net_debt": _int(fins.get("net_debt")),
                    "filing_form": fins.get("filing_form"),
                    "fiscal_year": fins.get("fiscal_year"),
                    "fiscal_quarter": fins.get("fiscal_quarter"),
                    "period_end_date": fins.get("period_end_date"),
                    "financial_basis": fins.get("financial_basis"),
                    "interim_period_months": fins.get(
                        "interim_period_months"
                    ),
                    "data_source": "SEC_EDGAR",
                    "filing_date": fins.get("filing_date"),
                    "annualized_revenue": _int(
                        fins.get("annualized_revenue")
                    ),
                    "annualized_gross_profit": _int(
                        fins.get("annualized_gross_profit")
                    ),
                    "annualized_ebitda": _int(
                        fins.get("annualized_ebitda")
                    ),
                    "annualized_ebit": _int(
                        fins.get("annualized_ebit")
                    ),
                    "annualized_net_income": _int(
                        fins.get("annualized_net_income")
                    ),
                    "annualized_eps_diluted": fins.get(
                        "annualized_eps_diluted"
                    ),
                    "annualized_operating_cash_flow": _int(
                        fins.get("annualized_operating_cash_flow")
                    ),
                    "annualized_free_cash_flow": _int(
                        fins.get("annualized_free_cash_flow")
                    ),
                    "ttm_revenue": _int(fins.get("ttm_revenue")),
                    "ttm_gross_profit": _int(
                        fins.get("ttm_gross_profit")
                    ),
                    "ttm_ebitda": _int(fins.get("ttm_ebitda")),
                    "ttm_ebit": _int(fins.get("ttm_ebit")),
                    "ttm_net_income": _int(
                        fins.get("ttm_net_income")
                    ),
                    "ttm_eps_diluted": fins.get("ttm_eps_diluted"),
                    "ttm_operating_cash_flow": _int(
                        fins.get("ttm_operating_cash_flow")
                    ),
                    "ttm_free_cash_flow": _int(
                        fins.get("ttm_free_cash_flow")
                    ),
                }.items()
                if v is not None
            }

            async with AsyncSessionLocal() as db:
                await upsert_financial_statement(
                    db, ticker, fs_data, commit=False
                )
                await recalculate_multiples_for_ticker(
                    db, ticker, commit=False
                )
                await db.commit()

            ok += 1
        except Exception as exc:
            failed += 1
            logger.exception("Financial refresh failed for %s: %s", ticker, exc)
            await asyncio.sleep(1.0)

        await asyncio.sleep(0.15)

    async with AsyncSessionLocal() as db:
        await refresh_peer_statistics(db)

    logger.info(
        "Financials refresh done: %d ok, %d skipped, %d failed",
        ok, skipped, failed,
    )


async def sync_universe_job() -> None:
    logger.info("S&P 500 universe sync starting...")
    try:
        async with AsyncSessionLocal() as db:
            summary = await sync_sp500_universe(db)
            logger.info("S&P 500 universe sync complete: %s", summary)
    except Exception as exc:
        logger.exception("Universe sync failed: %s", exc)


def setup_scheduler() -> AsyncIOScheduler:
    scheduler.add_job(
        refresh_market_prices_job,
        trigger=IntervalTrigger(
            seconds=settings.MARKET_REFRESH_INTERVAL,
            timezone=UTC,
        ),
        id="market_price_refresh",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=120,
        next_run_time=datetime.now(UTC),
    )
    scheduler.add_job(
        refresh_financial_statements_job,
        trigger=CronTrigger(
            hour=settings.FINANCIALS_REFRESH_HOUR,
            minute=0,
            timezone=UTC,
        ),
        id="financial_refresh",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        sync_universe_job,
        trigger=CronTrigger(
            day_of_week="sun",
            hour=1,
            minute=0,
            timezone=UTC,
        ),
        id="universe_sync",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )
    return scheduler
