from typing import Optional

from fastapi import APIRouter, Body, Depends, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, optional_security_scheme
from app.db.database import get_db
from app.db.models.user import User
from app.schemas.auth import (
    CustomerRegisterRequest,
    CustomerRegisterResponse,
    LogoutRequest,
    LogoutResponse,
    SafeUserResponse,
)
from app.schemas.customer import CustomerLocationUpdateRequest, CustomerProfileResponse
from app.schemas.seller_portal import (
    SellerBankDetailsResponse,
    SellerBankDetailsRequest,
    SellerBankSaveResponse,
)
from app.services.auth_service import AuthService
from app.services.seller_portal_service import SellerPortalService

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
        login_id=tokens.login_id,
        role=tokens.role,
    )


@router.post(
    "/logout",
    response_model=LogoutResponse,
    summary="Customer logout (mobile app)",
    description=(
        "Revokes the Bearer access token when one is sent. "
        "Missing or expired tokens still return success."
    ),
)
def logout_customer(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_security_scheme),
    body: Optional[LogoutRequest] = Body(None),
    db: Session = Depends(get_db),
) -> LogoutResponse:
    access = credentials.credentials if credentials else None
    refresh = body.refresh_token if body else None
    return AuthService.logout_request(db=db, access_token=access, refresh_token=refresh)


@router.get(
    "/location",
    response_model=CustomerProfileResponse,
    summary="Get current customer location",
    description="Returns the authenticated user's saved district, city, location, and coordinates.",
)
def get_customer_location(
    current_user: User = Depends(get_current_user),
) -> CustomerProfileResponse:
    return CustomerProfileResponse.model_validate(current_user)


@router.put(
    "/location",
    response_model=CustomerProfileResponse,
    summary="Update customer location",
    description="Saves district, city, town/location, address, or GPS coordinates for the authenticated user.",
)
@router.post(
    "/location",
    response_model=CustomerProfileResponse,
    summary="Update customer location",
)
def update_customer_location(
    data: CustomerLocationUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CustomerProfileResponse:
    if data.district is not None:
        current_user.district = data.district.strip() or None
    if data.city is not None:
        current_user.city = data.city.strip() or None
    if data.location is not None:
        current_user.location = data.location.strip() or None
    if data.address is not None:
        current_user.address = data.address.strip() or None
    if data.latitude is not None:
        current_user.latitude = data.latitude
    if data.longitude is not None:
        current_user.longitude = data.longitude
    db.commit()
    db.refresh(current_user)
    return CustomerProfileResponse.model_validate(current_user)


@router.get(
    "/seller/bank-details",
    response_model=SellerBankDetailsResponse,
    summary="Get the logged-in seller's bank and UPI details",
)
def get_seller_bank_details(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SellerBankDetailsResponse:
    row = SellerPortalService.get_bank_details(db, current_user)
    if row is None:
        return SellerBankDetailsResponse(
            success=True,
            data=None,
            message="No bank details configured yet.",
        )
    return SellerBankDetailsResponse(success=True, data=SellerPortalService.to_bank_details(row))


@router.put(
    "/seller/bank-details",
    response_model=SellerBankSaveResponse,
    summary="Save or update the logged-in seller's bank and UPI details",
)
def save_seller_bank_details(
    data: SellerBankDetailsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SellerBankSaveResponse:
    row = SellerPortalService.save_bank_details(db, current_user, data)
    return SellerBankSaveResponse(
        success=True,
        message="Seller bank details saved successfully",
        data=SellerPortalService.to_bank_details(row),
    )
