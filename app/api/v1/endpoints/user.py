from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models.user import User, UserRole
from app.schemas.auth import SafeUserResponse
from app.schemas.response import (
    StandardListResponse,
    StandardResponse,
    list_response,
    success_response,
)

router = APIRouter(prefix="/users", tags=["Users"])


@router.get(
    "",
    response_model=StandardListResponse[SafeUserResponse],
    summary="List users",
    description="Returns a paginated list of users with optional filtering by role, status, verification, or keyword search.",
)
def list_users(
    search: Optional[str] = Query(None, description="Search keyword in user name, email, or phone"),
    role: Optional[UserRole] = Query(None, description="Filter by user role: ADMIN, MERCHANT, PUBLIC_USER"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    is_verified: Optional[bool] = Query(None, description="Filter by email verification status"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
) -> StandardListResponse[SafeUserResponse]:
    query = db.query(User)

    if role is not None:
        query = query.filter(User.role == role)

    if is_active is not None:
        query = query.filter(User.is_active == is_active)

    if is_verified is not None:
        query = query.filter(User.is_verified == is_verified)

    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                User.name.ilike(term),
                User.email.ilike(term),
                User.phone.ilike(term),
            )
        )

    total = query.count()
    skip = (page - 1) * page_size
    users = query.order_by(User.created_at.desc()).offset(skip).limit(page_size).all()

    return list_response(
        data=[SafeUserResponse.model_validate(u) for u in users],
        total_items=total,
        page=page,
        page_size=page_size,
        message=f"Retrieved {len(users)} user(s)",
    )


@router.get(
    "/{user_id}",
    response_model=StandardResponse[SafeUserResponse],
    summary="Get user details by ID",
    description="Returns safe profile details of a specific user by their ID.",
)
def get_user_by_id(
    user_id: int,
    db: Session = Depends(get_db),
) -> StandardResponse[SafeUserResponse]:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found.",
        )

    return success_response(
        data=SafeUserResponse.model_validate(user),
        message="User details retrieved successfully",
    )
