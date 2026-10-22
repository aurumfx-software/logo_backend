"""Centralized wallet, ledger, and merchant sale QR tables

Revision ID: 006_wallet_system
Revises: 005_merchant_approval
Create Date: 2026-10-22 10:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "006_wallet_system"
down_revision: Union[str, None] = "005_merchant_approval"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    existing_tables = insp.get_table_names()

    if "wallets" not in existing_tables:
        op.create_table(
            "wallets",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("wallet_type", sa.String(length=32), nullable=False),
            sa.Column("currency", sa.String(length=3), nullable=False, server_default="INR"),
            sa.Column("balance", sa.Numeric(18, 2), nullable=False, server_default="0.00"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id", name="uq_wallets_user_id"),
        )
        op.create_index("ix_wallets_id", "wallets", ["id"])
        op.create_index("ix_wallets_user_id", "wallets", ["user_id"])
        op.create_index("ix_wallets_wallet_type", "wallets", ["wallet_type"])

    if "wallet_transactions" not in existing_tables:
        op.create_table(
            "wallet_transactions",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("group_id", sa.String(length=36), nullable=False),
            sa.Column("transaction_type", sa.String(length=64), nullable=False),
            sa.Column("amount", sa.Numeric(18, 2), nullable=False),
            sa.Column("currency", sa.String(length=3), nullable=False, server_default="INR"),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("initiated_by_user_id", sa.Integer(), nullable=True),
            sa.Column("reference_id", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["initiated_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_wallet_transactions_id", "wallet_transactions", ["id"])
        op.create_index("ix_wallet_transactions_group_id", "wallet_transactions", ["group_id"])
        op.create_index("ix_wallet_transactions_transaction_type", "wallet_transactions", ["transaction_type"])
        op.create_index("ix_wallet_transactions_reference_id", "wallet_transactions", ["reference_id"])
        op.create_index("ix_wallet_transactions_created_at", "wallet_transactions", ["created_at"])

    if "wallet_ledger_entries" not in existing_tables:
        op.create_table(
            "wallet_ledger_entries",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("transaction_id", sa.Integer(), nullable=False),
            sa.Column("wallet_id", sa.Integer(), nullable=False),
            sa.Column("direction", sa.String(length=16), nullable=False),
            sa.Column("amount", sa.Numeric(18, 2), nullable=False),
            sa.Column("balance_after", sa.Numeric(18, 2), nullable=False),
            sa.Column("counterparty_wallet_id", sa.Integer(), nullable=True),
            sa.Column("note", sa.String(length=500), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["counterparty_wallet_id"], ["wallets.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["transaction_id"], ["wallet_transactions.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["wallet_id"], ["wallets.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_wallet_ledger_entries_id", "wallet_ledger_entries", ["id"])
        op.create_index("ix_wallet_ledger_entries_transaction_id", "wallet_ledger_entries", ["transaction_id"])
        op.create_index("ix_wallet_ledger_entries_wallet_id", "wallet_ledger_entries", ["wallet_id"])
        op.create_index("ix_wallet_ledger_entries_created_at", "wallet_ledger_entries", ["created_at"])

    if "merchant_sale_qrs" not in existing_tables:
        op.create_table(
            "merchant_sale_qrs",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("token", sa.String(length=36), nullable=False),
            sa.Column("merchant_profile_id", sa.Integer(), nullable=False),
            sa.Column("merchant_user_id", sa.Integer(), nullable=False),
            sa.Column("sale_amount", sa.Numeric(18, 2), nullable=False),
            sa.Column("currency", sa.String(length=3), nullable=False, server_default="INR"),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("redeemed_by_user_id", sa.Integer(), nullable=True),
            sa.Column("wallet_transaction_group_id", sa.String(length=36), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["merchant_profile_id"], ["merchant_profiles.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["merchant_user_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["redeemed_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("token"),
        )
        op.create_index("ix_merchant_sale_qrs_id", "merchant_sale_qrs", ["id"])
        op.create_index("ix_merchant_sale_qrs_token", "merchant_sale_qrs", ["token"])
        op.create_index("ix_merchant_sale_qrs_merchant_profile_id", "merchant_sale_qrs", ["merchant_profile_id"])
        op.create_index("ix_merchant_sale_qrs_merchant_user_id", "merchant_sale_qrs", ["merchant_user_id"])
        op.create_index("ix_merchant_sale_qrs_status", "merchant_sale_qrs", ["status"])
        op.create_index(
            "ix_merchant_sale_qrs_wallet_transaction_group_id",
            "merchant_sale_qrs",
            ["wallet_transaction_group_id"],
        )


def downgrade() -> None:
    op.drop_table("merchant_sale_qrs")
    op.drop_table("wallet_ledger_entries")
    op.drop_table("wallet_transactions")
    op.drop_table("wallets")
