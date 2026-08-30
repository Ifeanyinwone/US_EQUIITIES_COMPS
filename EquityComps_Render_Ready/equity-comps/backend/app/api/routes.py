from fastapi import APIRouter, Depends, Query, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List
import pandas as pd
import numpy as np
import io
import logging

from app.db.database import get_db
from app.db.crud import (
    get_all_companies_with_data, get_sectors, get_industries,
    get_peer_stats, refresh_peer_statistics, get_latest_refresh_timestamps,
)
from app.services.calculations import compute_peer_stats, calculate_discount_vs_median

logger = logging.getLogger(__name__)
router = APIRouter()

METRIC_FIELDS = [
    "pe_ratio", "ev_ebitda", "ev_sales", "price_to_book",
    "roe", "ebitda_margin", "gross_margin", "net_debt_ebitda",
    "fcf_yield", "revenue_growth", "dividend_yield",
    "eps", "debt_to_equity",
]

BENCHMARK_METRICS = ["pe_ratio", "ev_ebitda", "ev_sales", "price_to_book"]


def build_summary(companies: List[dict]) -> dict:
    """Compute mean/median for each metric across the filtered set."""
    summary = {}
    for metric in METRIC_FIELDS:
        values = [c.get(metric) for c in companies if c.get(metric) is not None]
        summary[metric] = compute_peer_stats(values)
    return summary


def enrich_with_discount(companies: List[dict], summary: dict) -> List[dict]:
    """
    Add discount_vs_median_* fields for all benchmark metrics.
    Uses the filtered-set median (summary), not sector-specific stats.
    """
    for metric in BENCHMARK_METRICS:
        med_key = f"discount_vs_median_{metric}"
        peer_median = summary.get(metric, {}).get("median")
        for c in companies:
            val = c.get(metric)
            c[med_key] = calculate_discount_vs_median(val, peer_median)
    return companies


@router.get("/comps")
async def get_comps(
    universe: Optional[str] = Query(None),
    sector:   Optional[str] = Query(None),
    industry: Optional[str] = Query(None),
    search:   Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    companies = await get_all_companies_with_data(
        db,
        universe=universe if universe and universe != "ALL" else None,
        sector=sector, industry=industry, search=search,
    )
    summary = build_summary(companies)
    companies = enrich_with_discount(companies, summary)
    timestamps = await get_latest_refresh_timestamps(db)
    return {
        "companies":   companies,
        "summary":     summary,
        "total_count": len(companies),
        "timestamps":  timestamps,
        "filters_applied": {
            "universe": universe or "ALL",
            "sector":   sector,
            "industry": industry,
            "search":   search,
        },
    }


@router.get("/filters")
async def get_filter_options(
    sector: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    return {
        "sectors":   await get_sectors(db),
        "industries": await get_industries(db, sector=sector),
        "universes": ["ALL", "SP500", "NASDAQ100"],
    }


@router.get("/timestamps")
async def get_timestamps(db: AsyncSession = Depends(get_db)):
    return await get_latest_refresh_timestamps(db)


@router.get("/peer-stats/{sector}")
async def get_sector_peer_stats(
    sector: str,
    universe: str = Query("ALL"),
    db: AsyncSession = Depends(get_db),
):
    stats = await get_peer_stats(db, sector=sector, universe=universe)
    if not stats:
        raise HTTPException(status_code=404, detail=f"No peer stats for: {sector}")
    return stats



@router.get("/export/csv")
async def export_csv(
    universe: Optional[str] = Query(None),
    sector:   Optional[str] = Query(None),
    industry: Optional[str] = Query(None),
    search:   Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    companies = await get_all_companies_with_data(
        db, universe=universe if universe and universe != "ALL" else None,
        sector=sector, industry=industry, search=search,
    )
    summary = build_summary(companies)
    companies = enrich_with_discount(companies, summary)
    df = _build_export_df(companies, summary)
    out = io.StringIO()
    df.to_csv(out, index=False)
    out.seek(0)
    return StreamingResponse(
        io.BytesIO(out.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=equity_comps.csv"},
    )


@router.get("/export/excel")
async def export_excel(
    universe: Optional[str] = Query(None),
    sector:   Optional[str] = Query(None),
    industry: Optional[str] = Query(None),
    search:   Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    companies = await get_all_companies_with_data(
        db, universe=universe if universe and universe != "ALL" else None,
        sector=sector, industry=industry, search=search,
    )
    summary = build_summary(companies)
    companies = enrich_with_discount(companies, summary)
    df = _build_export_df(companies, summary)

    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Comparable Analysis")

        # Peer Summary sheet — Median first, Mean second
        summary_rows = []
        label_map = {
            "pe_ratio": "P/E", "ev_ebitda": "EV/EBITDA", "ev_sales": "EV/Sales",
            "price_to_book": "P/Book", "roe": "ROE %", "ebitda_margin": "EBITDA Margin %",
            "gross_margin": "Gross Margin %", "net_debt_ebitda": "Net Debt/EBITDA",
            "fcf_yield": "FCF Yield %", "revenue_growth": "Revenue Growth %",
            "dividend_yield": "Dividend Yield %",
            "eps": "EPS", "debt_to_equity": "Debt/Equity",
        }
        for metric, stats in summary.items():
            lbl = label_map.get(metric, metric)
            summary_rows.append({"Metric": lbl, "Stat": "Peer Median",
                                  "Value": stats.get("median"), "N": stats.get("count", 0)})
            summary_rows.append({"Metric": lbl, "Stat": "Peer Mean",
                                  "Value": stats.get("mean"), "N": stats.get("count", 0)})
        pd.DataFrame(summary_rows).to_excel(writer, index=False, sheet_name="Peer Summary")

    out.seek(0)
    return StreamingResponse(
        out,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=equity_comps.xlsx"},
    )


@router.post("/admin/refresh-peer-stats")
async def trigger_peer_stats_refresh(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    background_tasks.add_task(refresh_peer_statistics, db)
    return {"status": "queued"}


def _build_export_df(companies: List[dict], summary: dict) -> pd.DataFrame:
    cols = {
        "ticker": "Ticker", "name": "Company", "sector": "Sector", "industry": "Industry",
        "price": "Price", "day_change_pct": "1D Chg %",
        "market_cap": "Market Cap", "enterprise_value": "EV",
        "pe_ratio": "P/E", "ev_ebitda": "EV/EBITDA", "ev_sales": "EV/Sales",
        "price_to_book": "P/Book",
        "discount_vs_median_pe_ratio":       "Disc vs Median (P/E) %",
        "discount_vs_median_ev_ebitda":      "Disc vs Median (EV/EBITDA) %",
        "discount_vs_median_ev_sales":       "Disc vs Median (EV/Sales) %",
        "discount_vs_median_price_to_book":  "Disc vs Median (P/Book) %",
        "roe": "ROE %", "ebitda_margin": "EBITDA Margin %",
        "gross_margin": "Gross Margin %", "net_debt_ebitda": "Net Debt/EBITDA",
        "fcf_yield": "FCF Yield %", "revenue_growth": "Revenue Growth %",
        "dividend_yield": "Dividend Yield %",
        "eps": "EPS", "debt_to_equity": "Debt/Equity",
        "revenue": "Revenue", "ebitda": "EBITDA",
        "net_income": "Net Income", "total_debt": "Total Debt", "cash": "Cash",
        "period_end_date": "Period End", "filing_form": "Filing",
    }
    df = pd.DataFrame(companies)

    # Append Peer Median and Peer Mean rows
    median_row: dict = {"ticker": "MEDIAN", "name": "Peer Median"}
    mean_row:   dict = {"ticker": "MEAN",   "name": "Peer Mean"}
    for m, stats in summary.items():
        median_row[m] = stats.get("median")
        mean_row[m]   = stats.get("mean")
    df = pd.concat([df, pd.DataFrame([median_row, mean_row])], ignore_index=True)

    available = [c for c in cols if c in df.columns]
    return df[available].rename(columns=cols)
