from datetime import datetime, timezone
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from app.db.models.promotion import Promotion


class PromotionService:
    @staticmethod
    def _as_utc(dt: datetime) -> datetime:
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    @staticmethod
    def _is_currently_valid(promo: Promotion, now: datetime) -> bool:
        if promo.start_at and PromotionService._as_utc(promo.start_at) > now:
            return False
        if promo.end_at and PromotionService._as_utc(promo.end_at) < now:
            return False
        return True

    @staticmethod
    def list_promotions(
        db: Session,
        status: Optional[str] = None,
        merchant_profile_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 50,
        active_only_for_public: bool = True,
    ) -> Tuple[List[Promotion], int]:
        now = datetime.now(timezone.utc)
        q = db.query(Promotion)

        if merchant_profile_id is not None:
            q = q.filter(Promotion.merchant_profile_id == merchant_profile_id)

        status_norm = (status or "").strip().lower()
        if status_norm == "active":
            q = q.filter(Promotion.is_active == True, Promotion.status == "ACTIVE")
        elif status_norm == "inactive":
            q = q.filter(Promotion.is_active == False)
        elif status_norm:
            q = q.filter(Promotion.status == status.strip().upper())

        rows = q.order_by(Promotion.priority.desc(), Promotion.created_at.desc()).all()

        if active_only_for_public and status_norm in ("", "active"):
            rows = [p for p in rows if PromotionService._is_currently_valid(p, now)]

        total = len(rows)
        page = rows[skip : skip + limit]
        return page, total
