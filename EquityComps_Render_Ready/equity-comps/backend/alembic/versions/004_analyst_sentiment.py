"""Legacy migration placeholder.

Analyst sentiment is no longer part of EquityComps. This revision is kept as
an empty compatibility node so existing Alembic databases retain a valid
linear history without creating obsolete tables.
"""
from alembic import op

revision = "004_analyst_sentiment"
down_revision = "003_eps_de_opp"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
