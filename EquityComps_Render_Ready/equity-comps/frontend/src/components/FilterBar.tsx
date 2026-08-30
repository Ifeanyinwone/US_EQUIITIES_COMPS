import React from 'react';
import { Search, Download, ChevronDown } from 'lucide-react';
import { Filters, BenchmarkMetric, getSectorMetricHints, FINANCIALS_SECTORS } from '../types';
import { BENCHMARK_OPTIONS } from '../utils/formatters';
import { getExportUrl } from '../services/api';

interface FilterBarProps {
  filters: Filters;
  sectors: string[];
  industries: string[];
  onFilterChange: (updates: Partial<Filters>) => void;
  loading: boolean;
  companyCount: number;
}

export default function FilterBar({
  filters, sectors, industries, onFilterChange, loading, companyCount
}: FilterBarProps) {
  const exportParams = {
    universe: filters.universe,
    sector:   filters.sector   || undefined,
    industry: filters.industry || undefined,
    search:   filters.search   || undefined,
  };

  const hints = getSectorMetricHints(filters.sector);
  const isFinancials = filters.sector ? FINANCIALS_SECTORS.has(filters.sector) : false;

  return (
    <div className="filter-bar">
      <div className="filter-bar-left">

        {/* Universe tabs */}
        <div className="universe-tabs">
          {(['ALL', 'SP500', 'NASDAQ100'] as const).map(u => (
            <button
              key={u}
              className={`universe-tab ${filters.universe === u ? 'active' : ''}`}
              onClick={() => onFilterChange({ universe: u })}
            >
              {u === 'SP500' ? 'S&P 500' : u === 'NASDAQ100' ? 'Nasdaq-100' : 'All'}
            </button>
          ))}
        </div>

        <div className="filter-divider" />

        {/* Sector */}
        <div className="filter-select-wrap">
          <label className="filter-label">Sector</label>
          <div className="select-container">
            <select
              className="filter-select"
              value={filters.sector}
              onChange={e => onFilterChange({ sector: e.target.value, industry: '' })}
            >
              <option value="">All Sectors</option>
              {sectors.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
            <ChevronDown size={11} className="select-icon" />
          </div>
        </div>

        {/* Industry */}
        <div className="filter-select-wrap">
          <label className="filter-label">Industry</label>
          <div className="select-container">
            <select
              className="filter-select"
              value={filters.industry}
              onChange={e => onFilterChange({ industry: e.target.value })}
              disabled={!filters.sector}
            >
              <option value="">All Industries</option>
              {industries.map(i => <option key={i} value={i}>{i}</option>)}
            </select>
            <ChevronDown size={11} className="select-icon" />
          </div>
        </div>

        <div className="filter-divider" />

        {/* Benchmark metric */}
        <div className="filter-select-wrap">
          <label className="filter-label">
            Benchmark
            {isFinancials && <span className="filter-label-hint"> · Financials: P/B, P/E, ROE</span>}
          </label>
          <div className="select-container">
            <select
              className="filter-select filter-select-benchmark"
              value={filters.benchmarkMetric}
              onChange={e => onFilterChange({ benchmarkMetric: e.target.value as BenchmarkMetric })}
            >
              {BENCHMARK_OPTIONS.map(o => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
            <ChevronDown size={11} className="select-icon" />
          </div>
        </div>

        {/* Sector hint pills */}
        {hints.length > 0 && (
          <div className="sector-hints">
            {hints.slice(0, 3).map(h => (
              <span key={h} className="sector-hint-pill">{h}</span>
            ))}
          </div>
        )}
      </div>

      <div className="filter-bar-right">
        {/* Search */}
        <div className="search-wrap">
          <Search size={13} className="search-icon" />
          <input
            type="text"
            className="search-input"
            placeholder="Ticker or company..."
            value={filters.search}
            onChange={e => onFilterChange({ search: e.target.value })}
          />
        </div>

        <span className="company-count">
          {loading ? '...' : `${companyCount.toLocaleString()} companies`}
        </span>

        {/* Export */}
        <div className="export-buttons">
          <a className="btn btn-export" href={getExportUrl('csv', exportParams)} download="equity_comps.csv">
            <Download size={11} /> CSV
          </a>
          <a className="btn btn-export" href={getExportUrl('excel', exportParams)} download="equity_comps.xlsx">
            <Download size={11} /> XLSX
          </a>
        </div>
      </div>
    </div>
  );
}
