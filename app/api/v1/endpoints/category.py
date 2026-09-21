from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.db.database import get_db
from app.db.models.user import User
from app.schemas.auth import GenericMessageResponse
from app.schemas.category import (
    CategoryCreateRequest,
    CategoryListResponse,
    CategoryResponse,
    CategoryUpdateRequest,
)
from app.services.category_service import CategoryService

router = APIRouter(prefix="/categories", tags=["Logo Categories"])


@router.get(
    "",
    response_model=CategoryListResponse,
    summary="List all logo categories",
    description="Returns all active logo categories along with the count of approved logos in each category.",
)
def list_categories(
    include_inactive: bool = Query(False, description="Include inactive categories (Admin only or preview)"),
    db: Session = Depends(get_db),
) -> CategoryListResponse:
    return CategoryService.list_categories(db=db, include_inactive=include_inactive)


@router.get(
    "/{id_or_slug}",
    response_model=CategoryResponse,
    summary="Get category details",
    description="Retrieve a single logo category by its integer ID or unique slug string.",
)
def get_category(
    id_or_slug: str,
    db: Session = Depends(get_db),
) -> CategoryResponse:
    category = CategoryService.get_category_by_id_or_slug(db=db, identifier=id_or_slug)
    return CategoryService.build_category_response(db=db, category=category)


@router.post(
    "",
    response_model=CategoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create category (Admin only)",
    description="Creates a new category for logos. Requires administrator authentication.",
)
def create_category(
    data: CategoryCreateRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> CategoryResponse:
    return CategoryService.create_category(db=db, data=data)


@router.patch(
    "/{category_id}",
    response_model=CategoryResponse,
    summary="Update category (Admin only)",
    description="Updates existing category metadata, slug, or active state. Requires administrator authentication.",
)
def update_category(
    category_id: int,
    data: CategoryUpdateRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> CategoryResponse:
    return CategoryService.update_category(db=db, category_id=category_id, data=data)


@router.delete(
    "/{category_id}",
    response_model=GenericMessageResponse,
    summary="Delete category (Admin only)",
    description="Deletes a category and unlinks logos previously assigned to it. Requires administrator authentication.",
)
def delete_category(
    category_id: int,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> GenericMessageResponse:
    CategoryService.delete_category(db=db, category_id=category_id)
    return GenericMessageResponse(message=f"Category {category_id} successfully deleted.")
