from datetime import datetime, timezone
from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy import or_, func, text
from sqlalchemy.orm import Session

from app.db.models.promotion import Promotion
from app.schemas.promotion import PromotionCreateRequest, PromotionUpdateRequest


def _as_utc(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class PromotionService:
    _STYLE_COLUMNS_ENSURED = False

    @staticmethod
    def ensure_style_columns(db: Session) -> None:
        if PromotionService._STYLE_COLUMNS_ENSURED:
            return
        try:
            db.execute(text("ALTER TABLE promotions ADD COLUMN IF NOT EXISTS bg_color VARCHAR(255)"))
            db.execute(text("ALTER TABLE promotions ADD COLUMN IF NOT EXISTS text_color VARCHAR(50)"))
            db.commit()
        except Exception:
            db.rollback()
        PromotionService._STYLE_COLUMNS_ENSURED = True

    @staticmethod
    def is_merchant_ad_subscription_active(db: Session, merchant_id: Optional[int]) -> bool:
        if not merchant_id:
            return False
        from app.db.models.merchant import MerchantProfile
        from app.db.models.subscription import (
            SubscriptionAudience,
            SubscriptionPackage,
            UserSubscription,
            UserSubscriptionStatus,
        )

        merchant = db.query(MerchantProfile).filter(MerchantProfile.id == merchant_id).first()
        if not merchant:
            return False

        now = datetime.now(timezone.utc)
        subs = (
            db.query(UserSubscription)
            .join(SubscriptionPackage)
            .filter(
                UserSubscription.merchant_profile_id == merchant_id,
                UserSubscription.status == UserSubscriptionStatus.ACTIVE,
                SubscriptionPackage.audience == SubscriptionAudience.MERCHANT,
            )
            .all()
        )
        valid_subs = [
            s for s in subs if s.expires_at is None or (_as_utc(s.expires_at) is not None and _as_utc(s.expires_at) >= now)
        ]
        if valid_subs:
            from app.services.subscription_service import MERCHANT_AD_PERMISSION_KEYS, SubscriptionService

            grants = SubscriptionService.get_merchant_grants(
                db, merchant_id, include_user_seller=False
            )
            has_any_ad = any(grants.get(k) for k in MERCHANT_AD_PERMISSION_KEYS)
            if not merchant.has_active_subscription:
                merchant.has_active_subscription = True
                db.commit()
            return has_any_ad
        return bool(getattr(merchant, "has_active_subscription", False))

    @staticmethod
    def get_all(
        db: Session,
        status_filter: Optional[str] = None,
        search: Optional[str] = None,
        placement: Optional[str] = None,
    ) -> List[Promotion]:
        PromotionService.ensure_style_columns(db)
        query = db.query(Promotion).filter(Promotion.type != "SYSTEM_CONFIG")
        if status_filter and status_filter.lower() != "all":
            if status_filter.lower() in ("active", "approved"):
                query = query.filter(or_(Promotion.status == "active", Promotion.status == "approved"))
            else:
                query = query.filter(Promotion.status == status_filter.lower())
        if placement:
            query = query.filter(Promotion.placement.ilike(f"%{placement}%"))
        if search:
            s = f"%{search}%"
            query = query.filter(
                or_(
                    Promotion.title.ilike(s),
                    Promotion.category.ilike(s),
                    Promotion.placement.ilike(s),
                    Promotion.location.ilike(s),
                )
            )
        return query.order_by(Promotion.id.desc()).all()

    @staticmethod
    def get_merchant_promotions(
        db: Session,
        merchant_id: int,
        status_filter: Optional[str] = None,
        placement: Optional[str] = None,
    ) -> List[Promotion]:
        PromotionService.ensure_style_columns(db)
        query = db.query(Promotion).filter(
            Promotion.merchant_id == merchant_id,
            Promotion.type != "SYSTEM_CONFIG",
        )
        if status_filter and status_filter.lower() != "all":
            if status_filter.lower() in ("active", "approved"):
                query = query.filter(or_(Promotion.status == "active", Promotion.status == "approved"))
            else:
                query = query.filter(Promotion.status == status_filter.lower())
        if placement:
            query = query.filter(Promotion.placement.ilike(f"%{placement}%"))
        return query.order_by(Promotion.id.desc()).all()

    @staticmethod
    def get_by_id(db: Session, promo_id: int) -> Promotion:
        PromotionService.ensure_style_columns(db)
        promo = db.query(Promotion).filter(Promotion.id == promo_id).first()
        if not promo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Promotion with ID {promo_id} not found",
            )
        return promo

    @staticmethod
    def create(db: Session, data: PromotionCreateRequest) -> Promotion:
        PromotionService.ensure_style_columns(db)
        # Generate unique promo_code
        max_id = db.query(func.max(Promotion.id)).scalar() or 0
        counter = max_id + 1
        code = f"BNR-{counter:03d}"
        while db.query(Promotion).filter(Promotion.promo_code == code).first():
            counter += 1
            code = f"BNR-{counter:03d}"

        placement_str = data.placement or "Home Top"
        resolved_media_type = (data.media_type or ("video" if data.video_url else "image")).strip().lower()
        if resolved_media_type not in ("image", "video", "text"):
            resolved_media_type = "video" if data.video_url else "image"

        promo = Promotion(
            promo_code=code,
            title=data.title,
            category=data.category,
            type=data.type or ("Text Banner" if resolved_media_type == "text" else ("Text Carousel" if "Moving" in placement_str or "Ticker" in placement_str else "Featured")),
            placement=placement_str,
            location=data.location,
            start_date=data.start_date or "2026-10-01",
            end_date=data.end_date or "2026-12-31",
            status=data.status or "active",
            impressions=data.impressions or 0,
            clicks=data.clicks or 0,
            image_url=data.image_url,
            video_url=data.video_url,
            media_type=resolved_media_type,
            bg_color=data.bg_color,
            text_color=data.text_color,
            thumbnail_url=data.thumbnail_url,
            target_url=data.target_url,
            description=data.description,
            merchant_id=data.merchant_id,
            merchant_name=data.merchant_name,
        )
        db.add(promo)
        db.commit()
        db.refresh(promo)
        return promo

    @staticmethod
    def update(db: Session, promo_id: int, data: PromotionUpdateRequest) -> Promotion:
        promo = PromotionService.get_by_id(db, promo_id)
        if data.title is not None:
            promo.title = data.title
        if data.category is not None:
            promo.category = data.category
        if data.type is not None:
            promo.type = data.type
        if data.placement is not None:
            promo.placement = data.placement
        if data.location is not None:
            promo.location = data.location
        if data.start_date is not None:
            promo.start_date = data.start_date
        if data.end_date is not None:
            promo.end_date = data.end_date
        if data.status is not None:
            promo.status = data.status
        if data.impressions is not None:
            promo.impressions = data.impressions
        if data.clicks is not None:
            promo.clicks = data.clicks
        if data.image_url is not None:
            promo.image_url = data.image_url
        if data.video_url is not None:
            promo.video_url = data.video_url
        if data.media_type is not None:
            mt = data.media_type.strip().lower()
            if mt in ("image", "video", "text"):
                promo.media_type = mt
        if data.bg_color is not None:
            promo.bg_color = data.bg_color
        if data.text_color is not None:
            promo.text_color = data.text_color
        if data.thumbnail_url is not None:
            promo.thumbnail_url = data.thumbnail_url
        if data.target_url is not None:
            promo.target_url = data.target_url
        if data.description is not None:
            promo.description = data.description
        if data.merchant_id is not None:
            promo.merchant_id = data.merchant_id
        if data.merchant_name is not None:
            promo.merchant_name = data.merchant_name
        if data.rejection_reason is not None:
            promo.rejection_reason = data.rejection_reason

        db.commit()
        db.refresh(promo)
        return promo

    @staticmethod
    def approve(db: Session, promo_id: int) -> Promotion:
        promo = PromotionService.get_by_id(db, promo_id)
        promo.status = "active"
        promo.rejection_reason = None
        db.commit()
        db.refresh(promo)
        return promo

    @staticmethod
    def reject(db: Session, promo_id: int, reason: Optional[str] = None) -> Promotion:
        promo = PromotionService.get_by_id(db, promo_id)
        promo.status = "rejected"
        promo.rejection_reason = reason or "Promotion rejected by administration."
        db.commit()
        db.refresh(promo)
        return promo

    @staticmethod
    def get_public_active(
        db: Session,
        search: Optional[str] = None,
        placement: Optional[str] = None,
    ) -> List[Promotion]:
        from app.db.models.merchant import MerchantProfile
        PromotionService.ensure_style_columns(db)

        query = db.query(Promotion).filter(
            or_(Promotion.status == "active", Promotion.status == "approved"),
            Promotion.type != "SYSTEM_CONFIG",
        )
        if placement:
            query = query.filter(Promotion.placement.ilike(f"%{placement}%"))
        else:
            # Keep store-only merchant ads scoped to each store's Merchant Detail page
            query = query.filter(
                or_(Promotion.placement.is_(None), Promotion.placement != "Merchant Store")
            )
        if search:
            s = f"%{search}%"
            query = query.filter(
                or_(
                    Promotion.title.ilike(s),
                    Promotion.category.ilike(s),
                    Promotion.placement.ilike(s),
                    Promotion.location.ilike(s),
                )
            )

        candidates = query.order_by(Promotion.id.desc()).all()
        valid_promos = []

        # Cache merchant check
        merchant_cache = {}

        for p in candidates:
            if p.merchant_id:
                if p.merchant_id not in merchant_cache:
                    m = db.query(MerchantProfile).filter(MerchantProfile.id == p.merchant_id).first()
                    merchant_cache[p.merchant_id] = m
                merch = merchant_cache[p.merchant_id]
                # Conditions: 1. Merchant approved, 2. Merchant promotion access ON
                if not merch:
                    continue
                if str(merch.approval_status).upper() != "APPROVED" and str(merch.status).upper() != "APPROVED":
                    continue
                if getattr(merch, "can_create_promotions", True) is False:
                    continue

            valid_promos.append(p)

        return valid_promos

    @staticmethod
    def delete(db: Session, promo_id: int) -> bool:
        promo = PromotionService.get_by_id(db, promo_id)
        db.delete(promo)
        db.commit()
        return True
