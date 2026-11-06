from typing import Any, List, Optional, Tuple
from fastapi import HTTPException, status
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session, joinedload, load_only

from app.core.security import hash_password, verify_password
from app.db.models.merchant import MerchantProfile
from app.db.models.otp import OTPPurpose
from app.db.models.user import User, UserRole
from app.schemas.merchant import (
    MerchantCreatorSummary,
    MerchantLinkedUser,
    MerchantOnboardingRequest,
    MerchantProfileResponse,
    MerchantRegisterRequest,
    MerchantUpdateRequest,
)
from app.schemas.auth import TokenResponse, UserLoginRequest
from app.services.otp_service import OTPService


class MerchantService:
    """Service handling merchant registration, profile management, and discovery."""

    _USER_LOAD_ONLY = (
        User.id,
        User.user_code,
        User.name,
        User.email,
        User.phone,
        User.role,
        User.is_active,
    )

    @staticmethod
    def _password_setup_required_exception() -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "MERCHANT_PASSWORD_NOT_SET",
                "message": (
                    "No merchant password is set. Use POST /api/v1/auth/forgot-password "
                    "to receive an OTP, then POST /api/v1/auth/reset-password to create your password."
                ),
                "password_setup_required": True,
            },
        )

    @staticmethod
    def _set_merchant_password(merchant: MerchantProfile, plain_password: str) -> None:
        hashed = hash_password(plain_password)
        merchant.password_hash = hashed

    @staticmethod
    def resolve_merchant_by_email(
        db: Session, email: str
    ) -> Tuple[Optional[MerchantProfile], Optional[User]]:
        clean_email = email.strip().lower()
        merchant = (
            db.query(MerchantProfile)
            .filter(func.lower(MerchantProfile.email) == clean_email)
            .first()
        )
        user: Optional[User] = None
        if merchant:
            user = db.query(User).filter(User.id == merchant.user_id).first()
            return merchant, user

        user = db.query(User).filter(User.email == clean_email).first()
        if not user:
            return None, None
        merchant = (
            db.query(MerchantProfile).filter(MerchantProfile.user_id == user.id).first()
        )
        return merchant, user

    @staticmethod
    def sync_merchant_password_from_user(db: Session, user: User, plain_password: str) -> None:
        merchants = db.query(MerchantProfile).filter(MerchantProfile.user_id == user.id).all()
        if not merchants:
            return
        hashed = hash_password(plain_password)
        for merchant in merchants:
            merchant.password_hash = hashed

    @staticmethod
    def _coerce_str_list(value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(x) for x in value if x is not None and str(x).strip()]
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            if text.startswith("[") and text.endswith("]"):
                return [text]
            return [part.strip() for part in text.split(",") if part.strip()]
        return [str(value)]

    @staticmethod
    def _merchant_list_options():
        return (
            joinedload(MerchantProfile.user).load_only(*MerchantService._USER_LOAD_ONLY),
            joinedload(MerchantProfile.onboarded_by).load_only(*MerchantService._USER_LOAD_ONLY),
        )

    @staticmethod
    def _merchant_matches_category(merchant: MerchantProfile, category: str) -> bool:
        cat_clean = category.strip().lower()
        if not cat_clean:
            return True
        if merchant.category and cat_clean in merchant.category.strip().lower():
            return True
        if merchant.category and merchant.category.strip().lower() == cat_clean:
            return True
        for c in merchant.categories or []:
            label = str(c).strip().lower()
            if cat_clean in label or label == cat_clean:
                return True
        return False

    @staticmethod
    def _apply_category_sql_filter(query, category: Optional[str]):
        if not category or not category.strip():
            return query
        pattern = f"%{category.strip()}%"
        return query.filter(
            or_(
                MerchantProfile.category.ilike(pattern),
                cast(MerchantProfile.categories, String).ilike(pattern),
            )
        )

    @staticmethod
    def load_linked_users(db: Session, user_ids: set) -> dict:
        """Batch-load owner users with only stable columns (avoids schema drift on users table)."""
        if not user_ids:
            return {}
        rows = (
            db.query(
                User.id,
                User.user_code,
                User.name,
                User.email,
                User.phone,
                User.profile_picture,
                User.district,
                User.city,
            )
            .filter(User.id.in_(user_ids))
            .all()
        )
        return {row.id: row for row in rows}

    @staticmethod
    def merge_linked_user(
        resp: MerchantProfileResponse,
        user_row: Any,
    ) -> MerchantProfileResponse:
        if not user_row:
            return resp
        linked = MerchantLinkedUser(
            id=user_row.id,
            user_code=user_row.user_code,
            name=user_row.name or "Unknown",
            email=user_row.email,
            phone=user_row.phone,
            profile_picture=user_row.profile_picture,
            district=user_row.district,
            city=user_row.city,
        )
        resp.user = linked
        if not resp.owner_name:
            resp.owner_name = linked.name
        if not resp.owner:
            resp.owner = linked.name
        if not resp.email:
            resp.email = linked.email
        if not resp.phone:
            resp.phone = linked.phone
        if not resp.contact_number:
            resp.contact_number = linked.phone
        if not resp.district and linked.district:
            resp.district = linked.district
        if not resp.city and linked.city:
            resp.city = linked.city
        if not resp.user_code and linked.user_code:
            resp.user_code = linked.user_code
        return resp

    @staticmethod
    def build_merchant_list_responses(
        db: Session,
        merchants: List[MerchantProfile],
        merge_users: bool = True,
        include_creator: bool = False,
    ) -> List[MerchantProfileResponse]:
        linked_map = {}
        if merge_users and merchants:
            linked_map = MerchantService.load_linked_users(
                db, {m.user_id for m in merchants if m.user_id}
            )
        results: List[MerchantProfileResponse] = []
        for merchant in merchants:
            try:
                resp = MerchantService.build_merchant_response(
                    merchant,
                    include_creator=include_creator,
                )
                if merge_users:
                    resp = MerchantService.merge_linked_user(
                        resp, linked_map.get(merchant.user_id)
                    )
                results.append(resp)
            except Exception:
                continue
        return results

    @staticmethod
    def build_merchant_response(
        merchant: MerchantProfile,
        include_creator: bool = True,
        linked_user: Any = None,
    ) -> MerchantProfileResponse:
        merchant.categories = MerchantService._coerce_str_list(merchant.categories)
        merchant.services = MerchantService._coerce_str_list(merchant.services)
        merchant.merchant_photos = MerchantService._coerce_str_list(merchant.merchant_photos)
        merchant.merchant_videos = MerchantService._coerce_str_list(merchant.merchant_videos)
        merchant.verification_documents = MerchantService._coerce_str_list(
            merchant.verification_documents
        )
        merchant.key_highlights = MerchantService._coerce_str_list(merchant.key_highlights)
        if merchant.rating is not None:
            try:
                merchant.rating = float(merchant.rating)
            except (TypeError, ValueError):
                merchant.rating = 0.0
        if merchant.latitude is not None:
            try:
                merchant.latitude = float(merchant.latitude)
            except (TypeError, ValueError):
                merchant.latitude = None
        if merchant.longitude is not None:
            try:
                merchant.longitude = float(merchant.longitude)
            except (TypeError, ValueError):
                merchant.longitude = None

        creator_user = None
        creator_summary = None
        if include_creator:
            try:
                if merchant.onboarded_by_id:
                    creator_user = merchant.onboarded_by
                else:
                    creator_user = merchant.user
            except Exception:
                creator_user = None
        if creator_user:
            role_str = creator_user.role.value if hasattr(creator_user.role, "value") else str(creator_user.role)
            creator_summary = MerchantCreatorSummary(
                id=creator_user.id,
                user_code=creator_user.user_code,
                name=creator_user.name or "Unknown",
                email=creator_user.email or "",
                phone=creator_user.phone,
                role=role_str,
            )
        resp = MerchantProfileResponse.model_validate(merchant)
        if (merchant.approval_status or "").upper() == "APPROVED":
            resp.status = "APPROVED"
        resp.cashback_percent = float(merchant.cashback_percent if merchant.cashback_percent is not None else 3)
        resp.company_fee_percent = float(
            merchant.company_fee_percent if merchant.company_fee_percent is not None else 2
        )
        resp.total_deduction_percent = round(resp.cashback_percent + resp.company_fee_percent, 2)
        if merchant.user_code:
            resp.user_code = merchant.user_code
        elif creator_summary:
            resp.user_code = creator_summary.user_code
        resp.creator = creator_summary
        resp.created_by = creator_summary
        resp.has_password = bool(merchant.password_hash)
        if linked_user is not None:
            resp = MerchantService.merge_linked_user(resp, linked_user)
        return resp

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

        # 1. Create login account in users table (merchant owner)
        hashed_pwd = hash_password(data.password)
        user = User(
            name=data.name.strip(),
            email=clean_email,
            phone=data.contact_number,
            password_hash=hashed_pwd,
            role=UserRole.MERCHANT,
            address=data.address,
            profile_picture=(data.merchant_photos[0] if data.merchant_photos else None),
            is_active=True,
            is_verified=False,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        # 2. Create business profile in merchant_profiles (linked by user_id)
        merchant = MerchantProfile(
            user_id=user.id,
            user_code=user.user_code,
            business_name=data.business_name.strip(),
            owner_name=data.name.strip(),
            owner=data.name.strip(),
            categories=data.categories,
            category=data.categories[0] if data.categories else None,
            location=data.location.strip(),
            services=data.services,
            service_timing=data.service_timing.strip(),
            merchant_photos=data.merchant_photos or [],
            contact_number=data.contact_number.strip(),
            phone=data.contact_number.strip(),
            email=clean_email,
            address=data.address.strip(),
            password_hash=hashed_pwd,
            is_verified=False,
            approval_status="PENDING",
            is_active=True,
        )
        db.add(merchant)
        db.commit()
        db.refresh(merchant)

        from app.services.activity_log_service import ActivityLogService
        ActivityLogService.log_activity(
            db=db,
            action="MERCHANT_REGISTERED",
            entity_type="MERCHANT",
            entity_id=merchant.id,
            user_id=user.id,
            details={"business_name": merchant.business_name, "location": merchant.location},
        )

        return user, merchant

    @staticmethod
    def onboard_merchant(
        db: Session,
        data: MerchantOnboardingRequest,
        onboarded_by: Optional[User] = None,
    ) -> Tuple[User, MerchantProfile]:
        import re
        import secrets

        # 1. Normalize categories
        categories = []
        if data.categories:
            categories = [c.strip() for c in data.categories if c and c.strip()]
        elif data.category:
            categories = [data.category.strip()]
        if not categories:
            categories = ["General"]

        # 2. Normalize location fields: District, City, Location
        district = data.district.strip() if data.district else None
        city = (data.city or data.city_region or "").strip() or None
        location = (data.location or data.city_region or data.city or "General").strip()
        landmark = data.landmark.strip() if data.landmark else None

        # 3. Normalize contact/phone number
        clean_phone = re.sub(r"[\s\-()]", "", data.phone_number)

        # 4. Resolve creator user (Field Staff or Admin)
        creator_user = None
        if onboarded_by:
            creator_user = onboarded_by
        elif data.user_code:
            creator_user = db.query(User).filter(User.user_code == data.user_code.strip()).first()
        elif data.user_id:
            creator_user = db.query(User).filter(User.id == data.user_id).first()

        creator_user_id = creator_user.id if creator_user else None

        # 5. Check or create linked User for merchant login if needed
        clean_email = data.email.strip().lower() if data.email else None
        user = None

        if clean_email:
            user = db.query(User).filter(User.email == clean_email).first()

        if not user:
            phone_user = db.query(User).filter(User.phone == clean_phone).first()
            if phone_user:
                user = phone_user

        if not user:
            owner_name = (data.owner_name or data.owner or data.business_name or "Business Owner").strip()
            random_pw = secrets.token_urlsafe(12)
            gen_email = clean_email or f"merchant_{re.sub(r'[^\w]', '', clean_phone)}@merchant.local"
            if db.query(User).filter(User.email == gen_email).first():
                gen_email = f"merchant_{re.sub(r'[^\w]', '', clean_phone)}_{secrets.token_hex(3)}@merchant.local"

            user = User(
                name=owner_name,
                email=gen_email,
                phone=clean_phone,
                password_hash=hash_password(random_pw),
                role=UserRole.MERCHANT,
                address=data.address.strip() if data.address else None,
                district=district,
                city=city,
                profile_picture=(data.merchant_photos[0] if data.merchant_photos else None),
                is_active=True,
                is_verified=False,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        elif user.role not in (UserRole.MERCHANT, UserRole.SUPER_ADMIN, UserRole.ADMIN):
            user.role = UserRole.MERCHANT
            db.commit()
            db.refresh(user)

        # 6. Create merchant_profiles row — always linked to owner user (users table)
        category_val = data.category or (categories[0] if categories else None)
        owner_val = data.owner or data.owner_name

        merchant_user_code = data.user_code if (data.user_code and data.user_code.startswith("MRH")) else None

        merchant_password_hash = None
        if getattr(data, "password", None):
            merchant_password_hash = hash_password(data.password)
            if user:
                user.password_hash = merchant_password_hash

        merchant = MerchantProfile(
            user_id=user.id,
            user_code=merchant_user_code or user.user_code,
            onboarded_by_id=creator_user_id,
            business_name=data.business_name.strip(),
            owner=owner_val.strip() if owner_val else "Business Owner",
            category=category_val,
            address=data.address.strip() if data.address else None,
            city=city,
            district=district,
            location=location,
            state=data.state,
            latitude=data.latitude,
            longitude=data.longitude,
            phone=clean_phone or data.phone,
            whatsapp=data.whatsapp,
            landline=data.landline,
            email=data.email.strip().lower() if data.email else None,
            password_hash=merchant_password_hash,
            website=data.website,
            facebook=data.facebook,
            instagram=data.instagram,
            twitter=data.twitter,
            youtube=data.youtube,
            photo_1=data.photo_1 or (data.merchant_photos[0] if data.merchant_photos else None),
            photo_2=data.photo_2 or (data.merchant_photos[1] if len(data.merchant_photos) > 1 else None),
            photo_3=data.photo_3 or (data.merchant_photos[2] if len(data.merchant_photos) > 2 else None),
            photo_4=data.photo_4 or (data.merchant_photos[3] if len(data.merchant_photos) > 3 else None),
            photo_5=data.photo_5 or (data.merchant_photos[4] if len(data.merchant_photos) > 4 else None),
            photo_6=data.photo_6 or (data.merchant_photos[5] if len(data.merchant_photos) > 5 else None),
            about=data.about,
            rating=data.rating or 0.0,
            reviews_count=data.reviews_count or 0,
            key_highlights=data.key_highlights or [],
            video_url=data.video_url or (data.merchant_videos[0] if data.merchant_videos else None),
            merchant_photos=data.merchant_photos or [],
            merchant_videos=data.merchant_videos or [],
            verification_documents=data.verification_documents or [],
            services=data.services or [],
            status=data.status or "PENDING",
            landmark=landmark,
            service_timing=data.service_timing or "General Store Hours",
            is_verified=False,
            is_active=True,
            approval_status="PENDING",
        )
        db.add(merchant)
        db.commit()
        db.refresh(merchant)

        from app.services.activity_log_service import ActivityLogService
        ActivityLogService.log_activity(
            db=db,
            action="MERCHANT_ONBOARDED",
            entity_type="MERCHANT",
            entity_id=merchant.id,
            user_id=user.id,
            details={
                "business_name": merchant.business_name,
                "district": merchant.district,
                "city": merchant.city,
                "location": merchant.location,
                "onboarded_by": creator_user.name if creator_user else "Field Staff / Onboarding Portal",
            },
        )

        return user, merchant

    @staticmethod
    def get_merchant_by_id(db: Session, merchant_id: int) -> MerchantProfile:
        merchant = db.query(MerchantProfile).filter(MerchantProfile.id == merchant_id).first()
        if not merchant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Merchant with ID {merchant_id} not found.",
            )
        return merchant

    @staticmethod
    def get_merchant_by_user_id(db: Session, user_id: int) -> MerchantProfile:
        merchant = (
            db.query(MerchantProfile)
            .filter(MerchantProfile.user_id == user_id)
            .order_by(MerchantProfile.id.desc())
            .first()
        )
        if not merchant:
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                if user.email:
                    merchant = (
                        db.query(MerchantProfile)
                        .filter(MerchantProfile.email.ilike(user.email.strip()))
                        .order_by(MerchantProfile.id.desc())
                        .first()
                    )
                if not merchant and user.phone:
                    merchant = (
                        db.query(MerchantProfile)
                        .filter(MerchantProfile.phone == user.phone.strip())
                        .order_by(MerchantProfile.id.desc())
                        .first()
                    )
                if merchant and not merchant.user_id:
                    merchant.user_id = user.id
                    db.commit()
                    db.refresh(merchant)
        if not merchant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Merchant profile not found for this account.",
            )
        return merchant

    @staticmethod
    def approve_merchant(db: Session, merchant_id: int, admin_user: User) -> MerchantProfile:
        from datetime import datetime, timezone
        from app.services.activity_log_service import ActivityLogService
        from app.services.notification_service import NotificationService

        merchant = MerchantService.get_merchant_by_id(db=db, merchant_id=merchant_id)
        merchant.approval_status = "APPROVED"
        merchant.status = "APPROVED"
        merchant.is_verified = True
        merchant.is_active = True
        merchant.approved_by_id = admin_user.id
        merchant.approved_at = datetime.now(timezone.utc)
        merchant.rejection_reason = None

        db.commit()
        db.refresh(merchant)

        # Notify merchant
        NotificationService.create_notification(
            db=db,
            user_id=merchant.user_id,
            title="Merchant Profile Approved! 🎉",
            message=f"Congratulations! Your merchant profile for '{merchant.business_name}' has been verified and approved by administration.",
            type="MERCHANT_APPROVAL",
            data={"merchant_id": merchant.id, "business_name": merchant.business_name},
        )

        # Audit log
        ActivityLogService.log_activity(
            db=db,
            action="MERCHANT_APPROVED",
            entity_type="MERCHANT",
            entity_id=merchant.id,
            user_id=admin_user.id,
            details={"business_name": merchant.business_name, "admin": admin_user.name},
        )

        return merchant

    @staticmethod
    def reject_merchant(
        db: Session, merchant_id: int, reason: str, admin_user: User
    ) -> MerchantProfile:
        from datetime import datetime, timezone
        from app.services.activity_log_service import ActivityLogService
        from app.services.notification_service import NotificationService

        merchant = MerchantService.get_merchant_by_id(db=db, merchant_id=merchant_id)
        merchant.approval_status = "REJECTED"
        merchant.status = "REJECTED"
        merchant.is_active = False
        merchant.rejection_reason = reason.strip()
        merchant.approved_by_id = admin_user.id
        merchant.approved_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(merchant)

        # Notify merchant
        NotificationService.create_notification(
            db=db,
            user_id=merchant.user_id,
            title="Merchant Profile Application Update",
            message=f"Your merchant application for '{merchant.business_name}' was not approved. Reason: {reason.strip()}",
            type="MERCHANT_REJECTION",
            data={"merchant_id": merchant.id, "rejection_reason": reason.strip()},
        )

        # Audit log
        ActivityLogService.log_activity(
            db=db,
            action="MERCHANT_REJECTED",
            entity_type="MERCHANT",
            entity_id=merchant.id,
            user_id=admin_user.id,
            details={"business_name": merchant.business_name, "rejection_reason": reason.strip(), "admin": admin_user.name},
        )

        return merchant

    @staticmethod
    def get_merchant_stats(db: Session) -> dict:
        from datetime import datetime, timedelta, timezone
        from collections import Counter

        merchants = db.query(MerchantProfile).join(User, MerchantProfile.user_id == User.id).all()

        total = len(merchants)
        active = sum(1 for m in merchants if m.is_active and m.user.is_active)
        inactive = total - active
        pending = sum(1 for m in merchants if getattr(m, "approval_status", "PENDING") == "PENDING")
        approved = sum(1 for m in merchants if getattr(m, "approval_status", "") == "APPROVED")
        rejected = sum(1 for m in merchants if getattr(m, "approval_status", "") == "REJECTED")
        verified = sum(1 for m in merchants if m.is_verified)
        unverified = total - verified

        now = datetime.now(timezone.utc)
        seven_days_ago = now - timedelta(days=7)
        thirty_days_ago = now - timedelta(days=30)

        def _is_after(dt, threshold):
            if dt is None:
                return False
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt >= threshold

        r_7d = sum(1 for m in merchants if _is_after(m.created_at, seven_days_ago))
        r_30d = sum(1 for m in merchants if _is_after(m.created_at, thirty_days_ago))

        # Location counts
        location_counts = Counter(m.location for m in merchants if m.location)
        top_locations = [{"location": loc, "count": count} for loc, count in location_counts.most_common(10)]

        # Category counts
        cat_counts = Counter()
        for m in merchants:
            for c in (m.categories or []):
                cat_counts[c] += 1
        top_categories = [{"category": cat, "count": count} for cat, count in cat_counts.most_common(10)]

        return {
            "total_merchants": total,
            "active_merchants": active,
            "inactive_merchants": inactive,
            "pending_merchants": pending,
            "approved_merchants": approved,
            "rejected_merchants": rejected,
            "verified_merchants": verified,
            "unverified_merchants": unverified,
            "top_locations": top_locations,
            "top_categories": top_categories,
            "recent_registrations_7d": r_7d,
            "recent_registrations_30d": r_30d,
        }

    @staticmethod
    def search_merchants(
        db: Session,
        query: Optional[str] = None,
        location: Optional[str] = None,
        service: Optional[str] = None,
        category: Optional[str] = None,
        is_verified: Optional[bool] = None,
        approval_status: Optional[str] = None,
        is_active: Optional[bool] = None,
        skip: int = 0,
        limit: int = 50,
        public_only: bool = True,
        current_user: Optional[User] = None,
        user_id: Optional[int] = None,
        user_code: Optional[str] = None,
    ) -> Tuple[List[MerchantProfile], int]:
        public_catalog = public_only and not user_code and not user_id
        if public_catalog:
            q = db.query(MerchantProfile)
        else:
            q = db.query(MerchantProfile).options(*MerchantService._merchant_list_options())

        # Scoped access or explicit filter:
        if user_code:
            code = user_code.strip()
            staff_user_ids = select(User.id).where(User.user_code == code)
            q = q.filter(
                (MerchantProfile.user_code == code)
                | (MerchantProfile.onboarded_by_id.in_(staff_user_ids))
                | MerchantProfile.user_id.in_(staff_user_ids)
            )
        elif (
            not public_only
            and current_user
            and current_user.role in (UserRole.FIELD_STAFF, UserRole.MERCHANT)
        ):
            q = q.filter(
                (MerchantProfile.user_id == current_user.id)
                | (MerchantProfile.onboarded_by_id == current_user.id)
            )
        elif user_id:
            q = q.filter(
                (MerchantProfile.user_id == user_id)
                | (MerchantProfile.onboarded_by_id == user_id)
            )

        if public_catalog:
            q = q.filter(
                MerchantProfile.is_active == True,
                func.upper(MerchantProfile.approval_status) == "APPROVED",
            )
        else:
            if approval_status:
                q = q.filter(MerchantProfile.approval_status == approval_status.upper())
            if is_active is not None:
                q = q.filter(MerchantProfile.is_active == is_active)

        if is_verified is not None:
            q = q.filter(MerchantProfile.is_verified == is_verified)

        if location:
            loc_clean = location.strip()
            q = q.filter(
                (MerchantProfile.location.ilike(f"%{loc_clean}%"))
                | (MerchantProfile.city.ilike(f"%{loc_clean}%"))
                | (MerchantProfile.district.ilike(f"%{loc_clean}%"))
                | (MerchantProfile.address.ilike(f"%{loc_clean}%"))
            )

        all_candidates = q.order_by(MerchantProfile.created_at.desc()).all()

        # In-memory filtering for JSON array attributes and free-text queries
        filtered = all_candidates

        if service:
            svc_clean = service.strip().lower()
            filtered = [
                m for m in filtered
                if any(svc_clean in str(s).lower() for s in (m.services or []))
            ]

        if category:
            filtered = [
                m for m in filtered
                if MerchantService._merchant_matches_category(m, category)
            ]

        if query:
            kw = query.strip().lower()
            filtered = [
                m for m in filtered
                if kw in (m.business_name or "").lower()
                or (m.owner_name and kw in m.owner_name.lower())
                or kw in (m.location or "").lower()
                or (m.city and kw in m.city.lower())
                or (m.district and kw in m.district.lower())
                or kw in (m.address or "").lower()
                or any(kw in str(s).lower() for s in (m.services or []))
                or any(kw in str(c).lower() for c in (m.categories or []))
            ]

        total = len(filtered)
        paginated = filtered[skip : skip + limit]
        return paginated, total

    @staticmethod
    def get_discovery_metadata(db: Session) -> dict:
        merchants = (
            db.query(MerchantProfile)
            .filter(MerchantProfile.approval_status == "APPROVED", MerchantProfile.is_active == True)
            .all()
        )
        locations = sorted(list({m.location.strip() for m in merchants if m.location}))
        services_set = set()
        categories_set = set()

        for m in merchants:
            for s in (m.services or []):
                if s:
                    services_set.add(s.strip())
            for c in (m.categories or []):
                if c:
                    categories_set.add(c.strip())

        return {
            "locations": sorted(list(locations)),
            "services": sorted(list(services_set)),
            "categories": sorted(list(categories_set)),
        }

    @staticmethod
    def get_locations_with_counts(db: Session, query: Optional[str] = None) -> List[dict]:
        from collections import Counter
        merchants = (
            db.query(MerchantProfile)
            .filter(MerchantProfile.approval_status == "APPROVED", MerchantProfile.is_active == True)
            .all()
        )
        counts = Counter(m.location.strip() for m in merchants if m.location)
        results = [{"location": loc, "count": count} for loc, count in counts.items()]
        if query:
            q_clean = query.strip().lower()
            results = [item for item in results if q_clean in item["location"].lower()]
        results.sort(key=lambda x: (-x["count"], x["location"]))
        return results

    @staticmethod
    def get_services_with_counts(db: Session, query: Optional[str] = None) -> List[dict]:
        from collections import Counter
        merchants = (
            db.query(MerchantProfile)
            .filter(MerchantProfile.approval_status == "APPROVED", MerchantProfile.is_active == True)
            .all()
        )
        counts = Counter()
        for m in merchants:
            for s in (m.services or []):
                if s:
                    counts[s.strip()] += 1
        results = [{"service": svc, "count": count} for svc, count in counts.items()]
        if query:
            q_clean = query.strip().lower()
            results = [item for item in results if q_clean in item["service"].lower()]
        results.sort(key=lambda x: (-x["count"], x["service"]))
        return results

    @staticmethod
    def update_merchant(
        db: Session, merchant: MerchantProfile, data: MerchantUpdateRequest
    ) -> MerchantProfile:
        # Names & Owner
        if data.business_name is not None and data.business_name.strip():
            merchant.business_name = data.business_name.strip()
        if data.name is not None and data.name.strip():
            merchant.business_name = data.name.strip()
        if data.owner is not None and data.owner.strip():
            merchant.owner = data.owner.strip()
            merchant.owner_name = data.owner.strip()
        if data.owner_name is not None and data.owner_name.strip():
            merchant.owner_name = data.owner_name.strip()
            merchant.owner = data.owner_name.strip()
        if data.contact_person is not None and data.contact_person.strip():
            merchant.owner = data.contact_person.strip()
            merchant.owner_name = data.contact_person.strip()

        # Categories
        if data.categories is not None:
            merchant.categories = data.categories
            if data.categories and len(data.categories) > 0:
                merchant.category = data.categories[0]
        if data.category is not None and data.category.strip():
            merchant.category = data.category.strip()
            if not merchant.categories:
                merchant.categories = [data.category.strip()]

        # Location & Address
        if data.address is not None:
            merchant.address = data.address.strip()
        if data.city is not None:
            merchant.city = data.city.strip()
        if data.district is not None:
            merchant.district = data.district.strip()
        if data.state is not None:
            merchant.state = data.state.strip()
        if data.location is not None:
            merchant.location = data.location.strip()
        if data.city_region is not None:
            merchant.location = data.city_region.strip()
        if data.landmark is not None:
            merchant.landmark = data.landmark.strip()
        if data.latitude is not None:
            merchant.latitude = data.latitude
        if data.longitude is not None:
            merchant.longitude = data.longitude

        # Contact Info
        if data.phone is not None:
            merchant.phone = data.phone.strip()
        if data.phone_number is not None:
            merchant.phone = data.phone_number.strip()
        if data.contact_number is not None:
            merchant.contact_number = data.contact_number.strip()
            if not merchant.phone:
                merchant.phone = data.contact_number.strip()
        if data.whatsapp is not None:
            merchant.whatsapp = data.whatsapp.strip()
        if data.landline is not None:
            merchant.landline = data.landline.strip()
        if data.email is not None:
            merchant.email = data.email.strip().lower()

        # Social & Web Links
        if data.website is not None:
            merchant.website = data.website.strip()
        if data.facebook is not None:
            merchant.facebook = data.facebook.strip()
        if data.instagram is not None:
            merchant.instagram = data.instagram.strip()
        if data.twitter is not None:
            merchant.twitter = data.twitter.strip()
        if data.youtube is not None:
            merchant.youtube = data.youtube.strip()

        # About, Rating & Highlights
        if data.about is not None:
            merchant.about = data.about.strip()
        if data.description is not None:
            merchant.about = data.description.strip()
        if data.rating is not None:
            merchant.rating = data.rating
        if data.reviews_count is not None:
            merchant.reviews_count = data.reviews_count
        if data.key_highlights is not None:
            merchant.key_highlights = data.key_highlights

        # Media & Documents
        if data.merchant_photos is not None:
            merchant.merchant_photos = data.merchant_photos
        elif data.photos is not None:
            merchant.merchant_photos = data.photos
        if data.photo_1 is not None:
            merchant.photo_1 = data.photo_1
        if data.photo_2 is not None:
            merchant.photo_2 = data.photo_2
        if data.photo_3 is not None:
            merchant.photo_3 = data.photo_3
        if data.photo_4 is not None:
            merchant.photo_4 = data.photo_4
        if data.photo_5 is not None:
            merchant.photo_5 = data.photo_5
        if data.photo_6 is not None:
            merchant.photo_6 = data.photo_6

        if data.video_url is not None:
            merchant.video_url = data.video_url
        if data.merchant_videos is not None:
            merchant.merchant_videos = data.merchant_videos
        if data.verification_documents is not None:
            merchant.verification_documents = data.verification_documents

        # Status & Services
        if data.services is not None:
            merchant.services = data.services
        if data.service_timing is not None:
            merchant.service_timing = data.service_timing.strip()
        if data.status is not None:
            merchant.status = data.status.strip().upper()
            if merchant.status in ("APPROVED", "ACTIVE"):
                merchant.approval_status = "APPROVED"
                merchant.is_verified = True
                merchant.is_active = True
            elif merchant.status in ("REJECTED", "SUSPENDED", "INACTIVE"):
                merchant.is_active = False

        if data.password is not None:
            MerchantService._set_merchant_password(merchant, data.password)
            user = db.query(User).filter(User.id == merchant.user_id).first()
            if user:
                user.password_hash = merchant.password_hash

        if data.cashback_percent is not None:
            merchant.cashback_percent = data.cashback_percent
        if data.company_fee_percent is not None:
            merchant.company_fee_percent = data.company_fee_percent

        db.commit()
        db.refresh(merchant)
        return merchant

    @staticmethod
    def delete_merchant(db: Session, merchant_id: int) -> bool:
        merchant = db.query(MerchantProfile).filter(MerchantProfile.id == merchant_id).first()
        if not merchant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Merchant with ID {merchant_id} not found.",
            )
        db.delete(merchant)
        db.commit()
        return True

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
        current_user: Optional[User] = None,
        user_code: Optional[str] = None,
        scope_to_current_user: bool = False,
    ) -> List[MerchantProfile]:
        """
        Public approved catalog for GET /merchants (guest or any logged-in user).
        scope_to_current_user=True only for GET /my-merchants (field staff / owner list).
        """
        scoped = scope_to_current_user
        items, _ = MerchantService.search_merchants(
            db=db,
            category=category,
            location=location,
            skip=skip,
            limit=limit,
            public_only=not scoped,
            current_user=current_user if scoped else None,
            user_id=current_user.id if (scoped and current_user) else None,
            user_code=user_code,
        )
        return items

    # ── Password Login ───────────────────────────────────────────────────────

    @staticmethod
    def authenticate_merchant_login(
        db: Session, login_data: UserLoginRequest
    ) -> TokenResponse:
        from app.services.auth_service import AuthService

        merchant, user = MerchantService.resolve_merchant_by_email(db, login_data.email)
        if not merchant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No merchant account found with this email address.",
            )

        if not merchant.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Merchant account is inactive. Please contact support.",
            )

        if not merchant.password_hash:
            raise MerchantService._password_setup_required_exception()

        if not verify_password(login_data.password, merchant.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not user:
            user = db.query(User).filter(User.id == merchant.user_id).first()
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Merchant account is inactive. Please contact support.",
            )

        return AuthService.generate_token_pair(user)

    # ── OTP Login ───────────────────────────────────────────────────────────

    @staticmethod
    def send_login_otp(
        db: Session, email: Optional[str] = None, phone: Optional[str] = None
    ) -> Optional[str]:
        """
        Step 1 of OTP login for merchants.
        Validates that the email or phone belongs to an active MERCHANT account,
        then generates and dispatches a MERCHANT_LOGIN OTP.
        """
        from app.services.auth_service import AuthService

        merchant = None
        user = None
        target_identifier = None

        if email:
            clean_email = email.strip().lower()
            target_identifier = clean_email
            merchant, user = MerchantService.resolve_merchant_by_email(db, clean_email)
        elif phone:
            target_identifier = AuthService.normalize_phone(phone)
            user = AuthService.find_user_by_phone(db, phone)
            if user:
                merchant = (
                    db.query(MerchantProfile)
                    .filter(MerchantProfile.user_id == user.id)
                    .first()
                )

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No merchant account found with this email or phone.",
            )

        if not user.is_active or (merchant and not merchant.is_active):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Merchant account is inactive. Please contact support.",
            )

        plain_otp, _ = OTPService.create_otp(
            db=db,
            identifier=target_identifier,
            purpose=OTPPurpose.MERCHANT_LOGIN,
        )
        return plain_otp

    @staticmethod
    def verify_login_otp(
        db: Session, otp: str, email: Optional[str] = None, phone: Optional[str] = None
    ) -> TokenResponse:
        """
        Step 2 of OTP login for merchants.
        Verifies the MERCHANT_LOGIN OTP then returns a JWT access + refresh token pair.
        """
        from app.services.auth_service import AuthService

        target_identifier = None
        if email:
            target_identifier = email.strip().lower()
        elif phone:
            target_identifier = AuthService.normalize_phone(phone)

        if not target_identifier:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Provide either email or phone",
            )

        # Verify OTP (raises HTTPException on failure)
        OTPService.verify_otp(
            db=db,
            identifier=target_identifier,
            otp=otp,
            purpose=OTPPurpose.MERCHANT_LOGIN,
        )

        user = None
        if email:
            _, user = MerchantService.resolve_merchant_by_email(db, target_identifier)
        elif phone:
            user = AuthService.find_user_by_phone(db, phone)

        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Merchant account not found or inactive.",
            )

        return AuthService.generate_token_pair(user)

    @staticmethod
    def attach_media(
        db: Session,
        merchant_id: int,
        photos: Optional[List[str]] = None,
        videos: Optional[List[str]] = None,
        documents: Optional[List[str]] = None,
    ) -> MerchantProfile:
        merchant = MerchantService.get_merchant_by_id(db=db, merchant_id=merchant_id)

        if photos:
            cur_photos = list(merchant.merchant_photos or [])
            cur_photos.extend(photos)
            merchant.merchant_photos = cur_photos

        if videos:
            cur_videos = list(merchant.merchant_videos or [])
            cur_videos.extend(videos)
            merchant.merchant_videos = cur_videos

        if documents:
            cur_docs = list(merchant.verification_documents or [])
            cur_docs.extend(documents)
            merchant.verification_documents = cur_docs

        db.commit()
        db.refresh(merchant)
        return merchant

    @staticmethod
    def get_region_metadata(db: Session) -> dict:
        """
        Returns structured lists of districts, cities, and locations.
        Includes database values plus well-known regions for seamless dropdown autocomplete.
        """
        db_districts = [
            d[0]
            for d in db.query(MerchantProfile.district)
            .filter(MerchantProfile.district.isnot(None))
            .distinct()
            if d[0]
        ]
        db_cities = [
            c[0]
            for c in db.query(MerchantProfile.city)
            .filter(MerchantProfile.city.isnot(None))
            .distinct()
            if c[0]
        ]
        db_locations = [
            l[0]
            for l in db.query(MerchantProfile.location)
            .filter(MerchantProfile.location.isnot(None))
            .distinct()
            if l[0]
        ]

        preset_districts = [
            "Bangalore Urban",
            "Bangalore Rural",
            "Ernakulam",
            "Thiruvananthapuram",
            "Kozhikode",
            "Thrissur",
            "Kannur",
            "Kollam",
            "Alappuzha",
            "Kottayam",
            "Palakkad",
            "Malappuram",
            "Wayanad",
            "Idukki",
            "Kasaragod",
            "Pathanamthitta",
        ]
        preset_cities = [
            "Bangalore",
            "Kochi",
            "Thiruvananthapuram",
            "Kozhikode",
            "Thrissur",
            "Kannur",
            "Kollam",
            "Alappuzha",
            "Kottayam",
            "Palakkad",
            "Malappuram",
            "Kalpetta",
            "Sulthan Bathery",
        ]
        preset_locations = [
            "Indiranagar",
            "Koramangala",
            "Whitefield",
            "HSR Layout",
            "Jayanagar",
            "MG Road",
            "Edappally",
            "Kaloor",
            "Marine Drive",
            "Palarivattom",
            "Vyttila",
            "Panampilly Nagar",
            "Fort Kochi",
            "Kakkanad",
            "Mananchira",
            "East Hill",
            "Kowdiar",
            "Pattom",
        ]

        districts = sorted(list(set(db_districts + preset_districts)))
        cities = sorted(list(set(db_cities + preset_cities)))
        locations = sorted(list(set(db_locations + preset_locations)))

        return {
            "districts": districts,
            "cities": cities,
            "locations": locations,
        }
