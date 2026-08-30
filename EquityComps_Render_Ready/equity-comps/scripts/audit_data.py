#!/usr/bin/env python3
"""Run a read-only integrity audit against the current PostgreSQL database."""

from __future__ import annotations

import asyncio
import math
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))


async def main():
    from sqlalchemy import select
    from app.db.database import AsyncSessionLocal
    from app.models.models import (
        Company,
        MarketPrice,
        FinancialStatement,
        CalculatedMultiple,
    )

    async with AsyncSessionLocal() as db:
        companies = (await db.scalars(select(Company).where(Company.is_active.is_(True)))).all()
        prices = (await db.scalars(select(MarketPrice))).all()
        financials = (await db.scalars(select(FinancialStatement))).all()
        multiples = (await db.scalars(select(CalculatedMultiple))).all()

    price_map = {row.ticker: row for row in prices}
    fs_map = {row.ticker: row for row in financials}
    cm_map = {row.ticker: row for row in multiples}

    bad_prices = []
    stale_prices = []
    invalid_financials = []
    basis_counts = {}

    now = datetime.now(timezone.utc)
    stale_cutoff = now - timedelta(hours=24)

    for company in companies:
        mp = price_map.get(company.ticker)
        fs = fs_map.get(company.ticker)
        cm = cm_map.get(company.ticker)

        if mp:
            try:
                if mp.price is not None:
                    value = float(mp.price)
                    if not math.isfinite(value) or value <= 0:
                        bad_prices.append(company.ticker)
                if mp.refreshed_at and mp.refreshed_at < stale_cutoff:
                    stale_prices.append(company.ticker)
            except (TypeError, ValueError):
                bad_prices.append(company.ticker)

        if fs:
            basis = fs.financial_basis or "N/A"
            basis_counts[basis] = basis_counts.get(basis, 0) + 1

            if basis == "TTM" and fs.annualized_revenue is not None:
                invalid_financials.append(f"{company.ticker}:TTM_has_annualized_revenue")
            if basis.startswith("Annualized") and fs.ttm_revenue is not None:
                invalid_financials.append(f"{company.ticker}:Annualized_has_ttm_revenue")

            for field in (
                "revenue", "gross_profit", "ebitda", "ebit",
                "net_income", "total_debt", "cash_and_equivalents",
                "shareholders_equity",
            ):
                value = getattr(fs, field, None)
                if value is not None:
                    try:
                        if not math.isfinite(float(value)):
                            invalid_financials.append(
                                f"{company.ticker}:{field}"
                            )
                    except (TypeError, ValueError):
                        invalid_financials.append(
                            f"{company.ticker}:{field}"
                        )

        if cm and cm.enterprise_value is not None:
            try:
                if float(cm.enterprise_value) <= 0:
                    invalid_financials.append(
                        f"{company.ticker}:enterprise_value"
                    )
            except (TypeError, ValueError):
                invalid_financials.append(
                    f"{company.ticker}:enterprise_value"
                )

    print("=" * 70)
    print("EquityComps DATA INTEGRITY AUDIT")
    print("=" * 70)
    print(f"Active companies:       {len(companies)}")
    print(f"Market-price rows:      {len(prices)}")
    print(f"Financial rows:         {len(financials)}")
    print(f"Multiple rows:          {len(multiples)}")
    print(f"Invalid prices:         {len(bad_prices)}")
    print(f"Prices >24h old:        {len(stale_prices)}")
    print(f"Invalid financials:     {len(invalid_financials)}")
    print("")
    print("Financial basis coverage:")
    for basis, count in sorted(basis_counts.items()):
        print(f"  {basis:<25} {count}")
    print("")

    if bad_prices:
        print("Invalid-price tickers:", ", ".join(bad_prices[:30]))
    if stale_prices:
        print("Stale-price tickers:", ", ".join(stale_prices[:30]))
    if invalid_financials:
        print("Invalid financial fields:", ", ".join(invalid_financials[:30]))

    if bad_prices or invalid_financials:
        print("\nAUDIT STATUS: FAIL")
        raise SystemExit(1)

    print("AUDIT STATUS: PASS")


if __name__ == "__main__":
    asyncio.run(main())
