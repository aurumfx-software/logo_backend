import os
import shutil
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import require_admin, require_field_staff_or_admin
from app.db.database import get_db
from app.db.models.user import User
from app.schemas.auth import GenericMessageResponse
from app.schemas.category import (
    CategoryCreateRequest,
    CategoryIconUploadResponse,
    CategoryListResponse,
    CategoryResponse,
    CategoryUpdateRequest,
)
from app.services.category_service import CategoryService

router = APIRouter(prefix="/categories", tags=["Logo Categories"])

ALLOWED_ICON_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".svg", ".ico"}


@router.get(
    "",
    response_model=CategoryListResponse,
    summary="List all logo categories",
    description="Returns all active logo categories along with the count of approved logos in each category.",
)
def list_categories(
    include_inactive: bool = Query(False, description="Include inactive categories (Admin or field staff preview)"),
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
    summary="Create category (Field Staff or Admin)",
    description=(
        "Creates a new category with Category Name, Icon (emoji or PNG URL/path), and status (Active/Inactive). "
        "Accessible to Field Staff, Admin, and Super Admin."
    ),
)
@router.post(
    "/add",
    response_model=CategoryResponse,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
def create_category(
    data: CategoryCreateRequest,
    current_user: User = Depends(require_field_staff_or_admin),
    db: Session = Depends(get_db),
) -> CategoryResponse:
    return CategoryService.create_category(db=db, data=data)


@router.post(
    "/upload-icon",
    response_model=CategoryIconUploadResponse,
    summary="Upload category icon image (PNG, SVG, JPG)",
    description="Uploads an icon image for a category and returns its static URL.",
)
def upload_category_icon(
    file: UploadFile = File(..., description="Icon file (PNG, SVG, JPG, WEBP)"),
    current_user: User = Depends(require_field_staff_or_admin),
) -> CategoryIconUploadResponse:
    ext = os.path.splitext(file.filename)[1].lower() if file.filename else ""
    if ext not in ALLOWED_ICON_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid icon format. Allowed formats: {', '.join(sorted(ALLOWED_ICON_EXTENSIONS))}",
        )

    upload_dir = os.path.join("uploads", "categories", "icons")
    os.makedirs(upload_dir, exist_ok=True)

    unique_name = f"{uuid.uuid4().hex}{ext}"
    dest_path = os.path.join(upload_dir, unique_name)
    with open(dest_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    icon_url = f"/static/categories/icons/{unique_name}"
    return CategoryIconUploadResponse(
        message="Category icon uploaded successfully",
        icon_url=icon_url,
    )


@router.post(
    "/form",
    response_model=CategoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create category via form data with optional icon upload",
    description="Create category via multipart/form-data. Supports uploading an icon PNG directly or providing an emoji/URL.",
)
def create_category_form(
    name: Optional[str] = Form(None),
    category_name: Optional[str] = Form(None),
    icon: Optional[str] = Form(None, description="Icon emoji or icon URL"),
    status: Optional[str] = Form("Active", description="Active or Inactive"),
    description: Optional[str] = Form(None),
    icon_file: Optional[UploadFile] = File(None, description="Optional icon PNG, SVG, or JPG file"),
    current_user: User = Depends(require_field_staff_or_admin),
    db: Session = Depends(get_db),
) -> CategoryResponse:
    final_icon = icon

    if icon_file and icon_file.filename:
        ext = os.path.splitext(icon_file.filename)[1].lower()
        if ext not in ALLOWED_ICON_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid icon file format. Allowed: {', '.join(sorted(ALLOWED_ICON_EXTENSIONS))}",
            )
        upload_dir = os.path.join("uploads", "categories", "icons")
        os.makedirs(upload_dir, exist_ok=True)
        unique_name = f"{uuid.uuid4().hex}{ext}"
        dest_path = os.path.join(upload_dir, unique_name)
        with open(dest_path, "wb") as buffer:
            shutil.copyfileobj(icon_file.file, buffer)
        final_icon = f"/static/categories/icons/{unique_name}"

    req = CategoryCreateRequest(
        name=name or category_name,
        category_name=category_name or name,
        icon=final_icon,
        icon_url=final_icon,
        status=status,
        description=description,
    )
    return CategoryService.create_category(db=db, data=req)


@router.patch(
    "/{category_id}",
    response_model=CategoryResponse,
    summary="Update category (Field Staff or Admin)",
    description="Updates existing category metadata, icon, slug, or active state. Requires field staff or admin authentication.",
)
def update_category(
    category_id: int,
    data: CategoryUpdateRequest,
    current_user: User = Depends(require_field_staff_or_admin),
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
