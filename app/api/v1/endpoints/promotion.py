import json
import logging
import os
from typing import Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_admin_user_flexible, get_current_user, get_current_user_optional
from app.db.database import get_db
from app.db.models.merchant import MerchantProfile
from app.db.models.user import User
from app.schemas.promotion import (
    PROMOTION_MEDIA_TYPE_OPTIONS,
    PROMOTION_PLACEMENT_OPTIONS,
    PROMOTION_TYPE_OPTIONS,
    PromotionCreateRequest,
    PromotionOptionTypesResponse,
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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/promotions", tags=["Promotions Management"])

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg", ".bmp"}
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".avi", ".mkv", ".m4v"}


@router.get("", response_model=StandardListResponse[PromotionResponse], summary="List promotions")
def list_promotions(
    status: Optional[str] = Query(
        "active",
        description="Filter by status (active, pending, inactive, all). Landing page uses active.",
    ),
    search: Optional[str] = Query(None, description="Search by title, category, placement, location"),
    placement: Optional[str] = Query(None, description="Filter by placement (e.g. Home Top, Middle Banner)"),
    merchant_id: Optional[int] = Query(None, description="Filter by merchant ID"),
    db: Session = Depends(get_db),
):
    status_norm = (status or "active").strip().lower()
    if status_norm in ("active", "approved"):
        promos = PromotionService.get_public_active(db, search=search, placement=placement)
    elif status_norm == "all":
        promos = PromotionService.get_all(db, status_filter="all", search=search, placement=placement)
    else:
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


def _promotion_option_types_payload() -> PromotionOptionTypesResponse:
    return PromotionOptionTypesResponse(
        types=PROMOTION_TYPE_OPTIONS,
        option_types=PROMOTION_TYPE_OPTIONS,
        placements=PROMOTION_PLACEMENT_OPTIONS,
        media_types=PROMOTION_MEDIA_TYPE_OPTIONS,
    )


@router.get(
    "/option-types",
    response_model=StandardResponse[PromotionOptionTypesResponse],
    summary="Promotion dropdown option types",
    description="Returns promotion type, placement, and media type options for admin/merchant forms.",
)
@router.get(
    "/types",
    response_model=StandardResponse[PromotionOptionTypesResponse],
    summary="Promotion option types (alias)",
    include_in_schema=False,
)
@router.get(
    "/options",
    response_model=StandardResponse[PromotionOptionTypesResponse],
    summary="Promotion form options (alias)",
    include_in_schema=False,
)
def get_promotion_option_types():
    return success_response(
        data=_promotion_option_types_payload(),
        message="Promotion option types retrieved successfully",
    )


@router.get("/merchant/{merchant_id}", response_model=StandardListResponse[PromotionResponse], summary="List promotions for a merchant")
def list_merchant_promotions(
    merchant_id: int,
    status: Optional[str] = Query(None, description="Filter by status (e.g. active, all)"),
    placement: Optional[str] = Query(None, description="Filter by placement (e.g. Merchant Store)"),
    db: Session = Depends(get_db),
):
    """Fetch promotions for a specific merchant (all for portal tracking, or active for store page)."""
    status_norm = (status or "").strip().lower()
    placement_norm = (placement or "").strip().lower()
    if status_norm in ("active", "approved") and placement_norm == "merchant store":
        if not PromotionService.is_merchant_ad_subscription_active(db, merchant_id):
            return list_response(
                data=[],
                total_items=0,
                message="Active ₹999 merchant subscription required for live store advertisements",
            )
    promos = PromotionService.get_merchant_promotions(
        db,
        merchant_id=merchant_id,
        status_filter=status,
        placement=placement,
    )
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
    Create a promotion or store advertisement.
    - If submitted by Admin: Can be directly active.
    - If submitted by Merchant: Requires active ₹999+ Merchant Subscription (`MERCHANT_PROMO_BASIC`).
      Store advertisements (`placement == 'Merchant Store'`) go live immediately upon active subscription.
    """
    is_admin = False
    if current_user:
        role_str = str(getattr(current_user, "role", "")).upper()
        if "ADMIN" in role_str or "SUPER" in role_str or getattr(current_user, "email", "") == "admin@aurumfx.com":
            is_admin = True

    if not is_admin:
        if not current_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required to create merchant advertisements.",
            )
        from app.services.subscription_service import SubscriptionService

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

        merchant = SubscriptionService._assert_merchant_access(db, current_user, merchant.id)

        grants = SubscriptionService.merged_grants(db, merchant_profile_id=merchant.id)
        payload.merchant_id = merchant.id
        payload.merchant_name = merchant.business_name
        placement_str = str(payload.placement or "").strip()
        if placement_str.lower() == "merchant store":
            if not grants.get("can_add_detail_page_ad"):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="The ₹3999 plan is required to advertise on the merchant details page.",
                )
            req_status = str(payload.status or "active").strip().lower()
            payload.status = "inactive" if req_status == "inactive" else "active"
        else:
            if not grants.get("can_promote_landing"):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="The ₹4999 plan is required to promote on the app landing page. An admin must approve the ad.",
                )
            payload.status = "pending"

    promo = PromotionService.create(db, payload)

    # All-time notification for admin on new promotion request
    try:
        NotificationService.notify_admins(
            db=db,
            title="New Promotion Request" if promo.status == "pending" else "New Merchant Store Ad",
            message=f"Merchant '{promo.merchant_name or 'Store'}' published advertisement '{promo.title}'.",
            type="PROMOTION_REQUEST",
            data={"promo_id": promo.id, "merchant_id": promo.merchant_id, "title": promo.title},
        )
    except Exception as err:
        logger.exception("Admin notification failed on promotion create: %s", err)

    return success_response(
        data=PromotionResponse.model_validate(promo),
        message="Store advertisement saved successfully" if promo.status == "active" else "Promotion submitted for Admin approval",
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
        logger.exception("Notification failed on promotion approve: %s", err)

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
        logger.exception("Notification failed on promotion reject: %s", err)

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


def _assert_admin_or_promo_owner(db: Session, current_user: User, promo) -> bool:
    role_str = str(getattr(current_user, "role", "")).upper()
    if "ADMIN" in role_str or "SUPER" in role_str or getattr(current_user, "email", "") == "admin@aurumfx.com":
        return True
    if not promo.merchant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to modify this promotion.")
    from app.services.subscription_service import SubscriptionService
    SubscriptionService._assert_merchant_access(db, current_user, promo.merchant_id)
    return False


@router.put("/{promo_id}", response_model=StandardResponse[PromotionResponse], summary="Update promotion")
@router.patch("/{promo_id}", response_model=StandardResponse[PromotionResponse], summary="Update promotion (PATCH alias)")
def update_promotion(
    promo_id: int,
    payload: PromotionUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    existing = PromotionService.get_by_id(db, promo_id)
    is_admin = _assert_admin_or_promo_owner(db, current_user, existing)
    if not is_admin:
        if not PromotionService.is_merchant_ad_subscription_active(db, existing.merchant_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="₹999 Merchant Advertisement Subscription required.",
            )
        if str(existing.placement or "").strip().lower() == "merchant store":
            if payload.status is not None:
                st = str(payload.status).strip().lower()
                payload.status = "inactive" if st == "inactive" else "active"
        else:
            payload.status = None
    promo = PromotionService.update(db, promo_id, payload)
    return success_response(
        data=PromotionResponse.model_validate(promo),
        message="Promotion updated successfully",
    )


@router.delete("/{promo_id}", response_model=StandardResponse[bool], summary="Delete promotion")
def delete_promotion(
    promo_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    existing = PromotionService.get_by_id(db, promo_id)
    _assert_admin_or_promo_owner(db, current_user, existing)
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
    current_user: Optional[User] = Depends(get_current_user_optional),
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


from typing import Dict


SLIDER_AD_TYPE_KEYS = (
    "home_top",
    "home_middle",
    "above_footer",
    "featured_offers",
    "business_network",
    "moving_text",
    "merchant_store",
)


def _clamp_sec(val: Optional[int], default: int = 4) -> int:
    try:
        num = int(val) if val is not None else default
    except (TypeError, ValueError):
        num = default
    return max(2, min(num, 60))


def _normalize_slider_settings(raw: Optional[dict]) -> dict:
    src = raw if isinstance(raw, dict) else {}
    global_sec = _clamp_sec(src.get("interval_seconds"), 4)
    raw_map = src.get("per_type_seconds") if isinstance(src.get("per_type_seconds"), dict) else {}

    per_type: Dict[str, int] = {}
    for key in SLIDER_AD_TYPE_KEYS:
        default_for_key = 5 if key == "business_network" else global_sec
        field_val = src.get(f"{key}_seconds")
        if field_val is None:
            field_val = raw_map.get(key)
        per_type[key] = _clamp_sec(field_val, default_for_key)

    raw_overrides = src.get("merchant_overrides") if isinstance(src.get("merchant_overrides"), dict) else {}
    merchant_overrides: Dict[str, int] = {}
    for m_key, m_val in raw_overrides.items():
        clean_key = str(m_key).strip()
        if clean_key:
            merchant_overrides[clean_key] = _clamp_sec(m_val, per_type.get("merchant_store", global_sec))

    result = {
        "interval_seconds": global_sec,
        "per_type_seconds": per_type,
        "merchant_overrides": merchant_overrides,
    }
    for key, val in per_type.items():
        result[f"{key}_seconds"] = val
    return result


class MerchantSliderSpeedPayload(BaseModel):
    interval_seconds: int = Field(..., ge=2, le=60)


class SliderSettingsPayload(BaseModel):
    interval_seconds: Optional[int] = Field(default=None, ge=2, le=60)
    home_top_seconds: Optional[int] = Field(default=None, ge=2, le=60)
    home_middle_seconds: Optional[int] = Field(default=None, ge=2, le=60)
    above_footer_seconds: Optional[int] = Field(default=None, ge=2, le=60)
    featured_offers_seconds: Optional[int] = Field(default=None, ge=2, le=60)
    business_network_seconds: Optional[int] = Field(default=None, ge=2, le=60)
    moving_text_seconds: Optional[int] = Field(default=None, ge=2, le=60)
    merchant_store_seconds: Optional[int] = Field(default=None, ge=2, le=60)
    per_type_seconds: Optional[Dict[str, int]] = None
    apply_all: bool = False


@router.get("/settings/slider", summary="Get global & per-type slider speed settings")
def get_slider_settings(
    merchant_id: Optional[int] = Query(None, description="Optional merchant store ID override"),
    db: Session = Depends(get_db),
):
    """
    Public endpoint: Returns global, per-ad-type, and optional merchant-specific slider speed intervals in seconds.
    """
    from app.db.models.promotion import Promotion
    config = db.query(Promotion).filter(Promotion.placement == "SYSTEM_CONFIG_SLIDER").first()
    raw_data = {}
    if config and config.description:
        try:
            raw_data = json.loads(config.description) or {}
        except Exception:
            raw_data = {}

    normalized = _normalize_slider_settings(raw_data)
    if merchant_id is not None:
        m_default = normalized["per_type_seconds"].get("merchant_store", normalized["interval_seconds"])
        normalized["merchant_interval_seconds"] = _clamp_sec(
            normalized.get("merchant_overrides", {}).get(str(merchant_id)),
            m_default,
        )

    return success_response(
        data=normalized,
        message="Slider settings retrieved" if config else "Default slider settings",
    )


@router.put("/merchant/{merchant_id}/slider", summary="Update slider swipe speed for a specific merchant store")
def update_merchant_slider_speed(
    merchant_id: int,
    payload: MerchantSliderSpeedPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Merchant / Admin endpoint: Saves a per-merchant store advertisement auto-slide interval in seconds.
    """
    from app.db.models.promotion import Promotion
    from app.services.subscription_service import SubscriptionService

    role_str = str(getattr(current_user, "role", "")).upper()
    is_admin = (
        "ADMIN" in role_str
        or "SUPER" in role_str
        or getattr(current_user, "email", "") == "admin@aurumfx.com"
    )
    if not is_admin:
        SubscriptionService._assert_merchant_access(db, current_user, merchant_id)

    clamped = _clamp_sec(payload.interval_seconds, 4)
    config = db.query(Promotion).filter(Promotion.placement == "SYSTEM_CONFIG_SLIDER").first()
    existing_raw = {}
    if config and config.description:
        try:
            existing_raw = json.loads(config.description) or {}
        except Exception:
            existing_raw = {}

    merged = _normalize_slider_settings(existing_raw)
    overrides = dict(merged.get("merchant_overrides") or {})
    overrides[str(merchant_id)] = clamped
    merged["merchant_overrides"] = overrides
    normalized = _normalize_slider_settings(merged)

    if not config:
        config = Promotion(
            title="System Slider Settings",
            type="SYSTEM_CONFIG",
            placement="SYSTEM_CONFIG_SLIDER",
            status="active",
            description=json.dumps(normalized),
        )
        db.add(config)
    else:
        config.description = json.dumps(normalized)
    db.commit()
    return success_response(
        data={"merchant_id": merchant_id, "interval_seconds": clamped, "slider_settings": normalized},
        message=f"Store ad swipe speed updated to {clamped}s",
    )


@router.put("/settings/slider", summary="Update global & per-type slider speed settings")
def update_slider_settings(
    payload: SliderSettingsPayload,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_admin_user_flexible),
):
    """
    Admin endpoint: Updates global and/or per-ad-type slider speed intervals across all ad carousels.
    """
    from app.db.models.promotion import Promotion

    config = db.query(Promotion).filter(Promotion.placement == "SYSTEM_CONFIG_SLIDER").first()
    existing_raw = {}
    if config and config.description:
        try:
            existing_raw = json.loads(config.description) or {}
        except Exception:
            existing_raw = {}

    merged = _normalize_slider_settings(existing_raw)

    if payload.interval_seconds is not None:
        g_sec = _clamp_sec(payload.interval_seconds, merged["interval_seconds"])
        merged["interval_seconds"] = g_sec
        if payload.apply_all:
            for key in SLIDER_AD_TYPE_KEYS:
                merged["per_type_seconds"][key] = g_sec
                merged[f"{key}_seconds"] = g_sec

    if isinstance(payload.per_type_seconds, dict):
        for key in SLIDER_AD_TYPE_KEYS:
            if key in payload.per_type_seconds and payload.per_type_seconds[key] is not None:
                c_val = _clamp_sec(payload.per_type_seconds[key], merged["interval_seconds"])
                merged["per_type_seconds"][key] = c_val
                merged[f"{key}_seconds"] = c_val

    for key in SLIDER_AD_TYPE_KEYS:
        direct_val = getattr(payload, f"{key}_seconds", None)
        if direct_val is not None:
            c_val = _clamp_sec(direct_val, merged["interval_seconds"])
            merged["per_type_seconds"][key] = c_val
            merged[f"{key}_seconds"] = c_val

    normalized = _normalize_slider_settings(merged)
    if not config:
        config = Promotion(
            title="System Slider Settings",
            type="SYSTEM_CONFIG",
            placement="SYSTEM_CONFIG_SLIDER",
            status="active",
            description=json.dumps(normalized),
        )
        db.add(config)
    else:
        config.description = json.dumps(normalized)
    db.commit()
    return success_response(data=normalized, message="Slider settings updated successfully")

