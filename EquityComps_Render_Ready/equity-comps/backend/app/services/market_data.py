"""Yahoo Finance market-data service.

Integrity rules:
- A price is accepted only if it is finite and > 0.
- Scheduled refreshes use genuine multi-ticker Yahoo downloads.
- Intraday prices are preferred during the regular US session.
- Outside the session, the latest completed daily close is used.
- Previous close is always a different completed trading day.
- A missing Yahoo price is returned as missing; existing DB values are never
  overwritten by a fabricated zero or stale fallback.
"""
from __future__ import annotations

import asyncio
import logging
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Dict, List, Optional, Set
from zoneinfo import ZoneInfo

import pandas as pd
try:
    import yfinance as yf
except ImportError:  # Allows non-market-data unit tests to import the module.
    yf = None

from app.core.config import settings

logger = logging.getLogger(__name__)

NY_TZ = ZoneInfo("America/New_York")

_rl_lock = threading.Lock()
_cooldown_until = 0.0

_cache: Dict[str, tuple[float, Dict[str, Any]]] = {}
_cache_lock = threading.Lock()
CACHE_TTL_SECONDS = 30.0

_inflight: Set[str] = set()
_inflight_lock = threading.Lock()

_executor = ThreadPoolExecutor(
    max_workers=max(1, settings.YF_CONCURRENCY),
    thread_name_prefix="yf_worker",
)


def _valid_number(value: Any) -> Optional[float]:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _valid_price(value: Any) -> Optional[float]:
    value = _valid_number(value)
    return value if value is not None and value > 0 else None


def _valid_int(value: Any) -> Optional[int]:
    value = _valid_number(value)
    return int(value) if value is not None else None


def _first_valid_price(*values: Any) -> Optional[float]:
    for value in values:
        price = _valid_price(value)
        if price is not None:
            return price
    return None


def _is_rate_limit(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(x in msg for x in ("429", "too many requests", "rate limit"))


def _is_network_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(
        x in msg
        for x in (
            "403", "forbidden", "connection", "timeout", "expecting value",
            "json", "nodataerror", "currenttradingperiod",
            "unknowntimezone", "no data found",
        )
    )


def _set_cooldown(extra: float = 0.0) -> None:
    global _cooldown_until
    wait = max(0.0, settings.YF_COOLDOWN_PERIOD + extra)
    with _rl_lock:
        _cooldown_until = max(_cooldown_until, time.time() + wait)
    logger.warning("Yahoo cooldown set for %.0fs", wait)


def _wait_cooldown() -> None:
    while True:
        with _rl_lock:
            remaining = _cooldown_until - time.time()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 5.0))


def _cache_get(ticker: str) -> Optional[Dict[str, Any]]:
    now = time.monotonic()
    with _cache_lock:
        item = _cache.get(ticker)
        if not item:
            return None
        created, data = item
        if now - created > CACHE_TTL_SECONDS:
            _cache.pop(ticker, None)
            return None
        return dict(data)


def _cache_put(ticker: str, data: Dict[str, Any]) -> None:
    if data.get("price") is None:
        return
    with _cache_lock:
        _cache[ticker] = (time.monotonic(), dict(data))


def _require_yfinance() -> None:
    if yf is None:
        raise RuntimeError(
            "yfinance is not installed. Run: pip install -r requirements.txt"
        )


def _download_sync(
    tickers: List[str],
    period: str,
    interval: str,
) -> pd.DataFrame:
    _require_yfinance()
    _wait_cooldown()
    return yf.download(
        tickers=tickers,
        period=period,
        interval=interval,
        auto_adjust=False,
        progress=False,
        threads=False,
        group_by="column",
        prepost=False,
        actions=False,
    )


def _extract_series(
    frame: Optional[pd.DataFrame],
    field: str,
    ticker: str,
) -> Optional[pd.Series]:
    """Extract exactly one ticker/field without guessing across columns."""
    if frame is None or frame.empty:
        return None

    ticker = ticker.upper().strip()
    field = field.strip()

    try:
        if isinstance(frame.columns, pd.MultiIndex):
            direct = []
            for col in frame.columns:
                if len(col) != 2:
                    continue
                a, b = str(col[0]), str(col[1])
                if a == field and b.upper() == ticker:
                    direct.append(col)
                elif a.upper() == ticker and b == field:
                    direct.append(col)

            if len(direct) != 1:
                if len(direct) > 1:
                    logger.warning(
                        "[%s] ambiguous Yahoo column mapping for %s; rejecting",
                        ticker, field,
                    )
                return None
            return frame[direct[0]]

        if field in frame.columns:
            return frame[field]

        return None
    except Exception as exc:
        logger.debug("[%s] column extraction failed: %s", ticker, exc)
        return None


def _series_rows(series: Optional[pd.Series]) -> List[tuple[pd.Timestamp, float]]:
    if series is None:
        return []
    rows: List[tuple[pd.Timestamp, float]] = []
    for idx, value in series.dropna().items():
        numeric = _valid_price(value)
        if numeric is None:
            continue
        try:
            ts = pd.Timestamp(idx)
        except Exception:
            continue
        rows.append((ts, numeric))
    rows.sort(key=lambda x: x[0])
    return rows


def _timestamp_ny(ts: pd.Timestamp) -> pd.Timestamp:
    if ts.tzinfo is None:
        return ts.tz_localize(NY_TZ)
    return ts.tz_convert(NY_TZ)


def _latest_row(series: Optional[pd.Series]) -> Optional[tuple[pd.Timestamp, float]]:
    rows = _series_rows(series)
    return rows[-1] if rows else None


def _is_regular_market_hours(now: Optional[datetime] = None) -> bool:
    now = now or datetime.now(NY_TZ)
    if now.weekday() >= 5:
        return False
    t = now.time()
    return datetime.strptime("09:30", "%H:%M").time() <= t <= datetime.strptime("16:00", "%H:%M").time()


def _previous_completed_daily_close(
    daily_close: Optional[pd.Series],
    price_timestamp: Optional[pd.Timestamp],
) -> Optional[float]:
    rows = _series_rows(daily_close)
    if not rows:
        return None

    if price_timestamp is None:
        return rows[-2][1] if len(rows) >= 2 else None

    price_day = _timestamp_ny(price_timestamp).date()
    prior = [
        value
        for ts, value in rows
        if _timestamp_ny(ts).date() < price_day
    ]
    return prior[-1] if prior else None


def _day_change(price: Optional[float], prev_close: Optional[float]) -> Optional[float]:
    price = _valid_price(price)
    prev_close = _valid_price(prev_close)
    if price is None or prev_close is None:
        return None
    return round(((price - prev_close) / prev_close) * 100.0, 4)


def _fetch_info_sync(ticker: str) -> Dict[str, Any]:
    _require_yfinance()
    _wait_cooldown()
    info = yf.Ticker(ticker).info or {}
    if not info:
        raise ValueError(f"empty Yahoo info for {ticker}")

    price = _first_valid_price(
        info.get("currentPrice"),
        info.get("regularMarketPrice"),
    )
    if price is None:
        raise ValueError(f"Yahoo info has no valid price for {ticker}")

    prev = _valid_price(info.get("previousClose"))
    shares = _valid_int(info.get("sharesOutstanding"))
    market_cap = _valid_int(info.get("marketCap"))

    if market_cap is None and shares is not None:
        market_cap = int(price * shares)

    raw_dividend = _valid_number(info.get("dividendYield"))
    dividend_yield = raw_dividend * 100.0 if raw_dividend is not None else None

    return {
        "price": price,
        "prev_close": prev,
        "day_change_pct": _day_change(price, prev),
        "market_cap": market_cap,
        "shares_outstanding": shares,
        "week_52_high": _valid_price(info.get("fiftyTwoWeekHigh")),
        "week_52_low": _valid_price(info.get("fiftyTwoWeekLow")),
        "volume": _valid_int(info.get("volume")),
        "avg_volume_30d": _valid_int(info.get("averageVolume")),
        "dividend_yield": dividend_yield,
        "name": info.get("shortName") or info.get("longName"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "exchange": info.get("exchange"),
        "currency": info.get("currency") or "USD",
        "_source": "yahoo_info",
        "_price_type": "quote",
        "_price_timestamp": None,
        "_has_price": True,
    }


def _fetch_fast_info_sync(ticker: str) -> Dict[str, Any]:
    _require_yfinance()
    _wait_cooldown()
    fi = yf.Ticker(ticker).fast_info
    price = _valid_price(getattr(fi, "last_price", None))
    if price is None:
        raise ValueError(f"Yahoo fast_info has no valid price for {ticker}")

    prev = _valid_price(getattr(fi, "previous_close", None))
    shares = _valid_int(getattr(fi, "shares", None))
    market_cap = _valid_int(getattr(fi, "market_cap", None))
    if market_cap is None and shares is not None:
        market_cap = int(price * shares)

    return {
        "price": price,
        "prev_close": prev,
        "day_change_pct": _day_change(price, prev),
        "market_cap": market_cap,
        "shares_outstanding": shares,
        "week_52_high": _valid_price(getattr(fi, "year_high", None)),
        "week_52_low": _valid_price(getattr(fi, "year_low", None)),
        "_source": "yahoo_fast_info",
        "_price_type": "quote",
        "_price_timestamp": None,
        "_has_price": True,
    }


async def fetch_market_data(ticker: str) -> Dict[str, Any]:
    ticker = ticker.upper().strip()
    cached = _cache_get(ticker)
    if cached is not None:
        return cached

    loop = asyncio.get_running_loop()
    result: Dict[str, Any] = {}

    with _inflight_lock:
        _inflight.add(ticker)

    try:
        for attempt in range(settings.YF_MAX_RETRIES):
            try:
                result = await loop.run_in_executor(
                    _executor, _fetch_info_sync, ticker
                )
                _cache_put(ticker, result)
                return result
            except Exception as exc:
                if _is_rate_limit(exc):
                    _set_cooldown(10.0 * (2 ** attempt))
                elif _is_network_error(exc):
                    logger.debug("[%s] Yahoo info unavailable: %s", ticker, exc)
                else:
                    logger.debug("[%s] Yahoo info failed: %s", ticker, exc)
                if attempt < settings.YF_MAX_RETRIES - 1:
                    await asyncio.sleep(settings.YF_REQUEST_DELAY * (attempt + 1))

        for attempt in range(settings.YF_MAX_RETRIES):
            try:
                result = await loop.run_in_executor(
                    _executor, _fetch_fast_info_sync, ticker
                )
                _cache_put(ticker, result)
                return result
            except Exception as exc:
                if _is_rate_limit(exc):
                    _set_cooldown(15.0 * (2 ** attempt))
                logger.debug("[%s] Yahoo fast_info failed: %s", ticker, exc)
                if attempt < settings.YF_MAX_RETRIES - 1:
                    await asyncio.sleep(settings.YF_REQUEST_DELAY * (attempt + 1))

        return {
            "_source": "none",
            "_has_price": False,
            "name": ticker,
            "currency": "USD",
        }
    finally:
        with _inflight_lock:
            _inflight.discard(ticker)


async def fetch_price_only(ticker: str) -> Dict[str, Any]:
    """Single-ticker price fallback. Scheduled refreshes use batch downloads."""
    ticker = ticker.upper().strip()
    loop = asyncio.get_running_loop()
    for attempt in range(settings.YF_MAX_RETRIES):
        try:
            return await loop.run_in_executor(
                _executor, _fetch_fast_info_sync, ticker
            )
        except Exception as exc:
            if _is_rate_limit(exc):
                _set_cooldown(15.0 * (2 ** attempt))
            if attempt < settings.YF_MAX_RETRIES - 1:
                await asyncio.sleep(settings.YF_REQUEST_DELAY * (attempt + 1))
    return {}


def _download_batch_sync(tickers: List[str]) -> Dict[str, Dict[str, Any]]:
    intraday = _download_sync(tickers, "1d", "1m")
    daily = _download_sync(tickers, "5d", "1d")

    results: Dict[str, Dict[str, Any]] = {}
    use_intraday = _is_regular_market_hours()

    for ticker in tickers:
        try:
            intraday_series = _extract_series(intraday, "Close", ticker)
            daily_series = _extract_series(daily, "Close", ticker)

            intraday_row = _latest_row(intraday_series)
            daily_rows = _series_rows(daily_series)

            if use_intraday:
                # During the live session, a daily close is stale. If Yahoo
                # does not return a valid intraday bar, skip this ticker rather
                # than writing yesterday's close as today's price.
                if intraday_row is None:
                    logger.warning(
                        "[%s] no valid intraday price during market hours; "
                        "ticker skipped",
                        ticker,
                    )
                    continue
                ts, price = intraday_row
                prev_close = _previous_completed_daily_close(
                    daily_series, ts
                )
                price_type = "intraday"
                source = "yahoo_download_1m"
            else:
                if not daily_rows:
                    logger.warning(
                        "[%s] Yahoo returned no valid daily close",
                        ticker,
                    )
                    continue
                ts, price = daily_rows[-1]
                prev_close = daily_rows[-2][1] if len(daily_rows) >= 2 else None
                price_type = "daily_close"
                source = "yahoo_download_1d"

            if _valid_price(price) is None:
                continue

            results[ticker] = {
                "price": price,
                "prev_close": prev_close,
                "day_change_pct": _day_change(price, prev_close),
                "_price_timestamp": ts.isoformat(),
                "_price_type": price_type,
                "_source": source,
                "_has_price": True,
            }
        except Exception as exc:
            logger.warning("[%s] batch price extraction failed: %s", ticker, exc)

    return results


async def fetch_batch_prices(
    tickers: List[str],
    batch_size: int = 50,
) -> Dict[str, Dict[str, Any]]:
    """Fetch prices in genuine multi-ticker Yahoo batches."""
    clean: List[str] = []
    seen: Set[str] = set()

    for raw in tickers:
        ticker = (raw or "").upper().strip()
        if ticker and ticker not in seen:
            seen.add(ticker)
            clean.append(ticker)

    results: Dict[str, Dict[str, Any]] = {}
    if not clean:
        return results

    loop = asyncio.get_running_loop()

    for start in range(0, len(clean), batch_size):
        batch = clean[start:start + batch_size]
        batch_no = start // batch_size + 1
        total = (len(clean) + batch_size - 1) // batch_size

        for attempt in range(settings.YF_MAX_RETRIES):
            try:
                logger.info(
                    "Yahoo price batch %d/%d: %d tickers",
                    batch_no, total, len(batch),
                )
                batch_result = await loop.run_in_executor(
                    _executor, _download_batch_sync, batch
                )
                results.update(batch_result)
                logger.info(
                    "Yahoo price batch %d/%d complete: %d/%d valid prices",
                    batch_no, total, len(batch_result), len(batch),
                )
                break
            except Exception as exc:
                if _is_rate_limit(exc):
                    _set_cooldown(20.0 * (2 ** attempt))
                logger.warning(
                    "Yahoo price batch %d/%d failed on attempt %d: %s",
                    batch_no, total, attempt + 1, exc,
                )
                if attempt < settings.YF_MAX_RETRIES - 1:
                    await asyncio.sleep(settings.YF_REQUEST_DELAY * (attempt + 1))

        if start + batch_size < len(clean):
            await asyncio.sleep(settings.YF_BATCH_DELAY)

    logger.info(
        "Yahoo batch price fetch complete: %d/%d valid prices",
        len(results), len(clean),
    )
    return results


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()
