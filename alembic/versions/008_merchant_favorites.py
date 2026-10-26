"""Merchant favorites per user

Revision ID: 008_merchant_favorites
Revises: 007_logout_revocation
Create Date: 2026-10-26 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "008_merchant_favorites"
down_revision: Union[str, None] = "007_logout_revocation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    if "merchant_favorites" not in sa.inspect(conn).get_table_names():
        op.create_table(
            "merchant_favorites",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("merchant_profile_id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["merchant_profile_id"], ["merchant_profiles.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "user_id",
                "merchant_profile_id",
                name="uq_user_merchant_favorite",
            ),
        )
        op.create_index("ix_merchant_favorites_user_id", "merchant_favorites", ["user_id"])
        op.create_index(
            "ix_merchant_favorites_merchant_profile_id",
            "merchant_favorites",
            ["merchant_profile_id"],
        )


def downgrade() -> None:
    conn = op.get_bind()
    if "merchant_favorites" in sa.inspect(conn).get_table_names():
        op.drop_table("merchant_favorites")
