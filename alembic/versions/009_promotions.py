"""Promotions (legacy schema) and community products tables

Revision ID: 009_promotions
Revises: 008_merchant_favorites
Create Date: 2026-10-26 17:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009_promotions"
down_revision: Union[str, None] = "008_merchant_favorites"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = insp.get_table_names()

    if "promotions" not in tables:
        op.create_table(
            "promotions",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("promo_code", sa.String(length=50), nullable=True),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("category", sa.String(length=100), nullable=True),
            sa.Column("type", sa.String(length=50), nullable=False, server_default="Featured"),
            sa.Column("placement", sa.String(length=255), nullable=True),
            sa.Column("location", sa.String(length=255), nullable=True),
            sa.Column("start_date", sa.String(length=50), nullable=True),
            sa.Column("end_date", sa.String(length=50), nullable=True),
            sa.Column("status", sa.String(length=50), nullable=False, server_default="active"),
            sa.Column("impressions", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("clicks", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("image_url", sa.String(length=500), nullable=True),
            sa.Column("video_url", sa.String(length=500), nullable=True),
            sa.Column("media_type", sa.String(length=20), nullable=False, server_default="image"),
            sa.Column("thumbnail_url", sa.String(length=500), nullable=True),
            sa.Column("target_url", sa.String(length=500), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("merchant_id", sa.Integer(), nullable=True),
            sa.Column("merchant_name", sa.String(length=255), nullable=True),
            sa.Column("rejection_reason", sa.String(length=500), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_promotions_id"), "promotions", ["id"], unique=False)
        op.create_index(op.f("ix_promotions_promo_code"), "promotions", ["promo_code"], unique=True)
        op.create_index(op.f("ix_promotions_status"), "promotions", ["status"], unique=False)
        op.create_index(op.f("ix_promotions_merchant_id"), "promotions", ["merchant_id"], unique=False)
    else:
        cols = {c["name"] for c in insp.get_columns("promotions")}
        if "video_url" not in cols:
            op.add_column("promotions", sa.Column("video_url", sa.String(length=500), nullable=True))
        if "media_type" not in cols:
            op.add_column(
                "promotions",
                sa.Column("media_type", sa.String(length=20), nullable=False, server_default="image"),
            )
        if "thumbnail_url" not in cols:
            op.add_column("promotions", sa.Column("thumbnail_url", sa.String(length=500), nullable=True))
        if "description" not in cols:
            op.add_column("promotions", sa.Column("description", sa.Text(), nullable=True))

    user_cols = {c["name"] for c in insp.get_columns("users")}
    if "can_sell_products" not in user_cols:
        op.add_column(
            "users",
            sa.Column("can_sell_products", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        )
    if "is_subscriber" not in user_cols:
        op.add_column(
            "users",
            sa.Column("is_subscriber", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        )

    if "merchant_profiles" in tables:
        merch_cols = {c["name"] for c in insp.get_columns("merchant_profiles")}
        if "can_create_promotions" not in merch_cols:
            op.add_column(
                "merchant_profiles",
                sa.Column("can_create_promotions", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            )

    if "customer_products" not in tables:
        op.create_table(
            "customer_products",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("seller_id", sa.Integer(), nullable=False),
            sa.Column("seller_name", sa.String(length=255), nullable=True),
            sa.Column("seller_phone", sa.String(length=50), nullable=True),
            sa.Column("seller_whatsapp", sa.String(length=50), nullable=True),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("category", sa.String(length=100), nullable=False, server_default="General"),
            sa.Column("price", sa.Numeric(10, 2), nullable=False),
            sa.Column("original_price", sa.Numeric(10, 2), nullable=True),
            sa.Column("images", sa.JSON(), nullable=True),
            sa.Column("sizes", sa.JSON(), nullable=True),
            sa.Column("stock_status", sa.String(length=50), nullable=False, server_default="IN_STOCK"),
            sa.Column("district", sa.String(length=100), nullable=True),
            sa.Column("city", sa.String(length=100), nullable=True),
            sa.Column("location", sa.String(length=255), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("approval_status", sa.String(length=50), nullable=False, server_default="APPROVED"),
            sa.Column("rejection_reason", sa.Text(), nullable=True),
            sa.Column("views_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("orders_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["seller_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_customer_products_id"), "customer_products", ["id"], unique=False)
        op.create_index(op.f("ix_customer_products_seller_id"), "customer_products", ["seller_id"], unique=False)
        op.create_index(op.f("ix_customer_products_name"), "customer_products", ["name"], unique=False)
        op.create_index(op.f("ix_customer_products_category"), "customer_products", ["category"], unique=False)
        op.create_index(op.f("ix_customer_products_district"), "customer_products", ["district"], unique=False)
        op.create_index(op.f("ix_customer_products_is_active"), "customer_products", ["is_active"], unique=False)
        op.create_index(
            op.f("ix_customer_products_approval_status"),
            "customer_products",
            ["approval_status"],
            unique=False,
        )

    if "product_orders" not in tables:
        op.create_table(
            "product_orders",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("order_code", sa.String(length=50), nullable=False),
            sa.Column("product_id", sa.Integer(), nullable=False),
            sa.Column("seller_id", sa.Integer(), nullable=False),
            sa.Column("buyer_name", sa.String(length=255), nullable=False),
            sa.Column("buyer_phone", sa.String(length=50), nullable=False),
            sa.Column("buyer_address", sa.Text(), nullable=False),
            sa.Column("buyer_location", sa.String(length=255), nullable=True),
            sa.Column("buyer_city", sa.String(length=100), nullable=True),
            sa.Column("buyer_district", sa.String(length=100), nullable=True),
            sa.Column("buyer_pincode", sa.String(length=20), nullable=False),
            sa.Column("selected_size", sa.String(length=50), nullable=True),
            sa.Column("quantity", sa.Integer(), nullable=False, server_default=sa.text("1")),
            sa.Column("total_price", sa.Numeric(10, 2), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=50), nullable=False, server_default="PENDING"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["product_id"], ["customer_products.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["seller_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("order_code"),
        )
        op.create_index(op.f("ix_product_orders_id"), "product_orders", ["id"], unique=False)
        op.create_index(op.f("ix_product_orders_order_code"), "product_orders", ["order_code"], unique=True)
        op.create_index(op.f("ix_product_orders_product_id"), "product_orders", ["product_id"], unique=False)
        op.create_index(op.f("ix_product_orders_seller_id"), "product_orders", ["seller_id"], unique=False)
        op.create_index(op.f("ix_product_orders_buyer_phone"), "product_orders", ["buyer_phone"], unique=False)


def downgrade() -> None:
    op.drop_table("product_orders")
    op.drop_table("customer_products")
