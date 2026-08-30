export function fmtPrice(v: number | null | undefined): string {
  if (v == null) return 'N/A';
  return `$${v.toFixed(2)}`;
}

export function fmtPct(v: number | null | undefined): string {
  if (v == null) return 'N/A';
  const sign = v > 0 ? '+' : '';
  return `${sign}${v.toFixed(2)}%`;
}

export function fmtSignedPct(v: number | null | undefined): string {
  if (v == null) return 'N/A';
  const sign = v > 0 ? '+' : '';
  return `${sign}${v.toFixed(1)}%`;
}

export function fmtMarketCap(v: number | null | undefined): string {
  if (v == null) return 'N/A';
  if (v >= 1e12) return `$${(v / 1e12).toFixed(2)}T`;
  if (v >= 1e9)  return `$${(v / 1e9).toFixed(2)}B`;
  if (v >= 1e6)  return `$${(v / 1e6).toFixed(1)}M`;
  return `$${v.toLocaleString()}`;
}

export function fmtMultiple(v: number | null | undefined, decimals = 1): string {
  if (v == null) return 'N/A';
  return `${v.toFixed(decimals)}x`;
}

export function fmtPercent(v: number | null | undefined, decimals = 1): string {
  if (v == null) return 'N/A';
  return `${v.toFixed(decimals)}%`;
}

export function fmtNumber(v: number | null | undefined, decimals = 2): string {
  if (v == null) return 'N/A';
  return v.toFixed(decimals);
}

export function fmtEps(v: number | null | undefined): string {
  if (v == null) return 'N/A';
  const sign = v < 0 ? '-' : '';
  return `${sign}$${Math.abs(v).toFixed(2)}`;
}

export function fmtRatio(v: number | null | undefined, decimals = 2): string {
  if (v == null) return 'N/A';
  return `${v.toFixed(decimals)}x`;
}

/** Format a UTC ISO timestamp as "May 30 14:32 UTC" */
export function fmtTimestamp(iso: string | null | undefined): string {
  if (!iso) return 'Never';
  try {
    const d = new Date(iso);
    return d.toLocaleString('en-US', {
      month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit',
      timeZone: 'UTC', timeZoneName: 'short',
    });
  } catch {
    return iso;
  }
}

export const METRIC_LABELS: Record<string, string> = {
  pe_ratio:       'P/E',
  ev_ebitda:      'EV/EBITDA',
  ev_sales:       'EV/Sales',
  price_to_book:  'P/Book',
  roe:            'ROE',
  ebitda_margin:  'EBITDA Mgn',
  gross_margin:   'Gross Mgn',
  net_debt_ebitda:'ND/EBITDA',
  fcf_yield:      'FCF Yield',
  revenue_growth: 'Rev Growth',
  dividend_yield: 'Div Yield',
  eps:            'EPS',
  debt_to_equity: 'Debt/Equity',
};

export const BENCHMARK_OPTIONS = [
  { value: 'pe_ratio',      label: 'P/E Ratio' },
  { value: 'ev_ebitda',     label: 'EV/EBITDA' },
  { value: 'ev_sales',      label: 'EV/Sales' },
  { value: 'price_to_book', label: 'Price/Book' },
];
