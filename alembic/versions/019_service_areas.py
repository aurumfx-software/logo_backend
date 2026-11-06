"""Add Kerala service areas for the geography screen.

Revision ID: 019_service_areas
Revises: 018_wallet_withdrawals
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "019_service_areas"
down_revision: Union[str, None] = "018_wallet_withdrawals"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "service_areas",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("district", sa.String(length=100), nullable=False),
        sa.Column("town", sa.String(length=150), nullable=False),
        sa.Column("zones", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("district", "town", name="uq_service_areas_district_town"),
    )
    op.create_index("ix_service_areas_district", "service_areas", ["district"])
    op.create_index("ix_service_areas_town", "service_areas", ["town"])


def downgrade() -> None:
    op.drop_index("ix_service_areas_town", table_name="service_areas")
    op.drop_index("ix_service_areas_district", table_name="service_areas")
    op.drop_table("service_areas")
