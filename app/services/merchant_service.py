from typing import List, Optional, Tuple
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.models.merchant import MerchantProfile
from app.db.models.otp import OTPPurpose
from app.db.models.user import User, UserRole
from app.schemas.merchant import MerchantRegisterRequest, MerchantUpdateRequest
from app.schemas.auth import TokenResponse
from app.services.otp_service import OTPService


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
            role=UserRole.FIELD_STAFF,
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
            db.query(MerchantProfile).filter(MerchantProfile.user_id == user_id).first()
        )
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
        merchant.is_verified = True
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
    ) -> Tuple[List[MerchantProfile], int]:
        q = db.query(MerchantProfile).join(User, MerchantProfile.user_id == User.id)

        if public_only:
            # Public discovery: only active users and approved merchants
            q = q.filter(
                MerchantProfile.is_active == True,
                User.is_active == True,
                MerchantProfile.approval_status == "APPROVED",
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
            cat_clean = category.strip().lower()
            filtered = [
                m for m in filtered
                if any(cat_clean in str(c).lower() for c in (m.categories or []))
            ]

        if query:
            kw = query.strip().lower()
            filtered = [
                m for m in filtered
                if kw in m.business_name.lower()
                or kw in m.location.lower()
                or kw in m.address.lower()
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

    # ── OTP Login ───────────────────────────────────────────────────────────

    @staticmethod
    def send_login_otp(db: Session, email: str) -> Optional[str]:
        """
        Step 1 of OTP login.
        Validates that the email belongs to an active MERCHANT account,
        then generates and dispatches a MERCHANT_LOGIN OTP.
        Returns the plain OTP in development; None in production.
        """
        clean_email = email.strip().lower()
        user = db.query(User).filter(User.email == clean_email).first()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No account found with this email address.",
            )

        merchant = db.query(MerchantProfile).filter(MerchantProfile.user_id == user.id).first()
        if not merchant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="This account does not have an associated merchant profile.",
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Merchant account is inactive. Please contact support.",
            )

        plain_otp, _ = OTPService.create_otp(
            db=db,
            identifier=clean_email,
            purpose=OTPPurpose.MERCHANT_LOGIN,
        )
        return plain_otp

    @staticmethod
    def verify_login_otp(db: Session, email: str, otp: str) -> TokenResponse:
        """
        Step 2 of OTP login.
        Verifies the MERCHANT_LOGIN OTP then returns a JWT access + refresh token pair.
        """
        # Import here to avoid circular imports
        from app.services.auth_service import AuthService

        clean_email = email.strip().lower()

        # Verify OTP (raises HTTPException on failure)
        OTPService.verify_otp(
            db=db,
            identifier=clean_email,
            otp=otp,
            purpose=OTPPurpose.MERCHANT_LOGIN,
        )

        user = db.query(User).filter(User.email == clean_email).first()
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Merchant account not found or inactive.",
            )

        return AuthService.generate_token_pair(user)
