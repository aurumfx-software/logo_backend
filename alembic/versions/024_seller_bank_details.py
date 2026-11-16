"""Seller payout bank account and UPI id.

Revision ID: 024_seller_bank_details
Revises: 023_buyer_commerce
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "024_seller_bank_details"
down_revision: Union[str, None] = "023_buyer_commerce"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "seller_bank_details" in inspector.get_table_names():
        return
    op.create_table(
        "seller_bank_details",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("account_holder_name", sa.String(255), nullable=False),
        sa.Column("bank_name", sa.String(255), nullable=False),
        sa.Column("account_number", sa.String(18), nullable=False),
        sa.Column("ifsc_code", sa.String(11), nullable=False),
        sa.Column("upi_id", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", name="uq_seller_bank_details_user_id"),
    )
    op.create_index("ix_seller_bank_details_user_id", "seller_bank_details", ["user_id"], unique=True)


def downgrade() -> None:
    pass
