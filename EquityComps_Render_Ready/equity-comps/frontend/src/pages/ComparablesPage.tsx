import React from 'react';
import { TrendingUp, AlertCircle } from 'lucide-react';
import FilterBar from '../components/FilterBar';
import CompsTable from '../components/CompsTable';
import StatsBar from '../components/StatsBar';
import DataFreshnessBar from '../components/DataFreshnessBar';
import EmptyState from '../components/EmptyState';
import { useComps } from '../hooks/useComps';

export default function ComparablesPage() {
  const {
    filters, data, filterOptions,
    loading, error, timestamps,
    updateFilters, refresh,
  } = useComps();

  const benchmarkLabel: Record<string, string> = {
    pe_ratio: 'P/E', ev_ebitda: 'EV/EBITDA',
    ev_sales: 'EV/Sales', price_to_book: 'P/Book',
  };

  return (
    <div className="app">

      {/* ── Header ──────────────────────────────────────── */}
      <header className="app-header">
        <div className="header-left">
          <div className="logo">
            <TrendingUp size={18} />
            <span className="logo-text">EquityComps</span>
            <span className="logo-sub">U.S. Large-Cap Comparable Analysis</span>
          </div>
        </div>
        <div className="header-right">
          <span className="header-badge-sep">·</span>
          <span className="header-badge">S&amp;P 500</span>
          <span className="header-badge">Nasdaq-100</span>
          <span className="header-badge-sep">·</span>
          <span className="header-meta">SEC EDGAR · TTM / Annualized Basis · Peer Median Benchmark</span>
        </div>
      </header>

      {/* ── Filter Bar ───────────────────────────────────── */}
      <FilterBar
        filters={filters}
        sectors={filterOptions.sectors}
        industries={filterOptions.industries}
        onFilterChange={updateFilters}
        loading={loading}
        companyCount={data?.total_count ?? 0}
      />

      {/* ── Data Freshness Timestamps ────────────────────── */}
      <DataFreshnessBar
        timestamps={timestamps}
        loading={loading}
        onRefresh={refresh}
      />

      {/* ── Peer Median Stats Bar ────────────────────────── */}
      {data && data.total_count > 0 && (
        <StatsBar
          summary={data.summary}
          benchmarkMetric={filters.benchmarkMetric}
          sector={filters.sector}
        />
      )}

      {/* ── Error Banner ─────────────────────────────────── */}
      {error && (
        <div className="error-banner">
          <AlertCircle size={14} />
          <span>{error} — ensure the backend is running on port 8000.</span>
        </div>
      )}

      {/* ── Main Table ───────────────────────────────────── */}
      <main className="app-main">
        {!loading && data && data.total_count === 0 && !filters.search && !filters.sector ? (
          <EmptyState />
        ) : (
          <div className="table-container">

            {/* Table header row */}
            <div className="table-header">
              <div className="table-title">
                <span>Comparable Analysis</span>
                {filters.sector && (
                  <span className="table-subtitle">· {filters.sector}</span>
                )}
                {filters.industry && (
                  <span className="table-subtitle table-subtitle-dim">/ {filters.industry}</span>
                )}
              </div>
              <div className="table-meta">
                <div className="benchmark-badge">
                  <span className="benchmark-badge-label">Benchmark</span>
                  <span className="benchmark-badge-value">
                    {benchmarkLabel[filters.benchmarkMetric]}
                  </span>
                  <span className="benchmark-badge-sub">vs Peer Median</span>
                </div>
                <span className="methodology-note">
                  EV = Mkt Cap + Debt − Cash · Multiples from raw SEC EDGAR · Selected Financial Basis
                 
                </span>
              </div>
            </div>

            {/* AG Grid comparable table */}
            <CompsTable
              companies={data?.companies ?? []}
              summary={data?.summary ?? {}}
              benchmarkMetric={filters.benchmarkMetric}
              loading={loading}
            />

            {/* Table footer */}
            <div className="table-footer">
              <span className="footer-note">
                <span className="footer-legend footer-discount">▼ Discount</span>
                &nbsp;= &gt;10% below peer median &nbsp;·&nbsp;
                <span className="footer-legend footer-premium">▲ Premium</span>
                &nbsp;= &gt;10% above peer median &nbsp;·&nbsp;
                Disc vs Median % = ((Multiple − Median) / Median) × 100
                &nbsp;·&nbsp; Summary rows: Peer Median (primary) · Peer Mean (reference)
                &nbsp;·&nbsp; Click any ticker for full research page
              </span>
            </div>

          </div>
        )}
      </main>
    </div>
  );
}
