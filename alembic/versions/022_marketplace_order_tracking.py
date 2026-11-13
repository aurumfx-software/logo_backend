"""Track which customer bought a marketplace item and the delivery steps.

Revision ID: 022_marketplace_order_tracking
Revises: 021_wallet_withdrawal_columns
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "022_marketplace_order_tracking"
down_revision: Union[str, None] = "021_wallet_withdrawal_columns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "product_orders" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("product_orders")}
    if "unit_price" not in existing:
        op.add_column("product_orders", sa.Column("unit_price", sa.Numeric(10, 2), nullable=True))
    if "buyer_user_id" not in existing:
        op.add_column("product_orders", sa.Column("buyer_user_id", sa.Integer(), nullable=True))
        op.create_index("ix_product_orders_buyer_user_id", "product_orders", ["buyer_user_id"])
        op.create_foreign_key(
            "fk_product_orders_buyer_user_id",
            "product_orders",
            "users",
            ["buyer_user_id"],
            ["id"],
            ondelete="SET NULL",
        )
    if "status_history" not in existing:
        op.add_column("product_orders", sa.Column("status_history", sa.JSON(), nullable=True))
    if "customer_products" in inspector.get_table_names():
        product_columns = {column["name"] for column in inspector.get_columns("customer_products")}
        if "stock_quantity" not in product_columns:
            op.add_column("customer_products", sa.Column("stock_quantity", sa.Integer(), nullable=True))


def downgrade() -> None:
    pass
