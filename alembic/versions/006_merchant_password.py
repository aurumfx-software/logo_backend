"""Add password_hash to merchant_profiles

Revision ID: 006_merchant_password
Revises: 005_merchant_approval
Create Date: 2026-10-29 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "006_merchant_password"
down_revision: Union[str, None] = "005_merchant_approval"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    existing_cols = [c["name"] for c in insp.get_columns("merchant_profiles")]

    if "password_hash" not in existing_cols:
        op.add_column(
            "merchant_profiles",
            sa.Column("password_hash", sa.String(length=255), nullable=True),
        )

    op.execute(
        """
        UPDATE merchant_profiles mp
        SET password_hash = u.password_hash
        FROM users u
        WHERE mp.user_id = u.id
          AND mp.password_hash IS NULL
          AND u.password_hash IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE merchant_profiles mp
        SET email = u.email
        FROM users u
        WHERE mp.user_id = u.id
          AND (mp.email IS NULL OR TRIM(mp.email) = '')
          AND u.email IS NOT NULL
        """
    )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    existing_cols = [c["name"] for c in insp.get_columns("merchant_profiles")]
    if "password_hash" in existing_cols:
        op.drop_column("merchant_profiles", "password_hash")
