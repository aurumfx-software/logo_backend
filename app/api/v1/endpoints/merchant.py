import os
import shutil
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_current_user_optional, require_role, require_any_authenticated
from app.core.config import settings
from app.db.database import get_db
from app.db.models.user import User, UserRole
from app.schemas.auth import SafeUserResponse, TokenResponse
from app.schemas.merchant import (
    LocationCountItem,
    MerchantDiscoveryMetaResponse,
    MerchantLoginOTPRequest,
    MerchantLoginOTPResponse,
    MerchantMediaUploadResponse,
    MerchantOnboardingRequest,
    MerchantOnboardingResponse,
    MerchantPhotosUploadResponse,
    MerchantProfileResponse,
    MerchantRegionResponse,
    MerchantRegisterRequest,
    MerchantRegisterResponse,
    MerchantStatsResponse,
    MerchantUpdateRequest,
    MerchantVerifyOTPLoginRequest,
    ServiceCountItem,
)
from app.schemas.response import (
    StandardListResponse,
    StandardResponse,
    list_response,
    success_response,
)
from app.services.merchant_service import MerchantService

router = APIRouter(prefix="/merchants", tags=["Merchants"])

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic"}
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".avi", ".mkv", ".3gp"}
ALLOWED_DOCUMENT_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".doc", ".docx"}


@router.post(
    "/register",
    response_model=MerchantRegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new merchant",
    description=(
        "Registers a merchant account with role FIELD_STAFF, business name, categories, "
        "location, services, service timing, photos, contact number, and address."
    ),
)
def register_merchant(
    merchant_data: MerchantRegisterRequest,
    db: Session = Depends(get_db),
) -> MerchantRegisterResponse:
    user, merchant = MerchantService.register_merchant(db=db, data=merchant_data)
    return MerchantRegisterResponse(
        message="Merchant registered successfully",
        user=SafeUserResponse.model_validate(user),
        merchant=MerchantProfileResponse.model_validate(merchant),
    )


@router.post(
    "/onboard",
    response_model=MerchantOnboardingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Field Staff Merchant Onboarding",
    description=(
        "Registers a new merchant via the Field Staff Onboarding Form. "
        "Captures Business Name, Category, Owner/Contact Person, Phone Number, "
        "District, City, Location, Address, Landmark, Photos, Documents, and Videos."
    ),
)
@router.post(
    "/onboarding",
    response_model=MerchantOnboardingResponse,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
def onboard_merchant(
    data: MerchantOnboardingRequest,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> MerchantOnboardingResponse:
    user, merchant = MerchantService.onboard_merchant(
        db=db, data=data, onboarded_by=current_user
    )
    return MerchantOnboardingResponse(
        message="Merchant onboarded successfully",
        merchant=MerchantProfileResponse.model_validate(merchant),
        user=SafeUserResponse.model_validate(user),
    )


@router.post(
    "/upload-media",
    response_model=MerchantMediaUploadResponse,
    summary="Upload merchant photos, videos, and verification documents",
    description=(
        "Uploads shop front photos, promotional videos, and verification documents. "
        "Optionally associates the media directly with a merchant if merchant_id is provided."
    ),
)
def upload_merchant_media(
    photos: Optional[List[UploadFile]] = File(None, description="Shop front or gallery photos (JPG, PNG, WEBP)"),
    videos: Optional[List[UploadFile]] = File(None, description="Shop videos (MP4, MOV, WEBM, AVI)"),
    documents: Optional[List[UploadFile]] = File(None, description="Verification documents (PDF, JPG, PNG)"),
    files: Optional[List[UploadFile]] = File(None, description="General media files auto-detected by extension"),
    merchant_id: Optional[int] = Form(None, description="Optional merchant ID to attach media to"),
    db: Session = Depends(get_db),
) -> MerchantMediaUploadResponse:
    photos_dir = os.path.join("uploads", "merchants", "photos")
    videos_dir = os.path.join("uploads", "merchants", "videos")
    documents_dir = os.path.join("uploads", "merchants", "documents")

    os.makedirs(photos_dir, exist_ok=True)
    os.makedirs(videos_dir, exist_ok=True)
    os.makedirs(documents_dir, exist_ok=True)

    saved_photos: List[str] = []
    saved_videos: List[str] = []
    saved_docs: List[str] = []

    def _save_file(file: UploadFile, target_dir: str, prefix_url: str) -> str:
        ext = os.path.splitext(file.filename)[1].lower() if file.filename else ""
        unique_name = f"{uuid.uuid4().hex}{ext}"
        dest_path = os.path.join(target_dir, unique_name)
        with open(dest_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        return f"{prefix_url}/{unique_name}"

    if photos:
        for p in photos:
            if not p or not p.filename:
                continue
            ext = os.path.splitext(p.filename)[1].lower()
            if ext not in ALLOWED_IMAGE_EXTENSIONS:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Photo {p.filename} has unsupported format. Allowed: {', '.join(sorted(ALLOWED_IMAGE_EXTENSIONS))}",
                )
            saved_photos.append(_save_file(p, photos_dir, "/static/merchants/photos"))

    if videos:
        for v in videos:
            if not v or not v.filename:
                continue
            ext = os.path.splitext(v.filename)[1].lower()
            if ext not in ALLOWED_VIDEO_EXTENSIONS:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Video {v.filename} has unsupported format. Allowed: {', '.join(sorted(ALLOWED_VIDEO_EXTENSIONS))}",
                )
            saved_videos.append(_save_file(v, videos_dir, "/static/merchants/videos"))

    if documents:
        for d in documents:
            if not d or not d.filename:
                continue
            ext = os.path.splitext(d.filename)[1].lower()
            if ext not in ALLOWED_DOCUMENT_EXTENSIONS:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Document {d.filename} has unsupported format. Allowed: {', '.join(sorted(ALLOWED_DOCUMENT_EXTENSIONS))}",
                )
            saved_docs.append(_save_file(d, documents_dir, "/static/merchants/documents"))

    if files:
        for f in files:
            if not f or not f.filename:
                continue
            ext = os.path.splitext(f.filename)[1].lower()
            if ext in ALLOWED_IMAGE_EXTENSIONS:
                saved_photos.append(_save_file(f, photos_dir, "/static/merchants/photos"))
            elif ext in ALLOWED_VIDEO_EXTENSIONS:
                saved_videos.append(_save_file(f, videos_dir, "/static/merchants/videos"))
            elif ext in ALLOWED_DOCUMENT_EXTENSIONS:
                saved_docs.append(_save_file(f, documents_dir, "/static/merchants/documents"))
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"File {f.filename} has unsupported extension: {ext}",
                )

    all_urls = saved_photos + saved_videos + saved_docs

    if merchant_id:
        MerchantService.attach_media(
            db=db,
            merchant_id=merchant_id,
            photos=saved_photos,
            videos=saved_videos,
            documents=saved_docs,
        )

    return MerchantMediaUploadResponse(
        message=f"Successfully uploaded {len(all_urls)} file(s).",
        photos=saved_photos,
        videos=saved_videos,
        documents=saved_docs,
        all_urls=all_urls,
        total_files=len(all_urls),
    )


@router.post(
    "/{merchant_id}/upload-media",
    response_model=MerchantMediaUploadResponse,
    summary="Upload media and attach directly to merchant ID",
    description="Uploads photos, videos, and documents directly linked to a specific merchant ID.",
)
def upload_merchant_media_by_id(
    merchant_id: int,
    photos: Optional[List[UploadFile]] = File(None, description="Shop front or gallery photos"),
    videos: Optional[List[UploadFile]] = File(None, description="Shop tour or promotion videos"),
    documents: Optional[List[UploadFile]] = File(None, description="Verification documents or licenses"),
    files: Optional[List[UploadFile]] = File(None, description="General media files auto-detected by extension"),
    db: Session = Depends(get_db),
) -> MerchantMediaUploadResponse:
    return upload_merchant_media(
        photos=photos,
        videos=videos,
        documents=documents,
        files=files,
        merchant_id=merchant_id,
        db=db,
    )


@router.get(
    "/regions",
    response_model=StandardResponse[MerchantRegionResponse],
    summary="Get districts, cities, and locations hierarchy",
    description="Returns distinct districts, cities, and locations for field staff onboarding dropdowns.",
)
def get_merchant_regions(
    db: Session = Depends(get_db),
) -> StandardResponse[MerchantRegionResponse]:
    regions = MerchantService.get_region_metadata(db=db)
    return success_response(
        data=MerchantRegionResponse(**regions),
        message="Regions retrieved successfully",
    )


@router.get(
    "/me",
    response_model=MerchantProfileResponse,
    summary="Get current merchant profile",
    description="Returns the business profile for the currently authenticated merchant.",
)
def get_my_merchant_profile(
    current_user: User = Depends(require_any_authenticated),
    db: Session = Depends(get_db),
) -> MerchantProfileResponse:
    merchant = MerchantService.get_merchant_by_user_id(
        db=db, user_id=current_user.id
    )
    return MerchantProfileResponse.model_validate(merchant)


@router.put(
    "/me",
    response_model=MerchantProfileResponse,
    summary="Update current merchant profile",
    description="Updates business details, timing, location, address, contact, or services.",
)
def update_my_merchant_profile(
    update_data: MerchantUpdateRequest,
    current_user: User = Depends(require_any_authenticated),
    db: Session = Depends(get_db),
) -> MerchantProfileResponse:
    merchant = MerchantService.get_merchant_by_user_id(
        db=db, user_id=current_user.id
    )
    updated = MerchantService.update_merchant(
        db=db, merchant=merchant, data=update_data
    )
    return MerchantProfileResponse.model_validate(updated)


@router.post(
    "/upload-photos",
    response_model=MerchantPhotosUploadResponse,
    summary="Upload multiple merchant shop/service photos",
    description="Uploads one or more merchant photos (JPG, PNG, WEBP) and attaches them to the merchant profile.",
)
def upload_merchant_photos(
    photos: List[UploadFile] = File(...),
    current_user: User = Depends(require_any_authenticated),
    db: Session = Depends(get_db),
) -> MerchantPhotosUploadResponse:
    merchant = MerchantService.get_merchant_by_user_id(
        db=db, user_id=current_user.id
    )

    upload_dir = os.path.join("uploads", "merchants")
    os.makedirs(upload_dir, exist_ok=True)

    saved_urls = []
    for photo in photos:
        ext = os.path.splitext(photo.filename)[1].lower() if photo.filename else ""
        if ext not in ALLOWED_IMAGE_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File {photo.filename} has an invalid format. Allowed: JPG, JPEG, PNG, WEBP.",
            )

        unique_name = f"{uuid.uuid4().hex}{ext}"
        dest_path = os.path.join(upload_dir, unique_name)
        with open(dest_path, "wb") as buffer:
            shutil.copyfileobj(photo.file, buffer)

        saved_urls.append(f"/static/merchants/{unique_name}")

    updated_merchant = MerchantService.add_photos(
        db=db, merchant=merchant, new_photo_urls=saved_urls
    )

    return MerchantPhotosUploadResponse(
        message=f"Successfully uploaded {len(saved_urls)} photo(s).",
        uploaded_photo_urls=saved_urls,
        total_photos=updated_merchant.merchant_photos,
    )


@router.get(
    "",
    response_model=List[MerchantProfileResponse],
    summary="Discover & list merchants",
    description="Public endpoint to list registered merchants, optionally filtered by category or location.",
)
def list_merchants(
    category: Optional[str] = Query(None, description="Filter by category (e.g. Salon, Restaurant)"),
    location: Optional[str] = Query(None, description="Filter by location/city"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
) -> List[MerchantProfileResponse]:
    merchants = MerchantService.list_merchants(
        db=db, category=category, location=location, skip=skip, limit=limit
    )
    return [MerchantProfileResponse.model_validate(m) for m in merchants]


@router.get(
    "/list",
    response_model=StandardListResponse[MerchantProfileResponse],
    summary="List merchants with filters and pagination",
    description="Returns a paginated list of approved and active merchants with filters for category, location, service, and search query.",
)
def list_merchants_paginated(
    search: Optional[str] = Query(None, description="Search by business name, location, address, or service"),
    category: Optional[str] = Query(None, description="Filter by category (e.g. Salon, Spa, Cafe)"),
    location: Optional[str] = Query(None, description="Filter by location/city"),
    service: Optional[str] = Query(None, description="Filter by specific service offered"),
    is_verified: Optional[bool] = Query(None, description="Filter by verified status"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
) -> StandardListResponse[MerchantProfileResponse]:
    skip = (page - 1) * page_size
    results, total = MerchantService.search_merchants(
        db=db,
        query=search,
        location=location,
        service=service,
        category=category,
        is_verified=is_verified,
        skip=skip,
        limit=page_size,
        public_only=True,
    )
    return list_response(
        data=[MerchantProfileResponse.model_validate(m) for m in results],
        total_items=total,
        page=page,
        page_size=page_size,
        message=f"Retrieved {len(results)} merchant(s)",
    )


@router.get(
    "/search",
    response_model=StandardListResponse[MerchantProfileResponse],
    summary="Search merchants by location, service, and keywords",
    description="Unified search across location, services, categories, and business name with standardized response.",
)
def search_merchants(
    q: Optional[str] = Query(None, description="General search keyword (name, service, category, location)"),
    location: Optional[str] = Query(None, description="Search by location / city / area"),
    service: Optional[str] = Query(None, description="Search by specific service offered (e.g. Haircut, Facial)"),
    category: Optional[str] = Query(None, description="Filter by category (e.g. Salon, Spa)"),
    is_verified: Optional[bool] = Query(None, description="Filter by verified status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> StandardListResponse[MerchantProfileResponse]:
    results, total = MerchantService.search_merchants(
        db=db,
        query=q,
        location=location,
        service=service,
        category=category,
        is_verified=is_verified,
        skip=skip,
        limit=limit,
        public_only=True,
    )
    page = (skip // limit) + 1
    return list_response(
        data=[MerchantProfileResponse.model_validate(m) for m in results],
        total_items=total,
        page=page,
        page_size=limit,
        message=f"Found {total} merchant(s) matching search criteria",
    )


@router.get(
    "/search/location",
    response_model=StandardListResponse[MerchantProfileResponse],
    summary="Search merchants by location",
    description="Dedicated location search finding merchants by city, area, or address.",
)
def search_merchants_by_location(
    location: str = Query(..., min_length=2, description="City, area, or locality name to search"),
    category: Optional[str] = Query(None, description="Optional category filter"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> StandardListResponse[MerchantProfileResponse]:
    results, total = MerchantService.search_merchants(
        db=db,
        location=location,
        category=category,
        skip=skip,
        limit=limit,
        public_only=True,
    )
    page = (skip // limit) + 1
    return list_response(
        data=[MerchantProfileResponse.model_validate(m) for m in results],
        total_items=total,
        page=page,
        page_size=limit,
        message=f"Found {total} merchant(s) in '{location}'",
    )


@router.get(
    "/search/service",
    response_model=StandardListResponse[MerchantProfileResponse],
    summary="Search merchants by service",
    description="Dedicated service search finding merchants offering a specific service (e.g. Haircut, Spa, Car Wash).",
)
def search_merchants_by_service(
    service: str = Query(..., min_length=2, description="Service name to search (e.g. Haircut, Oil Change)"),
    location: Optional[str] = Query(None, description="Optional location filter"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> StandardListResponse[MerchantProfileResponse]:
    results, total = MerchantService.search_merchants(
        db=db,
        service=service,
        location=location,
        skip=skip,
        limit=limit,
        public_only=True,
    )
    page = (skip // limit) + 1
    return list_response(
        data=[MerchantProfileResponse.model_validate(m) for m in results],
        total_items=total,
        page=page,
        page_size=limit,
        message=f"Found {total} merchant(s) offering service '{service}'",
    )


@router.get(
    "/stats",
    response_model=StandardResponse[MerchantStatsResponse],
    summary="Get active and inactive merchant statistics",
    description="Aggregates platform merchant statistics including active, inactive, pending, approved, rejected, and verified counts.",
)
def get_merchant_statistics(
    db: Session = Depends(get_db),
) -> StandardResponse[MerchantStatsResponse]:
    stats = MerchantService.get_merchant_stats(db=db)
    return success_response(
        data=MerchantStatsResponse(**stats),
        message="Merchant statistics retrieved successfully",
    )


@router.get(
    "/locations",
    response_model=StandardResponse[List[LocationCountItem]],
    summary="Get merchant locations",
    description="Returns available merchant locations with active merchant counts and optional search filter.",
)
def get_merchant_locations(
    query: Optional[str] = Query(None, description="Filter locations by name"),
    db: Session = Depends(get_db),
) -> StandardResponse[List[LocationCountItem]]:
    locations = MerchantService.get_locations_with_counts(db=db, query=query)
    return success_response(
        data=[LocationCountItem(**loc) for loc in locations],
        message="Locations retrieved successfully",
    )


@router.get(
    "/services",
    response_model=StandardResponse[List[ServiceCountItem]],
    summary="Get merchant services",
    description="Returns available merchant services with active merchant counts and optional search filter.",
)
def get_merchant_services(
    query: Optional[str] = Query(None, description="Filter services by name"),
    db: Session = Depends(get_db),
) -> StandardResponse[List[ServiceCountItem]]:
    services = MerchantService.get_services_with_counts(db=db, query=query)
    return success_response(
        data=[ServiceCountItem(**svc) for svc in services],
        message="Services retrieved successfully",
    )


@router.get(
    "/discovery-meta",
    response_model=StandardResponse[MerchantDiscoveryMetaResponse],
    summary="Get discovery metadata (locations & services)",
    description="Returns distinct locations, services, and categories for search suggestions and dropdowns.",
)
@router.get(
    "/meta/discovery",
    response_model=StandardResponse[MerchantDiscoveryMetaResponse],
    include_in_schema=False,
)
def get_discovery_metadata(
    db: Session = Depends(get_db),
) -> StandardResponse[MerchantDiscoveryMetaResponse]:
    meta = MerchantService.get_discovery_metadata(db=db)
    return success_response(
        data=MerchantDiscoveryMetaResponse(**meta),
        message="Discovery metadata retrieved successfully",
    )


# ── OTP Login Flow ────────────────────────────────────────────────────────────

@router.post(
    "/login/send-otp",
    response_model=MerchantLoginOTPResponse,
    summary="Step 1 — Request merchant OTP login code",
    description=(
        "Sends a 6-digit OTP to the registered merchant's email. "
        "The OTP expires in a few minutes and is single-use. "
        "Only works for accounts with MERCHANT role that are active."
    ),
)
def merchant_login_send_otp(
    req: MerchantLoginOTPRequest,
    db: Session = Depends(get_db),
) -> MerchantLoginOTPResponse:
    plain_otp = MerchantService.send_login_otp(db=db, email=req.email)
    dev_otp = plain_otp if settings.ENVIRONMENT == "development" else None
    return MerchantLoginOTPResponse(
        message=f"OTP sent to {req.email}. Please check your inbox.",
        expires_in_minutes=settings.OTP_EXPIRE_MINUTES,
        dev_otp=dev_otp,
    )


@router.post(
    "/login/verify-otp",
    response_model=TokenResponse,
    summary="Step 2 — Verify OTP and receive JWT tokens",
    description=(
        "Verifies the 6-digit OTP sent to the merchant's email. "
        "On success, returns a JWT access token and refresh token pair "
        "to authenticate subsequent requests."
    ),
)
def merchant_login_verify_otp(
    req: MerchantVerifyOTPLoginRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    return MerchantService.verify_login_otp(db=db, email=req.email, otp=req.otp)
