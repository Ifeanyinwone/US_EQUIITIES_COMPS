"""Pure valuation calculations with strict missing-data handling."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

import numpy as np

BOUNDS: Dict[str, tuple[float, float]] = {
    "pe_ratio": (0.1, 500.0),
    "ev_ebitda": (0.1, 200.0),
    "ev_sales": (0.0, 100.0),
    "price_to_book": (0.0, 200.0),
    "roe": (-500.0, 500.0),
    "ebitda_margin": (-200.0, 100.0),
    "net_debt_ebitda": (-50.0, 50.0),
    "fcf_yield": (-100.0, 100.0),
    "revenue_growth": (-100.0, 500.0),
    "gross_margin": (-100.0, 100.0),
    "dividend_yield": (0.0, 30.0),
    "eps": (-1000.0, 1000.0),
    "debt_to_equity": (-50.0, 50.0),
}


def _finite(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _safe_divide(num: Optional[float], den: Optional[float]) -> Optional[float]:
    num = _finite(num)
    den = _finite(den)
    if num is None or den is None or den == 0:
        return None
    result = num / den
    return result if math.isfinite(result) else None


def _pct(value: Optional[float]) -> Optional[float]:
    value = _finite(value)
    return value * 100.0 if value is not None else None


def _bound(value: Optional[float], metric: str) -> Optional[float]:
    value = _finite(value)
    if value is None:
        return None
    lo, hi = BOUNDS.get(metric, (-1e12, 1e12))
    return value if lo <= value <= hi else None


def calculate_enterprise_value(
    market_cap: Optional[int],
    total_debt: Optional[float],
    cash: Optional[float],
) -> Optional[int]:
    """EV = Market Cap + Debt - Cash.

    Debt and cash are required. Missing values are not silently treated as zero.
    """
    if market_cap is None or market_cap <= 0:
        return None
    if total_debt is None or cash is None:
        return None

    ev = float(market_cap) + float(total_debt) - float(cash)
    if not math.isfinite(ev) or ev <= 0:
        return None
    return int(ev)


def calculate_market_cap_fallback(
    price: Optional[float],
    shares_outstanding: Optional[int],
) -> Optional[int]:
    if price is None or shares_outstanding is None:
        return None
    if price <= 0 or shares_outstanding <= 0:
        return None
    value = float(price) * int(shares_outstanding)
    if not math.isfinite(value) or value <= 0:
        return None
    return int(value)


def calculate_pe(price: Optional[float], eps: Optional[float]) -> Optional[float]:
    if price is None or price <= 0 or eps is None or eps <= 0:
        return None
    return _bound(_safe_divide(price, eps), "pe_ratio")


def calculate_ev_ebitda(ev: Optional[int], ebitda: Optional[float]) -> Optional[float]:
    if ev is None or ev <= 0 or ebitda is None or ebitda <= 0:
        return None
    return _bound(_safe_divide(ev, ebitda), "ev_ebitda")


def calculate_ev_sales(ev: Optional[int], revenue: Optional[float]) -> Optional[float]:
    if ev is None or ev <= 0 or revenue is None or revenue <= 0:
        return None
    return _bound(_safe_divide(ev, revenue), "ev_sales")


def calculate_price_to_book(
    market_cap: Optional[int],
    equity: Optional[float],
) -> Optional[float]:
    if market_cap is None or market_cap <= 0 or equity is None or equity <= 0:
        return None
    return _bound(_safe_divide(market_cap, equity), "price_to_book")


def calculate_roe(net_income: Optional[float], equity: Optional[float]) -> Optional[float]:
    if net_income is None or equity is None or equity <= 0:
        return None
    return _bound(_pct(_safe_divide(net_income, equity)), "roe")


def calculate_ebitda_margin(ebitda: Optional[float], revenue: Optional[float]) -> Optional[float]:
    if ebitda is None or revenue is None or revenue <= 0:
        return None
    return _bound(_pct(_safe_divide(ebitda, revenue)), "ebitda_margin")


def calculate_gross_margin(gross_profit: Optional[float], revenue: Optional[float]) -> Optional[float]:
    if gross_profit is None or revenue is None or revenue <= 0:
        return None
    return _bound(_pct(_safe_divide(gross_profit, revenue)), "gross_margin")


def calculate_net_debt_ebitda(
    net_debt: Optional[float],
    ebitda: Optional[float],
) -> Optional[float]:
    if net_debt is None or ebitda is None or ebitda <= 0:
        return None
    return _bound(_safe_divide(net_debt, ebitda), "net_debt_ebitda")


def calculate_fcf_yield(
    fcf: Optional[float],
    market_cap: Optional[int],
) -> Optional[float]:
    if fcf is None or market_cap is None or market_cap <= 0:
        return None
    return _bound(_pct(_safe_divide(fcf, market_cap)), "fcf_yield")


def calculate_revenue_growth(
    revenue: Optional[float],
    revenue_prior: Optional[float],
) -> Optional[float]:
    if revenue is None or revenue_prior is None or revenue_prior <= 0:
        return None
    return _bound(
        _pct(_safe_divide(revenue - revenue_prior, revenue_prior)),
        "revenue_growth",
    )


def calculate_eps(
    net_income: Optional[float],
    shares_outstanding: Optional[int],
) -> Optional[float]:
    if net_income is None or shares_outstanding is None or shares_outstanding <= 0:
        return None
    return _bound(
        _safe_divide(net_income, shares_outstanding),
        "eps",
    )


def calculate_debt_to_equity(
    total_debt: Optional[float],
    shareholders_equity: Optional[float],
) -> Optional[float]:
    if total_debt is None or shareholders_equity is None or shareholders_equity <= 0:
        return None
    return _bound(
        _safe_divide(total_debt, shareholders_equity),
        "debt_to_equity",
    )


def calculate_discount_vs_median(
    value: Optional[float],
    peer_median: Optional[float],
) -> Optional[float]:
    if value is None or peer_median is None or peer_median == 0:
        return None
    result = ((float(value) - float(peer_median)) / float(peer_median)) * 100.0
    return result if math.isfinite(result) else None


def calculate_all_multiples(
    price: Optional[float],
    market_cap: Optional[int],
    revenue: Optional[float],
    revenue_prior: Optional[float],
    ebitda: Optional[float],
    net_income: Optional[float],
    eps_diluted: Optional[float],
    total_debt: Optional[float],
    cash: Optional[float],
    shareholders_equity: Optional[float],
    gross_profit: Optional[float] = None,
    free_cash_flow: Optional[float] = None,
    dividend_yield: Optional[float] = None,
    shares_outstanding: Optional[int] = None,
) -> Dict[str, Any]:
    effective_market_cap = market_cap
    if effective_market_cap is None:
        effective_market_cap = calculate_market_cap_fallback(
            price, shares_outstanding
        )

    ev = calculate_enterprise_value(
        effective_market_cap,
        total_debt,
        cash,
    )

    net_debt = None
    if total_debt is not None and cash is not None:
        net_debt = float(total_debt) - float(cash)

    pe_eps = eps_diluted
    if pe_eps is None:
        pe_eps = calculate_eps(net_income, shares_outstanding)

    return {
        "enterprise_value": ev,
        "pe_ratio": calculate_pe(price, pe_eps),
        "ev_ebitda": calculate_ev_ebitda(ev, ebitda),
        "ev_sales": calculate_ev_sales(ev, revenue),
        "price_to_book": calculate_price_to_book(
            effective_market_cap, shareholders_equity
        ),
        "roe": calculate_roe(net_income, shareholders_equity),
        "ebitda_margin": calculate_ebitda_margin(ebitda, revenue),
        "gross_margin": calculate_gross_margin(gross_profit, revenue),
        "net_debt_ebitda": calculate_net_debt_ebitda(net_debt, ebitda),
        "fcf_yield": calculate_fcf_yield(
            free_cash_flow, effective_market_cap
        ),
        "revenue_growth": calculate_revenue_growth(
            revenue, revenue_prior
        ),
        "dividend_yield": _bound(dividend_yield, "dividend_yield"),
        "eps": calculate_eps(net_income, shares_outstanding),
        "debt_to_equity": calculate_debt_to_equity(
            total_debt, shareholders_equity
        ),
    }


def compute_peer_stats(values: List[Optional[float]]) -> Dict[str, Any]:
    clean: List[float] = []
    for value in values:
        numeric = _finite(value)
        if numeric is not None:
            clean.append(numeric)

    if not clean:
        return {"mean": None, "median": None, "count": 0}

    arr = np.asarray(clean, dtype=float)
    return {
        "mean": float(np.mean(arr)),
        "median": float(np.median(arr)),
        "count": len(clean),
    }
