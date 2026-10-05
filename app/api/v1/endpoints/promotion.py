from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_admin_user_flexible
from app.db.database import get_db
from app.db.models.user import User
from app.schemas.promotion import (
    PromotionCreateRequest,
    PromotionResponse,
    PromotionUpdateRequest,
)
from app.schemas.response import (
    StandardListResponse,
    StandardResponse,
    list_response,
    success_response,
)
from app.services.promotion_service import PromotionService

router = APIRouter(prefix="/promotions", tags=["Promotions Management"])


@router.get("", response_model=StandardListResponse[PromotionResponse], summary="List all promotions")
def list_promotions(
    status: Optional[str] = Query(None, description="Filter by status (active, pending, inactive, all)"),
    search: Optional[str] = Query(None, description="Search by title, category, placement, location"),
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user_flexible),
):
    promos = PromotionService.get_all(db, status_filter=status, search=search)
    return list_response(
        data=[PromotionResponse.model_validate(p) for p in promos],
        total_items=len(promos),
        message="Promotions retrieved successfully",
    )


@router.post("", response_model=StandardResponse[PromotionResponse], status_code=status.HTTP_201_CREATED, summary="Create promotion")
def create_promotion(
    payload: PromotionCreateRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user_flexible),
):
    promo = PromotionService.create(db, payload)
    return success_response(
        data=PromotionResponse.model_validate(promo),
        message="Promotion created successfully",
    )


@router.get("/{promo_id}", response_model=StandardResponse[PromotionResponse], summary="Get promotion by ID")
def get_promotion(
    promo_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user_flexible),
):
    promo = PromotionService.get_by_id(db, promo_id)
    return success_response(
        data=PromotionResponse.model_validate(promo),
        message="Promotion retrieved successfully",
    )


@router.put("/{promo_id}", response_model=StandardResponse[PromotionResponse], summary="Update promotion")
def update_promotion(
    promo_id: int,
    payload: PromotionUpdateRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user_flexible),
):
    promo = PromotionService.update(db, promo_id, payload)
    return success_response(
        data=PromotionResponse.model_validate(promo),
        message="Promotion updated successfully",
    )


@router.delete("/{promo_id}", response_model=StandardResponse[bool], summary="Delete promotion")
def delete_promotion(
    promo_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user_flexible),
):
    PromotionService.delete(db, promo_id)
    return success_response(
        data=True,
        message="Promotion deleted successfully",
    )
