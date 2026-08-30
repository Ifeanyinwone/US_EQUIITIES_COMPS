"""SEC EDGAR XBRL financial-data service.

The service uses the SEC Company Facts API and treats XBRL facts as
period-specific data. Flow items are converted to standalone quarters before
TTM calculations; balance-sheet items remain point-in-time.

Hierarchy for flow metrics:
1. TTM from four standalone quarters
2. Annualized latest interim period (Q1/H1/9M)
3. Latest reported annual
4. Latest reported interim

No missing debt/cash/capex value is silently converted to zero.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

EDGAR_BASE = "https://data.sec.gov"
HEADERS = {
    "User-Agent": "EquityComps/2.0 contact@equitycomps.example.com",
    "Accept-Encoding": "gzip, deflate",
}

INCOME_CONCEPTS = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "SalesRevenueGoodsNet",
    ],
    "gross_profit": ["GrossProfit"],
    "ebit": [
        "OperatingIncomeLoss",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
    ],
    "net_income": [
        "NetIncomeLoss",
        "NetIncomeLossAvailableToCommonStockholdersBasic",
        "ProfitLoss",
    ],
    "eps_diluted": [
        "EarningsPerShareDiluted",
        "IncomeLossFromContinuingOperationsPerDilutedShare",
    ],
    "depreciation_amortization": [
        "DepreciationDepletionAndAmortization",
        "DepreciationAndAmortization",
        "Depreciation",
    ],
    "cfo": [
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ],
    "capex": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsForCapitalImprovements",
        "PaymentsToAcquireProductiveAssets",
    ],
}

BALANCE_CONCEPTS = {
    "total_assets": ["Assets"],
    "cash": [
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ],
    "current_debt": [
        "DebtCurrent",
        "LongTermDebtCurrent",
        "ShortTermBorrowings",
        "CommercialPaper",
        "NotesPayableCurrent",
    ],
    "noncurrent_debt": [
        "LongTermDebtNoncurrent",
        "LongTermDebt",
        "LongTermNotesPayable",
    ],
    "shareholders_equity": [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ],
    "shares_outstanding": [
        "CommonStockSharesOutstanding",
    ],
}



def _parse_filing_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _entry_value(entry: Optional[Dict[str, Any]]) -> Optional[float]:
    if not entry or entry.get("val") is None:
        return None
    try:
        value = float(entry["val"])
    except (TypeError, ValueError):
        return None
    return value


def _duration_days(entry: Dict[str, Any]) -> Optional[int]:
    start, end = entry.get("start"), entry.get("end")
    if not start or not end:
        return None
    try:
        return (datetime.fromisoformat(end) - datetime.fromisoformat(start)).days
    except ValueError:
        return None


def _classify_duration(entry: Dict[str, Any]) -> Optional[str]:
    days = _duration_days(entry)
    if days is None:
        return None
    if 70 <= days <= 110:
        return "3M"
    if 160 <= days <= 210:
        return "6M"
    if 250 <= days <= 300:
        return "9M"
    if 330 <= days <= 390:
        return "FY"
    return None


def _unit_entries(concept: Dict[str, Any]) -> List[Dict[str, Any]]:
    units = concept.get("units", {})
    preferred = (
        "USD",
        "USD/shares",
        "USD-per-shares",
        "shares",
        "pure",
    )
    for unit in preferred:
        entries = units.get(unit)
        if entries:
            return list(entries)

    # Last resort: accept exactly one unit bucket rather than guessing among
    # several incompatible units.
    if len(units) == 1:
        entries = next(iter(units.values()))
        if entries:
            return list(entries)
    return []


def _all_filings(
    facts: Dict[str, Any],
    taxonomy: str,
    concepts: List[str],
) -> List[Dict[str, Any]]:
    """Use the first concept with the strongest usable filing coverage."""
    taxonomy_facts = facts.get("facts", {}).get(taxonomy, {})
    candidates: List[List[Dict[str, Any]]] = []

    for concept in concepts:
        data = taxonomy_facts.get(concept)
        if not data:
            continue
        entries = [
            e for e in _unit_entries(data)
            if e.get("val") is not None and e.get("end")
        ]
        if entries:
            candidates.append(entries)

    if not candidates:
        return []

    # Prefer the concept with the most complete history. This avoids selecting
    # a sparse alternative concept merely because it appears first.
    candidates.sort(key=len, reverse=True)
    return candidates[0]


def _latest_by_end(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for entry in entries:
        grouped.setdefault(entry["end"], []).append(entry)

    chosen: List[Dict[str, Any]] = []
    for end, group in grouped.items():
        non_amended = [
            e for e in group if not str(e.get("form", "")).endswith("/A")
        ]
        pool = non_amended or group
        chosen.append(max(pool, key=lambda e: e.get("filed", "")))

    return sorted(chosen, key=lambda e: e["end"])


def _flow_periods(entries: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    periods = {"3M": [], "6M": [], "9M": [], "FY": []}
    for entry in entries:
        if entry.get("form") not in ("10-Q", "10-Q/A", "10-K", "10-K/A", "20-F", "20-F/A"):
            continue
        duration = _classify_duration(entry)
        if duration:
            periods[duration].append(entry)
    return {
        key: _latest_by_end(value)
        for key, value in periods.items()
    }


def _match_prior_end(
    entries: List[Dict[str, Any]],
    before_end: str,
) -> Optional[Dict[str, Any]]:
    candidates = [e for e in entries if e.get("end", "") < before_end]
    return max(candidates, key=lambda e: e["end"]) if candidates else None


def _build_standalone_quarters(
    entries: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Convert cumulative 6M/9M/FY facts into standalone quarters."""
    periods = _flow_periods(entries)
    quarters: List[Dict[str, Any]] = []

    for entry in periods["3M"]:
        quarters.append({
            "end": entry["end"],
            "val": _entry_value(entry),
            "filed": entry.get("filed"),
            "source": "Q1_3M",
        })

    for entry in periods["6M"]:
        prior = _match_prior_end(periods["3M"], entry["end"])
        value, prior_value = _entry_value(entry), _entry_value(prior)
        if value is not None and prior_value is not None:
            quarters.append({
                "end": entry["end"],
                "val": value - prior_value,
                "filed": entry.get("filed"),
                "source": "Q2_6M_MINUS_Q1",
            })

    for entry in periods["9M"]:
        prior = _match_prior_end(periods["6M"], entry["end"])
        value, prior_value = _entry_value(entry), _entry_value(prior)
        if value is not None and prior_value is not None:
            quarters.append({
                "end": entry["end"],
                "val": value - prior_value,
                "filed": entry.get("filed"),
                "source": "Q3_9M_MINUS_H1",
            })

    for entry in periods["FY"]:
        prior = _match_prior_end(periods["9M"], entry["end"])
        value, prior_value = _entry_value(entry), _entry_value(prior)
        if value is not None and prior_value is not None:
            quarters.append({
                "end": entry["end"],
                "val": value - prior_value,
                "filed": entry.get("filed"),
                "source": "Q4_FY_MINUS_9M",
            })

    # Same period end can arise from multiple filing routes. Keep the latest
    # constructed fact for that end date.
    by_end: Dict[str, Dict[str, Any]] = {}
    for q in quarters:
        if q["val"] is None:
            continue
        existing = by_end.get(q["end"])
        if existing is None or (q.get("filed") or "") > (existing.get("filed") or ""):
            by_end[q["end"]] = q

    return sorted(by_end.values(), key=lambda q: q["end"])


def _latest_four_quarters(entries: List[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
    quarters = _build_standalone_quarters(entries)
    if len(quarters) < 4:
        return None
    latest = quarters[-4:]
    if len({q["end"] for q in latest}) != 4:
        return None
    return latest


def _ttm(entries: List[Dict[str, Any]]) -> Optional[float]:
    quarters = _latest_four_quarters(entries)
    if not quarters:
        return None
    return float(sum(q["val"] for q in quarters))


def _prior_ttm(entries: List[Dict[str, Any]]) -> Optional[float]:
    quarters = _build_standalone_quarters(entries)
    if len(quarters) < 8:
        return None
    return float(sum(q["val"] for q in quarters[-8:-4]))


def _latest_interim(entries: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    periods = _flow_periods(entries)
    candidates = periods["9M"] + periods["6M"] + periods["3M"]
    return max(candidates, key=lambda e: (e.get("end", ""), e.get("filed", ""))) if candidates else None


def _prior_same_duration(
    entries: List[Dict[str, Any]],
    current: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    current_duration = _classify_duration(current)
    if current_duration is None:
        return None

    current_end = datetime.fromisoformat(current["end"])
    candidates = []
    for entry in entries:
        if _classify_duration(entry) != current_duration:
            continue
        try:
            end = datetime.fromisoformat(entry["end"])
        except ValueError:
            continue
        days = abs((current_end - end).days)
        if 300 <= days <= 400:
            candidates.append((days, entry))

    if not candidates:
        return None
    return min(candidates, key=lambda x: (x[0], x[1].get("filed", "")))[1]


def _annualized(value: Optional[float], duration: Optional[str]) -> Optional[float]:
    months = {"3M": 3, "6M": 6, "9M": 9}.get(duration)
    if value is None or months is None:
        return None
    return value * (12.0 / months)


def _latest_annual(entries: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    annual = [
        e for e in entries
        if e.get("form") in ("10-K", "10-K/A", "20-F", "20-F/A")
        and _classify_duration(e) == "FY"
    ]
    return max(annual, key=lambda e: (e.get("end", ""), e.get("filed", ""))) if annual else None


def _select_flow(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    ttm = _ttm(entries)
    prior_ttm = _prior_ttm(entries)
    interim = _latest_interim(entries)
    annual = _latest_annual(entries)

    if ttm is not None:
        return {
            "best": ttm,
            "ttm": ttm,
            "annualized": None,
            "prior": prior_ttm,
            "basis": "TTM",
            "interim_months": None,
            "reference_entry": None,
        }

    if interim is not None:
        duration = _classify_duration(interim)
        raw = _entry_value(interim)
        annualized = _annualized(raw, duration)
        prior = _prior_same_duration(entries, interim)
        prior_annualized = _annualized(
            _entry_value(prior), _classify_duration(prior) if prior else None
        )
        if annualized is not None:
            label = {
                "3M": "Annualized Q1",
                "6M": "Annualized H1",
                "9M": "Annualized 9M",
            }[duration]
            return {
                "best": annualized,
                "ttm": None,
                "annualized": annualized,
                "prior": prior_annualized,
                "basis": label,
                "interim_months": {"3M": 3, "6M": 6, "9M": 9}[duration],
                "reference_entry": interim,
            }

    if annual is not None:
        return {
            "best": _entry_value(annual),
            "ttm": None,
            "annualized": None,
            "prior": _entry_value(_previous_annual(entries, annual)),
            "basis": f"Annual FY{annual['end'][:4]}",
            "interim_months": None,
            "reference_entry": annual,
        }

    if interim is not None:
        return {
            "best": _entry_value(interim),
            "ttm": None,
            "annualized": None,
            "prior": _entry_value(_prior_same_duration(entries, interim)),
            "basis": "Reported Interim",
            "interim_months": None,
            "reference_entry": interim,
        }

    return {
        "best": None,
        "ttm": None,
        "annualized": None,
        "prior": None,
        "basis": "N/A",
        "interim_months": None,
        "reference_entry": None,
    }


def _previous_annual(
    entries: List[Dict[str, Any]],
    current: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    annual = [
        e for e in entries
        if e.get("form") in ("10-K", "10-K/A", "20-F", "20-F/A")
        and _classify_duration(e) == "FY"
        and e.get("end", "") < current.get("end", "")
    ]
    return max(annual, key=lambda e: (e.get("end", ""), e.get("filed", ""))) if annual else None


def _balance_entries(facts: Dict[str, Any], concepts: List[str]) -> List[Dict[str, Any]]:
    entries = _all_filings(facts, "us-gaap", concepts)
    return [
        e for e in entries
        if e.get("val") is not None
        and e.get("end")
        and not e.get("start")
    ]


def _latest_balance_date(facts: Dict[str, Any]) -> Optional[str]:
    assets = _balance_entries(facts, BALANCE_CONCEPTS["total_assets"])
    if assets:
        return max(e["end"] for e in assets)

    dates: List[str] = []
    for concepts in BALANCE_CONCEPTS.values():
        dates.extend(e["end"] for e in _balance_entries(facts, concepts))
    return max(dates) if dates else None


def _balance_at_date(
    facts: Dict[str, Any],
    concepts: List[str],
    as_of: Optional[str],
) -> Optional[float]:
    if not as_of:
        return None
    matches = [
        e for e in _balance_entries(facts, concepts)
        if e["end"] == as_of
    ]
    if not matches:
        return None
    chosen = max(matches, key=lambda e: e.get("filed", ""))
    return _entry_value(chosen)


def _debt_at_date(facts: Dict[str, Any], as_of: Optional[str]) -> Optional[float]:
    current = _balance_at_date(facts, BALANCE_CONCEPTS["current_debt"], as_of)
    noncurrent = _balance_at_date(facts, BALANCE_CONCEPTS["noncurrent_debt"], as_of)

    if current is not None and noncurrent is not None:
        return current + noncurrent

    # Missing one side is not assumed to be zero. If no current debt is
    # disclosed, a reported noncurrent debt figure is still a legitimate
    # debt figure, but it is explicitly incomplete.
    if current is None and noncurrent is not None:
        return noncurrent
    if noncurrent is None and current is not None:
        return current
    return None


async def get_cik_map() -> Dict[str, str]:
    from app.core.cik_map import STATIC_CIK_MAP

    live: Dict[str, str] = {}
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                "https://www.sec.gov/files/company_tickers.json",
                headers=HEADERS,
            )
            response.raise_for_status()
            data = response.json()
            live = {
                item["ticker"]: str(item["cik_str"]).zfill(10)
                for item in data.values()
            }
            logger.info("SEC live CIK map loaded: %d entries", len(live))
    except Exception as exc:
        logger.warning("SEC CIK map unavailable; using static fallback: %s", exc)

    merged = dict(STATIC_CIK_MAP)
    merged.update(live)
    return merged


async def fetch_company_facts(cik: str) -> Optional[Dict[str, Any]]:
    url = f"{EDGAR_BASE}/api/xbrl/companyfacts/CIK{str(cik).zfill(10)}.json"
    try:
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.get(url, headers=HEADERS)
            response.raise_for_status()
            return response.json()
    except Exception as exc:
        logger.warning("EDGAR facts failed for CIK %s: %s", cik, exc)
        return None


async def extract_financials(ticker: str, cik: str) -> Dict[str, Any]:
    facts = await fetch_company_facts(cik)
    if not facts:
        return {}

    result: Dict[str, Any] = {}
    selections: Dict[str, Dict[str, Any]] = {}

    for field in (
        "revenue",
        "gross_profit",
        "ebit",
        "net_income",
        "depreciation_amortization",
        "cfo",
        "capex",
    ):
        entries = _all_filings(facts, "us-gaap", INCOME_CONCEPTS[field])
        selection = _select_flow(entries)
        selections[field] = selection

        if selection["best"] is not None:
            result[field] = selection["best"]
        if selection["ttm"] is not None:
            result[f"ttm_{field}"] = selection["ttm"]
        if selection["annualized"] is not None:
            result[f"annualized_{field}"] = selection["annualized"]

    # EPS: sum four standalone quarterly EPS values for TTM. If TTM is not
    # available, do not pretend that cumulative EPS is a standalone quarter.
    eps_entries = _all_filings(
        facts, "us-gaap", INCOME_CONCEPTS["eps_diluted"]
    )
    eps_ttm = _ttm(eps_entries)
    eps_selection = _select_flow(eps_entries)

    if eps_ttm is not None:
        result["eps_diluted"] = eps_ttm
        result["ttm_eps_diluted"] = eps_ttm
    elif eps_selection["basis"].startswith("Annual FY"):
        result["eps_diluted"] = eps_selection["best"]
    else:
        # The annualized EPS will be derived below from annualized net income
        # and point-in-time shares; this is more internally coherent than
        # multiplying cumulative EPS by 4, 2, or 4/3.
        result["eps_diluted"] = None

    # Revenue prior is basis-matched by _select_flow.
    revenue_selection = selections["revenue"]
    result["revenue_prior"] = revenue_selection.get("prior")
    result["financial_basis"] = revenue_selection.get("basis", "N/A")
    result["interim_period_months"] = revenue_selection.get("interim_months")

    ref = revenue_selection.get("reference_entry")
    if ref:
        result["filing_form"] = ref.get("form")
        result["period_end_date"] = ref.get("end")
        result["filing_date"] = _parse_filing_date(ref.get("filed"))
        result["fiscal_quarter"] = ref.get("fp")
        try:
            result["fiscal_year"] = int(ref["end"][:4])
        except Exception:
            result["fiscal_year"] = None

    # FCF: CapEx is required. A missing CapEx fact must not become zero.
    cfo = selections["cfo"].get("best")
    capex = selections["capex"].get("best")
    if cfo is not None and capex is not None:
        result["operating_cash_flow"] = int(cfo)
        result["free_cash_flow"] = int(cfo - abs(capex))

    ttm_cfo = selections["cfo"].get("ttm")
    ttm_capex = selections["capex"].get("ttm")
    if ttm_cfo is not None and ttm_capex is not None:
        result["ttm_operating_cash_flow"] = int(ttm_cfo)
        result["ttm_free_cash_flow"] = int(ttm_cfo - abs(ttm_capex))

    ann_cfo = selections["cfo"].get("annualized")
    ann_capex = selections["capex"].get("annualized")
    if ann_cfo is not None and ann_capex is not None:
        result["annualized_operating_cash_flow"] = int(ann_cfo)
        result["annualized_free_cash_flow"] = int(ann_cfo - abs(ann_capex))

    # EBITDA at the same basis as EBIT and D&A.
    ebit = selections["ebit"].get("best")
    da = selections["depreciation_amortization"].get("best")
    if ebit is not None and da is not None:
        result["ebitda"] = int(ebit + da)

    ttm_ebit = selections["ebit"].get("ttm")
    ttm_da = selections["depreciation_amortization"].get("ttm")
    if ttm_ebit is not None and ttm_da is not None:
        result["ttm_ebitda"] = int(ttm_ebit + ttm_da)

    ann_ebit = selections["ebit"].get("annualized")
    ann_da = selections["depreciation_amortization"].get("annualized")
    if ann_ebit is not None and ann_da is not None:
        result["annualized_ebitda"] = int(ann_ebit + ann_da)

    # Balance sheet is anchored to one common date.
    balance_date = _latest_balance_date(facts)
    result["total_assets"] = _balance_at_date(
        facts, BALANCE_CONCEPTS["total_assets"], balance_date
    )
    result["cash_and_equivalents"] = _balance_at_date(
        facts, BALANCE_CONCEPTS["cash"], balance_date
    )
    result["shareholders_equity"] = _balance_at_date(
        facts, BALANCE_CONCEPTS["shareholders_equity"], balance_date
    )
    result["shares_outstanding_bs"] = _balance_at_date(
        facts, BALANCE_CONCEPTS["shares_outstanding"], balance_date
    )
    result["total_debt"] = _debt_at_date(facts, balance_date)

    debt = result["total_debt"]
    cash = result["cash_and_equivalents"]
    if debt is not None and cash is not None:
        result["net_debt"] = int(debt - cash)

    # If annualized income is the selected basis, derive EPS from the same
    # annualized net income using the latest disclosed share count. This avoids
    # multiplying cumulative EPS by an arbitrary factor.
    if result.get("eps_diluted") is None:
        annualized_net_income = selections["net_income"].get("annualized")
        shares = result.get("shares_outstanding_bs")
        if annualized_net_income is not None and shares and shares > 0:
            result["annualized_eps_diluted"] = round(
                annualized_net_income / shares, 4
            )
            result["eps_diluted"] = result["annualized_eps_diluted"]

    # Ensure values written to integer DB columns are integral.
    for field in (
        "revenue", "revenue_prior", "gross_profit", "ebitda", "ebit",
        "net_income", "operating_cash_flow", "free_cash_flow",
        "total_assets", "total_debt", "cash_and_equivalents",
        "shareholders_equity", "shares_outstanding_bs", "net_debt",
        "ttm_revenue", "ttm_gross_profit", "ttm_ebitda", "ttm_ebit",
        "ttm_net_income", "ttm_operating_cash_flow", "ttm_free_cash_flow",
        "annualized_revenue", "annualized_gross_profit",
        "annualized_ebitda", "annualized_ebit", "annualized_net_income",
        "annualized_operating_cash_flow", "annualized_free_cash_flow",
    ):
        if result.get(field) is not None:
            result[field] = int(result[field])

    return result
