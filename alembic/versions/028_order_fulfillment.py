"""Shipment tracking, returns, refunds, and replacements for marketplace orders.

Revision ID: 028_order_fulfillment
Revises: 027_merchant_advertisements
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "028_order_fulfillment"
down_revision: Union[str, None] = "027_merchant_advertisements"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "platform_settings" not in tables:
        op.create_table(
            "platform_settings",
            sa.Column("key", sa.String(length=80), nullable=False),
            sa.Column("value", sa.String(length=255), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("key"),
        )
    if "shipments" not in tables:
        op.create_table(
            "shipments",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("order_id", sa.Integer(), nullable=False),
            sa.Column("courier_name", sa.String(length=120), nullable=True),
            sa.Column("tracking_number", sa.String(length=64), nullable=True),
            sa.Column("tracking_url", sa.String(length=500), nullable=True),
            sa.Column("shipment_status", sa.String(length=40), nullable=False, server_default="ORDER_PLACED"),
            sa.Column("remarks", sa.Text(), nullable=True),
            sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("estimated_delivery", sa.DateTime(timezone=True), nullable=True),
            sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["order_id"], ["product_orders.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("order_id"),
        )
        op.create_index("ix_shipments_order_id", "shipments", ["order_id"])
        op.create_index("ix_shipments_tracking_number", "shipments", ["tracking_number"])
        op.create_index("ix_shipments_shipment_status", "shipments", ["shipment_status"])
    if "shipment_history" not in tables:
        op.create_table(
            "shipment_history",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("shipment_id", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=40), nullable=False),
            sa.Column("location", sa.String(length=255), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("updated_by", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["shipment_id"], ["shipments.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_shipment_history_shipment_id", "shipment_history", ["shipment_id"])
    if "order_returns" not in tables:
        op.create_table(
            "order_returns",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("return_number", sa.String(length=32), nullable=False),
            sa.Column("order_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("return_reason", sa.String(length=80), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("return_type", sa.String(length=32), nullable=False),
            sa.Column("return_status", sa.String(length=40), nullable=False, server_default="REQUESTED"),
            sa.Column("courier_name", sa.String(length=120), nullable=True),
            sa.Column("awb_number", sa.String(length=64), nullable=True),
            sa.Column("shipping_date", sa.String(length=40), nullable=True),
            sa.Column("receipt_url", sa.String(length=500), nullable=True),
            sa.Column("pickup_date", sa.String(length=40), nullable=True),
            sa.Column("pickup_remarks", sa.Text(), nullable=True),
            sa.Column("admin_notes", sa.Text(), nullable=True),
            sa.Column("rejection_reason", sa.String(length=500), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["order_id"], ["product_orders.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("return_number"),
        )
        op.create_index("ix_order_returns_order_id", "order_returns", ["order_id"])
        op.create_index("ix_order_returns_user_id", "order_returns", ["user_id"])
        op.create_index("ix_order_returns_return_status", "order_returns", ["return_status"])
    if "return_items" not in tables:
        op.create_table(
            "return_items",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("return_id", sa.Integer(), nullable=False),
            sa.Column("order_item_id", sa.Integer(), nullable=False),
            sa.Column("product_id", sa.Integer(), nullable=True),
            sa.Column("quantity", sa.Integer(), nullable=False),
            sa.Column("product_condition", sa.String(length=80), nullable=True),
            sa.Column("image_urls", sa.JSON(), nullable=True),
            sa.ForeignKeyConstraint(["return_id"], ["order_returns.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["order_item_id"], ["product_orders.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["product_id"], ["customer_products.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_return_items_return_id", "return_items", ["return_id"])
    if "return_history" not in tables:
        op.create_table(
            "return_history",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("return_id", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=40), nullable=False),
            sa.Column("remarks", sa.Text(), nullable=True),
            sa.Column("updated_by", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["return_id"], ["order_returns.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_return_history_return_id", "return_history", ["return_id"])
    if "refund_transactions" not in tables:
        op.create_table(
            "refund_transactions",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("return_id", sa.Integer(), nullable=False),
            sa.Column("refund_amount", sa.Numeric(12, 2), nullable=False),
            sa.Column("refund_method", sa.String(length=32), nullable=False),
            sa.Column("transaction_reference", sa.String(length=120), nullable=True),
            sa.Column("refund_status", sa.String(length=20), nullable=False, server_default="PENDING"),
            sa.Column("admin_remarks", sa.Text(), nullable=True),
            sa.Column("refund_date", sa.String(length=40), nullable=True),
            sa.Column("processed_by", sa.Integer(), nullable=True),
            sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("wallet_credited", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["return_id"], ["order_returns.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["processed_by"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_refund_transactions_return_id", "refund_transactions", ["return_id"])
        op.create_index("ix_refund_transactions_refund_status", "refund_transactions", ["refund_status"])
    if "replacement_orders" not in tables:
        op.create_table(
            "replacement_orders",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("original_order_id", sa.Integer(), nullable=False),
            sa.Column("return_id", sa.Integer(), nullable=False),
            sa.Column("replacement_order_id", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=40), nullable=False, server_default="CREATED"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["original_order_id"], ["product_orders.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["return_id"], ["order_returns.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["replacement_order_id"], ["product_orders.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("return_id"),
        )
        op.create_index("ix_replacement_orders_original_order_id", "replacement_orders", ["original_order_id"])


def downgrade() -> None:
    pass
