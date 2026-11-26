from datetime import date
from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.db.models.advertisement import MerchantAdvertisement
from app.db.models.merchant import MerchantProfile
from app.db.models.user import User
from app.schemas.advertisement import AdvertisementCreateRequest, AdvertisementUpdateRequest


class AdvertisementService:
    @staticmethod
    def ensure_table(db: Session) -> None:
        if db.info.get("merchant_ads_ready"):
            return
        bind = db.get_bind()
        if "merchant_advertisements" not in inspect(bind).get_table_names():
            MerchantAdvertisement.__table__.create(bind=bind, checkfirst=True)
        db.info["merchant_ads_ready"] = True

    @staticmethod
    def merchant_for_user(db: Session, user: User) -> MerchantProfile:
        merchant = (
            db.query(MerchantProfile)
            .filter(MerchantProfile.user_id == user.id)
            .order_by(MerchantProfile.id.desc())
            .first()
        )
        if not merchant and user.email:
            merchant = (
                db.query(MerchantProfile)
                .filter(MerchantProfile.email.ilike(user.email))
                .order_by(MerchantProfile.id.desc())
                .first()
            )
        if not merchant and user.phone:
            clean_phone = user.phone.strip().replace(" ", "").replace("-", "")[-10:]
            merchant = (
                db.query(MerchantProfile)
                .filter(MerchantProfile.phone.endswith(clean_phone))
                .order_by(MerchantProfile.id.desc())
                .first()
            )
        if not merchant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Merchant profile not found for current user.",
            )
        return merchant

    @staticmethod
    def _clean_status(value: Optional[str]) -> str:
        status_value = (value or "active").strip().lower()
        if status_value not in {"active", "inactive"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Advertisement status must be active or inactive.",
            )
        return status_value

    @staticmethod
    def create(db: Session, merchant: MerchantProfile, data: AdvertisementCreateRequest) -> MerchantAdvertisement:
        AdvertisementService.ensure_table(db)
        ad = MerchantAdvertisement(
            merchant_id=merchant.id,
            title=data.title.strip(),
            description=(data.description or "").strip() or None,
            image_url=(data.image_url or "").strip() or None,
            video_url=(data.video_url or "").strip() or None,
            link_url=(data.link_url or "").strip() or None,
            start_date=(data.start_date or "").strip() or None,
            end_date=(data.end_date or "").strip() or None,
            status=AdvertisementService._clean_status(data.status),
        )
        db.add(ad)
        db.commit()
        db.refresh(ad)
        return ad

    @staticmethod
    def list_for_merchant(db: Session, merchant_id: int) -> List[MerchantAdvertisement]:
        AdvertisementService.ensure_table(db)
        return (
            db.query(MerchantAdvertisement)
            .filter(MerchantAdvertisement.merchant_id == merchant_id)
            .order_by(MerchantAdvertisement.id.desc())
            .all()
        )

    @staticmethod
    def visible_on(ad: MerchantAdvertisement, today: Optional[str] = None) -> bool:
        if (ad.status or "").lower() != "active":
            return False
        current = today or date.today().isoformat()
        if ad.start_date and ad.start_date > current:
            return False
        if ad.end_date and ad.end_date < current:
            return False
        return True

    @staticmethod
    def list_visible(db: Session, merchant_id: int) -> List[MerchantAdvertisement]:
        return [ad for ad in AdvertisementService.list_for_merchant(db, merchant_id) if AdvertisementService.visible_on(ad)]

    @staticmethod
    def get_owned(db: Session, merchant_id: int, advertisement_id: int) -> MerchantAdvertisement:
        AdvertisementService.ensure_table(db)
        ad = (
            db.query(MerchantAdvertisement)
            .filter(
                MerchantAdvertisement.id == advertisement_id,
                MerchantAdvertisement.merchant_id == merchant_id,
            )
            .first()
        )
        if not ad:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Advertisement not found.")
        return ad

    @staticmethod
    def update(
        db: Session,
        merchant_id: int,
        advertisement_id: int,
        data: AdvertisementUpdateRequest,
    ) -> MerchantAdvertisement:
        ad = AdvertisementService.get_owned(db, merchant_id, advertisement_id)
        changes = data.model_dump(exclude_unset=True)
        if "title" in changes and changes["title"] is not None:
            ad.title = changes["title"].strip()
        for field in ("description", "image_url", "video_url", "link_url", "start_date", "end_date"):
            if field in changes:
                value = changes[field]
                setattr(ad, field, value.strip() if isinstance(value, str) and value.strip() else None)
        if "status" in changes and changes["status"] is not None:
            ad.status = AdvertisementService._clean_status(changes["status"])
        db.commit()
        db.refresh(ad)
        return ad

    @staticmethod
    def delete(db: Session, merchant_id: int, advertisement_id: int) -> None:
        ad = AdvertisementService.get_owned(db, merchant_id, advertisement_id)
        db.delete(ad)
        db.commit()
