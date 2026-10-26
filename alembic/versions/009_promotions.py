"""Promotions table

Revision ID: 009_promotions
Revises: 008_merchant_favorites
Create Date: 2026-10-26 17:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009_promotions"
down_revision: Union[str, None] = "008_merchant_favorites"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    if "promotions" in sa.inspect(conn).get_table_names():
        return

    op.create_table(
        "promotions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("subtitle", sa.String(length=255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("image_url", sa.String(length=500), nullable=True),
        sa.Column("link_url", sa.String(length=500), nullable=True),
        sa.Column("discount_label", sa.String(length=120), nullable=True),
        sa.Column("promo_code", sa.String(length=64), nullable=True),
        sa.Column("merchant_profile_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ACTIVE"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["merchant_profile_id"],
            ["merchant_profiles.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_promotions_id"), "promotions", ["id"], unique=False)
    op.create_index(op.f("ix_promotions_title"), "promotions", ["title"], unique=False)
    op.create_index(op.f("ix_promotions_promo_code"), "promotions", ["promo_code"], unique=False)
    op.create_index(op.f("ix_promotions_merchant_profile_id"), "promotions", ["merchant_profile_id"], unique=False)
    op.create_index(op.f("ix_promotions_status"), "promotions", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_promotions_status"), table_name="promotions")
    op.drop_index(op.f("ix_promotions_merchant_profile_id"), table_name="promotions")
    op.drop_index(op.f("ix_promotions_promo_code"), table_name="promotions")
    op.drop_index(op.f("ix_promotions_title"), table_name="promotions")
    op.drop_index(op.f("ix_promotions_id"), table_name="promotions")
    op.drop_table("promotions")
