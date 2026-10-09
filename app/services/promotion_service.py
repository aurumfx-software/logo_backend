from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db.models.promotion import Promotion
from app.schemas.promotion import PromotionCreateRequest, PromotionUpdateRequest


class PromotionService:
    @staticmethod
    def get_all(
        db: Session,
        status_filter: Optional[str] = None,
        search: Optional[str] = None,
        placement: Optional[str] = None,
    ) -> List[Promotion]:
        query = db.query(Promotion)
        if status_filter and status_filter.lower() != "all":
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
    def get_by_id(db: Session, promo_id: int) -> Promotion:
        promo = db.query(Promotion).filter(Promotion.id == promo_id).first()
        if not promo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Promotion with ID {promo_id} not found",
            )
        return promo

    @staticmethod
    def create(db: Session, data: PromotionCreateRequest) -> Promotion:
        # Generate promo_code
        count = db.query(Promotion).count() + 1
        code = f"BNR-{count:03d}"

        placement_str = data.placement or "Home Top"
        if data.category and data.category not in placement_str:
            placement_str = f"{placement_str} ({data.category})"

        promo = Promotion(
            promo_code=code,
            title=data.title,
            category=data.category,
            type=data.type or "Featured",
            placement=placement_str,
            location=data.location,
            start_date=data.start_date or "2026-10-01",
            end_date=data.end_date or "2026-12-31",
            status=data.status or "active",
            impressions=data.impressions or 0,
            clicks=data.clicks or 0,
            image_url=data.image_url,
            video_url=data.video_url,
            media_type=data.media_type or ("video" if data.video_url else "image"),
            thumbnail_url=data.thumbnail_url,
            target_url=data.target_url,
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
            promo.media_type = data.media_type
        if data.thumbnail_url is not None:
            promo.thumbnail_url = data.thumbnail_url
        if data.target_url is not None:
            promo.target_url = data.target_url

        db.commit()
        db.refresh(promo)
        return promo

    @staticmethod
    def delete(db: Session, promo_id: int) -> bool:
        promo = PromotionService.get_by_id(db, promo_id)
        db.delete(promo)
        db.commit()
        return True
