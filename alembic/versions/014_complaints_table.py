"""Create complaints table for support tickets

Revision ID: 014_complaints_table
Revises: 013_normalize_user_roles
Create Date: 2026-10-29 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "014_complaints_table"
down_revision: Union[str, None] = "013_normalize_user_roles"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "complaints" in insp.get_table_names():
        return

    op.create_table(
        "complaints",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("complaint_code", sa.String(length=50), nullable=True),
        sa.Column("user", sa.String(length=255), nullable=False),
        sa.Column("user_email", sa.String(length=255), nullable=True),
        sa.Column("user_phone", sa.String(length=50), nullable=True),
        sa.Column("merchant", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False, server_default="General"),
        sa.Column("priority", sa.String(length=50), nullable=False, server_default="medium"),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="open"),
        sa.Column("date", sa.String(length=50), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("admin_response", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_complaints_id"), "complaints", ["id"], unique=False)
    op.create_index(op.f("ix_complaints_complaint_code"), "complaints", ["complaint_code"], unique=True)
    op.create_index(op.f("ix_complaints_status"), "complaints", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_complaints_status"), table_name="complaints")
    op.drop_index(op.f("ix_complaints_complaint_code"), table_name="complaints")
    op.drop_index(op.f("ix_complaints_id"), table_name="complaints")
    op.drop_table("complaints")
