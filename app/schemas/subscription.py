from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.db.models.subscription import (
    SubscriptionAudience,
    SubscriptionBillingPeriod,
    UserSubscriptionStatus,
)


class SubscriptionAccessFlags(BaseModel):
    """Checkbox access stored on a package. Admin can turn each one on or off."""

    can_sell_products: bool = False
    cashback_on_sales: bool = False
    can_add_photos: bool = False
    can_add_videos: bool = False
    can_add_detail_page_ad: bool = False
    can_promote_landing: bool = False


class SubscriptionAccessUpdate(BaseModel):
    """Partial checkbox update. Omitted keys are left unchanged."""

    can_sell_products: Optional[bool] = None
    cashback_on_sales: Optional[bool] = None
    can_add_photos: Optional[bool] = None
    can_add_videos: Optional[bool] = None
    can_add_detail_page_ad: Optional[bool] = None
    can_promote_landing: Optional[bool] = None


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
    access: SubscriptionAccessFlags = Field(default_factory=SubscriptionAccessFlags)
    is_active: bool = True
    sort_order: int = 0

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def access_from_grants(self):
        grants = self.grants or {}
        self.access = SubscriptionAccessFlags(
            can_sell_products=bool(grants.get("can_sell_products") or grants.get("merchant_product_section")),
            cashback_on_sales=bool(grants.get("cashback_on_sales")),
            can_add_photos=bool(grants.get("can_add_photos") or grants.get("merchant_profile_photos")),
            can_add_videos=bool(grants.get("can_add_videos") or grants.get("merchant_profile_video")),
            can_add_detail_page_ad=bool(
                grants.get("can_add_detail_page_ad")
                or grants.get("merchant_store_ad")
                or grants.get("merchant_store_video_ad")
            ),
            can_promote_landing=bool(
                grants.get("can_promote_landing")
                or any(
                    grants.get(k)
                    for k in (
                        "ad_home_top",
                        "ad_home_middle",
                        "ad_above_footer",
                        "ad_featured_offers",
                        "ad_special_deals",
                        "ad_business_network",
                        "ad_square_poster",
                    )
                )
            ),
        )
        return self


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
    access: Optional[SubscriptionAccessUpdate] = None
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
    access: Optional[SubscriptionAccessUpdate] = None
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
    package_id: Optional[int] = None
    package_code: Optional[str] = Field(
        None,
        description="Package code such as USER_SELLER_500 or MERCHANT_PROMO_BASIC",
    )
    merchant_profile_id: Optional[int] = Field(
        None,
        description="Shop id for MERCHANT packages. Resolved from the logged-in merchant when omitted.",
    )
    payment_reference: Optional[str] = Field(
        None,
        max_length=255,
        description="Payment gateway reference (Razorpay order id, etc.)",
    )

    @model_validator(mode="before")
    @classmethod
    def accept_client_aliases(cls, data):
        if not isinstance(data, dict):
            return data
        payload = dict(data)
        if not payload.get("package_code"):
            for key in ("code", "plan_code", "plan", "package"):
                if payload.get(key):
                    payload["package_code"] = payload[key]
                    break
        raw_id = payload.get("package_id", payload.get("packageId", payload.get("plan_id")))
        if isinstance(raw_id, str):
            text = raw_id.strip()
            if text.isdigit():
                payload["package_id"] = int(text)
            elif text:
                payload["package_code"] = payload.get("package_code") or text
                payload["package_id"] = None
        if not payload.get("payment_reference"):
            payload["payment_reference"] = (
                payload.get("payment_id")
                or payload.get("razorpay_payment_id")
                or payload.get("reference_id")
            )
        merchant_id = payload.get("merchant_profile_id", payload.get("merchantProfileId"))
        if isinstance(merchant_id, str) and merchant_id.strip().isdigit():
            payload["merchant_profile_id"] = int(merchant_id.strip())
        return payload


class AdminAssignSubscriptionRequest(BaseModel):
    user_id: int
    package_id: int
    merchant_profile_id: Optional[int] = None
    payment_reference: Optional[str] = None
    amount_paid: Optional[Decimal] = None


MERCHANT_PERMISSION_CATALOG: list[dict[str, str]] = [
    {
        "key": "merchant_profile_photos",
        "label": "Store Profile Photos",
        "group": "Profile Media",
        "description": "Upload and update up to 4 shop gallery photos on Web & Mobile",
    },
    {
        "key": "merchant_profile_video",
        "label": "Store Tour & Promo Video",
        "group": "Profile Media",
        "description": "Upload store tour video in profile header on Web & Mobile",
    },
    {
        "key": "merchant_store_ad",
        "label": "Store Page Ads (Image & Text)",
        "group": "Store Advertisements",
        "description": "Create and publish image banners and text ads inside store page",
    },
    {
        "key": "merchant_store_video_ad",
        "label": "Store Video Advertisements",
        "group": "Store Advertisements",
        "description": "Upload and publish video ads inside store advertisements",
    },
    {
        "key": "merchant_product_section",
        "label": "Product Selling & Storefront Orders",
        "group": "Products & Selling",
        "description": "Unlock My Products, Sell / Post an Ad, Customer Orders & Dispatched tabs",
    },
    {
        "key": "ad_home_top",
        "label": "Hero / Home Top Banner Ad",
        "group": "Platform Ad Placements",
        "description": "Publish advertisements in Home Top / Hero Banner slider",
    },
    {
        "key": "ad_home_middle",
        "label": "Home Middle Showcase Ad",
        "group": "Platform Ad Placements",
        "description": "Publish advertisements in Home Middle Showcase / Middle Banner",
    },
    {
        "key": "ad_above_footer",
        "label": "Above Footer / Footer Strip Ad",
        "group": "Platform Ad Placements",
        "description": "Publish advertisements in Above Footer / Footer Strip slider",
    },
    {
        "key": "ad_featured_offers",
        "label": "Featured Offers / Category Top Ad",
        "group": "Platform Ad Placements",
        "description": "Publish advertisements in Featured Offers / Category Top placement",
    },
    {
        "key": "ad_special_deals",
        "label": "Special Deals / Feed / Popup Ad",
        "group": "Platform Ad Placements",
        "description": "Publish advertisements in Special Deals, Moving Text, In-Between Feed, or Popup",
    },
    {
        "key": "ad_business_network",
        "label": "Business Network Poster Ad",
        "group": "Platform Ad Placements",
        "description": "Publish advertisements in Business Network Poster slider",
    },
    {
        "key": "ad_square_poster",
        "label": "Square Poster & Product Ad",
        "group": "Platform Ad Placements",
        "description": "Publish advertisements in Square Poster & Product Section placement",
    },
]

MERCHANT_PERMISSION_KEYS: tuple[str, ...] = tuple(item["key"] for item in MERCHANT_PERMISSION_CATALOG)


class ActiveSubscriptionSummary(BaseModel):
    user_subscriptions: List[UserSubscriptionResponse] = Field(default_factory=list)
    merchant_subscriptions: List[UserSubscriptionResponse] = Field(default_factory=list)
    can_sell_products: bool = False
    cashback_on_sales: bool = False
    is_subscriber: bool = False
    subscription_plan: Optional[str] = None
    grants: Dict[str, Any] = Field(default_factory=dict)
    access: SubscriptionAccessFlags = Field(default_factory=SubscriptionAccessFlags)
    merchant_has_active_subscription: bool = False
    merchant_profile_id: Optional[int] = None
    merchant_business_name: Optional[str] = None
    merchant_grants: dict[str, bool] = Field(default_factory=dict)


class SubscriptionRazorpayOrderRequest(BaseModel):
    package_id: Optional[int] = None
    package_code: Optional[str] = None
    merchant_profile_id: Optional[int] = None

    @model_validator(mode="before")
    @classmethod
    def accept_aliases(cls, data):
        return SubscribeRequest.accept_client_aliases(data)


class SubscriptionRazorpayOrderResponse(BaseModel):
    message: str = "Razorpay subscription order created"
    razorpay_key_id: str = ""
    razorpay_order_id: str
    amount: Decimal
    amount_paise: int
    currency: str = "INR"
    package_id: int
    package_code: str
    package_name: str
    merchant_profile_id: Optional[int] = None


class SubscriptionRazorpayVerifyRequest(BaseModel):
    package_id: Optional[int] = None
    package_code: Optional[str] = None
    merchant_profile_id: Optional[int] = None
    razorpay_order_id: str = Field(..., min_length=4, max_length=64)
    razorpay_payment_id: str = Field(..., min_length=4, max_length=64)
    razorpay_signature: str = Field(..., min_length=8, max_length=128)

    @model_validator(mode="before")
    @classmethod
    def accept_aliases(cls, data):
        return SubscribeRequest.accept_client_aliases(data)
