"""Login ID for merchants and customers.

Revision ID: 025_user_login_id
Revises: 024_seller_bank_details
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "025_user_login_id"
down_revision: Union[str, None] = "024_seller_bank_details"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "users" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("users")}
    if "login_id" not in columns:
        op.add_column("users", sa.Column("login_id", sa.String(length=20), nullable=True))
        op.create_index("ix_users_login_id", "users", ["login_id"], unique=True)


def downgrade() -> None:
    pass
