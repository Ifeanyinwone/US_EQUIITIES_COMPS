"""Add current TTM/annualized valuation fields.

The obsolete analyst/news fields are intentionally not created.
All changes are additive and idempotent.
"""
from alembic import op
from sqlalchemy import text

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None

_COLUMNS = [
    ("financial_statements", "operating_cash_flow", "BIGINT"),
    ("financial_statements", "annualized_revenue", "BIGINT"),
    ("financial_statements", "annualized_gross_profit", "BIGINT"),
    ("financial_statements", "annualized_ebitda", "BIGINT"),
    ("financial_statements", "annualized_ebit", "BIGINT"),
    ("financial_statements", "annualized_net_income", "BIGINT"),
    ("financial_statements", "annualized_eps_diluted", "NUMERIC(20,4)"),
    ("financial_statements", "annualized_operating_cash_flow", "BIGINT"),
    ("financial_statements", "annualized_free_cash_flow", "BIGINT"),
    ("financial_statements", "ttm_revenue", "BIGINT"),
    ("financial_statements", "ttm_gross_profit", "BIGINT"),
    ("financial_statements", "ttm_ebitda", "BIGINT"),
    ("financial_statements", "ttm_ebit", "BIGINT"),
    ("financial_statements", "ttm_net_income", "BIGINT"),
    ("financial_statements", "ttm_eps_diluted", "NUMERIC(20,4)"),
    ("financial_statements", "ttm_operating_cash_flow", "BIGINT"),
    ("financial_statements", "ttm_free_cash_flow", "BIGINT"),
    ("financial_statements", "financial_basis", "VARCHAR(30)"),
    ("financial_statements", "interim_period_months", "INTEGER"),
    ("calculated_multiples", "financial_basis", "VARCHAR(30)"),
    ("calculated_multiples", "pe_basis", "VARCHAR(30)"),
    ("calculated_multiples", "ev_ebitda_basis", "VARCHAR(30)"),
    ("calculated_multiples", "ev_sales_basis", "VARCHAR(30)"),
    ("calculated_multiples", "fcf_yield_basis", "VARCHAR(30)"),
]


def upgrade() -> None:
    conn = op.get_bind()
    for table, column, data_type in _COLUMNS:
        conn.execute(
            text(
                f"ALTER TABLE {table} "
                f"ADD COLUMN IF NOT EXISTS {column} {data_type}"
            )
        )


def downgrade() -> None:
    pass
