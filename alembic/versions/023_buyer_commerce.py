"""Buyer addresses, wishlist, cart, reviews, order payments, and courier tracking.

Revision ID: 023_buyer_commerce
Revises: 022_marketplace_order_tracking
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "023_buyer_commerce"
down_revision: Union[str, None] = "022_marketplace_order_tracking"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(inspector, table: str) -> set:
    if table not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    order_columns = _columns(inspector, "product_orders")
    order_adds = {
        "payment_status": sa.Column("payment_status", sa.String(32), nullable=True),
        "payment_method": sa.Column("payment_method", sa.String(32), nullable=True),
        "razorpay_order_id": sa.Column("razorpay_order_id", sa.String(64), nullable=True),
        "razorpay_payment_id": sa.Column("razorpay_payment_id", sa.String(64), nullable=True),
        "cancellation_reason": sa.Column("cancellation_reason", sa.String(500), nullable=True),
        "cancelled_at": sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        "courier_partner": sa.Column("courier_partner", sa.String(100), nullable=True),
        "tracking_number": sa.Column("tracking_number", sa.String(64), nullable=True),
        "tracking_url": sa.Column("tracking_url", sa.String(500), nullable=True),
        "estimated_delivery_at": sa.Column("estimated_delivery_at", sa.DateTime(timezone=True), nullable=True),
        "courier_events": sa.Column("courier_events", sa.JSON(), nullable=True),
    }
    for name, column in order_adds.items():
        if order_columns and name not in order_columns:
            op.add_column("product_orders", column)
    product_columns = _columns(inspector, "customer_products")
    for name in ("rating_sum", "rating_count"):
        if product_columns and name not in product_columns:
            op.add_column("customer_products", sa.Column(name, sa.Integer(), nullable=True))

    tables = set(inspector.get_table_names())
    if "delivery_addresses" not in tables:
        op.create_table(
            "delivery_addresses",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("label", sa.String(50), nullable=False),
            sa.Column("recipient_name", sa.String(255), nullable=False),
            sa.Column("phone", sa.String(50), nullable=False),
            sa.Column("address_line", sa.Text(), nullable=False),
            sa.Column("location", sa.String(255), nullable=True),
            sa.Column("city", sa.String(100), nullable=True),
            sa.Column("district", sa.String(100), nullable=True),
            sa.Column("pincode", sa.String(20), nullable=False),
            sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_delivery_addresses_user_id", "delivery_addresses", ["user_id"])
    if "product_wishlists" not in tables:
        op.create_table(
            "product_wishlists",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("product_id", sa.Integer(), sa.ForeignKey("customer_products.id", ondelete="CASCADE"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("user_id", "product_id", name="uq_user_product_wishlist"),
        )
        op.create_index("ix_product_wishlists_user_id", "product_wishlists", ["user_id"])
    if "cart_items" not in tables:
        op.create_table(
            "cart_items",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("product_id", sa.Integer(), sa.ForeignKey("customer_products.id", ondelete="CASCADE"), nullable=False),
            sa.Column("selected_size", sa.String(50), nullable=False, server_default=""),
            sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("user_id", "product_id", "selected_size", name="uq_user_cart_product_size"),
        )
        op.create_index("ix_cart_items_user_id", "cart_items", ["user_id"])
    if "product_reviews" not in tables:
        op.create_table(
            "product_reviews",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("product_id", sa.Integer(), sa.ForeignKey("customer_products.id", ondelete="CASCADE"), nullable=False),
            sa.Column("order_id", sa.Integer(), sa.ForeignKey("product_orders.id", ondelete="CASCADE"), nullable=False),
            sa.Column("buyer_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("rating", sa.Integer(), nullable=False),
            sa.Column("title", sa.String(120), nullable=True),
            sa.Column("comment", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("order_id", name="uq_product_review_order"),
        )
        op.create_index("ix_product_reviews_product_id", "product_reviews", ["product_id"])


def downgrade() -> None:
    pass
