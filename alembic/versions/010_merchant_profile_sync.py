"""Add missing merchant_profiles columns for API compatibility

Revision ID: 010_merchant_profile_sync
Revises: 009_promotions
Create Date: 2026-10-27 10:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "010_merchant_profile_sync"
down_revision: Union[str, None] = "009_promotions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_column_if_missing(table: str, name: str, column: sa.Column) -> None:
    conn = op.get_bind()
    cols = {c["name"] for c in sa.inspect(conn).get_columns(table)}
    if name not in cols:
        op.add_column(table, column)


def upgrade() -> None:
    conn = op.get_bind()
    if "merchant_profiles" not in sa.inspect(conn).get_table_names():
        return

    optional_string = lambda length: sa.Column(sa.String(length), nullable=True)
    optional_text = sa.Column(sa.Text(), nullable=True)

    columns = [
        ("user_code", optional_string(50)),
        ("owner", optional_string(255)),
        ("owner_name", optional_string(255)),
        ("category", optional_string(150)),
        ("city", optional_string(100)),
        ("district", optional_string(100)),
        ("state", optional_string(100)),
        ("landmark", optional_string(255)),
        ("phone", optional_string(20)),
        ("whatsapp", optional_string(20)),
        ("landline", optional_string(20)),
        ("email", optional_string(255)),
        ("website", optional_string(255)),
        ("facebook", optional_string(255)),
        ("instagram", optional_string(255)),
        ("twitter", optional_string(255)),
        ("youtube", optional_string(255)),
        ("photo_1", optional_text),
        ("photo_2", optional_text),
        ("photo_3", optional_text),
        ("photo_4", optional_text),
        ("photo_5", optional_text),
        ("photo_6", optional_text),
        ("about", optional_text),
        ("video_url", optional_text),
        ("status", sa.Column(sa.String(50), nullable=False, server_default="PENDING")),
        ("onboarded_by_id", sa.Column(sa.Integer(), nullable=True)),
        ("latitude", sa.Column(sa.Numeric(10, 8), nullable=True)),
        ("longitude", sa.Column(sa.Numeric(11, 8), nullable=True)),
        ("rating", sa.Column(sa.Numeric(3, 2), nullable=True, server_default=sa.text("0"))),
        ("reviews_count", sa.Column(sa.Integer(), nullable=False, server_default=sa.text("0"))),
        ("key_highlights", sa.Column(sa.JSON(), nullable=True)),
        ("merchant_videos", sa.Column(sa.JSON(), nullable=True)),
        ("verification_documents", sa.Column(sa.JSON(), nullable=True)),
    ]

    for name, col in columns:
        _add_column_if_missing("merchant_profiles", name, col)


def downgrade() -> None:
    pass
