from typing import List, Tuple

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.db.models.merchant import MerchantFavorite, MerchantProfile
from app.db.models.user import User
from app.schemas.merchant import MerchantProfileResponse
from app.services.merchant_service import MerchantService


class MerchantFavoriteService:
    @staticmethod
    def add_favorite(db: Session, user: User, merchant_id: int) -> MerchantProfileResponse:
        merchant = MerchantService.get_merchant_by_id(db, merchant_id)
        existing = (
            db.query(MerchantFavorite)
            .filter(
                MerchantFavorite.user_id == user.id,
                MerchantFavorite.merchant_profile_id == merchant.id,
            )
            .first()
        )
        if not existing:
            db.add(MerchantFavorite(user_id=user.id, merchant_profile_id=merchant.id))
            db.commit()
        return MerchantService.build_merchant_response(merchant)

    @staticmethod
    def remove_favorite(db: Session, user: User, merchant_id: int) -> None:
        row = (
            db.query(MerchantFavorite)
            .filter(
                MerchantFavorite.user_id == user.id,
                MerchantFavorite.merchant_profile_id == merchant_id,
            )
            .first()
        )
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Merchant is not in your favorites.",
            )
        db.delete(row)
        db.commit()

    @staticmethod
    def list_favorites(db: Session, user: User) -> Tuple[List[MerchantProfileResponse], int]:
        rows = (
            db.query(MerchantProfile)
            .join(MerchantFavorite, MerchantFavorite.merchant_profile_id == MerchantProfile.id)
            .filter(MerchantFavorite.user_id == user.id)
            .order_by(MerchantFavorite.created_at.desc())
            .all()
        )
        items = [MerchantService.build_merchant_response(m) for m in rows]
        return items, len(items)
