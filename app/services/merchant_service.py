from typing import List, Optional, Tuple
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.models.merchant import MerchantProfile
from app.db.models.user import User, UserRole
from app.schemas.merchant import MerchantRegisterRequest, MerchantUpdateRequest


class MerchantService:
    """Service handling merchant registration, profile management, and discovery."""

    @staticmethod
    def register_merchant(
        db: Session, data: MerchantRegisterRequest
    ) -> Tuple[User, MerchantProfile]:
        clean_email = data.email.strip().lower()

        # Check existing user email
        existing_user = db.query(User).filter(User.email == clean_email).first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists.",
            )

        # Check existing phone
        existing_phone = db.query(User).filter(User.phone == data.contact_number).first()
        if existing_phone:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this contact number already exists.",
            )

        # 1. Create User with MERCHANT role
        user = User(
            name=data.name.strip(),
            email=clean_email,
            phone=data.contact_number,
            password_hash=hash_password(data.password),
            role=UserRole.MERCHANT,
            address=data.address,
            profile_picture=(data.merchant_photos[0] if data.merchant_photos else None),
            is_active=True,
            is_verified=False,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        # 2. Create Merchant Profile
        merchant = MerchantProfile(
            user_id=user.id,
            business_name=data.business_name.strip(),
            categories=data.categories,
            location=data.location.strip(),
            services=data.services,
            service_timing=data.service_timing.strip(),
            merchant_photos=data.merchant_photos or [],
            contact_number=data.contact_number.strip(),
            address=data.address.strip(),
            is_verified=False,
        )
        db.add(merchant)
        db.commit()
        db.refresh(merchant)

        return user, merchant

    @staticmethod
    def get_merchant_by_user_id(db: Session, user_id: int) -> MerchantProfile:
        merchant = (
            db.query(MerchantProfile).filter(MerchantProfile.user_id == user_id).first()
        )
        if not merchant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Merchant profile not found for this account.",
            )
        return merchant

    @staticmethod
    def update_merchant(
        db: Session, merchant: MerchantProfile, data: MerchantUpdateRequest
    ) -> MerchantProfile:
        if data.business_name is not None:
            merchant.business_name = data.business_name.strip()
        if data.categories is not None:
            merchant.categories = data.categories
        if data.location is not None:
            merchant.location = data.location.strip()
        if data.services is not None:
            merchant.services = data.services
        if data.service_timing is not None:
            merchant.service_timing = data.service_timing.strip()
        if data.merchant_photos is not None:
            merchant.merchant_photos = data.merchant_photos
        if data.contact_number is not None:
            merchant.contact_number = data.contact_number.strip()
        if data.address is not None:
            merchant.address = data.address.strip()

        db.commit()
        db.refresh(merchant)
        return merchant

    @staticmethod
    def add_photos(
        db: Session, merchant: MerchantProfile, new_photo_urls: List[str]
    ) -> MerchantProfile:
        current_photos = list(merchant.merchant_photos or [])
        current_photos.extend(new_photo_urls)
        merchant.merchant_photos = current_photos
        db.commit()
        db.refresh(merchant)
        return merchant

    @staticmethod
    def list_merchants(
        db: Session,
        category: Optional[str] = None,
        location: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> List[MerchantProfile]:
        query = db.query(MerchantProfile)
        if location:
            query = query.filter(MerchantProfile.location.ilike(f"%{location}%"))
        results = query.offset(skip).limit(limit).all()

        if category:
            cat_clean = category.strip().lower()
            results = [
                m
                for m in results
                if any(cat_clean in c.lower() for c in (m.categories or []))
            ]

        return results
