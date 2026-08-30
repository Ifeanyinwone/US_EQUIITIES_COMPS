import React from 'react';
import { Clock, TrendingUp, BarChart2, RefreshCw } from 'lucide-react';
import { DataTimestamps } from '../types';
import { fmtTimestamp } from '../utils/formatters';

interface Props {
  timestamps: DataTimestamps | null;
  loading: boolean;
  onRefresh: () => void;
}

export default function DataFreshnessBar({ timestamps, loading, onRefresh }: Props) {
  return (
    <div className="freshness-bar">
      <div className="freshness-items">
        <div className="freshness-item">
          <TrendingUp size={11} className="freshness-icon freshness-price" />
          <span className="freshness-label">Prices</span>
          <span className="freshness-value">
            {fmtTimestamp(timestamps?.price_last_updated)}
          </span>
        </div>
        <div className="freshness-sep">·</div>
        <div className="freshness-item">
          <BarChart2 size={11} className="freshness-icon freshness-fin" />
          <span className="freshness-label">Financials</span>
          <span className="freshness-value">
            {fmtTimestamp(timestamps?.financials_last_updated)}
          </span>
        </div>
        <div className="freshness-sep">·</div>
        <div className="freshness-item">
          <Clock size={11} className="freshness-icon freshness-peer" />
          <span className="freshness-label">Peer Stats</span>
          <span className="freshness-value">
            {fmtTimestamp(timestamps?.peer_stats_last_updated)}
          </span>
        </div>
      </div>
      <button
        className={`btn btn-ghost btn-icon btn-xs ${loading ? 'spinning' : ''}`}
        onClick={onRefresh}
        disabled={loading}
        title="Refresh data"
      >
        <RefreshCw size={12} />
      </button>
    </div>
  );
}
