import os
from typing import List, Optional
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
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
from app.services.storage_service import storage_service

router = APIRouter(prefix="/promotions", tags=["Promotions Management"])

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg", ".bmp"}
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".avi", ".mkv", ".m4v"}


@router.get("", response_model=StandardListResponse[PromotionResponse], summary="List all promotions")
def list_promotions(
    status: Optional[str] = Query(None, description="Filter by status (active, pending, inactive, all)"),
    search: Optional[str] = Query(None, description="Search by title, category, placement, location"),
    placement: Optional[str] = Query(None, description="Filter by placement (e.g. Home Top, Middle Banner)"),
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user_flexible),
):
    promos = PromotionService.get_all(db, status_filter=status, search=search, placement=placement)
    return list_response(
        data=[PromotionResponse.model_validate(p) for p in promos],
        total_items=len(promos),
        message="Promotions retrieved successfully",
    )


@router.get("/active", response_model=StandardListResponse[PromotionResponse], summary="List active promotions for landing page")
@router.get("/hero-banners", response_model=StandardListResponse[PromotionResponse], summary="Get hero banner promotions (video & image)")
def list_active_hero_promotions(
    placement: Optional[str] = Query(None, description="Filter by placement, e.g. Home Top"),
    search: Optional[str] = Query(None, description="Search by title or category"),
    db: Session = Depends(get_db),
):
    """
    Public endpoint to fetch active promotions / hero banners (images and videos).
    Does not require admin credentials.
    """
    promos = PromotionService.get_all(db, status_filter="active", search=search, placement=placement)
    return list_response(
        data=[PromotionResponse.model_validate(p) for p in promos],
        total_items=len(promos),
        message="Active hero promotions retrieved successfully",
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


@router.post("/upload-media", summary="Upload hero banner image or video")
@router.post("/upload", summary="Alias to upload hero banner media")
def upload_banner_media(
    file: Optional[UploadFile] = File(None, description="Banner image or video file"),
    image: Optional[UploadFile] = File(None, description="Banner image file"),
    video: Optional[UploadFile] = File(None, description="Banner video file"),
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user_flexible),
):
    """
    Upload a hero banner image or video directly to DigitalOcean Spaces CDN storage.
    Supports JPG, PNG, WEBP, GIF, SVG, and MP4, WEBM, MOV video formats.
    Returns the CDN public URL and media type ('image' or 'video').
    """
    target_file = file or video or image
    if not target_file or not target_file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No file provided. Please provide 'file', 'image', or 'video'.",
        )

    filename = target_file.filename
    ext = os.path.splitext(filename)[1].lower()

    if ext in ALLOWED_VIDEO_EXTENSIONS:
        media_type = "video"
        folder = "banners/videos"
    elif ext in ALLOWED_IMAGE_EXTENSIONS:
        media_type = "image"
        folder = "banners/images"
    else:
        allowed_all = sorted(list(ALLOWED_IMAGE_EXTENSIONS | ALLOWED_VIDEO_EXTENSIONS))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported format '{ext}'. Supported formats: {', '.join(allowed_all)}",
        )

    uploaded_url = storage_service.upload_file(target_file, folder=folder)

    return success_response(
        data={
            "url": uploaded_url,
            "media_url": uploaded_url,
            "image_url": uploaded_url if media_type == "image" else None,
            "video_url": uploaded_url if media_type == "video" else None,
            "media_type": media_type,
            "filename": filename,
        },
        message=f"Banner {media_type} uploaded successfully to CDN",
    )
