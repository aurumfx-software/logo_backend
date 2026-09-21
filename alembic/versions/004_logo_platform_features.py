"""Create categories, logos, and logo_favorites tables

Revision ID: 004_logo_platform_features
Revises: 003_merchant_profiles
Create Date: 2026-09-17 18:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "004_logo_platform_features"
down_revision: Union[str, None] = "003_merchant_profiles"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create categories table
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("icon_url", sa.String(length=500), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index(op.f("ix_categories_id"), "categories", ["id"], unique=False)
    op.create_index(op.f("ix_categories_name"), "categories", ["name"], unique=True)
    op.create_index(op.f("ix_categories_slug"), "categories", ["slug"], unique=True)

    # 2. Create logos table
    op.create_table(
        "logos",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("image_url", sa.String(length=500), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("submitted_by_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="PENDING"),
        sa.Column("rejection_reason", sa.String(length=500), nullable=True),
        sa.Column("reviewed_by_id", sa.Integer(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("views_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("favorites_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["submitted_by_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewed_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_logos_id"), "logos", ["id"], unique=False)
    op.create_index(op.f("ix_logos_title"), "logos", ["title"], unique=False)
    op.create_index(op.f("ix_logos_category_id"), "logos", ["category_id"], unique=False)
    op.create_index(op.f("ix_logos_submitted_by_id"), "logos", ["submitted_by_id"], unique=False)
    op.create_index(op.f("ix_logos_status"), "logos", ["status"], unique=False)

    # 3. Create logo_favorites table
    op.create_table(
        "logo_favorites",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("logo_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["logo_id"], ["logos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "logo_id", name="uq_user_logo_favorite"),
    )
    op.create_index(op.f("ix_logo_favorites_id"), "logo_favorites", ["id"], unique=False)
    op.create_index(op.f("ix_logo_favorites_user_id"), "logo_favorites", ["user_id"], unique=False)
    op.create_index(op.f("ix_logo_favorites_logo_id"), "logo_favorites", ["logo_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_logo_favorites_logo_id"), table_name="logo_favorites")
    op.drop_index(op.f("ix_logo_favorites_user_id"), table_name="logo_favorites")
    op.drop_index(op.f("ix_logo_favorites_id"), table_name="logo_favorites")
    op.drop_table("logo_favorites")

    op.drop_index(op.f("ix_logos_status"), table_name="logos")
    op.drop_index(op.f("ix_logos_submitted_by_id"), table_name="logos")
    op.drop_index(op.f("ix_logos_category_id"), table_name="logos")
    op.drop_index(op.f("ix_logos_title"), table_name="logos")
    op.drop_index(op.f("ix_logos_id"), table_name="logos")
    op.drop_table("logos")

    op.drop_index(op.f("ix_categories_slug"), table_name="categories")
    op.drop_index(op.f("ix_categories_name"), table_name="categories")
    op.drop_index(op.f("ix_categories_id"), table_name="categories")
    op.drop_table("categories")
