"""Tag wallet transactions with the platform card they belong to.

Revision ID: 026_wallet_source_pool
Revises: 025_user_login_id
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "026_wallet_source_pool"
down_revision: Union[str, None] = "025_user_login_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "wallet_transactions" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("wallet_transactions")}
    if "source_pool" not in columns:
        op.add_column("wallet_transactions", sa.Column("source_pool", sa.String(length=32), nullable=True))
        op.create_index("ix_wallet_transactions_source_pool", "wallet_transactions", ["source_pool"])


def downgrade() -> None:
    pass
