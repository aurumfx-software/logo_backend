from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.db.database import get_db
from app.db.models.user import User
from app.schemas.geography import GeographyResponse, GeographyTownCreateRequest, GeographyTownItem
from app.services.geography_service import GeographyService

router = APIRouter(prefix="/admin/geography", tags=["Admin Geography"])


@router.get(
    "",
    response_model=GeographyResponse,
    summary="Geography and service areas",
    description=(
        "Fills the Geography screen: 14 Kerala districts, active municipalities, "
        "merchant and customer reach, and the towns table. Filter with district or search."
    ),
)
def get_geography(
    district: Optional[str] = Query(None, description="One Kerala district, or All Districts"),
    search: Optional[str] = Query(None, description="Search town, zone, or district"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> GeographyResponse:
    return GeographyService.get_geography(
        db=db,
        district=district,
        search=search,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/towns",
    response_model=GeographyTownItem,
    status_code=status.HTTP_201_CREATED,
    summary="Add a Kerala town or commercial hub",
)
def add_geography_town(
    payload: GeographyTownCreateRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> GeographyTownItem:
    return GeographyService.add_town(db, payload)
