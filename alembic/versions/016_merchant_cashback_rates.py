"""Store per-merchant cashback and company fee percents

Revision ID: 016_merchant_cashback_rates
Revises: 015_user_location
Create Date: 2026-10-30 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "016_merchant_cashback_rates"
down_revision: Union[str, None] = "015_user_location"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing = {col["name"] for col in insp.get_columns("merchant_profiles")}
    if "cashback_percent" not in existing:
        op.add_column(
            "merchant_profiles",
            sa.Column("cashback_percent", sa.Numeric(5, 2), nullable=False, server_default="3"),
        )
    if "company_fee_percent" not in existing:
        op.add_column(
            "merchant_profiles",
            sa.Column("company_fee_percent", sa.Numeric(5, 2), nullable=False, server_default="2"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing = {col["name"] for col in insp.get_columns("merchant_profiles")}
    if "company_fee_percent" in existing:
        op.drop_column("merchant_profiles", "company_fee_percent")
    if "cashback_percent" in existing:
        op.drop_column("merchant_profiles", "cashback_percent")
