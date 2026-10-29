from typing import Optional

from fastapi import APIRouter, Body, Depends, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, security_scheme
from app.db.database import get_db
from app.db.models.user import User
from app.schemas.auth import (
    CustomerRegisterRequest,
    CustomerRegisterResponse,
    LogoutRequest,
    LogoutResponse,
    SafeUserResponse,
)
from app.services.auth_service import AuthService

router = APIRouter(prefix="/customer", tags=["Customer"])


@router.post(
    "/register",
    response_model=CustomerRegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register Logo App customer (mobile)",
    description=(
        "Creates a customer account in the users table (role FIELD_STAFF / public user). "
        "Phone is required; email is optional. Returns JWT tokens for immediate sign-in."
    ),
)
def register_customer(
    data: CustomerRegisterRequest,
    db: Session = Depends(get_db),
) -> CustomerRegisterResponse:
    tokens = AuthService.register_customer(db=db, data=data)
    return CustomerRegisterResponse(
        message="Customer registered successfully",
        user=SafeUserResponse.model_validate(tokens.user),
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        token_type=tokens.token_type,
        user_code=tokens.user_code,
        role=tokens.role,
    )


@router.post(
    "/logout",
    response_model=LogoutResponse,
    summary="Customer logout (mobile app)",
    description=(
        "Same behaviour as POST /api/v1/auth/logout: revokes the Bearer access token "
        "(and optional refresh token in body), sets logged_out_at, and records USER_LOGOUT."
    ),
)
def logout_customer(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    current_user: User = Depends(get_current_user),
    body: Optional[LogoutRequest] = Body(None),
    db: Session = Depends(get_db),
) -> LogoutResponse:
    refresh = body.refresh_token if body else None
    logged_out_at = AuthService.logout_user(
        db=db,
        user=current_user,
        access_token=credentials.credentials,
        refresh_token=refresh,
    )
    return LogoutResponse(
        message=f"Customer {current_user.email} successfully logged out.",
        user_id=current_user.id,
        logged_out_at=logged_out_at,
    )
