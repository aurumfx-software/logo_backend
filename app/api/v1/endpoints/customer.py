from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import (
    get_current_user,
    get_current_user_optional,
    get_db,
)
from app.db.models.user import User
from app.schemas.customer import (
    CustomerAuthResponse,
    CustomerFavoriteListResponse,
    CustomerFavoriteSyncRequest,
    CustomerFavoriteToggleResponse,
    CustomerLoginRequest,
    CustomerLocationUpdateRequest,
    CustomerPhoneLoginRequest,
    CustomerProfileResponse,
    CustomerRegisterRequest,
    NearbyMerchantsResponse,
)
from app.services.customer_service import CustomerService

router = APIRouter(prefix="/customer", tags=["Customer & Location Discovery"])


@router.post(
    "/phone-login",
    response_model=CustomerAuthResponse,
    status_code=status.HTTP_200_OK,
    summary="OTP-Free Customer Phone Login & Auto-Register",
    description="Authenticates or automatically registers a customer with their 10-digit mobile number for Web & Mobile App.",
)
@router.post(
    "/quick-login",
    response_model=CustomerAuthResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
def phone_or_quick_login(
    data: CustomerPhoneLoginRequest,
    db: Session = Depends(get_db),
) -> CustomerAuthResponse:
    user, access_token, refresh_token = CustomerService.phone_or_quick_login(db=db, data=data)
    return CustomerAuthResponse(
        success=True,
        message="Customer authenticated successfully.",
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        customer=CustomerProfileResponse.model_validate(user),
    )


@router.post(
    "/register",
    response_model=CustomerAuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Customer Registration with Location Details",
    description="Registers a new Customer account with name, email, phone, password, district, city, place/location, and optional coordinates.",
)
def register_customer(
    data: CustomerRegisterRequest,
    db: Session = Depends(get_db),
) -> CustomerAuthResponse:
    user, access_token, refresh_token = CustomerService.register_customer(db=db, data=data)
    return CustomerAuthResponse(
        success=True,
        message="Customer registration successful.",
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        customer=CustomerProfileResponse.model_validate(user),
    )


@router.post(
    "/login",
    response_model=CustomerAuthResponse,
    status_code=status.HTTP_200_OK,
    summary="Customer Login",
    description="Authenticates a customer via email (or phone) and password, returning JWT tokens and saved location details.",
)
def login_customer(
    data: CustomerLoginRequest,
    db: Session = Depends(get_db),
) -> CustomerAuthResponse:
    user, access_token, refresh_token = CustomerService.login_customer(db=db, data=data)
    return CustomerAuthResponse(
        success=True,
        message="Login successful.",
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        customer=CustomerProfileResponse.model_validate(user),
    )


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    summary="Customer Logout",
    description="Logs out the customer and clears session.",
)
def logout_customer(
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    name = current_user.name if current_user else "Customer"
    return {
        "success": True,
        "message": f"{name} logged out successfully.",
    }



# =========================================================================
# Customer Wishlist / Saved Merchants Endpoints (Web & Mobile App)
# =========================================================================

@router.get(
    "/favorites",
    response_model=CustomerFavoriteListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Customer's Favorited / Wishlisted Merchants",
    description="Returns the list of merchant IDs and full merchant details saved by the authenticated customer.",
)
def get_customer_favorites(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CustomerFavoriteListResponse:
    fav_ids, merchants = CustomerService.get_user_merchant_favorites(db=db, user=current_user)
    return CustomerFavoriteListResponse(
        success=True,
        total=len(fav_ids),
        favorite_merchant_ids=fav_ids,
        merchants=merchants,
    )


@router.post(
    "/favorites/toggle/{merchant_id}",
    response_model=CustomerFavoriteToggleResponse,
    status_code=status.HTTP_200_OK,
    summary="Toggle Merchant in Customer's Wishlist",
    description="Adds or removes the specified merchant from the customer's cloud wishlist.",
)
def toggle_customer_favorite(
    merchant_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CustomerFavoriteToggleResponse:
    is_fav, all_fav_ids = CustomerService.toggle_merchant_favorite(
        db=db, user=current_user, merchant_id=merchant_id
    )
    return CustomerFavoriteToggleResponse(
        success=True,
        message="Merchant added to wishlist." if is_fav else "Merchant removed from wishlist.",
        merchant_id=merchant_id,
        is_favorite=is_fav,
        favorite_merchant_ids=all_fav_ids,
    )


@router.post(
    "/favorites/sync",
    response_model=CustomerFavoriteListResponse,
    status_code=status.HTTP_200_OK,
    summary="Sync Local Guest Wishlist to Customer Account",
    description="Merges client-side localStorage merchant IDs into the authenticated customer's cloud database.",
)
def sync_customer_favorites(
    data: CustomerFavoriteSyncRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CustomerFavoriteListResponse:
    synced_ids = CustomerService.sync_merchant_favorites(
        db=db, user=current_user, merchant_ids=data.merchant_ids
    )
    fav_ids, merchants = CustomerService.get_user_merchant_favorites(db=db, user=current_user)
    return CustomerFavoriteListResponse(
        success=True,
        total=len(fav_ids),
        favorite_merchant_ids=fav_ids,
        merchants=merchants,
    )


@router.delete(
    "/favorites/clear",
    status_code=status.HTTP_200_OK,
    summary="Clear All Customer Saved Merchants",
    description="Removes all merchant favorites from the customer's cloud wishlist.",
)
def clear_customer_favorites(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    CustomerService.clear_user_merchant_favorites(db=db, user=current_user)
    return {
        "success": True,
        "message": "All saved merchants cleared from wishlist.",
        "favorite_merchant_ids": [],
    }



@router.get(
    "/me",
    response_model=CustomerProfileResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Logged-in Customer Profile & Location",
    description="Returns current customer's profile, including their registered district, city, and location coordinates.",
)
def get_customer_profile(
    current_user: User = Depends(get_current_user),
) -> CustomerProfileResponse:
    return CustomerProfileResponse.model_validate(current_user)


@router.put(
    "/location",
    response_model=CustomerProfileResponse,
    status_code=status.HTTP_200_OK,
    summary="Update Customer's Saved Location",
    description="Allows a customer to update their active city, district, town/location, or GPS coordinates.",
)
def update_customer_location(
    data: CustomerLocationUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CustomerProfileResponse:
    updated = CustomerService.update_location(db=db, user=current_user, data=data)
    return CustomerProfileResponse.model_validate(updated)


@router.get(
    "/nearby-merchants",
    response_model=NearbyMerchantsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Nearby Merchants for Landing Page",
    description="Returns approved merchants prioritized and sorted by proximity to the customer's registered or provided location.",
)
def get_nearby_merchants_for_customer(
    district: Optional[str] = Query(None, description="Filter by district (e.g. Kannur, Kozhikode)"),
    city: Optional[str] = Query(None, description="Filter by city/town (e.g. Payyanur, Calicut)"),
    location: Optional[str] = Query(None, description="Filter by sub-location / area"),
    latitude: Optional[float] = Query(None, description="Customer GPS latitude"),
    longitude: Optional[float] = Query(None, description="Customer GPS longitude"),
    radius_km: Optional[float] = Query(50.0, description="Proximity radius in kilometers"),
    category: Optional[str] = Query(None, description="Filter by category"),
    search: Optional[str] = Query(None, description="Search keyword in merchant details"),
    limit: int = Query(50, ge=1, le=100),
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> NearbyMerchantsResponse:
    result = CustomerService.get_nearby_merchants(
        db=db,
        customer_user=current_user,
        district=district,
        city=city,
        location=location,
        latitude=latitude,
        longitude=longitude,
        radius_km=radius_km,
        category=category,
        search=search,
        limit=limit,
    )
    return NearbyMerchantsResponse(**result)
