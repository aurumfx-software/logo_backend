import os
import shutil
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_role
from app.db.database import get_db
from app.db.models.user import User, UserRole
from app.schemas.auth import SafeUserResponse
from app.schemas.merchant import (
    MerchantPhotosUploadResponse,
    MerchantProfileResponse,
    MerchantRegisterRequest,
    MerchantRegisterResponse,
    MerchantUpdateRequest,
)
from app.services.merchant_service import MerchantService

router = APIRouter(prefix="/merchants", tags=["Merchants"])

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


@router.post(
    "/register",
    response_model=MerchantRegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new merchant",
    description=(
        "Registers a merchant account with role MERCHANT, business name, categories, "
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


@router.get(
    "/me",
    response_model=MerchantProfileResponse,
    summary="Get current merchant profile",
    description="Returns the business profile for the currently authenticated merchant.",
)
def get_my_merchant_profile(
    current_user: User = Depends(require_role(UserRole.MERCHANT)),
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
    current_user: User = Depends(require_role(UserRole.MERCHANT)),
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
    current_user: User = Depends(require_role(UserRole.MERCHANT)),
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
