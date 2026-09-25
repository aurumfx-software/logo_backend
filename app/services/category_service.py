import re
from typing import Optional
from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models.logo import Logo, LogoCategory, LogoStatus
from app.schemas.category import (
    CategoryCreateRequest,
    CategoryListResponse,
    CategoryResponse,
    CategoryUpdateRequest,
)


def slugify(text: str) -> str:
    """Convert text to URL-friendly lowercase slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text.strip("-")


class CategoryService:
    @staticmethod
    def get_category_by_id_or_slug(db: Session, identifier: str) -> LogoCategory:
        """Fetch category by either integer ID or unique slug string."""
        category = None
        if identifier.isdigit():
            category = db.query(LogoCategory).filter(LogoCategory.id == int(identifier)).first()
        if not category:
            category = db.query(LogoCategory).filter(LogoCategory.slug == identifier).first()

        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Category '{identifier}' not found.",
            )
        return category

    @staticmethod
    def build_category_response(db: Session, category: LogoCategory) -> CategoryResponse:
        """Build CategoryResponse with approved logo count."""
        logo_count = (
            db.query(func.count(Logo.id))
            .filter(Logo.category_id == category.id, Logo.status == LogoStatus.APPROVED)
            .scalar()
            or 0
        )
        return CategoryResponse(
            id=category.id,
            name=category.name,
            category_name=category.name,
            slug=category.slug,
            description=category.description,
            icon=category.icon_url,
            icon_url=category.icon_url,
            is_active=category.is_active,
            status="Active" if category.is_active else "Inactive",
            logo_count=logo_count,
            created_at=category.created_at,
            updated_at=category.updated_at,
        )

    @classmethod
    def list_categories(
        cls, db: Session, include_inactive: bool = False
    ) -> CategoryListResponse:
        """List categories with active count and logo counts."""
        query = db.query(LogoCategory)
        if not include_inactive:
            query = query.filter(LogoCategory.is_active.is_(True))

        categories = query.order_by(LogoCategory.name.asc()).all()
        items = [cls.build_category_response(db, cat) for cat in categories]
        return CategoryListResponse(items=items, total=len(items))

    @classmethod
    def create_category(
        cls, db: Session, data: CategoryCreateRequest
    ) -> CategoryResponse:
        """Create a new logo category with unique name and slug."""
        clean_name = data.name.strip()
        slug = data.slug.strip().lower() if data.slug else slugify(clean_name)

        if not slug:
            slug = slugify(clean_name)

        # Check uniqueness of name
        existing_name = db.query(LogoCategory).filter(LogoCategory.name.ilike(clean_name)).first()
        if existing_name:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Category with name '{clean_name}' already exists.",
            )

        # Check uniqueness of slug
        existing_slug = db.query(LogoCategory).filter(LogoCategory.slug == slug).first()
        if existing_slug:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Category with slug '{slug}' already exists.",
            )

        category = LogoCategory(
            name=clean_name,
            slug=slug,
            description=data.description.strip() if data.description else None,
            icon_url=data.icon_url.strip() if data.icon_url else None,
            is_active=data.is_active,
        )
        db.add(category)
        db.commit()
        db.refresh(category)
        return cls.build_category_response(db, category)

    @classmethod
    def update_category(
        cls, db: Session, category_id: int, data: CategoryUpdateRequest
    ) -> CategoryResponse:
        """Update category fields."""
        category = db.query(LogoCategory).filter(LogoCategory.id == category_id).first()
        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Category with ID {category_id} not found.",
            )

        if data.name is not None:
            clean_name = data.name.strip()
            existing = (
                db.query(LogoCategory)
                .filter(LogoCategory.name.ilike(clean_name), LogoCategory.id != category_id)
                .first()
            )
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Category with name '{clean_name}' already exists.",
                )
            category.name = clean_name

        if data.slug is not None:
            clean_slug = data.slug.strip().lower()
            existing = (
                db.query(LogoCategory)
                .filter(LogoCategory.slug == clean_slug, LogoCategory.id != category_id)
                .first()
            )
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Category with slug '{clean_slug}' already exists.",
                )
            category.slug = clean_slug

        if data.description is not None:
            category.description = data.description.strip() if data.description else None
        if data.icon_url is not None:
            category.icon_url = data.icon_url.strip() if data.icon_url else None
        if data.is_active is not None:
            category.is_active = data.is_active

        db.commit()
        db.refresh(category)
        return cls.build_category_response(db, category)

    @classmethod
    def delete_category(cls, db: Session, category_id: int) -> None:
        """Delete category and detach logos."""
        category = db.query(LogoCategory).filter(LogoCategory.id == category_id).first()
        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Category with ID {category_id} not found.",
            )

        # Nullify foreign keys on logos before deletion
        db.query(Logo).filter(Logo.category_id == category_id).update(
            {"category_id": None}, synchronize_session=False
        )
        db.delete(category)
        db.commit()
