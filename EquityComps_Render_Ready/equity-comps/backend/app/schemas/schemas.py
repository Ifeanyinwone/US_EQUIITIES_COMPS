from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class CompanyRow(BaseModel):
    ticker: str
    name: str
    sector: Optional[str]
    industry: Optional[str]
    in_sp500: bool = False
    in_nasdaq100: bool = False

    # Market data
    price: Optional[float]
    day_change_pct: Optional[float]
    market_cap: Optional[int]
    volume: Optional[int]
    week_52_high: Optional[float]
    week_52_low: Optional[float]

    # Financial statement highlights
    revenue: Optional[int]
    ebitda: Optional[int]
    net_income: Optional[int]
    eps_diluted: Optional[float]
    total_debt: Optional[int]
    cash: Optional[int]
    net_debt: Optional[int]
    shareholders_equity: Optional[int]

    # Calculated multiples
    enterprise_value: Optional[int]
    pe_ratio: Optional[float]
    ev_ebitda: Optional[float]
    ev_sales: Optional[float]
    price_to_book: Optional[float]
    roe: Optional[float]
    ebitda_margin: Optional[float]
    net_debt_ebitda: Optional[float]

    # Metadata
    price_refreshed_at: Optional[str]
    financials_refreshed_at: Optional[str]

    class Config:
        from_attributes = True


class SummaryStats(BaseModel):
    metric: str
    mean: Optional[float]
    median: Optional[float]
    count: int


class CompsResponse(BaseModel):
    companies: List[CompanyRow]
    summary: dict  # mean/median for each metric
    total_count: int
    filters_applied: dict


class PeerStatsResponse(BaseModel):
    sector: str
    universe: str
    median_pe: Optional[float]
    median_ev_ebitda: Optional[float]
    median_ev_sales: Optional[float]
    median_price_to_book: Optional[float]
    mean_pe: Optional[float]
    mean_ev_ebitda: Optional[float]
    mean_ev_sales: Optional[float]
    mean_price_to_book: Optional[float]
    company_count: Optional[int]


class FilterOptions(BaseModel):
    sectors: List[str]
    industries: List[str]
    universes: List[str] = ["ALL", "SP500", "NASDAQ100"]


class RefreshStatusResponse(BaseModel):
    market_price_job: str
    financial_job: str
    last_price_refresh: Optional[str]
    company_count: int
