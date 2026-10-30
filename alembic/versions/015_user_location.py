"""Add location coordinates on users

Revision ID: 015_user_location
Revises: 014_complaints_table
Create Date: 2026-10-30 11:25:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "015_user_location"
down_revision: Union[str, None] = "014_complaints_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing = {col["name"] for col in insp.get_columns("users")}
    if "location" not in existing:
        op.add_column("users", sa.Column("location", sa.String(length=255), nullable=True))
    if "latitude" not in existing:
        op.add_column("users", sa.Column("latitude", sa.Numeric(10, 8), nullable=True))
    if "longitude" not in existing:
        op.add_column("users", sa.Column("longitude", sa.Numeric(11, 8), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing = {col["name"] for col in insp.get_columns("users")}
    if "longitude" in existing:
        op.drop_column("users", "longitude")
    if "latitude" in existing:
        op.drop_column("users", "latitude")
    if "location" in existing:
        op.drop_column("users", "location")
