"""Add video_url, media_type, and thumbnail_url to promotions table

Revision ID: 006_promotion_media_fields
Revises: 005_merchant_approval
Create Date: 2026-10-09 11:35:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic (max 32 chars in alembic_version table)
revision: str = "006_promotion_media_fields"
down_revision: Union[str, None] = "005_merchant_approval"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    existing_tables = insp.get_table_names()

    if "promotions" in existing_tables:
        existing_cols = [c["name"] for c in insp.get_columns("promotions")]

        if "video_url" not in existing_cols:
            op.add_column(
                "promotions",
                sa.Column("video_url", sa.String(length=500), nullable=True),
            )

        if "media_type" not in existing_cols:
            op.add_column(
                "promotions",
                sa.Column("media_type", sa.String(length=20), nullable=False, server_default="image"),
            )

        if "thumbnail_url" not in existing_cols:
            op.add_column(
                "promotions",
                sa.Column("thumbnail_url", sa.String(length=500), nullable=True),
            )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    existing_tables = insp.get_table_names()

    if "promotions" in existing_tables:
        existing_cols = [c["name"] for c in insp.get_columns("promotions")]

        if "thumbnail_url" in existing_cols:
            op.drop_column("promotions", "thumbnail_url")

        if "media_type" in existing_cols:
            op.drop_column("promotions", "media_type")

        if "video_url" in existing_cols:
            op.drop_column("promotions", "video_url")
