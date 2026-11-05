"""Add wallet withdrawal tracking for RazorpayX payouts.

Revision ID: 018_wallet_withdrawals
Revises: 017_search_events
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "018_wallet_withdrawals"
down_revision: Union[str, None] = "017_search_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "wallet_withdrawals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("payout_id", sa.String(length=64), nullable=True),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="INR"),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="PROCESSING"),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("bank_account_holder_name", sa.String(length=100), nullable=False),
        sa.Column("bank_account_last4", sa.String(length=4), nullable=False),
        sa.Column("bank_ifsc", sa.String(length=11), nullable=False),
        sa.Column("wallet_transaction_group_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("payout_id"),
    )
    op.create_index("ix_wallet_withdrawals_id", "wallet_withdrawals", ["id"])
    op.create_index("ix_wallet_withdrawals_user_id", "wallet_withdrawals", ["user_id"])
    op.create_index("ix_wallet_withdrawals_payout_id", "wallet_withdrawals", ["payout_id"])
    op.create_index("ix_wallet_withdrawals_status", "wallet_withdrawals", ["status"])
    op.create_index("ix_wallet_withdrawals_wallet_transaction_group_id", "wallet_withdrawals", ["wallet_transaction_group_id"])


def downgrade() -> None:
    op.drop_table("wallet_withdrawals")
