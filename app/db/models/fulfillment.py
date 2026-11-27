from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, Text, Boolean
from sqlalchemy.types import JSON
from sqlalchemy.orm import relationship

from app.db.database import Base


def _now():
    return datetime.now(timezone.utc)


class PlatformSetting(Base):
    __tablename__ = "platform_settings"

    key = Column(String(80), primary_key=True)
    value = Column(String(255), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)


class Shipment(Base):
    __tablename__ = "shipments"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    order_id = Column(Integer, ForeignKey("product_orders.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    courier_name = Column(String(120), nullable=True)
    courier_id = Column(String(32), nullable=True)
    tracking_number = Column(String(64), nullable=True, index=True)
    awb_number = Column(String(64), nullable=True, index=True)
    tracking_url = Column(String(500), nullable=True)
    label_url = Column(String(500), nullable=True)
    shiprocket_order_id = Column(String(64), nullable=True, index=True)
    shiprocket_shipment_id = Column(String(64), nullable=True, index=True)
    shipment_status = Column(String(40), nullable=False, default="ORDER_PLACED", index=True)
    remarks = Column(Text, nullable=True)
    dispatched_at = Column(DateTime(timezone=True), nullable=True)
    estimated_delivery = Column(DateTime(timezone=True), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)

    order = relationship("ProductOrder", backref="shipment")
    history = relationship("ShipmentHistory", back_populates="shipment", order_by="ShipmentHistory.id")


class ShipmentHistory(Base):
    __tablename__ = "shipment_history"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    shipment_id = Column(Integer, ForeignKey("shipments.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(40), nullable=False)
    location = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    event_time = Column(DateTime(timezone=True), nullable=True)
    event_key = Column(String(180), nullable=True, unique=True, index=True)
    updated_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)

    shipment = relationship("Shipment", back_populates="history")


class OrderReturn(Base):
    __tablename__ = "order_returns"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    return_number = Column(String(32), unique=True, nullable=False, index=True)
    order_id = Column(Integer, ForeignKey("product_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    return_reason = Column(String(80), nullable=False)
    description = Column(Text, nullable=True)
    return_type = Column(String(32), nullable=False)
    return_status = Column(String(40), nullable=False, default="REQUESTED", index=True)
    courier_name = Column(String(120), nullable=True)
    awb_number = Column(String(64), nullable=True, index=True)
    shiprocket_order_id = Column(String(64), nullable=True)
    shiprocket_shipment_id = Column(String(64), nullable=True, index=True)
    tracking_url = Column(String(500), nullable=True)
    shipping_date = Column(String(40), nullable=True)
    receipt_url = Column(String(500), nullable=True)
    pickup_date = Column(String(40), nullable=True)
    pickup_remarks = Column(Text, nullable=True)
    admin_notes = Column(Text, nullable=True)
    rejection_reason = Column(String(500), nullable=True)
    inspection_status = Column(String(40), nullable=True)
    refund_amount = Column(Numeric(12, 2), nullable=True)
    refund_status = Column(String(20), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)

    items = relationship("ReturnItem", back_populates="order_return")
    history = relationship("ReturnHistory", back_populates="order_return", order_by="ReturnHistory.id")
    refunds = relationship("RefundTransaction", back_populates="order_return")


class ReturnItem(Base):
    __tablename__ = "return_items"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    return_id = Column(Integer, ForeignKey("order_returns.id", ondelete="CASCADE"), nullable=False, index=True)
    order_item_id = Column(Integer, ForeignKey("product_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("customer_products.id", ondelete="SET NULL"), nullable=True, index=True)
    quantity = Column(Integer, nullable=False)
    product_condition = Column(String(80), nullable=True)
    image_urls = Column(JSON, default=list, nullable=True)

    order_return = relationship("OrderReturn", back_populates="items")


class ReturnHistory(Base):
    __tablename__ = "return_history"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    return_id = Column(Integer, ForeignKey("order_returns.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(40), nullable=False)
    remarks = Column(Text, nullable=True)
    updated_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)

    order_return = relationship("OrderReturn", back_populates="history")


class RefundTransaction(Base):
    __tablename__ = "refund_transactions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    return_id = Column(Integer, ForeignKey("order_returns.id", ondelete="CASCADE"), nullable=False, index=True)
    refund_amount = Column(Numeric(12, 2), nullable=False)
    refund_method = Column(String(32), nullable=False)
    transaction_reference = Column(String(120), nullable=True)
    refund_status = Column(String(20), nullable=False, default="PENDING", index=True)
    admin_remarks = Column(Text, nullable=True)
    refund_date = Column(String(40), nullable=True)
    processed_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    wallet_credited = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)

    order_return = relationship("OrderReturn", back_populates="refunds")


class ReplacementOrder(Base):
    __tablename__ = "replacement_orders"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    original_order_id = Column(Integer, ForeignKey("product_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    return_id = Column(Integer, ForeignKey("order_returns.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    replacement_order_id = Column(Integer, ForeignKey("product_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(40), nullable=False, default="CREATED")
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)
