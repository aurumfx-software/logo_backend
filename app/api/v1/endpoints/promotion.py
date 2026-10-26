from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.promotion import PromotionListResponse, PromotionResponse
from app.services.promotion_service import PromotionService

router = APIRouter(prefix="/promotions", tags=["Promotions"])


@router.get(
    "",
    response_model=PromotionListResponse,
    summary="List promotions",
    description=(
        "Returns promotions from the promotions table. "
        "Use status=active (default behavior when status is active) for live campaigns within start/end dates."
    ),
)
def list_promotions(
    status: Optional[str] = Query(
        None,
        description="Filter by status, e.g. active, ACTIVE, inactive",
    ),
    merchant_profile_id: Optional[int] = Query(
        None,
        description="Filter promotions for a specific merchant",
    ),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> PromotionListResponse:
    items, total = PromotionService.list_promotions(
        db=db,
        status=status,
        merchant_profile_id=merchant_profile_id,
        skip=skip,
        limit=limit,
        active_only_for_public=True,
    )
    return PromotionListResponse(
        items=[PromotionResponse.model_validate(p) for p in items],
        total=total,
    )
