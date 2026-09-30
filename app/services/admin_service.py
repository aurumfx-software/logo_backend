from datetime import datetime, timezone
from typing import Optional
from fastapi import HTTPException, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.models.logo import Logo, LogoCategory, LogoFavorite, LogoStatus
from app.db.models.merchant import MerchantProfile
from app.db.models.user import User, UserRole
from app.schemas.admin import (
    AdminCategoryDistributionItem,
    AdminDashboardStats,
    AdminUserCreateRequest,
    AdminUserDetailResponse,
    AdminUserListItem,
    AdminUserListResponse,
    AdminUserUpdateRequest,
)
from app.schemas.auth import SafeUserResponse
from app.services.logo_service import LogoService


class AdminService:
    @staticmethod
    def get_dashboard_stats(db: Session) -> AdminDashboardStats:
        """Aggregate platform metrics, user counts, logo statuses, and recent activities."""
        # 1. User counts
        total_users = db.query(func.count(User.id)).scalar() or 0
        total_merchants = db.query(func.count(MerchantProfile.id)).scalar() or 0
        total_field_staff = (
            db.query(func.count(User.id)).filter(User.role == UserRole.FIELD_STAFF).scalar() or 0
        )
        total_admins = (
            db.query(func.count(User.id))
            .filter(User.role.in_([UserRole.ADMIN, UserRole.SUPER_ADMIN]))
            .scalar()
            or 0
        )
        active_users = (
            db.query(func.count(User.id)).filter(User.is_active.is_(True)).scalar() or 0
        )

        # 2. Logo counts
        total_logos = db.query(func.count(Logo.id)).scalar() or 0
        approved_logos = (
            db.query(func.count(Logo.id)).filter(Logo.status == LogoStatus.APPROVED).scalar() or 0
        )
        pending_logos = (
            db.query(func.count(Logo.id)).filter(Logo.status == LogoStatus.PENDING).scalar() or 0
        )
        rejected_logos = (
            db.query(func.count(Logo.id)).filter(Logo.status == LogoStatus.REJECTED).scalar() or 0
        )

        # 3. Overall platform metrics
        total_categories = db.query(func.count(LogoCategory.id)).scalar() or 0
        total_views = db.query(func.sum(Logo.views_count)).scalar() or 0
        total_favorites = db.query(func.count(LogoFavorite.id)).scalar() or 0

        # 4. Recent pending logos (awaiting approval)
        pending_query = (
            db.query(Logo)
            .filter(Logo.status == LogoStatus.PENDING)
            .order_by(Logo.created_at.desc())
            .limit(5)
            .all()
        )
        recent_pending_logos = [LogoService._build_logo_response(logo) for logo in pending_query]

        # 5. Recent registered users
        users_query = db.query(User).order_by(User.created_at.desc()).limit(5).all()
        recent_users = [SafeUserResponse.model_validate(u) for u in users_query]

        # 6. Trending logos (approved, sorted by favorites and views)
        trending_query = (
            db.query(Logo)
            .filter(Logo.status == LogoStatus.APPROVED)
            .order_by(Logo.favorites_count.desc(), Logo.views_count.desc())
            .limit(5)
            .all()
        )
        trending_logos = [LogoService._build_logo_response(logo) for logo in trending_query]

        # 7. Category distribution
        categories = db.query(LogoCategory).all()
        category_distribution = []
        for cat in categories:
            count = (
                db.query(func.count(Logo.id))
                .filter(Logo.category_id == cat.id, Logo.status == LogoStatus.APPROVED)
                .scalar()
                or 0
            )
            category_distribution.append(
                AdminCategoryDistributionItem(
                    category_id=cat.id,
                    name=cat.name,
                    slug=cat.slug,
                    logo_count=count,
                )
            )

        return AdminDashboardStats(
            total_users=total_users,
            total_merchants=total_merchants,
            total_field_staff=total_field_staff,
            total_admins=total_admins,
            active_users=active_users,
            total_logos=total_logos,
            approved_logos=approved_logos,
            pending_logos=pending_logos,
            rejected_logos=rejected_logos,
            total_categories=total_categories,
            total_views=total_views,
            total_favorites=total_favorites,
            recent_pending_logos=recent_pending_logos,
            recent_users=recent_users,
            trending_logos=trending_logos,
            category_distribution=category_distribution,
        )

    @classmethod
    def list_users(
        cls,
        db: Session,
        role: Optional[str] = None,
        is_active: Optional[bool] = None,
        search: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
        sort: Optional[str] = "asc",
    ) -> AdminUserListResponse:
        """Search and paginate users with submitted logos and favorite counts."""
        query = db.query(User)

        if role:
            role_clean = role.strip().upper().replace(" ", "_").replace("-", "_")
            if role_clean in ("PUBLIC_USER", "PUBLICUSER", "USER", "FIELDSTAFF"):
                query = query.filter(or_(User.role == UserRole.FIELD_STAFF, User.role == "PUBLIC_USER"))
            else:
                try:
                    role_enum = UserRole(role_clean)
                    query = query.filter(User.role == role_enum)
                except ValueError:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Invalid user role: '{role}'. Allowed roles are: SUPER_ADMIN, ADMIN, FIELD_STAFF.",
                    )

        if is_active is not None:
            query = query.filter(User.is_active == is_active)

        if search and search.strip():
            term = search.strip()
            pat = f"%{term}%"
            search_filters = [
                User.name.ilike(pat),
                User.email.ilike(pat),
                User.phone.ilike(pat),
                User.user_code.ilike(pat),
            ]
            if term.isdigit():
                search_filters.append(User.id == int(term))

            query = query.filter(or_(*search_filters))

        total = query.count()
        order_clause = User.id.desc() if sort and sort.lower() == "desc" else User.id.asc()
        users = query.order_by(order_clause).offset(skip).limit(limit).all()

        items = []
        for u in users:
            sub_count = db.query(func.count(Logo.id)).filter(Logo.submitted_by_id == u.id).scalar() or 0
            fav_count = db.query(func.count(LogoFavorite.id)).filter(LogoFavorite.user_id == u.id).scalar() or 0
            items.append(
                AdminUserListItem(
                    id=u.id,
                    user_code=u.user_code,
                    name=u.name,
                    email=u.email,
                    phone=u.phone,
                    role=u.role,
                    district=u.district,
                    regions=u.regions or [],
                    city=u.city,
                    module_access=u.module_access or [],
                    send_email=bool(u.send_email),
                    status=u.status or ("ACTIVE" if u.is_active else "INACTIVE"),
                    last_active=u.last_active,
                    created_by=u.created_by,
                    is_active=u.is_active,
                    is_suspended=not u.is_active,
                    is_verified=u.is_verified,
                    address=u.address,
                    profile_picture=u.profile_picture,
                    created_at=u.created_at,
                    updated_at=u.updated_at,
                    submitted_logos_count=sub_count,
                    favorite_logos_count=fav_count,
                )
            )

        return AdminUserListResponse(items=items, total=total, skip=skip, limit=limit)

    @classmethod
    def get_user_details(cls, db: Session, user_id: int) -> AdminUserDetailResponse:
        """Fetch detailed information about a single user."""
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with ID {user_id} not found.",
            )

        sub_count = db.query(func.count(Logo.id)).filter(Logo.submitted_by_id == user.id).scalar() or 0
        fav_count = db.query(func.count(LogoFavorite.id)).filter(LogoFavorite.user_id == user.id).scalar() or 0

        merchant_data = None
        merchant_profile = db.query(MerchantProfile).filter(MerchantProfile.user_id == user.id).first()
        if merchant_profile:
            merchant_data = {
                "id": merchant_profile.id,
                "business_name": merchant_profile.business_name,
                "categories": merchant_profile.categories,
                "location": merchant_profile.location,
                "services": merchant_profile.services,
                "service_timing": merchant_profile.service_timing,
                "contact_number": merchant_profile.contact_number,
                "address": merchant_profile.address,
            }

        return AdminUserDetailResponse(
            id=user.id,
            user_code=user.user_code,
            name=user.name,
            email=user.email,
            phone=user.phone,
            role=user.role,
            district=user.district,
            regions=user.regions or [],
            city=user.city,
            module_access=user.module_access or [],
            send_email=bool(user.send_email),
            status=user.status or ("ACTIVE" if user.is_active else "INACTIVE"),
            last_active=user.last_active,
            created_by=user.created_by,
            is_active=user.is_active,
            is_suspended=not user.is_active,
            is_verified=user.is_verified,
            address=user.address,
            profile_picture=user.profile_picture,
            created_at=user.created_at,
            updated_at=user.updated_at,
            submitted_logos_count=sub_count,
            favorite_logos_count=fav_count,
            merchant_profile=merchant_data,
        )

    @classmethod
    def create_user(
        cls,
        db: Session,
        user_data: AdminUserCreateRequest,
        current_admin: Optional[User] = None,
    ) -> User:
        """Create a new user with all 17 fields, including module access array and binary send_email."""
        clean_email = user_data.email.strip().lower()
        existing_email = db.query(User).filter(User.email == clean_email).first()
        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A user with this email already exists.",
            )

        if user_data.phone:
            existing_phone = db.query(User).filter(User.phone == user_data.phone).first()
            if existing_phone:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="A user with this phone number already exists.",
                )

        hashed_pwd = hash_password(user_data.password)
        assigned_role = user_data.role or UserRole.FIELD_STAFF
        creator = user_data.created_by or (current_admin.user_code if current_admin and current_admin.user_code else (current_admin.name if current_admin else None))

        user_status = user_data.status or "ACTIVE"
        is_active = (user_status.upper() != "INACTIVE")

        new_user = User(
            name=user_data.name.strip(),
            email=clean_email,
            phone=user_data.phone,
            password=hashed_pwd,
            password_hash=hashed_pwd,
            role=assigned_role,
            district=user_data.district,
            regions=user_data.regions or [],
            city=user_data.city,
            module_access=user_data.module_access or [],
            send_email=bool(user_data.send_email),
            status=user_status,
            is_active=is_active,
            is_verified=True,
            created_by=creator,
            address=user_data.address,
            profile_picture=user_data.profile_picture,
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return new_user

    @classmethod
    def update_user_role(
        cls, db: Session, user_id: int, new_role: UserRole, current_admin: User
    ) -> AdminUserDetailResponse:
        """Change a user's role, preventing self-demotion."""
        if user_id == current_admin.id and new_role not in (UserRole.ADMIN, UserRole.SUPER_ADMIN):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You cannot demote your own administrator account.",
            )

        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with ID {user_id} not found.",
            )

        user.role = new_role
        db.commit()
        db.refresh(user)
        return cls.get_user_details(db, user_id)

    @classmethod
    def update_user_status(
        cls,
        db: Session,
        user_id: int,
        is_active: Optional[bool] = None,
        current_admin: Optional[User] = None,
        status_text: Optional[str] = None,
        is_suspended: Optional[bool] = None,
    ) -> AdminUserDetailResponse:
        """Activate, deactivate, or suspend a user."""
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with ID {user_id} not found.",
            )

        if current_admin and user_id == current_admin.id and (is_active is False or is_suspended is True):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You cannot deactivate or ban your own administrator account.",
            )

        if is_suspended is not None:
            if is_suspended:
                user.is_active = False
                user.status = "INACTIVE"
            else:
                user.is_active = True
                user.status = "ACTIVE"
        elif is_active is not None:
            user.is_active = is_active
            user.status = "ACTIVE" if is_active else "INACTIVE"

        if status_text:
            s_clean = status_text.strip().lower()
            if s_clean in ("active", "approved", "enabled"):
                user.is_active = True
                user.status = "ACTIVE"
            elif s_clean in ("inactive", "suspended", "banned", "disabled"):
                user.is_active = False
                user.status = "INACTIVE" if s_clean == "inactive" else "SUSPENDED"
            else:
                user.status = status_text.strip().upper()

        db.commit()
        db.refresh(user)
        return cls.get_user_details(db, user_id)

    @classmethod
    def update_user(
        cls,
        db: Session,
        user_id: int,
        data: AdminUserUpdateRequest,
        current_admin: Optional[User] = None,
    ) -> AdminUserDetailResponse:
        """Update user profile, status, active/inactive, or suspended state."""
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with ID {user_id} not found.",
            )

        if current_admin and user_id == current_admin.id:
            if data.is_suspended is True or data.is_active is False:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="You cannot deactivate or ban your own administrator account.",
                )

        # Handle active / inactive / suspended
        if data.is_suspended is not None:
            if data.is_suspended:
                user.is_active = False
                user.status = "INACTIVE"
            else:
                user.is_active = True
                user.status = "ACTIVE"
        elif data.is_active is not None:
            user.is_active = data.is_active
            user.status = "ACTIVE" if data.is_active else "INACTIVE"

        if data.status is not None:
            s_clean = data.status.strip().lower()
            if s_clean in ("active", "approved", "enabled"):
                user.is_active = True
                user.status = "ACTIVE"
            elif s_clean in ("inactive", "suspended", "banned", "disabled"):
                user.is_active = False
                user.status = "INACTIVE" if s_clean == "inactive" else "SUSPENDED"
            else:
                user.status = data.status.strip().upper()

        if data.name is not None and data.name.strip():
            user.name = data.name.strip()
        if data.email is not None and data.email.strip():
            clean_email = data.email.strip().lower()
            if clean_email != user.email:
                existing = db.query(User).filter(User.email == clean_email, User.id != user.id).first()
                if existing:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="A user with this email already exists.",
                    )
                user.email = clean_email
        if data.phone is not None:
            clean_phone = data.phone.strip() if data.phone else None
            if clean_phone and clean_phone != user.phone:
                existing_p = db.query(User).filter(User.phone == clean_phone, User.id != user.id).first()
                if existing_p:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="A user with this phone number already exists.",
                    )
            user.phone = clean_phone
        if data.role is not None:
            user.role = data.role
        if data.district is not None:
            user.district = data.district
        if data.regions is not None:
            user.regions = data.regions
        if data.city is not None:
            user.city = data.city
        if data.module_access is not None:
            user.module_access = data.module_access
        if data.send_email is not None:
            user.send_email = data.send_email
        if data.address is not None:
            user.address = data.address
        if data.profile_picture is not None:
            user.profile_picture = data.profile_picture

        db.commit()
        db.refresh(user)
        return cls.get_user_details(db, user_id)

    @classmethod
    def delete_user(cls, db: Session, user_id: int, current_admin: User) -> None:
        """Delete a user, preventing self-deletion."""
        if user_id == current_admin.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You cannot delete your own administrator account.",
            )

        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with ID {user_id} not found.",
            )

        db.delete(user)
        db.commit()
