from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.subscription import (
    SubscriptionAudience,
    SubscriptionBillingPeriod,
    UserSubscriptionStatus,
)


class SubscriptionPackageResponse(BaseModel):
    id: int
    code: str
    name: str
    description: Optional[str] = None
    audience: SubscriptionAudience
    price: Decimal
    currency: str = "INR"
    billing_period: SubscriptionBillingPeriod
    duration_days: int
    features: List[str] = Field(default_factory=list)
    grants: Dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True
    sort_order: int = 0

    model_config = ConfigDict(from_attributes=True)


class SubscriptionPackageCreateRequest(BaseModel):
    code: str = Field(..., min_length=2, max_length=80)
    name: str = Field(..., min_length=2, max_length=255)
    description: Optional[str] = None
    audience: SubscriptionAudience
    price: Decimal = Field(default=Decimal("0.00"), ge=0)
    currency: str = Field(default="INR", max_length=3)
    billing_period: SubscriptionBillingPeriod = SubscriptionBillingPeriod.MONTHLY
    duration_days: int = Field(default=30, ge=1, le=3650)
    features: Optional[List[str]] = None
    grants: Optional[Dict[str, Any]] = None
    is_active: bool = True
    sort_order: int = 0


class SubscriptionPackageUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    price: Optional[Decimal] = Field(None, ge=0)
    currency: Optional[str] = Field(None, max_length=3)
    billing_period: Optional[SubscriptionBillingPeriod] = None
    duration_days: Optional[int] = Field(None, ge=1, le=3650)
    features: Optional[List[str]] = None
    grants: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class UserSubscriptionResponse(BaseModel):
    id: int
    subscription_code: str
    user_id: int
    merchant_profile_id: Optional[int] = None
    package_id: int
    package_code: Optional[str] = None
    package_name: Optional[str] = None
    audience: Optional[SubscriptionAudience] = None
    status: UserSubscriptionStatus
    amount_paid: Decimal
    currency: str
    payment_reference: Optional[str] = None
    started_at: datetime
    expires_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class SubscribeRequest(BaseModel):
    package_id: int
    merchant_profile_id: Optional[int] = Field(
        None,
        description="Required when subscribing to a MERCHANT audience package",
    )
    payment_reference: Optional[str] = Field(
        None,
        max_length=255,
        description="Payment gateway reference (Razorpay order id, etc.)",
    )


class AdminAssignSubscriptionRequest(BaseModel):
    user_id: int
    package_id: int
    merchant_profile_id: Optional[int] = None
    payment_reference: Optional[str] = None
    amount_paid: Optional[Decimal] = None


class ActiveSubscriptionSummary(BaseModel):
    user_subscriptions: List[UserSubscriptionResponse] = Field(default_factory=list)
    merchant_subscriptions: List[UserSubscriptionResponse] = Field(default_factory=list)
    can_sell_products: bool = False
    is_subscriber: bool = False
    subscription_plan: Optional[str] = None
    merchant_has_active_subscription: bool = False
