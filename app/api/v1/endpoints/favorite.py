from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_current_user_optional
from app.db.database import get_db
from app.db.models.user import User
from app.schemas.favorite import (
    FavoriteListResponse,
    MerchantFavoriteListResponse,
    MerchantFavoriteSaveResponse,
)
from app.services.logo_service import LogoService
from app.services.merchant_favorite_service import MerchantFavoriteService

router = APIRouter(prefix="/favorites", tags=["Favorites"])


@router.get(
    "",
    response_model=FavoriteListResponse,
    summary="List current user's favorite logos",
    description="Retrieves a paginated list of logos that the currently authenticated user has bookmarked or favorited.",
)
def get_my_favorites(
    skip: int = Query(0, ge=0, description="Offset for pagination"),
    limit: int = Query(20, ge=1, le=100, description="Page size limit"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FavoriteListResponse:
    return LogoService.list_user_favorites(db=db, user=current_user, skip=skip, limit=limit)


@router.get(
    "/merchants",
    response_model=MerchantFavoriteListResponse,
    summary="List favorite merchants for current user",
    description="Returns saved merchants for the logged-in user. Without auth, returns an empty list.",
)
def list_favorite_merchants(
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> MerchantFavoriteListResponse:
    if not current_user:
        return MerchantFavoriteListResponse(
            message="No user session; favorite list is empty.",
            items=[],
            total=0,
        )
    items, total = MerchantFavoriteService.list_favorites(db=db, user=current_user)
    return MerchantFavoriteListResponse(items=items, total=total)


@router.post(
    "/merchants/{merchant_id}",
    response_model=MerchantFavoriteSaveResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Save merchant to favorites",
)
def save_favorite_merchant(
    merchant_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MerchantFavoriteSaveResponse:
    merchant = MerchantFavoriteService.add_favorite(
        db=db, user=current_user, merchant_id=merchant_id
    )
    return MerchantFavoriteSaveResponse(
        message="Merchant saved to favorites.",
        merchant_id=merchant_id,
        merchant=merchant,
    )


@router.delete(
    "/merchants/{merchant_id}",
    status_code=status.HTTP_200_OK,
    summary="Remove merchant from favorites",
)
def remove_favorite_merchant(
    merchant_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MerchantFavoriteListResponse:
    MerchantFavoriteService.remove_favorite(db=db, user=current_user, merchant_id=merchant_id)
    return MerchantFavoriteListResponse(message="Merchant removed from favorites.")
