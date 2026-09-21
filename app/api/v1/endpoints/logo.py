import os
import shutil
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_current_user_optional, require_admin
from app.db.database import get_db
from app.db.models.user import User
from app.schemas.auth import GenericMessageResponse
from app.schemas.favorite import FavoriteCheckResponse, FavoriteToggleResponse
from app.schemas.logo import (
    LogoCreateRequest,
    LogoListResponse,
    LogoResponse,
    LogoUpdateRequest,
    LogoUploadResponse,
)
from app.services.logo_service import LogoService

router = APIRouter(prefix="/logos", tags=["Logos"])

ALLOWED_LOGO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".svg"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB


@router.get(
    "",
    response_model=LogoListResponse,
    summary="Search and filter logos",
    description=(
        "Public logo search and discovery endpoint. Supports full-text search across titles, descriptions, and tags, "
        "category filtering, tag filtering, sorting, and pagination. For public users, only approved logos are returned."
    ),
)
def search_logos(
    q: Optional[str] = Query(None, description="Search keyword matching title, description, or tags"),
    category_id: Optional[int] = Query(None, description="Filter by category ID"),
    category_slug: Optional[str] = Query(None, description="Filter by category slug"),
    tag: Optional[str] = Query(None, description="Filter by specific tag keyword"),
    status: Optional[str] = Query(None, description="Filter by status (Admin only or own submissions)"),
    submitted_by_id: Optional[int] = Query(None, description="Filter by submitter user ID"),
    sort_by: str = Query("created_at", description="Field to sort by: created_at, views_count, favorites_count, title"),
    sort_order: str = Query("desc", description="Sort direction: asc or desc"),
    skip: int = Query(0, ge=0, description="Offset for pagination"),
    limit: int = Query(20, ge=1, le=100, description="Page size limit"),
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> LogoListResponse:
    return LogoService.search_logos(
        db=db,
        q=q,
        category_id=category_id,
        category_slug=category_slug,
        tag=tag,
        logo_status=status,
        submitted_by_id=submitted_by_id,
        sort_by=sort_by,
        sort_order=sort_order,
        skip=skip,
        limit=limit,
        current_user=current_user,
    )


@router.get(
    "/{logo_id}",
    response_model=LogoResponse,
    summary="Get logo by ID",
    description="Fetches detailed information for a logo, increments its view counter, and checks favorite status if user is authenticated.",
)
def get_logo(
    logo_id: int,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> LogoResponse:
    return LogoService.get_logo_by_id(db=db, logo_id=logo_id, current_user=current_user, increment_view=True)


@router.post(
    "",
    response_model=LogoResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a new logo",
    description="Submits a new logo for moderation. Any authenticated user or merchant can submit. Initial status is PENDING.",
)
def submit_logo(
    data: LogoCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LogoResponse:
    return LogoService.create_logo(db=db, current_user=current_user, data=data)


@router.post(
    "/upload",
    response_model=LogoUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload logo image asset",
    description="Uploads an image file (.jpg, .jpeg, .png, .webp, .svg) and returns the public static URL.",
)
def upload_logo_image(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
) -> LogoUploadResponse:
    ext = os.path.splitext(file.filename)[1].lower() if file.filename else ""
    if ext not in ALLOWED_LOGO_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '{ext}'. Allowed types: {', '.join(ALLOWED_LOGO_EXTENSIONS)}",
        )

    logos_dir = os.path.join("uploads", "logos")
    os.makedirs(logos_dir, exist_ok=True)

    filename = f"logo_{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(logos_dir, filename)

    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save file: {str(exc)}",
        )

    public_url = f"/static/logos/{filename}"
    return LogoUploadResponse(
        message="Logo image uploaded successfully.",
        image_url=public_url,
    )


@router.patch(
    "/{logo_id}",
    response_model=LogoResponse,
    summary="Update logo",
    description="Updates logo information. Only the original submitter or an administrator can update. Non-admin updates reset status to PENDING.",
)
def update_logo(
    logo_id: int,
    data: LogoUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LogoResponse:
    return LogoService.update_logo(db=db, current_user=current_user, logo_id=logo_id, data=data)


@router.delete(
    "/{logo_id}",
    response_model=GenericMessageResponse,
    summary="Delete logo",
    description="Deletes a logo. Can only be performed by the submitter or an administrator.",
)
def delete_logo(
    logo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GenericMessageResponse:
    LogoService.delete_logo(db=db, current_user=current_user, logo_id=logo_id)
    return GenericMessageResponse(message=f"Logo {logo_id} successfully deleted.")


@router.post(
    "/{logo_id}/favorite",
    response_model=FavoriteToggleResponse,
    summary="Toggle logo favorite",
    description="Adds the logo to favorites if not favorited; otherwise removes it. Authenticated users only.",
)
def toggle_favorite(
    logo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FavoriteToggleResponse:
    return LogoService.toggle_favorite(db=db, user=current_user, logo_id=logo_id)


@router.get(
    "/{logo_id}/favorite",
    response_model=FavoriteCheckResponse,
    summary="Check if logo is favorited",
    description="Returns whether the authenticated user has favorited this logo.",
)
def check_favorite(
    logo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FavoriteCheckResponse:
    return LogoService.check_favorite(db=db, user=current_user, logo_id=logo_id)


@router.delete(
    "/{logo_id}/favorite",
    response_model=FavoriteToggleResponse,
    summary="Remove logo from favorites",
    description="Unfavorites a logo if it was previously favorited.",
)
def remove_favorite(
    logo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FavoriteToggleResponse:
    # If it is currently favorited, toggle removes it
    status_check = LogoService.check_favorite(db=db, user=current_user, logo_id=logo_id)
    if status_check.is_favorite:
        return LogoService.toggle_favorite(db=db, user=current_user, logo_id=logo_id)
    logo = LogoService.get_logo_by_id(db=db, logo_id=logo_id, current_user=current_user, increment_view=False)
    return FavoriteToggleResponse(
        message="Logo is not in favorites.",
        is_favorite=False,
        logo_id=logo_id,
        favorites_count=logo.favorites_count,
    )
