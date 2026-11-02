"""Record merchant searches for the admin dashboard

Revision ID: 017_search_events
Revises: 016_merchant_cashback_rates
Create Date: 2026-11-02 14:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "017_search_events"
down_revision: Union[str, None] = "016_merchant_cashback_rates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "search_events" in insp.get_table_names():
        return
    op.create_table(
        "search_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("query", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_search_events_source", "search_events", ["source"])
    op.create_index("ix_search_events_created_at", "search_events", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_search_events_created_at", table_name="search_events")
    op.drop_index("ix_search_events_source", table_name="search_events")
    op.drop_table("search_events")
