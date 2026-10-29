"""Add wallet top-up orders and WALLET_TOPUP transaction type support

Revision ID: 012_razorpay_wallet_topup
Revises: 011_subscription_packages
Create Date: 2026-10-29 15:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "012_razorpay_wallet_topup"
down_revision: Union[str, None] = "011_subscription_packages"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "wallet_topup_orders" in insp.get_table_names():
        return

    op.create_table(
        "wallet_topup_orders",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("merchant_profile_id", sa.Integer(), nullable=True),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("amount_paise", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="INR"),
        sa.Column("receipt", sa.String(length=40), nullable=False),
        sa.Column("razorpay_order_id", sa.String(length=64), nullable=False),
        sa.Column("razorpay_payment_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="CREATED"),
        sa.Column("wallet_transaction_group_id", sa.String(length=36), nullable=True),
        sa.Column("failure_reason", sa.String(length=500), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["merchant_profile_id"], ["merchant_profiles.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("receipt"),
        sa.UniqueConstraint("razorpay_order_id"),
        sa.UniqueConstraint("razorpay_payment_id"),
    )
    op.create_index("ix_wallet_topup_orders_id", "wallet_topup_orders", ["id"])
    op.create_index("ix_wallet_topup_orders_user_id", "wallet_topup_orders", ["user_id"])
    op.create_index("ix_wallet_topup_orders_status", "wallet_topup_orders", ["status"])


def downgrade() -> None:
    op.drop_table("wallet_topup_orders")
