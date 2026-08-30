"""Legacy migration placeholder.

The old analyst/news provider layer has been removed. This revision remains
in the chain so existing databases can migrate safely to the current schema.
"""
from alembic import op

revision = "006"
down_revision = "005_news_sentiment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
