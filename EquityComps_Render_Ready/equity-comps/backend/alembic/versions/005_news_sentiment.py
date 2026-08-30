"""Legacy migration placeholder.

News sentiment is no longer part of EquityComps. Kept only as a compatibility
node in the historical Alembic chain.
"""
from alembic import op

revision = "005_news_sentiment"
down_revision = "004_analyst_sentiment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
