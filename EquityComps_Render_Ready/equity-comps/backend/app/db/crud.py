from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    CalculatedMultiple,
    Company,
    FinancialStatement,
    MarketPrice,
)
from app.services.calculations import calculate_all_multiples, compute_peer_stats


def _f(value: Any) -> Optional[float]:
    return float(value) if value is not None else None


def _i(value: Any) -> Optional[int]:
    return int(value) if value is not None else None


def _first_not_none(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _touch_fields(model) -> Dict[str, datetime]:
    now = datetime.now(timezone.utc)
    columns = {column.name for column in model.__table__.columns}
    values: Dict[str, datetime] = {}
    if "refreshed_at" in columns:
        values["refreshed_at"] = now
    if "updated_at" in columns:
        values["updated_at"] = now
    if "calculated_at" in columns:
        values["calculated_at"] = now
    return values


async def _upsert(
    db: AsyncSession,
    model,
    ticker: str,
    data: Dict[str, Any],
    *,
    commit: bool = True,
) -> None:
    """Upsert one record and explicitly refresh timestamp columns."""
    payload = dict(data)
    payload.update(_touch_fields(model))

    stmt = pg_insert(model).values(ticker=ticker, **payload)
    stmt = stmt.on_conflict_do_update(
        index_elements=["ticker"],
        set_=payload,
    )
    await db.execute(stmt)

    if commit:
        await db.commit()


async def upsert_company(
    db: AsyncSession,
    ticker: str,
    data: Dict[str, Any],
    *,
    commit: bool = True,
) -> None:
    await _upsert(db, Company, ticker, data, commit=commit)


async def upsert_market_price(
    db: AsyncSession,
    ticker: str,
    data: Dict[str, Any],
    *,
    commit: bool = True,
) -> None:
    await _upsert(db, MarketPrice, ticker, data, commit=commit)


async def upsert_financial_statement(
    db: AsyncSession,
    ticker: str,
    data: Dict[str, Any],
    *,
    commit: bool = True,
) -> None:
    await _upsert(db, FinancialStatement, ticker, data, commit=commit)


async def recalculate_multiples_for_ticker(
    db: AsyncSession,
    ticker: str,
    *,
    commit: bool = True,
) -> None:
    mp = await db.scalar(
        select(MarketPrice).where(MarketPrice.ticker == ticker)
    )
    fs = await db.scalar(
        select(FinancialStatement).where(
            FinancialStatement.ticker == ticker
        )
    )

    if not mp or not fs:
        return

    def flow(name: str):
        ttm = getattr(fs, f"ttm_{name}", None)
        if ttm is not None:
            return ttm, "TTM"

        annualized = getattr(fs, f"annualized_{name}", None)
        if annualized is not None:
            return annualized, "Annualized"

        reported = getattr(fs, name, None)
        if reported is not None:
            return reported, fs.financial_basis or "Reported"

        return None, None

    revenue, revenue_basis = flow("revenue")
    gross_profit, gross_profit_basis = flow("gross_profit")
    ebitda, ebitda_basis = flow("ebitda")
    net_income, net_income_basis = flow("net_income")
    free_cash_flow, fcf_basis = flow("free_cash_flow")

    # EPS must match the financial basis when possible. If no EPS is available,
    # calculations.py derives it from the selected net income/share count.
    eps_diluted = None
    eps_basis = None
    if fs.ttm_eps_diluted is not None:
        eps_diluted = fs.ttm_eps_diluted
        eps_basis = "TTM"
    elif fs.annualized_eps_diluted is not None:
        eps_diluted = fs.annualized_eps_diluted
        eps_basis = "Annualized"
    elif fs.eps_diluted is not None and fs.financial_basis.startswith("Annual FY"):
        eps_diluted = fs.eps_diluted
        eps_basis = fs.financial_basis

    shares = _first_not_none(
        mp.shares_outstanding,
        fs.shares_outstanding_bs,
    )

    # Rebuild market cap from the current price and latest stored share count.
    # This prevents a stale market cap from surviving a fresh price update.
    market_cap = _i(mp.market_cap)
    if mp.price is not None and shares is not None:
        candidate = float(mp.price) * int(shares)
        if candidate > 0:
            market_cap = int(candidate)

    vals = calculate_all_multiples(
        price=_f(mp.price),
        market_cap=market_cap,
        revenue=_f(revenue),
        revenue_prior=_f(fs.revenue_prior),
        ebitda=_f(ebitda),
        net_income=_f(net_income),
        eps_diluted=_f(eps_diluted),
        total_debt=_f(fs.total_debt),
        cash=_f(fs.cash_and_equivalents),
        shareholders_equity=_f(fs.shareholders_equity),
        gross_profit=_f(gross_profit),
        free_cash_flow=_f(free_cash_flow),
        dividend_yield=_f(mp.dividend_yield),
        shares_outstanding=_i(shares),
    )

    vals.update({
        "pe_basis": eps_basis or net_income_basis,
        "ev_ebitda_basis": ebitda_basis,
        "ev_sales_basis": revenue_basis,
        "fcf_yield_basis": fcf_basis,
        "financial_basis": fs.financial_basis or revenue_basis or "Reported",
    })

    await _upsert(
        db,
        CalculatedMultiple,
        ticker,
        vals,
        commit=commit,
    )


async def refresh_peer_statistics(db: AsyncSession) -> None:
    # Peer statistics are computed dynamically by get_peer_stats().
    return None


async def get_latest_refresh_timestamps(
    db: AsyncSession,
) -> Dict[str, Any]:
    prices = await db.scalar(select(func.max(MarketPrice.refreshed_at)))
    financials = await db.scalar(select(func.max(FinancialStatement.refreshed_at)))
    multiples = await db.scalar(select(func.max(CalculatedMultiple.calculated_at)))
    return {
        "price_last_updated": prices,
        "financials_last_updated": financials,
        # Peer statistics are calculated dynamically from the current rows;
        # the multiples timestamp is the closest persisted calculation marker.
        "peer_stats_last_updated": multiples,
        # Backward-compatible aliases for older API clients.
        "prices": prices,
        "financials": financials,
        "multiples": multiples,
    }


async def get_all_companies_with_data(
    db: AsyncSession,
    universe=None,
    sector=None,
    industry=None,
    search=None,
):
    q = (
        select(
            Company,
            MarketPrice,
            FinancialStatement,
            CalculatedMultiple,
        )
        .outerjoin(
            MarketPrice,
            Company.ticker == MarketPrice.ticker,
        )
        .outerjoin(
            FinancialStatement,
            Company.ticker == FinancialStatement.ticker,
        )
        .outerjoin(
            CalculatedMultiple,
            Company.ticker == CalculatedMultiple.ticker,
        )
        .where(Company.is_active.is_(True))
    )

    if universe == "SP500":
        q = q.where(Company.in_sp500.is_(True))
    elif universe == "NASDAQ100":
        q = q.where(Company.in_nasdaq100.is_(True))

    if sector:
        q = q.where(Company.sector == sector)
    if industry:
        q = q.where(Company.industry == industry)

    if search:
        pattern = f"%{search}%"
        q = q.where(
            or_(
                Company.ticker.ilike(pattern),
                Company.name.ilike(pattern),
            )
        )

    rows = (await db.execute(q.order_by(Company.ticker))).all()
    out = []

    for company, mp, fs, cm in rows:
        revenue = _first_not_none(
            fs.ttm_revenue if fs else None,
            fs.annualized_revenue if fs else None,
            fs.revenue if fs else None,
        )
        ebitda = _first_not_none(
            fs.ttm_ebitda if fs else None,
            fs.annualized_ebitda if fs else None,
            fs.ebitda if fs else None,
        )
        net_income = _first_not_none(
            fs.ttm_net_income if fs else None,
            fs.annualized_net_income if fs else None,
            fs.net_income if fs else None,
        )
        gross_profit = _first_not_none(
            fs.ttm_gross_profit if fs else None,
            fs.annualized_gross_profit if fs else None,
            fs.gross_profit if fs else None,
        )
        free_cash_flow = _first_not_none(
            fs.ttm_free_cash_flow if fs else None,
            fs.annualized_free_cash_flow if fs else None,
            fs.free_cash_flow if fs else None,
        )
        eps_diluted = _first_not_none(
            fs.ttm_eps_diluted if fs else None,
            fs.annualized_eps_diluted if fs else None,
            fs.eps_diluted if fs else None,
        )

        out.append({
            "ticker": company.ticker,
            "name": company.name,
            "sector": company.sector,
            "industry": company.industry,
            "in_sp500": bool(company.in_sp500),
            "in_nasdaq100": bool(company.in_nasdaq100),

            "price": _f(mp.price) if mp else None,
            "day_change_pct": _f(mp.day_change_pct) if mp else None,
            "market_cap": _i(mp.market_cap) if mp else None,
            "volume": _i(mp.volume) if mp else None,
            "week_52_high": _f(mp.week_52_high) if mp else None,
            "week_52_low": _f(mp.week_52_low) if mp else None,

            "revenue": _i(revenue),
            "revenue_prior": _i(fs.revenue_prior) if fs else None,
            "ebitda": _i(ebitda),
            "net_income": _i(net_income),
            "eps_diluted": _f(eps_diluted),
            "total_debt": _i(fs.total_debt) if fs else None,
            "cash": _i(fs.cash_and_equivalents) if fs else None,
            "net_debt": _i(fs.net_debt) if fs else None,
            "shareholders_equity": _i(fs.shareholders_equity) if fs else None,
            "gross_profit": _i(gross_profit),
            "free_cash_flow": _i(free_cash_flow),

            "filing_form": fs.filing_form if fs else None,
            "period_end_date": fs.period_end_date if fs else None,
            "fiscal_year": fs.fiscal_year if fs else None,

            "enterprise_value": _i(cm.enterprise_value) if cm else None,
            "pe_ratio": _f(cm.pe_ratio) if cm else None,
            "ev_ebitda": _f(cm.ev_ebitda) if cm else None,
            "ev_sales": _f(cm.ev_sales) if cm else None,
            "price_to_book": _f(cm.price_to_book) if cm else None,
            "roe": _f(cm.roe) if cm else None,
            "ebitda_margin": _f(cm.ebitda_margin) if cm else None,
            "gross_margin": _f(cm.gross_margin) if cm else None,
            "net_debt_ebitda": _f(cm.net_debt_ebitda) if cm else None,
            "fcf_yield": _f(cm.fcf_yield) if cm else None,
            "revenue_growth": _f(cm.revenue_growth) if cm else None,
            "dividend_yield": _f(cm.dividend_yield) if cm else None,
            "eps": _f(cm.eps) if cm else None,
            "debt_to_equity": _f(cm.debt_to_equity) if cm else None,

            "price_refreshed_at": (
                mp.refreshed_at.isoformat()
                if mp and mp.refreshed_at else None
            ),
            "financials_refreshed_at": (
                fs.refreshed_at.isoformat()
                if fs and fs.refreshed_at else None
            ),
        })

    return out


async def get_sectors(db: AsyncSession):
    q = (
        select(Company.sector)
        .where(
            Company.sector.is_not(None),
            Company.is_active.is_(True),
        )
        .distinct()
        .order_by(Company.sector)
    )
    return list((await db.scalars(q)).all())


async def get_industries(db: AsyncSession, sector=None):
    q = select(Company.industry).where(
        Company.industry.is_not(None),
        Company.is_active.is_(True),
    )
    if sector:
        q = q.where(Company.sector == sector)
    q = q.distinct().order_by(Company.industry)
    return list((await db.scalars(q)).all())


async def get_peer_stats(db: AsyncSession, sector, universe="ALL"):
    rows = await get_all_companies_with_data(
        db,
        universe=universe,
        sector=sector,
    )
    if not rows:
        return None

    keys = [
        "pe_ratio",
        "ev_ebitda",
        "ev_sales",
        "price_to_book",
        "roe",
        "ebitda_margin",
        "revenue_growth",
        "fcf_yield",
    ]

    out = {
        "sector": sector,
        "company_count": len(rows),
    }

    for key in keys:
        stats = compute_peer_stats([row.get(key) for row in rows])
        out[f"median_{key}"] = stats["median"]
        out[f"mean_{key}"] = stats["mean"]
        out[f"count_{key}"] = stats["count"]

    return out
