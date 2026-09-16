"""Add address and profile_picture columns to users table

Revision ID: 002_add_address_and_profile_picture
Revises: 001_initial_auth
Create Date: 2026-09-16 18:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "002_user_profile"
down_revision: Union[str, None] = "001_initial_auth"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("address", sa.String(length=500), nullable=True))
    op.add_column("users", sa.Column("profile_picture", sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "profile_picture")
    op.drop_column("users", "address")
