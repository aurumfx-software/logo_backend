from datetime import datetime, timezone
from typing import List, Optional, Set
from fastapi import HTTPException, status
from sqlalchemy import String, cast, desc, func, or_
from sqlalchemy.orm import Session

from app.db.models.logo import Logo, LogoCategory, LogoFavorite, LogoStatus
from app.db.models.user import User, UserRole
from app.schemas.favorite import FavoriteCheckResponse, FavoriteListResponse, FavoriteToggleResponse
from app.schemas.logo import (
    LogoCategoryBrief,
    LogoCreateRequest,
    LogoListResponse,
    LogoResponse,
    LogoUpdateRequest,
    LogoUserBrief,
)


class LogoService:
    @staticmethod
    def _build_logo_response(
        logo: Logo,
        is_favorite: bool = False,
    ) -> LogoResponse:
        """Helper to construct standard LogoResponse with relationships."""
        category_brief = None
        if logo.category:
            category_brief = LogoCategoryBrief(
                id=logo.category.id,
                name=logo.category.name,
                slug=logo.category.slug,
            )

        submitter_brief = None
        if logo.submitted_by:
            submitter_brief = LogoUserBrief(
                id=logo.submitted_by.id,
                name=logo.submitted_by.name,
                email=logo.submitted_by.email,
                role=logo.submitted_by.role.value if hasattr(logo.submitted_by.role, "value") else str(logo.submitted_by.role),
            )

        return LogoResponse(
            id=logo.id,
            title=logo.title,
            description=logo.description,
            image_url=logo.image_url,
            tags=logo.tags if isinstance(logo.tags, list) else [],
            category_id=logo.category_id,
            category=category_brief,
            submitted_by_id=logo.submitted_by_id,
            submitted_by=submitter_brief,
            status=logo.status.value if hasattr(logo.status, "value") else str(logo.status),
            rejection_reason=logo.rejection_reason,
            reviewed_by_id=logo.reviewed_by_id,
            reviewed_at=logo.reviewed_at,
            views_count=logo.views_count,
            favorites_count=logo.favorites_count,
            is_favorite=is_favorite,
            created_at=logo.created_at,
            updated_at=logo.updated_at,
        )

    @classmethod
    def search_logos(
        cls,
        db: Session,
        q: Optional[str] = None,
        category_id: Optional[int] = None,
        category_slug: Optional[str] = None,
        tag: Optional[str] = None,
        logo_status: Optional[str] = None,
        submitted_by_id: Optional[int] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        skip: int = 0,
        limit: int = 20,
        current_user: Optional[User] = None,
    ) -> LogoListResponse:
        """Search and filter logos with RBAC, text query, sorting and pagination."""
        query = db.query(Logo)

        # 1. RBAC on status:
        is_admin = current_user is not None and current_user.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN)
        if is_admin:
            if logo_status:
                try:
                    status_enum = LogoStatus(logo_status.upper())
                    query = query.filter(Logo.status == status_enum)
                except ValueError:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Invalid logo status: '{logo_status}'.",
                    )
        else:
            # Non-admin / public users:
            if submitted_by_id and current_user and current_user.id == submitted_by_id:
                # Users can view their own submissions regardless of status
                query = query.filter(Logo.submitted_by_id == submitted_by_id)
                if logo_status:
                    try:
                        status_enum = LogoStatus(logo_status.upper())
                        query = query.filter(Logo.status == status_enum)
                    except ValueError:
                        pass
            else:
                # Publicly only APPROVED logos are visible
                query = query.filter(Logo.status == LogoStatus.APPROVED)

        # 2. Submitter filter
        if submitted_by_id and is_admin:
            query = query.filter(Logo.submitted_by_id == submitted_by_id)

        # 3. Category filtering
        if category_id:
            query = query.filter(Logo.category_id == category_id)
        elif category_slug:
            query = query.join(Logo.category).filter(LogoCategory.slug == category_slug.lower())

        # 4. Keyword search across title, description, and tags
        if q and q.strip():
            clean_q = q.strip()
            pattern = f"%{clean_q}%"
            query = query.filter(
                or_(
                    Logo.title.ilike(pattern),
                    Logo.description.ilike(pattern),
                    cast(Logo.tags, String).ilike(pattern),
                )
            )

        # 5. Tag filtering
        if tag and tag.strip():
            clean_tag = tag.strip().lower()
            query = query.filter(cast(Logo.tags, String).ilike(f"%{clean_tag}%"))

        # 6. Sorting
        sort_column_map = {
            "created_at": Logo.created_at,
            "views_count": Logo.views_count,
            "favorites_count": Logo.favorites_count,
            "title": Logo.title,
        }
        sort_col = sort_column_map.get(sort_by, Logo.created_at)
        if sort_order.lower() == "asc":
            query = query.order_by(sort_col.asc())
        else:
            query = query.order_by(sort_col.desc())

        total = query.count()
        logos = query.offset(skip).limit(limit).all()

        # Batch lookup user favorites if current_user is authenticated
        fav_logo_ids: Set[int] = set()
        if current_user and logos:
            logo_ids = [logo.id for logo in logos]
            favs = (
                db.query(LogoFavorite.logo_id)
                .filter(
                    LogoFavorite.user_id == current_user.id,
                    LogoFavorite.logo_id.in_(logo_ids),
                )
                .all()
            )
            fav_logo_ids = {f[0] for f in favs}

        items = [cls._build_logo_response(logo, is_favorite=(logo.id in fav_logo_ids)) for logo in logos]
        return LogoListResponse(items=items, total=total, skip=skip, limit=limit)

    @classmethod
    def get_logo_by_id(
        cls,
        db: Session,
        logo_id: int,
        current_user: Optional[User] = None,
        increment_view: bool = True,
    ) -> LogoResponse:
        """Fetch single logo, checking RBAC visibility and updating view count."""
        logo = db.query(Logo).filter(Logo.id == logo_id).first()
        if not logo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Logo with ID {logo_id} not found.",
            )

        # RBAC visibility check:
        is_admin = current_user is not None and current_user.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN)
        is_owner = current_user is not None and current_user.id == logo.submitted_by_id

        if logo.status != LogoStatus.APPROVED and not is_admin and not is_owner:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This logo is pending approval and is not publicly visible.",
            )

        # Increment view count if viewed publicly
        if increment_view and logo.status == LogoStatus.APPROVED:
            logo.views_count += 1
            db.commit()
            db.refresh(logo)

        is_fav = False
        if current_user:
            is_fav = (
                db.query(LogoFavorite)
                .filter(LogoFavorite.user_id == current_user.id, LogoFavorite.logo_id == logo.id)
                .first()
                is not None
            )

        return cls._build_logo_response(logo, is_favorite=is_fav)

    @classmethod
    def create_logo(
        cls,
        db: Session,
        current_user: User,
        data: LogoCreateRequest,
    ) -> LogoResponse:
        """Submit a new logo for moderation."""
        if data.category_id:
            category = db.query(LogoCategory).filter(LogoCategory.id == data.category_id).first()
            if not category or not category.is_active:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid or inactive category ID {data.category_id}.",
                )

        clean_tags = [t.strip().lower() for t in data.tags if t and t.strip()] if data.tags else []

        logo = Logo(
            title=data.title.strip(),
            description=data.description.strip() if data.description else None,
            image_url=data.image_url.strip(),
            tags=clean_tags,
            category_id=data.category_id,
            submitted_by_id=current_user.id,
            status=LogoStatus.PENDING,
            views_count=0,
            favorites_count=0,
        )
        db.add(logo)
        db.commit()
        db.refresh(logo)
        return cls._build_logo_response(logo, is_favorite=False)

    @classmethod
    def update_logo(
        cls,
        db: Session,
        current_user: User,
        logo_id: int,
        data: LogoUpdateRequest,
    ) -> LogoResponse:
        """Update logo. If edited by non-admin owner, resets status to PENDING."""
        logo = db.query(Logo).filter(Logo.id == logo_id).first()
        if not logo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Logo with ID {logo_id} not found.",
            )

        is_admin = current_user.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN)
        is_owner = current_user.id == logo.submitted_by_id

        if not is_admin and not is_owner:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to modify this logo.",
            )

        if data.category_id is not None:
            if data.category_id > 0:
                category = db.query(LogoCategory).filter(LogoCategory.id == data.category_id).first()
                if not category:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Category ID {data.category_id} not found.",
                    )
                logo.category_id = data.category_id
            else:
                logo.category_id = None

        if data.title is not None:
            logo.title = data.title.strip()
        if data.description is not None:
            logo.description = data.description.strip() if data.description else None
        if data.image_url is not None:
            logo.image_url = data.image_url.strip()
        if data.tags is not None:
            logo.tags = [t.strip().lower() for t in data.tags if t and t.strip()]

        # If modified by submitter, set back to PENDING for moderation re-review
        if not is_admin:
            logo.status = LogoStatus.PENDING
            logo.rejection_reason = None
            logo.reviewed_by_id = None
            logo.reviewed_at = None

        db.commit()
        db.refresh(logo)
        return cls._build_logo_response(logo)

    @classmethod
    def delete_logo(cls, db: Session, current_user: User, logo_id: int) -> None:
        """Delete logo. Allowed for submitter or admin."""
        logo = db.query(Logo).filter(Logo.id == logo_id).first()
        if not logo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Logo with ID {logo_id} not found.",
            )

        is_admin = current_user.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN)
        is_owner = current_user.id == logo.submitted_by_id

        if not is_admin and not is_owner:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to delete this logo.",
            )

        db.delete(logo)
        db.commit()

    @classmethod
    def approve_logo(cls, db: Session, admin_user: User, logo_id: int) -> LogoResponse:
        """Approve a logo (Admin only)."""
        logo = db.query(Logo).filter(Logo.id == logo_id).first()
        if not logo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Logo with ID {logo_id} not found.",
            )

        logo.status = LogoStatus.APPROVED
        logo.rejection_reason = None
        logo.reviewed_by_id = admin_user.id
        logo.reviewed_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(logo)
        return cls._build_logo_response(logo)

    @classmethod
    def reject_logo(
        cls, db: Session, admin_user: User, logo_id: int, rejection_reason: str
    ) -> LogoResponse:
        """Reject a logo with explanation (Admin only)."""
        logo = db.query(Logo).filter(Logo.id == logo_id).first()
        if not logo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Logo with ID {logo_id} not found.",
            )

        logo.status = LogoStatus.REJECTED
        logo.rejection_reason = rejection_reason.strip()
        logo.reviewed_by_id = admin_user.id
        logo.reviewed_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(logo)
        return cls._build_logo_response(logo)

    @classmethod
    def toggle_favorite(cls, db: Session, user: User, logo_id: int) -> FavoriteToggleResponse:
        """Toggle favorite for the authenticated user and update counter."""
        logo = db.query(Logo).filter(Logo.id == logo_id).first()
        if not logo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Logo with ID {logo_id} not found.",
            )

        existing_fav = (
            db.query(LogoFavorite)
            .filter(LogoFavorite.user_id == user.id, LogoFavorite.logo_id == logo.id)
            .first()
        )

        if existing_fav:
            db.delete(existing_fav)
            if logo.favorites_count > 0:
                logo.favorites_count -= 1
            db.commit()
            db.refresh(logo)
            return FavoriteToggleResponse(
                message="Logo removed from favorites.",
                is_favorite=False,
                logo_id=logo.id,
                favorites_count=logo.favorites_count,
            )
        else:
            new_fav = LogoFavorite(user_id=user.id, logo_id=logo.id)
            db.add(new_fav)
            logo.favorites_count += 1
            db.commit()
            db.refresh(logo)
            return FavoriteToggleResponse(
                message="Logo added to favorites.",
                is_favorite=True,
                logo_id=logo.id,
                favorites_count=logo.favorites_count,
            )

    @classmethod
    def check_favorite(cls, db: Session, user: User, logo_id: int) -> FavoriteCheckResponse:
        """Check if user has favorited this logo."""
        fav = (
            db.query(LogoFavorite)
            .filter(LogoFavorite.user_id == user.id, LogoFavorite.logo_id == logo_id)
            .first()
        )
        return FavoriteCheckResponse(logo_id=logo_id, is_favorite=fav is not None)

    @classmethod
    def list_user_favorites(
        cls, db: Session, user: User, skip: int = 0, limit: int = 20
    ) -> FavoriteListResponse:
        """List all logos favorited by the current user."""
        query = (
            db.query(Logo)
            .join(LogoFavorite, LogoFavorite.logo_id == Logo.id)
            .filter(LogoFavorite.user_id == user.id)
            .order_by(LogoFavorite.created_at.desc())
        )
        total = query.count()
        logos = query.offset(skip).limit(limit).all()

        items = [cls._build_logo_response(logo, is_favorite=True) for logo in logos]
        return FavoriteListResponse(items=items, total=total, skip=skip, limit=limit)
