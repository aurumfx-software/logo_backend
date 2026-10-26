from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.auth import CustomerRegisterRequest, CustomerRegisterResponse, SafeUserResponse
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
