"""Store RazorpayX payout id on wallet withdrawals.

Revision ID: 020_withdrawal_payout_id
Revises: 019_service_areas
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "020_withdrawal_payout_id"
down_revision: Union[str, None] = "019_service_areas"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "wallet_withdrawals" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("wallet_withdrawals")}
    if "payout_id" not in existing:
        op.add_column("wallet_withdrawals", sa.Column("payout_id", sa.String(length=64), nullable=True))
        op.create_index("ix_wallet_withdrawals_payout_id_model", "wallet_withdrawals", ["payout_id"], unique=True)
    if "fund_account_id" not in existing:
        op.add_column("wallet_withdrawals", sa.Column("fund_account_id", sa.String(length=64), nullable=True))
    if "razorpay_status" not in existing:
        op.add_column("wallet_withdrawals", sa.Column("razorpay_status", sa.String(length=32), nullable=True))
    if "failure_reason" not in existing:
        op.add_column("wallet_withdrawals", sa.Column("failure_reason", sa.String(length=500), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "wallet_withdrawals" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("wallet_withdrawals")}
    if "failure_reason" in existing:
        op.drop_column("wallet_withdrawals", "failure_reason")
    if "razorpay_status" in existing:
        op.drop_column("wallet_withdrawals", "razorpay_status")
    if "fund_account_id" in existing:
        op.drop_column("wallet_withdrawals", "fund_account_id")
    if "payout_id" in existing:
        op.drop_index("ix_wallet_withdrawals_payout_id_model", table_name="wallet_withdrawals")
        op.drop_column("wallet_withdrawals", "payout_id")
