import React, { useMemo, useCallback, useRef } from 'react';
import { AgGridReact } from 'ag-grid-react';
import type {
  ColDef, GridReadyEvent, ICellRendererParams,
  ValueFormatterParams, RowClassParams, ColGroupDef,
} from 'ag-grid-community';
import 'ag-grid-community/styles/ag-grid.css';
import 'ag-grid-community/styles/ag-theme-balham.css';

import { CompanyRow, BenchmarkMetric, MetricStats } from '../types';
import {
  fmtPrice, fmtPct, fmtSignedPct, fmtMarketCap,
  fmtMultiple, fmtPercent, fmtNumber, fmtEps, fmtRatio,
} from '../utils/formatters';

interface CompsTableProps {
  companies: CompanyRow[];
  summary: Record<string, MetricStats>;
  benchmarkMetric: BenchmarkMetric;
  loading: boolean;
}

// ─── Cell Renderers ───────────────────────────────────────────────────────

function ChangeCellRenderer(p: ICellRendererParams) {
  const v = p.value as number | null;
  if (p.node?.rowPinned) return <span className="summary-cell">{v != null ? fmtPct(v) : 'N/A'}</span>;
  if (v == null) return <span className="cell-na">N/A</span>;
  return <span className={v > 0 ? 'cell-positive' : v < 0 ? 'cell-negative' : 'cell-neutral'}>{fmtPct(v)}</span>;
}

function TickerCellRenderer(p: ICellRendererParams) {
  if (p.node?.rowPinned) {
    return <span className="summary-row-ticker">{p.value}</span>;
  }
  const badges = [];
  if (p.data?.in_sp500)    badges.push(<span key="sp" className="badge badge-sp">SPX</span>);
  if (p.data?.in_nasdaq100) badges.push(<span key="nq" className="badge badge-nq">NDX</span>);
  return (<div className="ticker-cell"><span className="ticker-symbol">{p.value}</span><div className="ticker-badges">{badges}</div></div>);
}

function NameCellRenderer(p: ICellRendererParams) {
  if (p.node?.rowPinned) return <span className="summary-row-name">{p.value}</span>;
  return <span className="company-name-cell" title={p.value}>{p.value}</span>;
}

function DiscountCellRenderer(p: ICellRendererParams) {
  const v = p.value as number | null;
  if (p.node?.rowPinned) return <span className="summary-cell">—</span>;
  if (v == null) return <span className="cell-na">N/A</span>;

  const abs = Math.abs(v);
  let signal: 'discount' | 'premium' | 'neutral';
  if (v < -5)       signal = 'discount';
  else if (v > 5)   signal = 'premium';
  else              signal = 'neutral';

  const arrow = signal === 'discount' ? '▼' : signal === 'premium' ? '▲' : '≈';
  return (
    <div className={`discount-cell discount-${signal}`}>
      <span className="discount-arrow">{arrow}</span>
      <span className="discount-value">{fmtSignedPct(v)}</span>
    </div>
  );
}

function MultipleWithSignalRenderer(
  p: ICellRendererParams,
  benchmarkField: BenchmarkMetric,
  discountField: string,
) {
  if (p.node?.rowPinned) {
    return <span className="summary-cell">{p.value != null ? fmtMultiple(p.value) : 'N/A'}</span>;
  }
  const v = p.value as number | null;
  if (v == null) return <span className="cell-na">N/A</span>;

  const discountVal = p.data?.[discountField] as number | null;
  let rowSignal: 'discount' | 'premium' | 'neutral' = 'neutral';
  if (discountVal != null) {
    if (discountVal < -10) rowSignal = 'discount';
    else if (discountVal > 10) rowSignal = 'premium';
  }

  return (
    <div className={`benchmark-cell benchmark-${rowSignal}`}>
      <span className="benchmark-value">{fmtMultiple(v)}</span>
      {rowSignal !== 'neutral' && (
        <span className="benchmark-vs">{rowSignal === 'discount' ? '▼' : '▲'}</span>
      )}
    </div>
  );
}



export default function CompsTable({ companies, summary, benchmarkMetric, loading }: CompsTableProps) {
  const gridRef = useRef<AgGridReact>(null);
  // Pinned bottom rows — Peer Median FIRST, then Peer Mean
  const pinnedBottomData = useMemo(() => {
    const MULTIPLES = [
      'pe_ratio','ev_ebitda','ev_sales','price_to_book',
      'roe','ebitda_margin','gross_margin','net_debt_ebitda',
      'fcf_yield','revenue_growth','dividend_yield',
      'eps','debt_to_equity',
    ];
    const medianRow: Record<string, unknown> = {
      ticker: 'MEDIAN', name: 'Peer Median',
      sector: '', industry: '',
    };
    const meanRow: Record<string, unknown> = {
      ticker: 'MEAN', name: 'Peer Mean',
      sector: '', industry: '',
    };
    for (const m of MULTIPLES) {
      const s = summary[m];
      medianRow[m] = s?.median ?? null;
      meanRow[m]   = s?.mean   ?? null;
    }
    return [medianRow, meanRow]; // Median always first
  }, [summary]);

  const discountField = `discount_vs_median_${benchmarkMetric}`;

  const benchmarkColRenderer = useCallback((p: ICellRendererParams) =>
    MultipleWithSignalRenderer(p, benchmarkMetric, discountField),
    [benchmarkMetric, discountField]
  );

  const pctFormatter = (p: ValueFormatterParams) => fmtPercent(p.value);
  const multFormatter = (p: ValueFormatterParams) => fmtMultiple(p.value);

  const columnDefs: (ColDef | ColGroupDef)[] = useMemo(() => [
    // ── Pinned left: Ticker + Company ───────────────────────────────
    {
      field: 'ticker',
      headerName: 'Ticker',
      width: 110,
      pinned: 'left',
      lockPinned: true,
      cellRenderer: TickerCellRenderer,
      comparator: (a: string, b: string) => a.localeCompare(b),
      cellClass: 'cell-mono',
    },
    {
      field: 'name',
      headerName: 'Company',
      width: 185,
      pinned: 'left',
      lockPinned: true,
      cellRenderer: NameCellRenderer,
      tooltipField: 'name',
    },

    // ── Classification ───────────────────────────────────────────────
    { field: 'sector',   headerName: 'Sector',   width: 155 },
    { field: 'industry', headerName: 'Industry', width: 175, hide: true },

    // ── Price & Market ───────────────────────────────────────────────
    {
      field: 'price',
      headerName: 'Price',
      width: 88,
      type: 'numericColumn',
      valueFormatter: (p) => fmtPrice(p.value),
    },
    {
      field: 'day_change_pct',
      headerName: '1D Chg',
      width: 88,
      type: 'numericColumn',
      cellRenderer: ChangeCellRenderer,
    },
    {
      field: 'market_cap',
      headerName: 'Mkt Cap',
      width: 108,
      type: 'numericColumn',
      valueFormatter: (p) => fmtMarketCap(p.value),
      comparator: (a: number, b: number) => (a ?? 0) - (b ?? 0),
    },
    {
      field: 'enterprise_value',
      headerName: 'EV',
      width: 108,
      type: 'numericColumn',
      valueFormatter: (p) => fmtMarketCap(p.value),
      comparator: (a: number, b: number) => (a ?? 0) - (b ?? 0),
    },

    // ── Benchmark metric column (highlighted) ────────────────────────
    {
      field: benchmarkMetric,
      headerName: { pe_ratio: 'P/E', ev_ebitda: 'EV/EBITDA', ev_sales: 'EV/Sales', price_to_book: 'P/Book' }[benchmarkMetric],
      width: 108,
      type: 'numericColumn',
      cellRenderer: benchmarkColRenderer,
      comparator: (a: number, b: number) => (a ?? 999) - (b ?? 999),
      headerClass: 'benchmark-header',
      pinned: false,
    },

    // ── Discount vs Median ───────────────────────────────────────────
    {
      field: discountField,
      headerName: 'Disc vs Median',
      width: 125,
      type: 'numericColumn',
      cellRenderer: DiscountCellRenderer,
      comparator: (a: number, b: number) => (a ?? 0) - (b ?? 0),
      headerClass: 'benchmark-header',
      pinned: false,
      headerTooltip: 'Discount vs Peer Median = ((Multiple − Median) / Median) × 100. Negative = trading below peers.',
    },

    // ── Other valuation multiples ────────────────────────────────────
    ...(benchmarkMetric !== 'pe_ratio' ? [{
      field: 'pe_ratio', headerName: 'P/E', width: 82,
      type: 'numericColumn', valueFormatter: multFormatter,
      comparator: (a: number, b: number) => (a ?? 999) - (b ?? 999),
    }] : []),
    ...(benchmarkMetric !== 'ev_ebitda' ? [{
      field: 'ev_ebitda', headerName: 'EV/EBITDA', width: 105,
      type: 'numericColumn', valueFormatter: multFormatter,
      comparator: (a: number, b: number) => (a ?? 999) - (b ?? 999),
    }] : []),
    ...(benchmarkMetric !== 'ev_sales' ? [{
      field: 'ev_sales', headerName: 'EV/Sales', width: 95,
      type: 'numericColumn', valueFormatter: multFormatter,
      comparator: (a: number, b: number) => (a ?? 999) - (b ?? 999),
    }] : []),
    ...(benchmarkMetric !== 'price_to_book' ? [{
      field: 'price_to_book', headerName: 'P/Book', width: 82,
      type: 'numericColumn', valueFormatter: multFormatter,
      comparator: (a: number, b: number) => (a ?? 999) - (b ?? 999),
    }] : []),

    // ── Quality & Profitability ──────────────────────────────────────
    {
      field: 'roe', headerName: 'ROE', width: 82,
      type: 'numericColumn', valueFormatter: pctFormatter,
      comparator: (a: number, b: number) => (a ?? -999) - (b ?? -999),
    },
    {
      field: 'ebitda_margin', headerName: 'EBITDA Mgn', width: 110,
      type: 'numericColumn', valueFormatter: pctFormatter,
      comparator: (a: number, b: number) => (a ?? -999) - (b ?? -999),
    },
    {
      field: 'gross_margin', headerName: 'Gross Mgn', width: 100,
      type: 'numericColumn', valueFormatter: pctFormatter,
      comparator: (a: number, b: number) => (a ?? -999) - (b ?? -999),
    },

    // ── New metrics ──────────────────────────────────────────────────
    {
      field: 'fcf_yield', headerName: 'FCF Yield', width: 95,
      type: 'numericColumn', valueFormatter: pctFormatter,
      comparator: (a: number, b: number) => (a ?? -999) - (b ?? -999),
      headerTooltip: 'Free Cash Flow Yield = FCF / Market Cap %',
    },
    {
      field: 'revenue_growth', headerName: 'Rev Growth', width: 100,
      type: 'numericColumn', valueFormatter: pctFormatter,
      comparator: (a: number, b: number) => (a ?? -999) - (b ?? -999),
      headerTooltip: 'Revenue Growth YoY %',
    },
    {
      field: 'dividend_yield', headerName: 'Div Yield', width: 92,
      type: 'numericColumn', valueFormatter: pctFormatter,
      comparator: (a: number, b: number) => (a ?? -1) - (b ?? -1),
    },

    // ── Leverage ─────────────────────────────────────────────────────
    {
      field: 'net_debt_ebitda', headerName: 'ND/EBITDA', width: 105,
      type: 'numericColumn', valueFormatter: multFormatter,
      comparator: (a: number, b: number) => (a ?? 999) - (b ?? 999),
    },

    // ── Institutional Research: Financial Strength ───────────────────
    {
      field: 'eps', headerName: 'EPS', width: 88,
      type: 'numericColumn',
      valueFormatter: (p: ValueFormatterParams) => fmtEps(p.value),
      comparator: (a: number, b: number) => (a ?? -999) - (b ?? -999),
      headerTooltip: 'Earnings Per Share (Diluted, from SEC EDGAR)',
    },
    {
      field: 'debt_to_equity', headerName: 'Debt/Equity', width: 110,
      type: 'numericColumn',
      valueFormatter: (p: ValueFormatterParams) => fmtRatio(p.value),
      comparator: (a: number, b: number) => (a ?? 999) - (b ?? 999),
      headerTooltip: 'Debt-to-Equity = Total Debt / Shareholders\' Equity. Lower is generally less leveraged.',
    },

  ], [benchmarkMetric, benchmarkColRenderer, discountField]);

  const defaultColDef: ColDef = useMemo(() => ({
    sortable: true,
    resizable: true,
    filter: false,
    suppressMovable: false,
    cellClass: 'cell-mono',
    headerClass: 'header-default',
  }), []);

  const getRowClass = useCallback((p: RowClassParams): string | undefined => {
    if (p.node?.rowPinned === 'bottom') return 'summary-pinned-row';
    // Subtle green highlight for discount candidates
    const discVal = p.data?.[discountField] as number | null;
    if (discVal != null && discVal < -10) return 'row-discount-candidate';
    return undefined;
  }, [discountField]);

  const onGridReady = useCallback((e: GridReadyEvent) => {
    e.api.sizeColumnsToFit();
  }, []);

  if (loading) {
    return (
      <div className="grid-loading">
        <div className="loading-spinner" />
        <span>Loading comparable data...</span>
      </div>
    );
  }

  return (
    <div className="ag-theme-balham comps-grid">
      <AgGridReact
        ref={gridRef}
        rowData={companies}
        columnDefs={columnDefs}
        defaultColDef={defaultColDef}
        pinnedBottomRowData={pinnedBottomData}
        getRowClass={getRowClass}
        onGridReady={onGridReady}
        rowHeight={34}
        headerHeight={38}
        suppressRowClickSelection
        enableCellTextSelection
        animateRows
        rowBuffer={20}
        tooltipShowDelay={400}
      />
    </div>
  );
}
