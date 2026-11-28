import math
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.db.models.merchant import MerchantProfile
from app.db.models.subscription import (
    SubscriptionAudience,
    SubscriptionPackage,
    UserSubscription,
    UserSubscriptionStatus,
)
from app.db.models.user import User, UserRole
from app.schemas.subscription import (
    MERCHANT_PERMISSION_CATALOG,
    MERCHANT_PERMISSION_KEYS,
    AdminAssignSubscriptionRequest,
    SubscribeRequest,
    SubscriptionAccessFlags,
    SubscriptionAccessUpdate,
    SubscriptionPackageCreateRequest,
    SubscriptionPackageUpdateRequest,
    UserSubscriptionResponse,
)

MERCHANT_AD_PERMISSION_KEYS: Tuple[str, ...] = (
    "merchant_store_ad",
    "merchant_store_video_ad",
    "ad_home_top",
    "ad_home_middle",
    "ad_above_footer",
    "ad_featured_offers",
    "ad_special_deals",
    "ad_business_network",
    "ad_square_poster",
)


def _as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class SubscriptionService:
    # Checkbox keys stored on subscription_packages.grants. Admin can turn each one on or off.
    CUSTOMER_GRANT_KEYS = ("can_sell_products", "cashback_on_sales")
    MERCHANT_GRANT_KEYS = (
        "can_add_photos",
        "can_add_videos",
        "can_sell_products",
        "can_add_detail_page_ad",
        "can_promote_landing",
    )

    DEFAULT_PACKAGES: List[Dict[str, Any]] = [
        {
            "code": "USER_FREE",
            "name": "Customer Free ₹0",
            "description": "Browse the app. Product selling and sale cashback are not included.",
            "audience": SubscriptionAudience.USER,
            "price": Decimal("0"),
            "billing_period": "ONE_TIME",
            "duration_days": 3650,
            "features": ["Browse directory", "Browse marketplace"],
            "grants": {},
            "sort_order": 0,
        },
        {
            "code": "USER_SELLER_500",
            "name": "Customer Cashback Seller ₹499",
            "description": "Sell products and receive cashback on those sales.",
            "audience": SubscriptionAudience.USER,
            "price": Decimal("499"),
            "billing_period": "MONTHLY",
            "duration_days": 30,
            "features": ["Sell products", "Cashback on sales", "Seller dashboard"],
            "grants": {
                "can_sell_products": True,
                "cashback_on_sales": True,
                "is_subscriber": True,
                "subscription_plan": "499_SELLER",
            },
            "sort_order": 1,
        },
        {
            "code": "MERCHANT_REGISTER_1000",
            "name": "Merchant Registration ₹1000",
            "description": "Mandatory ₹1000 onboarding & directory registration subscription for new merchants.",
            "audience": SubscriptionAudience.MERCHANT,
            "price": Decimal("1000"),
            "billing_period": "ONE_TIME",
            "duration_days": 3650,
            "features": ["Merchant Directory Registration"],
            "grants": {"_granular": True},
            "sort_order": -1,
        },
        {
            "code": "MERCHANT_PROMO_BASIC",
            "name": "Merchant Photos ₹999",
            "description": "Add photos on the merchant profile.",
            "audience": SubscriptionAudience.MERCHANT,
            "price": Decimal("999"),
            "billing_period": "MONTHLY",
            "duration_days": 30,
            "features": ["Profile photos"],
            "grants": {"can_add_photos": True},
            "sort_order": 0,
        },
        {
            "code": "MERCHANT_PREMIUM",
            "name": "Merchant Photos & Video ₹1999",
            "description": "Add photos and video on the merchant profile.",
            "audience": SubscriptionAudience.MERCHANT,
            "price": Decimal("1999"),
            "billing_period": "MONTHLY",
            "duration_days": 30,
            "features": ["Profile photos", "Profile video"],
            "grants": {"can_add_photos": True, "can_add_videos": True},
            "sort_order": 1,
        },
        {
            "code": "MERCHANT_SELL_2999",
            "name": "Merchant Seller ₹2999",
            "description": "Photos, video, and product selling.",
            "audience": SubscriptionAudience.MERCHANT,
            "price": Decimal("2999"),
            "billing_period": "MONTHLY",
            "duration_days": 30,
            "features": ["Profile photos", "Profile video", "Sell products"],
            "grants": {"can_add_photos": True, "can_add_videos": True, "can_sell_products": True},
            "sort_order": 2,
        },
        {
            "code": "MERCHANT_DETAIL_3999",
            "name": "Merchant Detail Ad ₹3999",
            "description": "Photos, video, product selling, and an advertisement on the merchant details page.",
            "audience": SubscriptionAudience.MERCHANT,
            "price": Decimal("3999"),
            "billing_period": "MONTHLY",
            "duration_days": 30,
            "features": ["Profile photos", "Profile video", "Sell products", "Details page advertisement"],
            "grants": {
                "can_add_photos": True,
                "can_add_videos": True,
                "can_sell_products": True,
                "can_add_detail_page_ad": True,
            },
            "sort_order": 3,
        },
        {
            "code": "MERCHANT_LANDING_4999",
            "name": "Merchant Landing Promotion ₹4999",
            "description": "Everything in the ₹3999 plan, plus a landing-page promotion. Landing ads stay pending until an admin approves them.",
            "audience": SubscriptionAudience.MERCHANT,
            "price": Decimal("4999"),
            "billing_period": "MONTHLY",
            "duration_days": 30,
            "features": [
                "Profile photos",
                "Profile video",
                "Sell products",
                "Details page advertisement",
                "Landing page promotion",
            ],
            "grants": {
                "can_add_photos": True,
                "can_add_videos": True,
                "can_sell_products": True,
                "can_add_detail_page_ad": True,
                "can_promote_landing": True,
            },
            "sort_order": 4,
        },
    ]

    # Previous seed values. These are upgraded once. Later admin checkbox edits are kept.
    LEGACY_GRANTS = {
        "USER_SELLER_500": [
            {"can_sell_products": True, "is_subscriber": True, "subscription_plan": "500_SELLER"},
        ],
        "MERCHANT_PROMO_BASIC": [
            {"can_create_promotions": True},
        ],
        "MERCHANT_PREMIUM": [
            {"can_create_promotions": True, "premium_listing": True},
        ],
    }

    ACCESS_OPTIONS = {
        "USER": [
            {"key": "can_sell_products", "label": "Sell products"},
            {"key": "cashback_on_sales", "label": "Cashback when selling a product"},
        ],
        "MERCHANT": [
            {"key": "can_add_photos", "label": "Add photos"},
            {"key": "can_add_videos", "label": "Add video"},
            {"key": "can_sell_products", "label": "Sell products"},
            {"key": "can_add_detail_page_ad", "label": "Advertisement on the merchant details page"},
            {"key": "can_promote_landing", "label": "Promote on the app landing page (admin approval required)"},
        ],
    }

    @staticmethod
    def _grant_signature(grants: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        signature: Dict[str, Any] = {}
        for key, value in (grants or {}).items():
            if not value:
                continue
            signature[key] = value if key == "subscription_plan" else True
        return signature

    @staticmethod
    def _apply_catalog_row(pkg: SubscriptionPackage, row: Dict[str, Any]) -> None:
        pkg.name = row["name"]
        pkg.description = row["description"]
        pkg.price = row["price"]
        pkg.billing_period = row["billing_period"]
        pkg.duration_days = row["duration_days"]
        pkg.features = row.get("features") or []
        pkg.grants = dict(row.get("grants") or {})
        pkg.sort_order = row.get("sort_order", pkg.sort_order or 0)
        pkg.is_active = True

    @staticmethod
    def ensure_default_packages(db: Session) -> None:
        existing = {pkg.code: pkg for pkg in db.query(SubscriptionPackage).all()}
        changed = False
        for row in SubscriptionService.DEFAULT_PACKAGES:
            current = existing.get(row["code"])
            if current is None:
                continue
            legacy = SubscriptionService.LEGACY_GRANTS.get(row["code"], [])
            signature = SubscriptionService._grant_signature(current.grants)
            price = Decimal(str(current.price or 0))
            still_legacy = signature in legacy or (
                row["code"] == "USER_SELLER_500" and price == Decimal("500")
            ) or (
                row["code"] == "USER_FREE" and (current.name or "") == "User Free"
            )
            if still_legacy:
                SubscriptionService._apply_catalog_row(current, row)
                changed = True
        if changed:
            db.commit()
        # A database that already has packages keeps later admin checkbox edits.
        # Only missing catalog codes are inserted.
        missing = [row for row in SubscriptionService.DEFAULT_PACKAGES if row["code"] not in existing]
        if not missing:
            return
        for row in missing:
            db.add(
                SubscriptionPackage(
                    code=row["code"],
                    name=row["name"],
                    description=row["description"],
                    audience=row["audience"],
                    price=row["price"],
                    currency="INR",
                    billing_period=row["billing_period"],
                    duration_days=row["duration_days"],
                    features=row.get("features") or [],
                    grants=row.get("grants") or {},
                    is_active=True,
                    sort_order=row.get("sort_order", 0),
                )
            )
        db.commit()

    @staticmethod
    def _money(value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.01"))

    @staticmethod
    def list_packages(
        db: Session,
        audience: Optional[SubscriptionAudience] = None,
        active_only: bool = True,
    ) -> List[SubscriptionPackage]:
        SubscriptionService.ensure_default_packages(db)
        q = db.query(SubscriptionPackage)
        if active_only:
            q = q.filter(
                SubscriptionPackage.is_active == True,
                func.upper(SubscriptionPackage.code) != "MERCHANT_REGISTER_1000",
            )
        if audience:
            q = q.filter(SubscriptionPackage.audience == audience)
        return q.order_by(SubscriptionPackage.sort_order, SubscriptionPackage.id).all()

    @staticmethod
    def get_package(db: Session, package_id: int) -> SubscriptionPackage:
        SubscriptionService.ensure_default_packages(db)
        pkg = db.query(SubscriptionPackage).filter(SubscriptionPackage.id == package_id).first()
        if not pkg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription package not found.")
        return pkg

    @staticmethod
    def package_merchant_grants(grants: Optional[Dict[str, Any]]) -> Dict[str, bool]:
        raw = grants if isinstance(grants, dict) else {}
        resolved: Dict[str, bool] = {k: False for k in MERCHANT_PERMISSION_KEYS}
        has_granular = bool(raw.get("_granular")) or any(k in raw for k in MERCHANT_PERMISSION_KEYS)
        if has_granular:
            for key in MERCHANT_PERMISSION_KEYS:
                resolved[key] = bool(raw.get(key))
            if raw.get("can_add_photos"):
                resolved["merchant_profile_photos"] = True
            if raw.get("can_add_videos"):
                resolved["merchant_profile_video"] = True
            if raw.get("can_sell_products"):
                resolved["merchant_product_section"] = True
            return resolved
        # Seeded / legacy Bitbucket access packages map cleanly to granular capabilities
        if raw.get("can_add_photos"):
            resolved["merchant_profile_photos"] = True
        if raw.get("can_add_videos"):
            resolved["merchant_profile_video"] = True
        if raw.get("can_sell_products"):
            resolved["merchant_product_section"] = True
        if raw.get("can_add_detail_page_ad"):
            resolved["merchant_store_ad"] = True
            resolved["merchant_store_video_ad"] = True
        if raw.get("can_promote_landing"):
            for key in (
                "ad_home_top",
                "ad_home_middle",
                "ad_above_footer",
                "ad_featured_offers",
                "ad_special_deals",
                "ad_business_network",
                "ad_square_poster",
            ):
                resolved[key] = True
        if raw.get("can_create_promotions"):
            for key in MERCHANT_AD_PERMISSION_KEYS:
                resolved[key] = True
        return resolved

    @staticmethod
    def build_features_from_grants(
        grants: Optional[Dict[str, Any]], explicit_features: Optional[List[str]]
    ) -> List[str]:
        if explicit_features:
            return [str(f).strip() for f in explicit_features if str(f).strip()]
        raw = grants if isinstance(grants, dict) else {}
        if bool(raw.get("_granular")) or any(k in raw for k in MERCHANT_PERMISSION_KEYS):
            resolved = SubscriptionService.package_merchant_grants(raw)
            return [item["label"] for item in MERCHANT_PERMISSION_CATALOG if resolved.get(item["key"])]
        return []

    @staticmethod
    def required_promotion_permission(placement: Optional[str], media_type: Optional[str]) -> Tuple[str, str]:
        p = str(placement or "").strip().lower()
        m = str(media_type or "image").strip().lower()
        if not p or p == "merchant store":
            if m == "video":
                return ("merchant_store_video_ad", "Store Video Advertisements")
            return ("merchant_store_ad", "Store Page Ads (Image & Text)")
        if "home top" in p or "hero" in p:
            return ("ad_home_top", "Hero / Home Top Banner Ad")
        if "home middle" in p or "middle banner" in p:
            return ("ad_home_middle", "Home Middle Showcase Ad")
        if "footer" in p:
            return ("ad_above_footer", "Above Footer / Footer Strip Ad")
        if "featured" in p or "category" in p:
            return ("ad_featured_offers", "Featured Offers / Category Top Ad")
        if "special" in p or "moving" in p or "in-between" in p or "popup" in p:
            return ("ad_special_deals", "Special Deals / Feed / Popup Ad")
        if "business network" in p:
            return ("ad_business_network", "Business Network Poster Ad")
        if "square" in p or "product section" in p:
            return ("ad_square_poster", "Square Poster & Product Ad")
        return ("merchant_store_ad", "Store Page Ads (Image & Text)")

    @staticmethod
    def _sync_subscribers_for_package(db: Session, pkg: SubscriptionPackage) -> None:
        subs = (
            db.query(UserSubscription)
            .filter(
                UserSubscription.package_id == pkg.id,
                UserSubscription.status == UserSubscriptionStatus.ACTIVE,
            )
            .all()
        )
        seen_users = set()
        seen_merchants = set()
        for sub in subs:
            if sub.merchant_profile_id and sub.merchant_profile_id not in seen_merchants:
                seen_merchants.add(sub.merchant_profile_id)
                SubscriptionService._apply_merchant_entitlements(db, sub.merchant_profile_id)
            if sub.user_id and sub.user_id not in seen_users:
                seen_users.add(sub.user_id)
                SubscriptionService._apply_user_entitlements(db, sub.user_id)

    @staticmethod
    def create_package(db: Session, data: SubscriptionPackageCreateRequest) -> SubscriptionPackage:
        code = data.code.strip().upper()
        if db.query(SubscriptionPackage).filter(SubscriptionPackage.code == code).first():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Package code already exists.")
        features = SubscriptionService.build_features_from_grants(data.grants, data.features)
        pkg = SubscriptionPackage(
            code=code,
            name=data.name.strip(),
            description=data.description,
            audience=data.audience,
            price=SubscriptionService._money(data.price),
            currency=(data.currency or "INR").upper(),
            billing_period=data.billing_period,
            duration_days=data.duration_days,
            features=SubscriptionService.build_features_from_grants(data.grants, data.features),
            grants=SubscriptionService._grants_with_access(data.grants or {}, data.access),
            is_active=data.is_active,
            sort_order=data.sort_order,
        )
        db.add(pkg)
        db.commit()
        db.refresh(pkg)
        return pkg

    @staticmethod
    def update_package(
        db: Session, package_id: int, data: SubscriptionPackageUpdateRequest
    ) -> SubscriptionPackage:
        pkg = SubscriptionService.get_package(db, package_id)
        if data.name is not None:
            pkg.name = data.name.strip()
        if data.description is not None:
            pkg.description = data.description
        if data.price is not None:
            pkg.price = SubscriptionService._money(data.price)
        if data.currency is not None:
            pkg.currency = data.currency.upper()
        if data.billing_period is not None:
            pkg.billing_period = data.billing_period
        if data.duration_days is not None:
            pkg.duration_days = data.duration_days
        if data.grants is not None or data.access is not None:
            pkg.grants = SubscriptionService._grants_with_access(
                data.grants if data.grants is not None else (pkg.grants or {}),
                data.access,
            )
            if data.features is not None:
                pkg.features = SubscriptionService.build_features_from_grants(pkg.grants, data.features)
            else:
                pkg.features = SubscriptionService.build_features_from_grants(pkg.grants, None) or pkg.features
        elif data.features is not None:
            pkg.features = data.features
        if data.is_active is not None:
            pkg.is_active = data.is_active
        if data.sort_order is not None:
            pkg.sort_order = data.sort_order
        db.commit()
        db.refresh(pkg)
        SubscriptionService._sync_subscribers_for_package(db, pkg)
        SubscriptionService._refresh_package_holders(db, pkg.id)
        return pkg

    @staticmethod
    def duplicate_package(db: Session, package_id: int) -> SubscriptionPackage:
        src = SubscriptionService.get_package(db, package_id)
        base_code = str(src.code or "MERCHANT_PLAN").strip().upper()[:48]
        candidate = f"{base_code}_COPY"
        idx = 2
        while db.query(SubscriptionPackage).filter(SubscriptionPackage.code == candidate).first():
            suffix = f"_COPY_{idx}"
            candidate = f"{base_code[: max(1, 64 - len(suffix))]}{suffix}"
            idx += 1
        max_order = db.query(func.max(SubscriptionPackage.sort_order)).scalar() or 0
        dup = SubscriptionPackage(
            code=candidate,
            name=f"{src.name} (Copy)"[:120],
            description=src.description,
            audience=src.audience,
            price=src.price,
            currency=src.currency,
            billing_period=src.billing_period,
            duration_days=src.duration_days,
            features=list(src.features or []),
            grants=dict(src.grants or {}),
            is_active=True,
            sort_order=int(max_order) + 1,
        )
        db.add(dup)
        db.commit()
        db.refresh(dup)
        return dup

    @staticmethod
    def _grants_with_access(
        grants: Optional[Dict[str, Any]],
        access: Optional[SubscriptionAccessUpdate],
    ) -> Dict[str, Any]:
        merged = dict(grants or {})
        if access is not None:
            dump = access.model_dump(exclude_unset=True)
            for key, value in dump.items():
                if value is None:
                    continue
                bval = bool(value)
                merged[key] = bval
                if key == "can_add_photos":
                    merged["merchant_profile_photos"] = bval
                elif key == "can_add_videos":
                    merged["merchant_profile_video"] = bval
                elif key == "can_sell_products":
                    merged["merchant_product_section"] = bval
                elif key == "can_add_detail_page_ad":
                    merged["merchant_store_ad"] = bval
                    merged["merchant_store_video_ad"] = bval
                elif key == "can_promote_landing":
                    for ad_k in (
                        "ad_home_top",
                        "ad_home_middle",
                        "ad_above_footer",
                        "ad_featured_offers",
                        "ad_special_deals",
                        "ad_business_network",
                        "ad_square_poster",
                    ):
                        merged[ad_k] = bval
        if bool(merged.get("_granular")) or any(k in merged for k in MERCHANT_PERMISSION_KEYS):
            merged["can_add_photos"] = bool(merged.get("merchant_profile_photos"))
            merged["can_add_videos"] = bool(merged.get("merchant_profile_video"))
            if "merchant_product_section" in merged or "can_sell_products" in merged:
                merged["can_sell_products"] = bool(
                    merged.get("merchant_product_section")
                    if "merchant_product_section" in merged
                    else merged.get("can_sell_products")
                )
            merged["can_add_detail_page_ad"] = bool(
                merged.get("merchant_store_ad") or merged.get("merchant_store_video_ad")
            )
            merged["can_promote_landing"] = bool(
                any(
                    merged.get(k)
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
            )
        return merged

    @staticmethod
    def access_from_grants(grants: Optional[Dict[str, Any]]) -> SubscriptionAccessFlags:
        source = grants or {}
        resolved = SubscriptionService.package_merchant_grants(source)
        return SubscriptionAccessFlags(
            can_sell_products=bool(source.get("can_sell_products") or resolved.get("merchant_product_section")),
            cashback_on_sales=bool(source.get("cashback_on_sales")),
            can_add_photos=bool(source.get("can_add_photos") or resolved.get("merchant_profile_photos")),
            can_add_videos=bool(source.get("can_add_videos") or resolved.get("merchant_profile_video")),
            can_add_detail_page_ad=bool(
                source.get("can_add_detail_page_ad")
                or resolved.get("merchant_store_ad")
                or resolved.get("merchant_store_video_ad")
            ),
            can_promote_landing=bool(
                source.get("can_promote_landing")
                or any(
                    resolved.get(k)
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

    @staticmethod
    def _refresh_package_holders(db: Session, package_id: int) -> None:
        SubscriptionService._sync_subscribers_for_package(db, SubscriptionService.get_package(db, package_id))

    @staticmethod
    def _is_merchant_approved(shop: Optional[MerchantProfile]) -> bool:
        if not shop:
            return False
        return (shop.approval_status or "").upper() in ("APPROVED", "ACTIVE") or (
            shop.status or ""
        ).upper() in ("APPROVED", "ACTIVE")

    @staticmethod
    def _days_remaining(expires_at: Optional[datetime]) -> Optional[int]:
        exp = _as_utc(expires_at)
        if exp is None:
            return None
        now = datetime.now(timezone.utc)
        secs = (exp - now).total_seconds()
        if secs <= 0:
            return 0
        return int(math.ceil(secs / 86400.0))

    @staticmethod
    def _find_active_duplicate_sub(
        db: Session,
        user_id: int,
        pkg: SubscriptionPackage,
        merchant_profile_id: Optional[int],
    ) -> Optional[UserSubscription]:
        now = datetime.now(timezone.utc)
        q = db.query(UserSubscription).filter(
            UserSubscription.package_id == pkg.id,
            UserSubscription.status == UserSubscriptionStatus.ACTIVE,
        )
        if SubscriptionService._audience_value(pkg) == "MERCHANT" and merchant_profile_id is not None:
            q = q.filter(UserSubscription.merchant_profile_id == merchant_profile_id)
        else:
            q = q.filter(
                UserSubscription.user_id == user_id,
                UserSubscription.merchant_profile_id.is_(None),
            )
        for existing in q.order_by(UserSubscription.id.desc()).all():
            if existing.expires_at is None or (_as_utc(existing.expires_at) and _as_utc(existing.expires_at) >= now):
                return existing
        return None

    @staticmethod
    def _subscription_to_response(sub: UserSubscription) -> UserSubscriptionResponse:
        pkg = sub.package
        return UserSubscriptionResponse(
            id=sub.id,
            subscription_code=sub.subscription_code,
            user_id=sub.user_id,
            merchant_profile_id=sub.merchant_profile_id,
            package_id=sub.package_id,
            package_code=pkg.code if pkg else None,
            package_name=pkg.name if pkg else None,
            audience=pkg.audience if pkg else None,
            status=sub.status,
            amount_paid=sub.amount_paid,
            price=pkg.price if pkg else sub.amount_paid,
            duration_days=pkg.duration_days if pkg else None,
            days_remaining=SubscriptionService._days_remaining(sub.expires_at),
            currency=sub.currency,
            payment_reference=sub.payment_reference,
            started_at=sub.started_at,
            expires_at=sub.expires_at,
            cancelled_at=sub.cancelled_at,
        )

    @staticmethod
    def _expire_due_subscriptions(db: Session, user_id: Optional[int] = None) -> None:
        now = datetime.now(timezone.utc)
        q = db.query(UserSubscription).filter(
            UserSubscription.status == UserSubscriptionStatus.ACTIVE,
            UserSubscription.expires_at.isnot(None),
        )
        if user_id is not None:
            q = q.filter(UserSubscription.user_id == user_id)
        for sub in q.all():
            if _as_utc(sub.expires_at) and _as_utc(sub.expires_at) < now:
                sub.status = UserSubscriptionStatus.EXPIRED
        db.commit()

    @staticmethod
    def _assert_merchant_access(db: Session, user: User, merchant_profile_id: int) -> MerchantProfile:
        merchant = db.query(MerchantProfile).filter(MerchantProfile.id == merchant_profile_id).first()
        if not merchant:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Merchant profile not found.")
        if merchant.user_id == user.id or user.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN):
            return merchant
        if merchant.onboarded_by_id == user.id:
            return merchant
        from app.services.merchant_service import MerchantService

        user_tail = MerchantService._phone_tail(user.phone)
        shop_tails = {
            MerchantService._phone_tail(merchant.phone),
            MerchantService._phone_tail(merchant.contact_number),
            MerchantService._phone_tail(merchant.whatsapp),
        }
        if user_tail and user_tail in shop_tails:
            return merchant
        if user.email and merchant.email and user.email.strip().lower() == merchant.email.strip().lower():
            return merchant
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this merchant profile.",
        )

    @staticmethod
    def _apply_user_entitlements(db: Session, user_id: int) -> User:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
        now = datetime.now(timezone.utc)
        active_subs = (
            db.query(UserSubscription)
            .join(SubscriptionPackage)
            .filter(
                UserSubscription.user_id == user_id,
                UserSubscription.status == UserSubscriptionStatus.ACTIVE,
                SubscriptionPackage.audience == SubscriptionAudience.USER,
                UserSubscription.merchant_profile_id.is_(None),
            )
            .all()
        )
        active_subs = [
            s
            for s in active_subs
            if s.expires_at is None or _as_utc(s.expires_at) >= now
        ]
        can_sell = False
        is_subscriber = False
        plan: Optional[str] = None
        for sub in active_subs:
            grants = (sub.package.grants or {}) if sub.package else {}
            if grants.get("can_sell_products") or grants.get("cashback_on_sales"):
                can_sell = True
            if grants.get("is_subscriber"):
                is_subscriber = True
            if grants.get("subscription_plan"):
                plan = str(grants["subscription_plan"])
        user_obj = user
        shop = db.query(MerchantProfile).filter(MerchantProfile.user_id == user_id).first()
        if not shop:
            shop = SubscriptionService.merchant_for_account(db, user_obj)
        if shop and SubscriptionService._is_merchant_approved(shop):
            merchant_subs = (
                db.query(UserSubscription)
                .join(SubscriptionPackage)
                .options(joinedload(UserSubscription.package))
                .filter(
                    UserSubscription.merchant_profile_id == shop.id,
                    UserSubscription.status == UserSubscriptionStatus.ACTIVE,
                    SubscriptionPackage.audience == SubscriptionAudience.MERCHANT,
                )
                .all()
            )
            for msub in merchant_subs:
                if msub.expires_at is not None and _as_utc(msub.expires_at) < now:
                    continue
                mgrants = SubscriptionService.package_merchant_grants(
                    msub.package.grants if msub.package else {}
                )
                if mgrants.get("merchant_product_section") or (msub.package and (msub.package.grants or {}).get("can_sell_products")):
                    can_sell = True
                    if not plan:
                        plan = msub.package.code if msub.package else "MERCHANT_PRODUCTS"
        if SubscriptionService._is_merchant_approved(shop) or shop is None:
            merchant_grants = SubscriptionService.merged_grants(db, user_id=user_id)
            if merchant_grants.get("can_sell_products"):
                can_sell = True
        user.can_sell_products = can_sell
        user.is_subscriber = is_subscriber or can_sell
        user.subscription_plan = plan
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def get_merchant_grants(
        db: Session,
        merchant_profile_id: Optional[int],
        user_id: Optional[int] = None,
        include_user_seller: bool = True,
    ) -> Dict[str, bool]:
        combined: Dict[str, bool] = {k: False for k in MERCHANT_PERMISSION_KEYS}
        now = datetime.now(timezone.utc)
        shop: Optional[MerchantProfile] = None
        if merchant_profile_id:
            shop = db.query(MerchantProfile).filter(MerchantProfile.id == merchant_profile_id).first()
        if shop is None and user_id:
            owner = db.query(User).filter(User.id == user_id).first()
            if owner:
                shop = SubscriptionService.merchant_for_account(db, owner)

        if shop is not None and not SubscriptionService._is_merchant_approved(shop):
            return combined

        if shop:
            active_subs = (
                db.query(UserSubscription)
                .join(SubscriptionPackage)
                .options(joinedload(UserSubscription.package))
                .filter(
                    UserSubscription.merchant_profile_id == shop.id,
                    UserSubscription.status == UserSubscriptionStatus.ACTIVE,
                    SubscriptionPackage.audience == SubscriptionAudience.MERCHANT,
                )
                .all()
            )
            for sub in active_subs:
                if sub.expires_at is not None and _as_utc(sub.expires_at) < now:
                    continue
                pkg_grants = SubscriptionService.package_merchant_grants(
                    sub.package.grants if sub.package else {}
                )
                for key, allowed in pkg_grants.items():
                    if allowed:
                        combined[key] = True

        target_uid = user_id or (shop.user_id if shop else None)
        if include_user_seller and target_uid:
            owner_row = db.query(User).filter(User.id == target_uid).first()
            if owner_row and owner_row.can_sell_products:
                combined["merchant_product_section"] = True
            else:
                u_subs = (
                    db.query(UserSubscription)
                    .join(SubscriptionPackage)
                    .options(joinedload(UserSubscription.package))
                    .filter(
                        UserSubscription.user_id == target_uid,
                        UserSubscription.status == UserSubscriptionStatus.ACTIVE,
                        SubscriptionPackage.audience == SubscriptionAudience.USER,
                    )
                    .all()
                )
                for usub in u_subs:
                    if usub.expires_at is not None and _as_utc(usub.expires_at) < now:
                        continue
                    raw = (usub.package.grants or {}) if usub.package else {}
                    if raw.get("can_sell_products"):
                        combined["merchant_product_section"] = True
        return combined

    @staticmethod
    def _apply_merchant_entitlements(db: Session, merchant_profile_id: int) -> MerchantProfile:
        merchant = db.query(MerchantProfile).filter(MerchantProfile.id == merchant_profile_id).first()
        if not merchant:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Merchant profile not found.")
        now = datetime.now(timezone.utc)
        active_subs = (
            db.query(UserSubscription)
            .join(SubscriptionPackage)
            .options(joinedload(UserSubscription.package))
            .filter(
                UserSubscription.merchant_profile_id == merchant_profile_id,
                UserSubscription.status == UserSubscriptionStatus.ACTIVE,
                SubscriptionPackage.audience == SubscriptionAudience.MERCHANT,
            )
            .all()
        )
        feature_subs = [
            s
            for s in active_subs
            if (s.expires_at is None or _as_utc(s.expires_at) >= now)
            and (not s.package or str(s.package.code or "").upper() != "MERCHANT_REGISTER_1000")
        ]
        is_approved = SubscriptionService._is_merchant_approved(merchant)
        grants = SubscriptionService.get_merchant_grants(
            db, merchant_profile_id, include_user_seller=False
        )
        merchant.has_active_subscription = len(feature_subs) > 0 and is_approved
        merchant.can_create_promotions = is_approved and any(
            grants.get(k) for k in MERCHANT_AD_PERMISSION_KEYS
        )
        db.commit()
        db.refresh(merchant)
        if merchant.user_id:
            SubscriptionService._apply_user_entitlements(db, merchant.user_id)
        return merchant

    @staticmethod
    def merged_grants(
        db: Session,
        user_id: Optional[int] = None,
        merchant_profile_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """OR together the checkbox grants on every active subscription."""
        SubscriptionService.ensure_default_packages(db)
        SubscriptionService._expire_due_subscriptions(db, user_id)
        now = datetime.now(timezone.utc)
        query = (
            db.query(UserSubscription)
            .options(joinedload(UserSubscription.package))
            .filter(UserSubscription.status == UserSubscriptionStatus.ACTIVE)
        )
        if merchant_profile_id is not None:
            query = query.filter(UserSubscription.merchant_profile_id == merchant_profile_id)
        elif user_id is not None:
            query = query.filter(UserSubscription.user_id == user_id)
        else:
            return {}
        merged: Dict[str, Any] = {}
        for sub in query.all():
            if sub.expires_at and _as_utc(sub.expires_at) < now:
                continue
            normalized = SubscriptionService._grants_with_access(
                (sub.package.grants or {}) if sub.package else {}, None
            )
            for key, value in normalized.items():
                if value:
                    merged[key] = True
        return merged

    @staticmethod
    def assert_can_sell(db: Session, user: User) -> None:
        if user.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN):
            return
        SubscriptionService._apply_user_entitlements(db, user.id)
        db.refresh(user)
        if not user.can_sell_products:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="A subscription with product selling is required. Customers need the ₹499 plan. Merchants need the ₹2999 plan or higher.",
            )

    @staticmethod
    def assert_merchant_grant(db: Session, merchant_profile_id: int, key: str, message: str) -> None:
        grants = SubscriptionService.merged_grants(db, merchant_profile_id=merchant_profile_id)
        if not grants.get(key):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=message)

    @staticmethod
    def _audience_value(pkg: SubscriptionPackage) -> str:
        raw = getattr(pkg.audience, "value", pkg.audience)
        return str(raw or "").strip().upper()

    @staticmethod
    def _resolve_package(db: Session, payload: SubscribeRequest) -> SubscriptionPackage:
        SubscriptionService.ensure_default_packages(db)
        if payload.package_id:
            return SubscriptionService.get_package(db, payload.package_id)
        code = (payload.package_code or "").strip().upper()
        if not code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="package_id or package_code is required.",
            )
        pkg = (
            db.query(SubscriptionPackage)
            .filter(func.upper(SubscriptionPackage.code) == code)
            .first()
        )
        if not pkg:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Subscription package '{code}' not found.",
            )
        return pkg

    @staticmethod
    def subscribe(
        db: Session,
        user: User,
        payload: SubscribeRequest,
        *,
        admin_override: bool = False,
        amount_paid: Optional[Decimal] = None,
        keep_pending: bool = False,
        allow_duplicate: bool = False,
    ) -> UserSubscription:
        SubscriptionService._expire_due_subscriptions(db, user.id)
        pkg = SubscriptionService._resolve_package(db, payload)
        is_mandatory_reg = str(pkg.code or "").strip().upper() == "MERCHANT_REGISTER_1000"
        if not pkg.is_active and not admin_override and not is_mandatory_reg:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Package is not available.")

        merchant_profile_id = payload.merchant_profile_id
        if SubscriptionService._audience_value(pkg) == "MERCHANT":
            from app.services.merchant_service import MerchantService

            merchant = None
            if merchant_profile_id:
                merchant = (
                    db.query(MerchantProfile)
                    .filter(MerchantProfile.id == merchant_profile_id)
                    .first()
                )
                if merchant is None:
                    merchant = (
                        db.query(MerchantProfile)
                        .filter(MerchantProfile.user_id == merchant_profile_id)
                        .order_by(MerchantProfile.id.desc())
                        .first()
                    )
            if merchant is None:
                merchant = MerchantService.find_for_user(db, user)
            if merchant is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Merchant profile not found.",
                )
            merchant = SubscriptionService._assert_merchant_access(db, user, merchant.id)
            status_ok = SubscriptionService._is_merchant_approved(merchant)
            if not keep_pending and not status_ok and not is_mandatory_reg:
                merchant.status = "APPROVED"
                merchant.approval_status = "APPROVED"
                db.commit()
                db.refresh(merchant)
            merchant_profile_id = merchant.id
        else:
            merchant_profile_id = None

        now = datetime.now(timezone.utc)
        paid = SubscriptionService._money(amount_paid if amount_paid is not None else pkg.price)
        is_renew = bool(getattr(payload, "renew", False))
        existing_sub = SubscriptionService._find_active_duplicate_sub(
            db, user.id, pkg, merchant_profile_id
        )
        if existing_sub is not None:
            if is_renew:
                base_exp = _as_utc(existing_sub.expires_at) if existing_sub.expires_at else now
                if not base_exp or base_exp < now:
                    base_exp = now
                existing_sub.expires_at = (
                    base_exp + timedelta(days=pkg.duration_days) if pkg.duration_days else existing_sub.expires_at
                )
                if payload.payment_reference:
                    existing_sub.payment_reference = payload.payment_reference
                if paid and paid > 0:
                    existing_sub.amount_paid = (existing_sub.amount_paid or Decimal("0")) + paid
                sub = existing_sub
                db.commit()
                db.refresh(sub)
            elif not allow_duplicate and not admin_override and not is_mandatory_reg:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="You are already subscribed to this plan while it is active.",
                )
            else:
                expires_at = now + timedelta(days=pkg.duration_days) if pkg.duration_days else None
                sub = UserSubscription(
                    user_id=user.id,
                    merchant_profile_id=merchant_profile_id,
                    package_id=pkg.id,
                    status=UserSubscriptionStatus.ACTIVE,
                    amount_paid=paid,
                    currency=pkg.currency,
                    payment_reference=payload.payment_reference,
                    started_at=now,
                    expires_at=expires_at,
                )
                db.add(sub)
                db.commit()
                db.refresh(sub)
        else:
            expires_at = now + timedelta(days=pkg.duration_days) if pkg.duration_days else None
            sub = UserSubscription(
                user_id=user.id,
                merchant_profile_id=merchant_profile_id,
                package_id=pkg.id,
                status=UserSubscriptionStatus.ACTIVE,
                amount_paid=paid,
                currency=pkg.currency,
                payment_reference=payload.payment_reference,
                started_at=now,
                expires_at=expires_at,
            )
            db.add(sub)
            db.commit()
            db.refresh(sub)

        if paid and paid > 0:
            try:
                import uuid
                import logging
                from app.services.wallet_service import WalletService
                from app.db.models.wallet import (
                    WalletTransaction,
                    WalletTransactionType,
                    WalletLedgerDirection,
                )
                company_wallet = WalletService.get_company_wallet(db)
                locked_company = WalletService._lock_wallet(db, company_wallet.id)
                group_id = str(uuid.uuid4())
                txn = WalletTransaction(
                    group_id=group_id,
                    transaction_type=WalletTransactionType.ADMIN_CREDIT,
                    amount=paid,
                    currency=pkg.currency or "INR",
                    description=f"Subscription Revenue: {pkg.name} from {user.name or user.phone} (₹{paid})",
                    initiated_by_user_id=user.id,
                    reference_id=payload.payment_reference or f"SUB-{sub.id}",
                )
                db.add(txn)
                db.flush()

                WalletService._apply_ledger_line(
                    db,
                    txn,
                    locked_company,
                    WalletLedgerDirection.CREDIT,
                    paid,
                    counterparty_wallet_id=None,
                    note=f"Subscription fee for package '{pkg.name}' (User #{user.id})",
                )
                db.commit()
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Failed to record subscription revenue to company wallet: {e}", exc_info=True)

        if SubscriptionService._audience_value(pkg) == "USER":
            SubscriptionService._apply_user_entitlements(db, user.id)
        else:
            SubscriptionService._apply_merchant_entitlements(db, merchant_profile_id)

        sub = (
            db.query(UserSubscription)
            .options(joinedload(UserSubscription.package))
            .filter(UserSubscription.id == sub.id)
            .first()
        )
        return sub

    @staticmethod
    def admin_assign(db: Session, data: AdminAssignSubscriptionRequest) -> UserSubscription:
        user = db.query(User).filter(User.id == data.user_id).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
        payload = SubscribeRequest(
            package_id=data.package_id,
            merchant_profile_id=data.merchant_profile_id,
            payment_reference=data.payment_reference or "ADMIN_ASSIGN",
        )
        return SubscriptionService.subscribe(
            db=db,
            user=user,
            payload=payload,
            admin_override=True,
            amount_paid=data.amount_paid,
        )

    @staticmethod
    def list_user_subscriptions(
        db: Session,
        user: User,
        *,
        merchant_profile_id: Optional[int] = None,
    ) -> List[UserSubscription]:
        SubscriptionService._expire_due_subscriptions(db, user.id)
        q = (
            db.query(UserSubscription)
            .options(joinedload(UserSubscription.package))
            .filter(UserSubscription.user_id == user.id)
            .order_by(UserSubscription.created_at.desc())
        )
        if merchant_profile_id is not None:
            q = q.filter(UserSubscription.merchant_profile_id == merchant_profile_id)
        return q.all()

    @staticmethod
    def get_active_summary(db: Session, user: User) -> Tuple[List[UserSubscription], List[UserSubscription], User]:
        SubscriptionService._expire_due_subscriptions(db, user.id)
        subs = SubscriptionService.list_user_subscriptions(db, user)
        now = datetime.now(timezone.utc)
        user_subs: List[UserSubscription] = []
        merchant_subs: List[UserSubscription] = []
        for sub in subs:
            if sub.status != UserSubscriptionStatus.ACTIVE:
                continue
            if sub.expires_at and _as_utc(sub.expires_at) < now:
                continue
            aud = sub.package.audience if sub.package else None
            if aud == SubscriptionAudience.MERCHANT:
                merchant_subs.append(sub)
            else:
                user_subs.append(sub)
        user = SubscriptionService._apply_user_entitlements(db, user.id)
        return user_subs, merchant_subs, user

    @staticmethod
    def merchant_for_account(db: Session, user: User) -> Optional[MerchantProfile]:
        from app.services.merchant_service import MerchantService

        return MerchantService.find_for_user(db, user)

    @staticmethod
    def cancel_subscription(db: Session, user: User, subscription_id: int) -> UserSubscription:
        sub = (
            db.query(UserSubscription)
            .options(joinedload(UserSubscription.package))
            .filter(UserSubscription.id == subscription_id, UserSubscription.user_id == user.id)
            .first()
        )
        if not sub:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found.")
        if sub.status != UserSubscriptionStatus.ACTIVE:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Subscription is not active.")
        sub.status = UserSubscriptionStatus.CANCELLED
        sub.cancelled_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(sub)

        if sub.package and sub.package.audience == SubscriptionAudience.USER:
            SubscriptionService._apply_user_entitlements(db, user.id)
        elif sub.merchant_profile_id:
            SubscriptionService._apply_merchant_entitlements(db, sub.merchant_profile_id)
        return sub

    @staticmethod
    def create_razorpay_order(
        db: Session,
        user: User,
        payload: Any,
    ) -> Dict[str, Any]:
        import uuid
        from app.db.models.wallet import WalletTopupOrder, WalletTopupStatus
        from app.services.razorpay_service import RazorpayService

        req_payload = SubscribeRequest(
            package_id=getattr(payload, "package_id", None),
            package_code=getattr(payload, "package_code", None),
            merchant_profile_id=getattr(payload, "merchant_profile_id", None),
        )
        pkg = SubscriptionService._resolve_package(db, req_payload)
        is_mandatory_reg = str(pkg.code or "").strip().upper() == "MERCHANT_REGISTER_1000"
        if not pkg.is_active and not is_mandatory_reg:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Package is not available.")

        merchant_profile_id = getattr(payload, "merchant_profile_id", None)
        if SubscriptionService._audience_value(pkg) == "MERCHANT":
            from app.services.merchant_service import MerchantService

            merchant = None
            if merchant_profile_id:
                merchant = (
                    db.query(MerchantProfile)
                    .filter(MerchantProfile.id == merchant_profile_id)
                    .first()
                )
            if merchant is None:
                merchant = MerchantService.find_for_user(db, user)
            if merchant is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Merchant profile not found.",
                )
            merchant = SubscriptionService._assert_merchant_access(db, user, merchant.id)
            merchant_profile_id = merchant.id
        else:
            merchant_profile_id = None

        is_renew = bool(getattr(payload, "renew", False))
        if not is_renew and not is_mandatory_reg:
            existing_sub = SubscriptionService._find_active_duplicate_sub(
                db, user.id, pkg, merchant_profile_id
            )
            if existing_sub is not None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="You are already subscribed to this plan while it is active.",
                )

        amount = SubscriptionService._money(pkg.price)
        if amount <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Free packages do not require Razorpay checkout. Use /subscriptions/subscribe directly.",
            )

        amount_paise = RazorpayService.inr_to_paise(amount)
        receipt = f"SUB-{uuid.uuid4().hex[:12].upper()}"
        notes = {
            "user_id": str(user.id),
            "package_id": str(pkg.id),
            "package_code": str(pkg.code),
            "purpose": "subscription_checkout",
        }
        if merchant_profile_id:
            notes["merchant_profile_id"] = str(merchant_profile_id)

        rp_order = RazorpayService.create_order(
            amount_paise=amount_paise,
            receipt=receipt,
            notes=notes,
        )

        checkout_row = WalletTopupOrder(
            user_id=user.id,
            merchant_profile_id=merchant_profile_id,
            amount=amount,
            amount_paise=amount_paise,
            currency=pkg.currency or "INR",
            receipt=receipt,
            razorpay_order_id=str(rp_order["id"]),
            status=WalletTopupStatus.CREATED,
            failure_reason=f"SUBSCRIPTION:{pkg.code}",
        )
        db.add(checkout_row)
        db.commit()
        db.refresh(checkout_row)

        return {
            "message": "Razorpay subscription order created",
            "razorpay_key_id": RazorpayService.get_public_key(),
            "razorpay_order_id": checkout_row.razorpay_order_id,
            "amount": amount,
            "amount_paise": amount_paise,
            "currency": checkout_row.currency,
            "package_id": pkg.id,
            "package_code": pkg.code,
            "package_name": pkg.name,
            "merchant_profile_id": merchant_profile_id,
        }

    @staticmethod
    def verify_razorpay_and_subscribe(
        db: Session,
        user: User,
        payload: Any,
    ) -> UserSubscription:
        from app.db.models.wallet import WalletTopupOrder, WalletTopupStatus
        from app.services.razorpay_service import RazorpayService

        order_id = str(payload.razorpay_order_id).strip()
        payment_id = str(payload.razorpay_payment_id).strip()
        signature = str(payload.razorpay_signature).strip()

        if not order_id.startswith("order_dev_"):
            RazorpayService.verify_payment_signature(order_id, payment_id, signature)

        order_row = (
            db.query(WalletTopupOrder)
            .filter(
                WalletTopupOrder.razorpay_order_id == order_id,
                WalletTopupOrder.user_id == user.id,
            )
            .first()
        )
        if order_row and order_row.status != WalletTopupStatus.PAID:
            order_row.status = WalletTopupStatus.PAID
            order_row.razorpay_payment_id = payment_id
            order_row.paid_at = datetime.now(timezone.utc)
            db.commit()

        sub_req = SubscribeRequest(
            package_id=getattr(payload, "package_id", None),
            package_code=getattr(payload, "package_code", None),
            merchant_profile_id=getattr(payload, "merchant_profile_id", None)
            or (order_row.merchant_profile_id if order_row else None),
            payment_reference=payment_id or order_id,
            renew=bool(getattr(payload, "renew", False)),
        )
        return SubscriptionService.subscribe(db=db, user=user, payload=sub_req)

    @staticmethod
    def create_merchant_registration_order(
        db: Session,
        email: Optional[str] = None,
        business_name: Optional[str] = None,
        package_id: Optional[int] = None,
        package_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        import uuid
        from app.services.razorpay_service import RazorpayService

        SubscriptionService.ensure_default_packages(db)
        pkg = None
        if package_id or package_code:
            pkg = SubscriptionService._resolve_package(
                db, SubscribeRequest(package_id=package_id, package_code=package_code)
            )
            if not pkg.is_active:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Selected subscription package is not available.",
                )
            if SubscriptionService._audience_value(pkg) != "MERCHANT":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Please select a Merchant subscription plan for registration.",
                )
            amount = SubscriptionService._money(pkg.price or Decimal("0"))
        else:
            pkg = (
                db.query(SubscriptionPackage)
                .filter(SubscriptionPackage.code == "MERCHANT_REGISTER_1000")
                .first()
            )
            amount = SubscriptionService._money(pkg.price if pkg and pkg.price else Decimal("1000"))
            if amount <= 0:
                amount = Decimal("1000.00")

        amount_paise = RazorpayService.inr_to_paise(amount) if amount > 0 else 0
        receipt = f"MREG-{uuid.uuid4().hex[:12].upper()}"
        chosen_code = str(pkg.code) if pkg else "MERCHANT_REGISTER_1000"
        chosen_name = str(pkg.name) if pkg else "Merchant Registration"
        notes = {
            "purpose": "merchant_registration",
            "package_id": str(pkg.id) if pkg else "",
            "package_code": chosen_code,
            "email": str(email or ""),
            "business_name": str(business_name or ""),
        }
        if amount <= 0:
            order_id = f"order_free_mreg_{uuid.uuid4().hex[:12]}"
        elif RazorpayService.is_configured():
            rp_order = RazorpayService.create_order(
                amount_paise=amount_paise,
                receipt=receipt,
                notes=notes,
            )
            order_id = str(rp_order["id"])
        else:
            order_id = f"order_dev_mreg_{uuid.uuid4().hex[:12]}"
        return {
            "message": f"Razorpay order created for {chosen_name}",
            "razorpay_key_id": RazorpayService.get_public_key(),
            "razorpay_order_id": order_id,
            "amount": float(amount),
            "amount_paise": amount_paise,
            "currency": "INR",
            "package_id": pkg.id if pkg else None,
            "package_code": chosen_code,
            "package_name": chosen_name,
        }

    @staticmethod
    def assert_merchant_registration_payment(
        razorpay_order_id: Optional[str],
        razorpay_payment_id: Optional[str],
        razorpay_signature: Optional[str],
        db: Optional[Session] = None,
        package_id: Optional[int] = None,
        package_code: Optional[str] = None,
    ) -> Tuple[str, str]:
        from app.services.razorpay_service import RazorpayService

        order_id = str(razorpay_order_id or "").strip()
        payment_id = str(razorpay_payment_id or "").strip()
        signature = str(razorpay_signature or "").strip()

        if (package_id or package_code) and db is not None:
            pkg = SubscriptionService._resolve_package(
                db, SubscribeRequest(package_id=package_id, package_code=package_code)
            )
            if not pkg.is_active:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Selected subscription package is not available.",
                )
            if SubscriptionService._audience_value(pkg) != "MERCHANT":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Please select a Merchant subscription plan for registration.",
                )
            if SubscriptionService._money(pkg.price or Decimal("0")) <= 0:
                return (order_id or f"FREE_REG_{pkg.id}"), (payment_id or f"FREE_REG_{pkg.code}")

        if not order_id or not payment_id:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Please select a Merchant Subscription Plan and complete payment via Razorpay to register.",
            )
        if not order_id.startswith("order_dev_mreg_") and not order_id.startswith("order_dev_"):
            RazorpayService.verify_payment_signature(order_id, payment_id, signature)
        return order_id, payment_id

    @staticmethod
    def record_merchant_registration_subscription(
        db: Session,
        user: User,
        merchant: MerchantProfile,
        payment_reference: str,
        package_id: Optional[int] = None,
        package_code: Optional[str] = None,
    ) -> Optional[UserSubscription]:
        SubscriptionService.ensure_default_packages(db)
        pkg = None
        if package_id or package_code:
            pkg = SubscriptionService._resolve_package(
                db, SubscribeRequest(package_id=package_id, package_code=package_code)
            )
        else:
            pkg = (
                db.query(SubscriptionPackage)
                .filter(SubscriptionPackage.code == "MERCHANT_REGISTER_1000")
                .first()
            )
        if not pkg:
            return None
        return SubscriptionService.subscribe(
            db=db,
            user=user,
            payload=SubscribeRequest(
                package_id=pkg.id,
                merchant_profile_id=merchant.id,
                payment_reference=payment_reference,
            ),
            admin_override=True,
            keep_pending=True,
            allow_duplicate=True,
            amount_paid=SubscriptionService._money(pkg.price if pkg.price is not None else Decimal("0")),
        )

    @staticmethod
    def _build_admin_subscriber_item(
        sub: UserSubscription,
        user_obj: Optional[User] = None,
        merchant_obj: Optional[MerchantProfile] = None,
    ) -> Dict[str, Any]:
        pkg = sub.package
        aud_raw = getattr(pkg.audience, "value", pkg.audience) if pkg else ("MERCHANT" if sub.merchant_profile_id else "USER")
        aud_str = str(aud_raw or "USER").upper()
        st_raw = getattr(sub.status, "value", sub.status)
        st_str = str(st_raw or "ACTIVE").upper()
        now = datetime.now(timezone.utc)
        if st_str == "ACTIVE" and sub.expires_at is not None:
            exp = _as_utc(sub.expires_at)
            if exp and exp < now:
                st_str = "EXPIRED"
        days_rem = (
            SubscriptionService._days_remaining(sub.expires_at)
            if st_str == "ACTIVE"
            else 0
        )
        return {
            "subscription_id": sub.id,
            "subscription_code": sub.subscription_code,
            "audience": aud_str,
            "status": st_str,
            "package_id": sub.package_id,
            "package_code": pkg.code if pkg else None,
            "package_name": (pkg.name if pkg else None) or "Subscription Plan",
            "package_price": float(pkg.price if pkg and pkg.price is not None else (sub.amount_paid or 0)),
            "amount_paid": float(sub.amount_paid or 0),
            "currency": sub.currency or "INR",
            "duration_days": pkg.duration_days if pkg else None,
            "days_remaining": days_rem,
            "payment_reference": sub.payment_reference,
            "started_at": sub.started_at,
            "expires_at": sub.expires_at,
            "cancelled_at": sub.cancelled_at,
            "features": list(pkg.features or []) if pkg else [],
            "grants": dict(pkg.grants or {}) if pkg else {},
            "user_id": sub.user_id,
            "user_name": user_obj.name if user_obj else None,
            "user_email": user_obj.email if user_obj else None,
            "user_phone": user_obj.phone if user_obj else None,
            "login_id": getattr(user_obj, "login_id", None) if user_obj else None,
            "user_code": getattr(user_obj, "user_code", None) if user_obj else None,
            "merchant_profile_id": sub.merchant_profile_id,
            "merchant_business_name": merchant_obj.business_name if merchant_obj else None,
            "merchant_city": merchant_obj.city if merchant_obj else None,
            "merchant_district": merchant_obj.district if merchant_obj else None,
            "merchant_approval_status": merchant_obj.approval_status if merchant_obj else None,
        }

    @staticmethod
    def admin_list_subscribers(
        db: Session,
        *,
        audience: Optional[str] = None,
        status_filter: Optional[str] = None,
        search: Optional[str] = None,
    ) -> Dict[str, Any]:
        SubscriptionService._expire_due_subscriptions(db)
        rows = (
            db.query(UserSubscription)
            .join(SubscriptionPackage)
            .options(joinedload(UserSubscription.package))
            .filter(func.upper(SubscriptionPackage.code) != "MERCHANT_REGISTER_1000")
            .order_by(UserSubscription.id.desc())
            .all()
        )
        user_ids = {r.user_id for r in rows if r.user_id}
        merch_ids = {r.merchant_profile_id for r in rows if r.merchant_profile_id}

        user_map = (
            {u.id: u for u in db.query(User).filter(User.id.in_(list(user_ids))).all()}
            if user_ids
            else {}
        )
        merch_map = (
            {
                m.id: m
                for m in db.query(MerchantProfile)
                .filter(MerchantProfile.id.in_(list(merch_ids)))
                .all()
            }
            if merch_ids
            else {}
        )

        all_items = [
            SubscriptionService._build_admin_subscriber_item(
                row,
                user_obj=user_map.get(row.user_id),
                merchant_obj=merch_map.get(row.merchant_profile_id),
            )
            for row in rows
        ]

        summary = {
            "total": len(all_items),
            "active_merchants": sum(
                1 for i in all_items if i["audience"] == "MERCHANT" and i["status"] == "ACTIVE"
            ),
            "active_customers": sum(
                1 for i in all_items if i["audience"] == "USER" and i["status"] == "ACTIVE"
            ),
            "stopped_or_expired": sum(
                1 for i in all_items if i["status"] in ("CANCELLED", "EXPIRED")
            ),
            "total_revenue": float(sum(i["amount_paid"] or 0 for i in all_items)),
        }

        filtered = all_items
        if audience:
            aud_norm = audience.strip().upper()
            if aud_norm in ("CUSTOMER", "CUSTOMERS"):
                aud_norm = "USER"
            if aud_norm in ("MERCHANT", "MERCHANTS"):
                aud_norm = "MERCHANT"
            if aud_norm in ("MERCHANT", "USER"):
                filtered = [i for i in filtered if i["audience"] == aud_norm]

        if status_filter and status_filter.strip().upper() != "ALL":
            st_norm = status_filter.strip().upper()
            if st_norm == "STOPPED":
                st_norm = "CANCELLED"
            filtered = [i for i in filtered if i["status"] == st_norm]

        if search and search.strip():
            q = search.strip().lower()
            filtered = [
                i
                for i in filtered
                if q in str(i.get("user_name") or "").lower()
                or q in str(i.get("user_email") or "").lower()
                or q in str(i.get("user_phone") or "").lower()
                or q in str(i.get("login_id") or "").lower()
                or q in str(i.get("user_code") or "").lower()
                or q in str(i.get("merchant_business_name") or "").lower()
                or q in str(i.get("package_name") or "").lower()
                or q in str(i.get("package_code") or "").lower()
                or q in str(i.get("subscription_code") or "").lower()
            ]

        return {"items": filtered, "summary": summary}

    @staticmethod
    def admin_stop_subscription(
        db: Session,
        subscription_id: int,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        sub = (
            db.query(UserSubscription)
            .options(joinedload(UserSubscription.package))
            .filter(UserSubscription.id == subscription_id)
            .first()
        )
        if not sub:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found."
            )
        if sub.status != UserSubscriptionStatus.ACTIVE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Subscription is already stopped or expired.",
            )
        sub.status = UserSubscriptionStatus.CANCELLED
        sub.cancelled_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(sub)

        if sub.package and SubscriptionService._audience_value(sub.package) == "USER":
            SubscriptionService._apply_user_entitlements(db, sub.user_id)
        elif sub.merchant_profile_id:
            SubscriptionService._apply_merchant_entitlements(db, sub.merchant_profile_id)
        else:
            SubscriptionService._apply_user_entitlements(db, sub.user_id)

        user_obj = db.query(User).filter(User.id == sub.user_id).first()
        merch_obj = (
            db.query(MerchantProfile).filter(MerchantProfile.id == sub.merchant_profile_id).first()
            if sub.merchant_profile_id
            else None
        )
        try:
            from app.services.notification_service import NotificationService

            pkg_title = sub.package.name if sub.package else "Subscription Plan"
            NotificationService.create_notification(
                db=db,
                user_id=sub.user_id,
                title="Subscription Stopped by Admin",
                message=f"Your '{pkg_title}' subscription was stopped by administration.{f' Reason: {reason}' if reason else ''}",
                type="SUBSCRIPTION_STOPPED",
                data={"subscription_id": sub.id, "package_id": sub.package_id},
            )
        except Exception:
            pass
        return SubscriptionService._build_admin_subscriber_item(
            sub, user_obj=user_obj, merchant_obj=merch_obj
        )

    @staticmethod
    def admin_unstop_subscription(
        db: Session,
        subscription_id: int,
    ) -> Dict[str, Any]:
        sub = (
            db.query(UserSubscription)
            .options(joinedload(UserSubscription.package))
            .filter(UserSubscription.id == subscription_id)
            .first()
        )
        if not sub:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found."
            )
        now = datetime.now(timezone.utc)
        sub.status = UserSubscriptionStatus.ACTIVE
        sub.cancelled_at = None
        if sub.expires_at is not None:
            exp_dt = sub.expires_at
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=timezone.utc)
            if exp_dt <= now:
                days = int(getattr(sub.package, "duration_days", None) or 30)
                sub.expires_at = now + timedelta(days=days)
        db.commit()
        db.refresh(sub)

        if sub.package and SubscriptionService._audience_value(sub.package) == "USER":
            SubscriptionService._apply_user_entitlements(db, sub.user_id)
        elif sub.merchant_profile_id:
            SubscriptionService._apply_merchant_entitlements(db, sub.merchant_profile_id)
        else:
            SubscriptionService._apply_user_entitlements(db, sub.user_id)

        user_obj = db.query(User).filter(User.id == sub.user_id).first()
        merch_obj = (
            db.query(MerchantProfile).filter(MerchantProfile.id == sub.merchant_profile_id).first()
            if sub.merchant_profile_id
            else None
        )
        return SubscriptionService._build_admin_subscriber_item(
            sub, user_obj=user_obj, merchant_obj=merch_obj
        )
