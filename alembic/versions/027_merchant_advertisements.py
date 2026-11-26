"""Store merchant advertisements shown on the merchant details screen.

Revision ID: 027_merchant_advertisements
Revises: 026_wallet_source_pool
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "027_merchant_advertisements"
down_revision: Union[str, None] = "026_wallet_source_pool"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "merchant_advertisements" in inspector.get_table_names():
        return
    op.create_table(
        "merchant_advertisements",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("merchant_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("image_url", sa.String(length=500), nullable=True),
        sa.Column("video_url", sa.String(length=500), nullable=True),
        sa.Column("link_url", sa.String(length=500), nullable=True),
        sa.Column("start_date", sa.String(length=50), nullable=True),
        sa.Column("end_date", sa.String(length=50), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_merchant_advertisements_merchant_id", "merchant_advertisements", ["merchant_id"])
    op.create_index("ix_merchant_advertisements_status", "merchant_advertisements", ["status"])


def downgrade() -> None:
    pass
