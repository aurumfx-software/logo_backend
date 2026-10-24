import os
from typing import List, Optional
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_admin_user_flexible, get_current_user_optional
from app.db.database import get_db
from app.db.models.merchant import MerchantProfile
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
from app.services.notification_service import NotificationService
from app.services.storage_service import storage_service

router = APIRouter(prefix="/promotions", tags=["Promotions Management"])

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg", ".bmp"}
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".avi", ".mkv", ".m4v"}


@router.get("", response_model=StandardListResponse[PromotionResponse], summary="List all promotions")
def list_promotions(
    status: Optional[str] = Query(None, description="Filter by status (active, pending, inactive, all)"),
    search: Optional[str] = Query(None, description="Search by title, category, placement, location"),
    placement: Optional[str] = Query(None, description="Filter by placement (e.g. Home Top, Middle Banner)"),
    merchant_id: Optional[int] = Query(None, description="Filter by merchant ID"),
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user_flexible),
):
    promos = PromotionService.get_all(db, status_filter=status, search=search, placement=placement)
    if merchant_id:
        promos = [p for p in promos if p.merchant_id == merchant_id]
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
    Only returns promotions that are approved and whose associated merchant has promotion access enabled.
    """
    promos = PromotionService.get_public_active(db, search=search, placement=placement)
    return list_response(
        data=[PromotionResponse.model_validate(p) for p in promos],
        total_items=len(promos),
        message="Active hero promotions retrieved successfully",
    )


@router.get("/merchant/{merchant_id}", response_model=StandardListResponse[PromotionResponse], summary="List promotions for a merchant")
def list_merchant_promotions(
    merchant_id: int,
    db: Session = Depends(get_db),
):
    """Fetch all promotions submitted by a specific merchant to track approval status."""
    promos = db.query(PromotionService.get_all(db)).filter(Promotion.merchant_id == merchant_id).all() if False else [
        p for p in PromotionService.get_all(db) if p.merchant_id == merchant_id
    ]
    return list_response(
        data=[PromotionResponse.model_validate(p) for p in promos],
        total_items=len(promos),
        message=f"Retrieved {len(promos)} promotions for merchant {merchant_id}",
    )


@router.post("", response_model=StandardResponse[PromotionResponse], status_code=status.HTTP_201_CREATED, summary="Create promotion")
def create_promotion(
    payload: PromotionCreateRequest,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    Create a promotion.
    - If submitted by Admin: Can be directly active.
    - If submitted by Merchant: Verified for promotion access. Set to PENDING approval.
    """
    is_admin = False
    if current_user:
        role_str = str(getattr(current_user, "role", "")).upper()
        if "ADMIN" in role_str or "SUPER" in role_str or getattr(current_user, "email", "") == "admin@aurumfx.com":
            is_admin = True

    if not is_admin:
        # Check merchant promotion permission
        merchant = None
        if payload.merchant_id:
            merchant = db.query(MerchantProfile).filter(MerchantProfile.id == payload.merchant_id).first()
        elif current_user:
            merchant = db.query(MerchantProfile).filter(MerchantProfile.user_id == current_user.id).first()

        if not merchant:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A valid merchant must be associated with this promotion.",
            )

        if not getattr(merchant, "can_create_promotions", False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Promotion access is currently disabled for this merchant. Please contact an administrator.",
            )

        # Force merchant binding & pending approval status
        payload.merchant_id = merchant.id
        payload.merchant_name = merchant.business_name
        payload.status = "pending"

    promo = PromotionService.create(db, payload)

    # All-time notification for admin on new promotion request
    try:
        NotificationService.notify_admins(
            db=db,
            title="New Promotion Request",
            message=f"Merchant '{promo.merchant_name or 'Store'}' submitted promotion '{promo.title}' for approval.",
            type="PROMOTION_REQUEST",
            data={"promo_id": promo.id, "merchant_id": promo.merchant_id, "title": promo.title},
        )
    except Exception as err:
        print("Admin notification error on promo create:", err)

    return success_response(
        data=PromotionResponse.model_validate(promo),
        message="Promotion created successfully" + (" (Pending Admin Approval)" if not is_admin else ""),
    )


@router.post("/{promo_id}/approve", response_model=StandardResponse[PromotionResponse], summary="Approve promotion")
@router.patch("/{promo_id}/approve", response_model=StandardResponse[PromotionResponse], summary="Approve promotion (PATCH alias)")
def approve_promotion(
    promo_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user_flexible),
):
    """Approve a submitted promotion and make it eligible for public landing page display."""
    promo = PromotionService.approve(db, promo_id)
    try:
        if promo.merchant_id:
            merch = db.query(MerchantProfile).filter(MerchantProfile.id == promo.merchant_id).first()
            if merch and merch.user_id:
                NotificationService.create_notification(
                    db=db,
                    user_id=merch.user_id,
                    title="Promotion Approved! 🎉",
                    message=f"Your promotion '{promo.title}' has been approved and is now live on Logo.",
                    type="PROMOTION_APPROVED",
                    data={"promo_id": promo.id},
                )
    except Exception as err:
        print("Notification error on promo approve:", err)

    return success_response(
        data=PromotionResponse.model_validate(promo),
        message=f"Promotion '{promo.title}' approved successfully",
    )


@router.post("/{promo_id}/reject", response_model=StandardResponse[PromotionResponse], summary="Reject promotion")
@router.patch("/{promo_id}/reject", response_model=StandardResponse[PromotionResponse], summary="Reject promotion (PATCH alias)")
def reject_promotion(
    promo_id: int,
    data: Optional[dict] = None,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user_flexible),
):
    """Reject a submitted promotion with an optional reason."""
    reason = (data or {}).get("reason") if isinstance(data, dict) else "Promotion rejected by administration."
    promo = PromotionService.reject(db, promo_id, reason=reason)
    try:
        if promo.merchant_id:
            merch = db.query(MerchantProfile).filter(MerchantProfile.id == promo.merchant_id).first()
            if merch and merch.user_id:
                NotificationService.create_notification(
                    db=db,
                    user_id=merch.user_id,
                    title="Promotion Update",
                    message=f"Your promotion '{promo.title}' was rejected: {reason}",
                    type="PROMOTION_REJECTED",
                    data={"promo_id": promo.id},
                )
    except Exception as err:
        print("Notification error on promo reject:", err)

    return success_response(
        data=PromotionResponse.model_validate(promo),
        message=f"Promotion '{promo.title}' rejected",
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
@router.patch("/{promo_id}", response_model=StandardResponse[PromotionResponse], summary="Update promotion (PATCH alias)")
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
