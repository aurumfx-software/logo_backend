"""Add Shiprocket identifiers to shipments and returns.

Revision ID: 029_shiprocket_columns
Revises: 028_order_fulfillment
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "029_shiprocket_columns"
down_revision: Union[str, None] = "028_order_fulfillment"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table: str) -> set:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table)}


def _add(table: str, name: str, column: sa.Column) -> None:
    if name not in _columns(table):
        op.add_column(table, column)


def upgrade() -> None:
    _add("shipments", "courier_id", sa.Column("courier_id", sa.String(length=32), nullable=True))
    _add("shipments", "awb_number", sa.Column("awb_number", sa.String(length=64), nullable=True))
    _add("shipments", "label_url", sa.Column("label_url", sa.String(length=500), nullable=True))
    _add("shipments", "shiprocket_order_id", sa.Column("shiprocket_order_id", sa.String(length=64), nullable=True))
    _add("shipments", "shiprocket_shipment_id", sa.Column("shiprocket_shipment_id", sa.String(length=64), nullable=True))
    _add("shipment_history", "event_time", sa.Column("event_time", sa.DateTime(timezone=True), nullable=True))
    _add("shipment_history", "event_key", sa.Column("event_key", sa.String(length=180), nullable=True))
    _add("order_returns", "shiprocket_order_id", sa.Column("shiprocket_order_id", sa.String(length=64), nullable=True))
    _add("order_returns", "shiprocket_shipment_id", sa.Column("shiprocket_shipment_id", sa.String(length=64), nullable=True))
    _add("order_returns", "tracking_url", sa.Column("tracking_url", sa.String(length=500), nullable=True))
    _add("order_returns", "inspection_status", sa.Column("inspection_status", sa.String(length=40), nullable=True))
    _add("order_returns", "refund_amount", sa.Column("refund_amount", sa.Numeric(12, 2), nullable=True))
    _add("order_returns", "refund_status", sa.Column("refund_status", sa.String(length=20), nullable=True))
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "shipment_history" in inspector.get_table_names():
        indexes = {index["name"] for index in inspector.get_indexes("shipment_history")}
        if "uq_shipment_history_event_key" not in indexes:
            op.create_index("uq_shipment_history_event_key", "shipment_history", ["event_key"], unique=True)


def downgrade() -> None:
    pass
