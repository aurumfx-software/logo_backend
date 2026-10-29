"""Normalize legacy users.role strings for SQLAlchemy loads

Revision ID: 013_normalize_user_roles
Revises: 012_razorpay_wallet_topup
Create Date: 2026-10-29 17:30:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = "013_normalize_user_roles"
down_revision: Union[str, None] = "012_razorpay_wallet_topup"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE users
        SET role = 'SUPER_ADMIN'
        WHERE role IN ('SUPER ADMIN', 'Super Admin', 'SUPERADMIN', 'super_admin')
        """
    )
    op.execute(
        """
        UPDATE users
        SET role = 'FIELD_STAFF'
        WHERE role IN ('PUBLIC_USER', 'PUBLIC USER', 'USER', 'FIELDSTAFF', 'Field Staff')
        """
    )
    op.execute(
        """
        UPDATE users
        SET role = 'MERCHANT'
        WHERE role IN ('MERCHANTS', 'Shop Owner', 'SHOP_OWNER')
        """
    )


def downgrade() -> None:
    pass
