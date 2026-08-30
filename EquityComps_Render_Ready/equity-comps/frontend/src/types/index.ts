export interface CompanyRow {
  ticker: string;
  name: string;
  sector: string | null;
  industry: string | null;
  in_sp500: boolean;
  in_nasdaq100: boolean;

  // Market data
  price: number | null;
  day_change_pct: number | null;
  market_cap: number | null;
  volume: number | null;
  week_52_high: number | null;
  week_52_low: number | null;

  // Financials
  revenue: number | null;
  revenue_prior: number | null;
  ebitda: number | null;
  net_income: number | null;
  eps_diluted: number | null;
  total_debt: number | null;
  cash: number | null;
  net_debt: number | null;
  shareholders_equity: number | null;
  gross_profit: number | null;
  free_cash_flow: number | null;
  filing_form: string | null;
  period_end_date: string | null;
  fiscal_year: number | null;

  // Calculated multiples
  enterprise_value: number | null;
  pe_ratio: number | null;
  ev_ebitda: number | null;
  ev_sales: number | null;
  price_to_book: number | null;
  roe: number | null;
  ebitda_margin: number | null;
  gross_margin: number | null;
  net_debt_ebitda: number | null;
  fcf_yield: number | null;
  revenue_growth: number | null;
  dividend_yield: number | null;

  // Additional financial strength metrics
  eps: number | null;
  debt_to_equity: number | null;

  // Discount vs Median (per benchmark metric)
  discount_vs_median_pe_ratio: number | null;
  discount_vs_median_ev_ebitda: number | null;
  discount_vs_median_ev_sales: number | null;
  discount_vs_median_price_to_book: number | null;

  // Metadata
  price_refreshed_at: string | null;
  financials_refreshed_at: string | null;
}


export type BenchmarkMetric = 'pe_ratio' | 'ev_ebitda' | 'ev_sales' | 'price_to_book';
export interface MetricStats { mean: number | null; median: number | null; count: number; }

export interface Filters {
  universe: 'ALL' | 'SP500' | 'NASDAQ100';
  sector: string;
  industry: string;
  search: string;
  benchmarkMetric: BenchmarkMetric;
}

export const FINANCIALS_SECTORS = new Set<string>([
  'Financial Services',
  'Financials',
]);

const SECTOR_METRIC_HINTS: Record<string, string[]> = {
  'Financial Services': ['P/E', 'P/Book', 'ROE'],
  'Financials': ['P/E', 'P/Book', 'ROE'],
  'Technology': ['EV/EBITDA', 'EV/Sales', 'P/E'],
  'Communication Services': ['EV/EBITDA', 'EV/Sales', 'P/E'],
  'Consumer Cyclical': ['EV/EBITDA', 'EV/Sales', 'P/E'],
  'Consumer Defensive': ['EV/EBITDA', 'P/E', 'FCF Yield'],
  'Healthcare': ['EV/EBITDA', 'P/E', 'EV/Sales'],
  'Industrials': ['EV/EBITDA', 'EV/Sales', 'P/E'],
  'Energy': ['EV/EBITDA', 'EV/Sales', 'FCF Yield'],
  'Utilities': ['EV/EBITDA', 'P/E', 'FCF Yield'],
  'Real Estate': ['P/Book', 'EV/EBITDA', 'FCF Yield'],
  'Basic Materials': ['EV/EBITDA', 'EV/Sales', 'P/E'],
};

export function getSectorMetricHints(sector: string | null | undefined): string[] {
  if (!sector) return [];
  return SECTOR_METRIC_HINTS[sector] ?? ['EV/EBITDA', 'EV/Sales', 'P/E'];
}

export interface DataTimestamps {
  price_last_updated: string | null;
  financials_last_updated: string | null;
  peer_stats_last_updated: string | null;
}

export interface CompsResponse {
  companies: CompanyRow[];
  summary: Record<string, MetricStats>;
  total_count: number;
  timestamps: DataTimestamps;
  filters_applied: {
    universe: string;
    sector: string | null;
    industry: string | null;
    search: string | null;
  };
}

export interface FilterOptions {
  sectors: string[];
  industries: string[];
  universes: string[];
}
