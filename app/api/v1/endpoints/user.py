from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_optional
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
    description="Returns a paginated list of users with optional filtering by role, status, verification, or keyword search. Accessible to Super Admin, Admin, and Users.",
)
def list_users(
    search: Optional[str] = Query(None, description="Search keyword in user name, email, or phone"),
    role: Optional[UserRole] = Query(None, description="Filter by user role: SUPER_ADMIN, ADMIN, FIELD_STAFF"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    is_verified: Optional[bool] = Query(None, description="Filter by email verification status"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    sort: str = Query("asc", description="Sort order by user ID: 'asc' (1, 2, 3...) or 'desc' (7, 6, 5...)"),
    current_user: Optional[User] = Depends(get_current_user_optional),
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
        term = search.strip()
        search_pat = f"%{term}%"
        search_filters = [
            User.name.ilike(search_pat),
            User.email.ilike(search_pat),
            User.phone.ilike(search_pat),
            User.user_code.ilike(search_pat),
        ]
        if term.isdigit():
            search_filters.append(User.id == int(term))

        query = query.filter(or_(*search_filters))

    total = query.count()
    skip = (page - 1) * page_size
    order_clause = User.id.desc() if sort and sort.lower() == "desc" else User.id.asc()
    users = query.order_by(order_clause).offset(skip).limit(page_size).all()

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
    summary="Get user details by ID or user code",
    description="Returns safe profile details of a specific user by their ID or user code (e.g. 1, ADM_1, FLS_1, SAD_1). Accessible to Super Admin, Admin, and Users.",
)
def get_user_by_id(
    user_id: str,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> StandardResponse[SafeUserResponse]:
    clean_id = user_id.strip()
    query_filters = [User.user_code.ilike(clean_id)]
    if clean_id.isdigit():
        query_filters.append(User.id == int(clean_id))

    user = db.query(User).filter(or_(*query_filters)).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID or code '{user_id}' not found.",
        )

    return success_response(
        data=SafeUserResponse.model_validate(user),
        message="User details retrieved successfully",
    )
