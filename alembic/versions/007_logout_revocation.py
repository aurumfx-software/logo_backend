"""User logout timestamp and revoked JWT table

Revision ID: 007_logout_revocation
Revises: 006_wallet_system
Create Date: 2026-10-26 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "007_logout_revocation"
down_revision: Union[str, None] = "006_wallet_system"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    user_cols = {c["name"] for c in insp.get_columns("users")}

    if "logged_out_at" not in user_cols:
        op.add_column(
            "users",
            sa.Column("logged_out_at", sa.DateTime(timezone=True), nullable=True),
        )

    if "revoked_tokens" not in insp.get_table_names():
        op.create_table(
            "revoked_tokens",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("jti", sa.String(length=64), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("token_type", sa.String(length=20), nullable=False),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("jti", name="uq_revoked_tokens_jti"),
        )
        op.create_index("ix_revoked_tokens_jti", "revoked_tokens", ["jti"])
        op.create_index("ix_revoked_tokens_user_id", "revoked_tokens", ["user_id"])


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "revoked_tokens" in insp.get_table_names():
        op.drop_table("revoked_tokens")
    user_cols = {c["name"] for c in insp.get_columns("users")}
    if "logged_out_at" in user_cols:
        op.drop_column("users", "logged_out_at")
