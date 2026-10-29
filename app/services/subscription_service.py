from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, status
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
    AdminAssignSubscriptionRequest,
    SubscribeRequest,
    SubscriptionPackageCreateRequest,
    SubscriptionPackageUpdateRequest,
    UserSubscriptionResponse,
)


def _as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class SubscriptionService:
    DEFAULT_PACKAGES: List[Dict[str, Any]] = [
        {
            "code": "USER_FREE",
            "name": "User Free",
            "description": "Browse merchants, favorites, and wallet cashback.",
            "audience": SubscriptionAudience.USER,
            "price": Decimal("0"),
            "billing_period": "ONE_TIME",
            "duration_days": 3650,
            "features": ["Browse directory", "Wallet cashback"],
            "grants": {},
            "sort_order": 0,
        },
        {
            "code": "USER_SELLER_500",
            "name": "Seller Plan ₹500",
            "description": "List products on Logo marketplace.",
            "audience": SubscriptionAudience.USER,
            "price": Decimal("500"),
            "billing_period": "MONTHLY",
            "duration_days": 30,
            "features": ["List products", "Seller dashboard", "Order notifications"],
            "grants": {
                "can_sell_products": True,
                "is_subscriber": True,
                "subscription_plan": "500_SELLER",
            },
            "sort_order": 1,
        },
        {
            "code": "MERCHANT_PROMO_BASIC",
            "name": "Merchant Promotions",
            "description": "Create shop promotions and hero banners.",
            "audience": SubscriptionAudience.MERCHANT,
            "price": Decimal("999"),
            "billing_period": "MONTHLY",
            "duration_days": 30,
            "features": ["Create promotions", "Hero banners"],
            "grants": {"can_create_promotions": True},
            "sort_order": 0,
        },
        {
            "code": "MERCHANT_PREMIUM",
            "name": "Merchant Premium",
            "description": "Promotions plus premium discovery visibility.",
            "audience": SubscriptionAudience.MERCHANT,
            "price": Decimal("1999"),
            "billing_period": "MONTHLY",
            "duration_days": 30,
            "features": ["All promotion features", "Premium listing badge"],
            "grants": {"can_create_promotions": True, "premium_listing": True},
            "sort_order": 1,
        },
    ]

    @staticmethod
    def ensure_default_packages(db: Session) -> None:
        if db.query(SubscriptionPackage).count() > 0:
            return
        for row in SubscriptionService.DEFAULT_PACKAGES:
            pkg = SubscriptionPackage(
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
            db.add(pkg)
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
            q = q.filter(SubscriptionPackage.is_active == True)
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
    def create_package(db: Session, data: SubscriptionPackageCreateRequest) -> SubscriptionPackage:
        code = data.code.strip().upper()
        if db.query(SubscriptionPackage).filter(SubscriptionPackage.code == code).first():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Package code already exists.")
        pkg = SubscriptionPackage(
            code=code,
            name=data.name.strip(),
            description=data.description,
            audience=data.audience,
            price=SubscriptionService._money(data.price),
            currency=(data.currency or "INR").upper(),
            billing_period=data.billing_period,
            duration_days=data.duration_days,
            features=data.features or [],
            grants=data.grants or {},
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
        if data.features is not None:
            pkg.features = data.features
        if data.grants is not None:
            pkg.grants = data.grants
        if data.is_active is not None:
            pkg.is_active = data.is_active
        if data.sort_order is not None:
            pkg.sort_order = data.sort_order
        db.commit()
        db.refresh(pkg)
        return pkg

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
        if merchant.user_id != user.id and user.role not in (UserRole.ADMIN, UserRole.SUPER_ADMIN):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this merchant profile.",
            )
        return merchant

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
            if grants.get("can_sell_products"):
                can_sell = True
            if grants.get("is_subscriber"):
                is_subscriber = True
            if grants.get("subscription_plan"):
                plan = str(grants["subscription_plan"])
        user.can_sell_products = can_sell
        user.is_subscriber = is_subscriber or can_sell
        user.subscription_plan = plan
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def _apply_merchant_entitlements(db: Session, merchant_profile_id: int) -> MerchantProfile:
        merchant = db.query(MerchantProfile).filter(MerchantProfile.id == merchant_profile_id).first()
        if not merchant:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Merchant profile not found.")
        now = datetime.now(timezone.utc)
        active_subs = (
            db.query(UserSubscription)
            .join(SubscriptionPackage)
            .filter(
                UserSubscription.merchant_profile_id == merchant_profile_id,
                UserSubscription.status == UserSubscriptionStatus.ACTIVE,
                SubscriptionPackage.audience == SubscriptionAudience.MERCHANT,
            )
            .all()
        )
        active_subs = [
            s
            for s in active_subs
            if s.expires_at is None or _as_utc(s.expires_at) >= now
        ]
        can_promo = False
        for sub in active_subs:
            grants = (sub.package.grants or {}) if sub.package else {}
            if grants.get("can_create_promotions"):
                can_promo = True
        merchant.has_active_subscription = len(active_subs) > 0
        if active_subs:
            merchant.can_create_promotions = can_promo or True
        else:
            merchant.can_create_promotions = True
        db.commit()
        db.refresh(merchant)
        return merchant

    @staticmethod
    def subscribe(
        db: Session,
        user: User,
        payload: SubscribeRequest,
        *,
        admin_override: bool = False,
        amount_paid: Optional[Decimal] = None,
    ) -> UserSubscription:
        SubscriptionService._expire_due_subscriptions(db, user.id)
        pkg = SubscriptionService.get_package(db, payload.package_id)
        if not pkg.is_active:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Package is not available.")

        merchant_profile_id = payload.merchant_profile_id
        if pkg.audience == SubscriptionAudience.MERCHANT:
            if not merchant_profile_id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="merchant_profile_id is required for merchant subscription packages.",
                )
            SubscriptionService._assert_merchant_access(db, user, merchant_profile_id)
        elif merchant_profile_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="merchant_profile_id must not be set for user subscription packages.",
            )

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=pkg.duration_days) if pkg.duration_days else None
        paid = SubscriptionService._money(amount_paid if amount_paid is not None else pkg.price)

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

        if pkg.audience == SubscriptionAudience.USER:
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
