"""Create merchant_profiles table

Revision ID: 003_merchant_profiles
Revises: 002_user_profile
Create Date: 2026-09-16 18:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "003_merchant_profiles"
down_revision: Union[str, None] = "002_user_profile"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "merchant_profiles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("business_name", sa.String(length=255), nullable=False),
        sa.Column("categories", sa.JSON(), nullable=False),
        sa.Column("location", sa.String(length=255), nullable=False),
        sa.Column("services", sa.JSON(), nullable=False),
        sa.Column("service_timing", sa.String(length=255), nullable=False),
        sa.Column("merchant_photos", sa.JSON(), nullable=False),
        sa.Column("contact_number", sa.String(length=50), nullable=False),
        sa.Column("address", sa.String(length=500), nullable=False),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index(op.f("ix_merchant_profiles_id"), "merchant_profiles", ["id"], unique=False)
    op.create_index(op.f("ix_merchant_profiles_user_id"), "merchant_profiles", ["user_id"], unique=True)
    op.create_index(op.f("ix_merchant_profiles_business_name"), "merchant_profiles", ["business_name"], unique=False)
    op.create_index(op.f("ix_merchant_profiles_location"), "merchant_profiles", ["location"], unique=False)
    op.create_index(op.f("ix_merchant_profiles_contact_number"), "merchant_profiles", ["contact_number"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_merchant_profiles_contact_number"), table_name="merchant_profiles")
    op.drop_index(op.f("ix_merchant_profiles_location"), table_name="merchant_profiles")
    op.drop_index(op.f("ix_merchant_profiles_business_name"), table_name="merchant_profiles")
    op.drop_index(op.f("ix_merchant_profiles_user_id"), table_name="merchant_profiles")
    op.drop_index(op.f("ix_merchant_profiles_id"), table_name="merchant_profiles")
    op.drop_table("merchant_profiles")
