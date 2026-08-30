import math
import pandas as pd
import pytest

from app.services.calculations import (
    calculate_all_multiples,
    calculate_debt_to_equity,
    calculate_eps,
    calculate_market_cap_fallback,
    compute_peer_stats,
)
from app.services.edgar_service import (
    _build_standalone_quarters,
    _select_flow,
)
from app.services.market_data import (
    _day_change,
    _extract_series,
    _valid_price,
)


def test_price_validation_rejects_bad_values():
    assert _valid_price(174.0) == 174.0
    assert _valid_price(0) is None
    assert _valid_price(-1) is None
    assert _valid_price(float("nan")) is None
    assert _valid_price(float("inf")) is None


def test_day_change_requires_independent_previous_close():
    assert _day_change(110, 100) == pytest.approx(10.0)
    assert _day_change(110, None) is None
    assert _day_change(110, 0) is None


def test_extract_series_handles_yahoo_multiindex():
    columns = pd.MultiIndex.from_tuples(
        [("Close", "AAPL"), ("Close", "MSFT")]
    )
    frame = pd.DataFrame(
        [[174.0, 500.0], [175.0, 501.0]],
        columns=columns,
    )
    aapl = _extract_series(frame, "Close", "AAPL")
    msft = _extract_series(frame, "Close", "MSFT")
    assert aapl.iloc[-1] == 175.0
    assert msft.iloc[-1] == 501.0


def test_extract_series_handles_reverse_multiindex():
    columns = pd.MultiIndex.from_tuples(
        [("AAPL", "Close"), ("MSFT", "Close")]
    )
    frame = pd.DataFrame(
        [[174.0, 500.0], [175.0, 501.0]],
        columns=columns,
    )
    assert _extract_series(frame, "Close", "AAPL").iloc[-1] == 175.0


def test_extract_series_rejects_ambiguous_mapping():
    columns = pd.MultiIndex.from_tuples(
        [("Close", "AAPL"), ("AAPL", "Close")]
    )
    frame = pd.DataFrame([[175.0, 176.0]], columns=columns)
    assert _extract_series(frame, "Close", "AAPL") is None


def test_standalone_quarter_construction():
    entries = [
        {"form": "10-Q", "start": "2025-01-01", "end": "2025-03-31", "val": 100, "filed": "2025-05-01"},
        {"form": "10-Q", "start": "2025-01-01", "end": "2025-06-30", "val": 230, "filed": "2025-08-01"},
        {"form": "10-Q", "start": "2025-01-01", "end": "2025-09-30", "val": 360, "filed": "2025-11-01"},
        {"form": "10-K", "start": "2025-01-01", "end": "2025-12-31", "val": 500, "filed": "2026-02-01"},
        {"form": "10-Q", "start": "2024-01-01", "end": "2024-03-31", "val": 90, "filed": "2024-05-01"},
        {"form": "10-Q", "start": "2024-01-01", "end": "2024-06-30", "val": 210, "filed": "2024-08-01"},
        {"form": "10-Q", "start": "2024-01-01", "end": "2024-09-30", "val": 330, "filed": "2024-11-01"},
        {"form": "10-K", "start": "2024-01-01", "end": "2024-12-31", "val": 450, "filed": "2025-02-01"},
    ]
    quarters = _build_standalone_quarters(entries)
    latest = {q["end"]: q["val"] for q in quarters}
    assert latest["2025-03-31"] == 100
    assert latest["2025-06-30"] == 130
    assert latest["2025-09-30"] == 130
    assert latest["2025-12-31"] == 140


def test_ttm_uses_standalone_quarters_not_cumulative_periods():
    entries = [
        {"form": "10-Q", "start": "2025-01-01", "end": "2025-03-31", "val": 100, "filed": "2025-05-01"},
        {"form": "10-Q", "start": "2025-01-01", "end": "2025-06-30", "val": 230, "filed": "2025-08-01"},
        {"form": "10-Q", "start": "2025-01-01", "end": "2025-09-30", "val": 360, "filed": "2025-11-01"},
        {"form": "10-K", "start": "2025-01-01", "end": "2025-12-31", "val": 500, "filed": "2026-02-01"},
    ]
    selection = _select_flow(entries)
    assert selection["best"] == pytest.approx(500.0)
    assert selection["basis"] == "TTM"


def test_annualized_h1_is_h1_times_two():
    entries = [
        {"form": "10-Q", "start": "2026-01-01", "end": "2026-06-30", "val": 600, "filed": "2026-08-01"},
    ]
    selection = _select_flow(entries)
    assert selection["best"] == pytest.approx(1200.0)
    assert selection["basis"] == "Annualized H1"


def test_missing_capex_does_not_create_fcf():
    # Calculation layer itself receives FCF directly; the EDGAR layer is
    # responsible for refusing to construct FCF when CapEx is missing.
    assert calculate_all_multiples(
        price=100,
        market_cap=1_000_000,
        revenue=500_000,
        revenue_prior=400_000,
        ebitda=100_000,
        net_income=50_000,
        eps_diluted=5,
        total_debt=100_000,
        cash=50_000,
        shareholders_equity=300_000,
        free_cash_flow=None,
        shares_outstanding=10_000,
    )["fcf_yield"] is None


def test_missing_debt_or_cash_does_not_create_ev():
    result = calculate_all_multiples(
        price=100,
        market_cap=1_000_000,
        revenue=500_000,
        revenue_prior=400_000,
        ebitda=100_000,
        net_income=50_000,
        eps_diluted=5,
        total_debt=None,
        cash=50_000,
        shareholders_equity=300_000,
        shares_outstanding=10_000,
    )
    assert result["enterprise_value"] is None
    assert result["ev_ebitda"] is None
    assert result["ev_sales"] is None


def test_market_cap_fallback():
    assert calculate_market_cap_fallback(175, 10_000_000) == 1_750_000_000
    assert calculate_market_cap_fallback(None, 10_000_000) is None


def test_eps():
    assert calculate_eps(100_000_000, 50_000_000) == pytest.approx(2.0)
    assert calculate_eps(100_000_000, 0) is None


def test_debt_to_equity():
    assert calculate_debt_to_equity(200, 300) == pytest.approx(2 / 3)
    assert calculate_debt_to_equity(200, 0) is None


def test_peer_stats_ignores_nan():
    stats = compute_peer_stats([10, 20, None, float("nan")])
    assert stats["count"] == 2
    assert stats["median"] == 15
    assert math.isfinite(stats["mean"])
