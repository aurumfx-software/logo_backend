from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.database import get_db
from app.db.models.user import User
from app.schemas.favorite import FavoriteListResponse
from app.services.logo_service import LogoService

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
