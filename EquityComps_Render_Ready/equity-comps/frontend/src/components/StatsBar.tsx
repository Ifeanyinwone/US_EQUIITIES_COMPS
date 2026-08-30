import React from 'react';
import { MetricStats, BenchmarkMetric, getSectorMetricHints } from '../types';
import { fmtMultiple, fmtPercent, METRIC_LABELS } from '../utils/formatters';

interface StatsBarProps {
  summary: Record<string, MetricStats>;
  benchmarkMetric: BenchmarkMetric;
  sector: string;
}

const DISPLAY_METRICS = [
  'pe_ratio', 'ev_ebitda', 'ev_sales', 'price_to_book',
  'roe', 'ebitda_margin', 'fcf_yield', 'revenue_growth',
];

function formatVal(metric: string, val: number | null): string {
  if (val == null) return 'N/A';
  if (['roe', 'ebitda_margin', 'gross_margin', 'fcf_yield', 'revenue_growth', 'dividend_yield'].includes(metric)) {
    return fmtPercent(val);
  }
  return fmtMultiple(val);
}

export default function StatsBar({ summary, benchmarkMetric, sector }: StatsBarProps) {
  const hints = getSectorMetricHints(sector);

  return (
    <div className="stats-bar">
      <div className="stats-header">
        <span className="stats-label">Universe Peer Medians</span>
        {hints.length > 0 && (
          <span className="stats-hint">
            Recommended for {sector || 'sector'}: {hints.join(' · ')}
          </span>
        )}
      </div>
      <div className="stats-chips">
        {DISPLAY_METRICS.map(metric => {
          const stats = summary[metric];
          const isBenchmark = metric === benchmarkMetric;
          return (
            <div key={metric} className={`stats-chip ${isBenchmark ? 'stats-chip-active' : ''}`}>
              <span className="stats-chip-label">{METRIC_LABELS[metric]}</span>
              <span className="stats-chip-median">{formatVal(metric, stats?.median ?? null)}</span>
              <div className="stats-chip-secondary">
                <span className="stats-chip-mean-label">μ</span>
                <span className="stats-chip-mean">{formatVal(metric, stats?.mean ?? null)}</span>
                <span className="stats-chip-sub">n={stats?.count ?? 0}</span>
              </div>
            </div>
          );
        })}
      </div>
      <div className="stats-legend">
        <span className="legend-item legend-discount">▼ &gt;10% below median = discount</span>
        <span className="legend-sep">·</span>
        <span className="legend-item legend-premium">▲ &gt;10% above median = premium</span>
        <span className="legend-sep">·</span>
        <span className="legend-note">Peer Median is primary benchmark · Mean shown as reference</span>
      </div>
    </div>
  );
}
