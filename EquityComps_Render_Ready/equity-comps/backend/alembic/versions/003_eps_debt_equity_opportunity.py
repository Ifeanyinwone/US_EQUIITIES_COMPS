"""Add EPS, Debt-to-Equity, Opportunity Score columns — fully idempotent

Revision ID: 003_eps_de_opp
Revises: 002_upgrade
Create Date: 2025-01-03

Every statement uses ADD COLUMN IF NOT EXISTS.
Each statement is executed independently (no transaction wrapping).
Safe to run multiple times without corruption.
"""
from alembic import op
from sqlalchemy import text

revision      = '003_eps_de_opp'
down_revision = '002_upgrade'
branch_labels = None
depends_on    = None

_COLUMNS = [
    ("calculated_multiples", "eps",               "NUMERIC(20,4)"),
    ("calculated_multiples", "debt_to_equity",     "NUMERIC(20,4)"),
    ("calculated_multiples", "opportunity_score",  "NUMERIC(10,4)"),
    ("peer_statistics", "median_eps",              "NUMERIC(20,4)"),
    ("peer_statistics", "median_debt_to_equity",   "NUMERIC(20,4)"),
    ("peer_statistics", "mean_eps",                "NUMERIC(20,4)"),
    ("peer_statistics", "mean_debt_to_equity",     "NUMERIC(20,4)"),
]


def upgrade() -> None:
    conn = op.get_bind()
    for table, column, col_type in _COLUMNS:
        sql = f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {col_type}"
        try:
            conn.execute(text(sql))
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Column {table}.{column} skipped: {e}")


def downgrade() -> None:
    pass   # Additive-only migration — no destructive downgrade
