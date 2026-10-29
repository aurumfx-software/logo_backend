import enum
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.db.database import Base


class SubscriptionAudience(str, enum.Enum):
    USER = "USER"
    MERCHANT = "MERCHANT"


class SubscriptionBillingPeriod(str, enum.Enum):
    MONTHLY = "MONTHLY"
    YEARLY = "YEARLY"
    ONE_TIME = "ONE_TIME"


class UserSubscriptionStatus(str, enum.Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class SubscriptionPackage(Base):
    __tablename__ = "subscription_packages"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    code = Column(String(80), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    audience = Column(
        Enum(SubscriptionAudience, name="subscription_audience", native_enum=False),
        nullable=False,
        index=True,
    )
    price = Column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    currency = Column(String(3), nullable=False, default="INR")
    billing_period = Column(
        Enum(SubscriptionBillingPeriod, name="subscription_billing_period", native_enum=False),
        nullable=False,
        default=SubscriptionBillingPeriod.MONTHLY,
    )
    duration_days = Column(Integer, nullable=False, default=30)
    features = Column(JSON, default=list, nullable=True)
    grants = Column(JSON, default=dict, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    sort_order = Column(Integer, default=0, nullable=False)
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

    subscriptions = relationship("UserSubscription", back_populates="package")


class UserSubscription(Base):
    __tablename__ = "user_subscriptions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    subscription_code = Column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
        default=lambda: f"SUB-{uuid.uuid4().hex[:10].upper()}",
    )
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    merchant_profile_id = Column(
        Integer,
        ForeignKey("merchant_profiles.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    package_id = Column(
        Integer,
        ForeignKey("subscription_packages.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status = Column(
        Enum(UserSubscriptionStatus, name="user_subscription_status", native_enum=False),
        nullable=False,
        default=UserSubscriptionStatus.ACTIVE,
        index=True,
    )
    amount_paid = Column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    currency = Column(String(3), nullable=False, default="INR")
    payment_reference = Column(String(255), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
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

    user = relationship("User", backref="subscriptions")
    merchant_profile = relationship("MerchantProfile", backref="subscriptions")
    package = relationship("SubscriptionPackage", back_populates="subscriptions")
