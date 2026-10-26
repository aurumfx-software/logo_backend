from datetime import datetime, timezone
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.db.database import Base


class CustomerProduct(Base):
    __tablename__ = "customer_products"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    seller_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    seller_name = Column(String(255), nullable=True)
    seller_phone = Column(String(50), nullable=True)
    seller_whatsapp = Column(String(50), nullable=True)

    name = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)
    category = Column(String(100), default="General", nullable=False, index=True)
    price = Column(Numeric(10, 2), nullable=False)
    original_price = Column(Numeric(10, 2), nullable=True)
    
    images = Column(JSON, default=list, nullable=True)  # List of image URLs
    sizes = Column(JSON, default=list, nullable=True)   # Available sizes e.g. ["S", "M", "L", "XL"]
    stock_status = Column(String(50), default="IN_STOCK", nullable=False)

    district = Column(String(100), nullable=True, index=True)
    city = Column(String(100), nullable=True)
    location = Column(String(255), nullable=True)

    is_active = Column(Boolean, default=True, nullable=False, index=True)  # Admin / Seller On/Off toggle
    approval_status = Column(String(50), default="APPROVED", nullable=False, index=True)  # APPROVED / DENIED / PENDING
    rejection_reason = Column(Text, nullable=True)

    views_count = Column(Integer, default=0, nullable=False)
    orders_count = Column(Integer, default=0, nullable=False)

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    seller = relationship("User", backref="customer_products")


class ProductOrder(Base):
    __tablename__ = "product_orders"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    order_code = Column(String(50), unique=True, index=True, nullable=False)
    product_id = Column(Integer, ForeignKey("customer_products.id", ondelete="CASCADE"), nullable=False, index=True)
    seller_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Buyer information
    buyer_name = Column(String(255), nullable=False)
    buyer_phone = Column(String(50), nullable=False, index=True)
    buyer_address = Column(Text, nullable=False)
    buyer_location = Column(String(255), nullable=True)
    buyer_city = Column(String(100), nullable=True)
    buyer_district = Column(String(100), nullable=True)
    buyer_pincode = Column(String(20), nullable=False)

    # Order item details
    selected_size = Column(String(50), nullable=True)
    quantity = Column(Integer, default=1, nullable=False)
    unit_price = Column(Numeric(10, 2), nullable=False)
    total_price = Column(Numeric(10, 2), nullable=False)

    # Order processing status
    status = Column(String(50), default="NEW", nullable=False, index=True)  # NEW, CONTACTED, SHIPPED, DELIVERED, CANCELLED
    notes = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    product = relationship("CustomerProduct", backref="product_orders")
    seller = relationship("User", backref="seller_orders")
