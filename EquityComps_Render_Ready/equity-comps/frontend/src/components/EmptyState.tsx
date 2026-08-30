import React from 'react';
import { Database, Terminal } from 'lucide-react';

export default function EmptyState() {
  return (
    <div className="empty-state">
      <div className="empty-state-icon">
        <Database size={40} />
      </div>
      <h2 className="empty-state-title">No data yet</h2>
      <p className="empty-state-desc">
        The database hasn't been seeded. Run the bootstrap script to fetch
        company data, market prices, and SEC EDGAR financials.
      </p>
      <div className="empty-state-cmd">
        <Terminal size={13} />
        <code>python scripts/seed.py</code>
      </div>
      <p className="empty-state-note">
        Pulls ~340 tickers · market prices via yfinance · financials via SEC EDGAR XBRL API
        <br />Expected time: 5–15 minutes
      </p>
    </div>
  );
}
