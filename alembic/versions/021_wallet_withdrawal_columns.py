"""Add missing wallet withdrawal columns used by the payout model.

Revision ID: 021_wallet_withdrawal_columns
Revises: 020_withdrawal_payout_id
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "021_wallet_withdrawal_columns"
down_revision: Union[str, None] = "020_withdrawal_payout_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_COLUMNS = (
    ("transaction_group_id", sa.String(length=36)),
    ("wallet_id", sa.Integer()),
    ("account_holder_name", sa.String(length=255)),
    ("account_number", sa.String(length=64)),
    ("ifsc", sa.String(length=32)),
    ("payout_mode", sa.String(length=16)),
    ("payout_id", sa.String(length=64)),
    ("fund_account_id", sa.String(length=64)),
    ("razorpay_status", sa.String(length=32)),
    ("failure_reason", sa.String(length=500)),
    ("admin_note", sa.String(length=500)),
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "wallet_withdrawals" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("wallet_withdrawals")}
    for name, column_type in _COLUMNS:
        if name not in existing:
            op.add_column("wallet_withdrawals", sa.Column(name, column_type, nullable=True))
    if "payout_id" not in existing:
        op.create_index(
            "ix_wallet_withdrawals_payout_id_model",
            "wallet_withdrawals",
            ["payout_id"],
            unique=True,
        )


def downgrade() -> None:
    pass
