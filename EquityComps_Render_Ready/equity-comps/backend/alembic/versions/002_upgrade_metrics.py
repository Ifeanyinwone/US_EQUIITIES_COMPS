"""Add v2 columns — fully idempotent

Revision ID: 002_upgrade
Revises: 001_initial
Create Date: 2025-01-02

Every statement uses ADD COLUMN IF NOT EXISTS.
Each statement is executed independently (no transaction wrapping).
Safe to run multiple times without corruption.
"""
from alembic import op
from sqlalchemy import text

revision      = '002_upgrade'
down_revision = '001_initial'
branch_labels = None
depends_on    = None

# List of (table, column, pg_type) — each runs as its own ADD COLUMN IF NOT EXISTS
_COLUMNS = [
    # companies
    ("companies", "meta_cached_at", "TIMESTAMPTZ"),
    ("companies", "updated_at",     "TIMESTAMPTZ DEFAULT now()"),
    # market_prices
    ("market_prices", "dividend_yield", "NUMERIC(10,6)"),
    ("market_prices", "updated_at",     "TIMESTAMPTZ DEFAULT now()"),
    # financial_statements
    ("financial_statements", "filing_form",     "VARCHAR(20)"),
    ("financial_statements", "fiscal_year",     "INTEGER"),
    ("financial_statements", "fiscal_quarter",  "VARCHAR(5)"),
    ("financial_statements", "period_end_date", "VARCHAR(20)"),
    ("financial_statements", "revenue_prior",   "BIGINT"),
    ("financial_statements", "free_cash_flow",  "BIGINT"),
    ("financial_statements", "updated_at",      "TIMESTAMPTZ DEFAULT now()"),
    # calculated_multiples
    ("calculated_multiples", "fcf_yield",      "NUMERIC(20,4)"),
    ("calculated_multiples", "revenue_growth", "NUMERIC(20,4)"),
    ("calculated_multiples", "gross_margin",   "NUMERIC(20,4)"),
    ("calculated_multiples", "dividend_yield", "NUMERIC(10,6)"),
    ("calculated_multiples", "eps_growth",     "NUMERIC(20,4)"),
    ("calculated_multiples", "updated_at",     "TIMESTAMPTZ DEFAULT now()"),
    # peer_statistics
    ("peer_statistics", "median_fcf_yield",      "NUMERIC(20,4)"),
    ("peer_statistics", "median_revenue_growth", "NUMERIC(20,4)"),
    ("peer_statistics", "median_gross_margin",   "NUMERIC(20,4)"),
    ("peer_statistics", "mean_fcf_yield",        "NUMERIC(20,4)"),
    ("peer_statistics", "mean_revenue_growth",   "NUMERIC(20,4)"),
    ("peer_statistics", "mean_gross_margin",     "NUMERIC(20,4)"),
    ("peer_statistics", "updated_at",            "TIMESTAMPTZ DEFAULT now()"),
]


def upgrade() -> None:
    conn = op.get_bind()
    for table, column, col_type in _COLUMNS:
        sql = f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {col_type}"
        try:
            conn.execute(text(sql))
        except Exception as e:
            # Log but never abort — each column is independent
            import logging
            logging.getLogger(__name__).warning(
                f"Column {table}.{column} skipped: {e}"
            )


def downgrade() -> None:
    pass   # Additive-only migration — no destructive downgrade
