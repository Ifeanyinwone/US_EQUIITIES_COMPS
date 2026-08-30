"""Initial schema — all tables

Revision ID: 001_initial
Revises:
Create Date: 2025-01-01

All DDL uses CREATE TABLE IF NOT EXISTS and CREATE INDEX IF NOT EXISTS.
Safe to run on any existing database — never raises duplicate-object errors.
"""
from alembic import op
from sqlalchemy import text

revision      = '001_initial'
down_revision = None
branch_labels = None
depends_on    = None


_TABLES = """
CREATE TABLE IF NOT EXISTS companies (
    ticker          VARCHAR(10)  PRIMARY KEY,
    name            VARCHAR(255) NOT NULL,
    sector          VARCHAR(100),
    industry        VARCHAR(150),
    cik             VARCHAR(20),
    in_sp500        BOOLEAN      DEFAULT FALSE,
    in_nasdaq100    BOOLEAN      DEFAULT FALSE,
    exchange        VARCHAR(20),
    currency        VARCHAR(5)   DEFAULT 'USD',
    is_active       BOOLEAN      DEFAULT TRUE,
    meta_cached_at  TIMESTAMPTZ,
    created_at      TIMESTAMPTZ  DEFAULT now(),
    updated_at      TIMESTAMPTZ  DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_companies_sector   ON companies(sector);
CREATE INDEX IF NOT EXISTS ix_companies_industry ON companies(industry);

CREATE TABLE IF NOT EXISTS market_prices (
    id                  SERIAL      PRIMARY KEY,
    ticker              VARCHAR(10) UNIQUE NOT NULL REFERENCES companies(ticker),
    price               NUMERIC(20,4),
    prev_close          NUMERIC(20,4),
    day_change_pct      NUMERIC(10,4),
    market_cap          BIGINT,
    volume              BIGINT,
    avg_volume_30d      BIGINT,
    week_52_high        NUMERIC(20,4),
    week_52_low         NUMERIC(20,4),
    shares_outstanding  BIGINT,
    dividend_yield      NUMERIC(10,6),
    refreshed_at        TIMESTAMPTZ DEFAULT now(),
    updated_at          TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_market_prices_ticker ON market_prices(ticker);

CREATE TABLE IF NOT EXISTS financial_statements (
    id                      SERIAL      PRIMARY KEY,
    ticker                  VARCHAR(10) UNIQUE NOT NULL REFERENCES companies(ticker),
    fiscal_year_end         VARCHAR(20),
    period_type             VARCHAR(10) DEFAULT 'LTM',
    filing_form             VARCHAR(20),
    fiscal_year             INTEGER,
    fiscal_quarter          VARCHAR(5),
    period_end_date         VARCHAR(20),
    revenue                 BIGINT,
    revenue_prior           BIGINT,
    gross_profit            BIGINT,
    ebitda                  BIGINT,
    ebit                    BIGINT,
    net_income              BIGINT,
    eps_diluted             NUMERIC(20,4),
    free_cash_flow          BIGINT,
    total_assets            BIGINT,
    total_debt              BIGINT,
    cash_and_equivalents    BIGINT,
    shareholders_equity     BIGINT,
    shares_outstanding_bs   BIGINT,
    net_debt                BIGINT,
    book_value_per_share    NUMERIC(20,4),
    data_source             VARCHAR(50) DEFAULT 'SEC_EDGAR',
    filing_date             TIMESTAMPTZ,
    refreshed_at            TIMESTAMPTZ DEFAULT now(),
    updated_at              TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_financial_statements_ticker ON financial_statements(ticker);

CREATE TABLE IF NOT EXISTS calculated_multiples (
    id                  SERIAL      PRIMARY KEY,
    ticker              VARCHAR(10) UNIQUE NOT NULL REFERENCES companies(ticker),
    enterprise_value    BIGINT,
    pe_ratio            NUMERIC(20,4),
    ev_ebitda           NUMERIC(20,4),
    ev_sales            NUMERIC(20,4),
    price_to_book       NUMERIC(20,4),
    roe                 NUMERIC(20,4),
    ebitda_margin       NUMERIC(20,4),
    net_debt_ebitda     NUMERIC(20,4),
    fcf_yield           NUMERIC(20,4),
    revenue_growth      NUMERIC(20,4),
    gross_margin        NUMERIC(20,4),
    dividend_yield      NUMERIC(10,6),
    eps_growth          NUMERIC(20,4),
    calculated_at       TIMESTAMPTZ DEFAULT now(),
    updated_at          TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_calculated_multiples_ticker ON calculated_multiples(ticker);

CREATE TABLE IF NOT EXISTS peer_statistics (
    id                          SERIAL      PRIMARY KEY,
    group_type                  VARCHAR(20)  NOT NULL,
    group_value                 VARCHAR(150) NOT NULL,
    universe                    VARCHAR(20)  DEFAULT 'ALL',
    median_pe                   NUMERIC(20,4),
    median_ev_ebitda            NUMERIC(20,4),
    median_ev_sales             NUMERIC(20,4),
    median_price_to_book        NUMERIC(20,4),
    median_roe                  NUMERIC(20,4),
    median_ebitda_margin        NUMERIC(20,4),
    median_net_debt_ebitda      NUMERIC(20,4),
    median_fcf_yield            NUMERIC(20,4),
    median_revenue_growth       NUMERIC(20,4),
    median_gross_margin         NUMERIC(20,4),
    mean_pe                     NUMERIC(20,4),
    mean_ev_ebitda              NUMERIC(20,4),
    mean_ev_sales               NUMERIC(20,4),
    mean_price_to_book          NUMERIC(20,4),
    mean_roe                    NUMERIC(20,4),
    mean_ebitda_margin          NUMERIC(20,4),
    mean_net_debt_ebitda        NUMERIC(20,4),
    mean_fcf_yield              NUMERIC(20,4),
    mean_revenue_growth         NUMERIC(20,4),
    mean_gross_margin           NUMERIC(20,4),
    company_count               INTEGER,
    calculated_at               TIMESTAMPTZ DEFAULT now(),
    updated_at                  TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT uq_peer_stats UNIQUE (group_type, group_value, universe)
);

CREATE INDEX IF NOT EXISTS ix_peer_stats_group ON peer_statistics(group_type, group_value);
"""


def upgrade() -> None:
    # Execute every statement individually so one failure never aborts the rest
    conn = op.get_bind()
    for stmt in _TABLES.strip().split(";"):
        stmt = stmt.strip()
        if stmt:
            conn.execute(text(stmt))


def downgrade() -> None:
    conn = op.get_bind()
    for tbl in [
        "peer_statistics", "calculated_multiples",
        "financial_statements", "market_prices", "companies",
    ]:
        conn.execute(text(f"DROP TABLE IF EXISTS {tbl} CASCADE"))
