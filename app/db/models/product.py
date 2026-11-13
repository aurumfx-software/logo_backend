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
    UniqueConstraint,
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
    stock_quantity = Column(Integer, nullable=True)

    district = Column(String(100), nullable=True, index=True)
    city = Column(String(100), nullable=True)
    location = Column(String(255), nullable=True)

    is_active = Column(Boolean, default=True, nullable=False, index=True)  # Admin / Seller On/Off toggle
    approval_status = Column(String(50), default="APPROVED", nullable=False, index=True)  # APPROVED / DENIED / PENDING
    rejection_reason = Column(Text, nullable=True)

    views_count = Column(Integer, default=0, nullable=False)
    orders_count = Column(Integer, default=0, nullable=False)
    rating_sum = Column(Integer, default=0, nullable=False)
    rating_count = Column(Integer, default=0, nullable=False)

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
    buyer_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

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
    status = Column(String(50), default="PLACED", nullable=False, index=True)
    notes = Column(Text, nullable=True)
    status_history = Column(JSON, default=list, nullable=True)
    payment_status = Column(String(32), default="UNPAID", nullable=False, index=True)
    payment_method = Column(String(32), nullable=True)
    razorpay_order_id = Column(String(64), nullable=True, index=True)
    razorpay_payment_id = Column(String(64), nullable=True)
    cancellation_reason = Column(String(500), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    courier_partner = Column(String(100), nullable=True)
    tracking_number = Column(String(64), nullable=True)
    tracking_url = Column(String(500), nullable=True)
    estimated_delivery_at = Column(DateTime(timezone=True), nullable=True)
    courier_events = Column(JSON, default=list, nullable=True)

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
    seller = relationship("User", foreign_keys=[seller_id], backref="seller_orders")
    buyer = relationship("User", foreign_keys=[buyer_user_id], backref="purchases")


class DeliveryAddress(Base):
    __tablename__ = "delivery_addresses"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    label = Column(String(50), default="Home", nullable=False)
    recipient_name = Column(String(255), nullable=False)
    phone = Column(String(50), nullable=False)
    address_line = Column(Text, nullable=False)
    location = Column(String(255), nullable=True)
    city = Column(String(100), nullable=True)
    district = Column(String(100), nullable=True)
    pincode = Column(String(20), nullable=False)
    is_default = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = relationship("User", backref="delivery_addresses")


class ProductWishlist(Base):
    __tablename__ = "product_wishlists"
    __table_args__ = (UniqueConstraint("user_id", "product_id", name="uq_user_product_wishlist"),)

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("customer_products.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", backref="product_wishlist")
    product = relationship("CustomerProduct", backref="wishlisted_by")


class CartItem(Base):
    __tablename__ = "cart_items"
    __table_args__ = (
        UniqueConstraint("user_id", "product_id", "selected_size", name="uq_user_cart_product_size"),
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("customer_products.id", ondelete="CASCADE"), nullable=False, index=True)
    selected_size = Column(String(50), default="", nullable=False)
    quantity = Column(Integer, default=1, nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = relationship("User", backref="cart_items")
    product = relationship("CustomerProduct")


class ProductReview(Base):
    __tablename__ = "product_reviews"
    __table_args__ = (UniqueConstraint("order_id", name="uq_product_review_order"),)

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey("customer_products.id", ondelete="CASCADE"), nullable=False, index=True)
    order_id = Column(Integer, ForeignKey("product_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    buyer_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    rating = Column(Integer, nullable=False)
    title = Column(String(120), nullable=True)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    product = relationship("CustomerProduct", backref="reviews")
    order = relationship("ProductOrder", backref="review")
    buyer = relationship("User", backref="product_reviews")
