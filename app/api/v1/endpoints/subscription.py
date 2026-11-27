from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_current_user_optional, require_admin
from app.db.database import get_db
from app.db.models.subscription import SubscriptionAudience
from app.db.models.user import User
from app.schemas.response import StandardListResponse, StandardResponse, list_response, success_response
from app.schemas.subscription import (
    ActiveSubscriptionSummary,
    AdminAssignSubscriptionRequest,
    SubscribeRequest,
    SubscriptionPackageCreateRequest,
    SubscriptionPackageResponse,
    SubscriptionPackageUpdateRequest,
    SubscriptionRazorpayOrderRequest,
    SubscriptionRazorpayOrderResponse,
    SubscriptionRazorpayVerifyRequest,
    UserSubscriptionResponse,
)
from app.services.subscription_service import SubscriptionService

router = APIRouter(prefix="/subscriptions", tags=["Subscriptions"])


@router.get(
    "/packages",
    response_model=StandardListResponse[SubscriptionPackageResponse],
    summary="List subscription packages",
    description="Public catalog of user and merchant subscription plans.",
)
def list_subscription_packages(
    audience: Optional[SubscriptionAudience] = Query(
        None,
        description="Filter by USER or MERCHANT packages",
    ),
    active_only: bool = Query(True, description="Only active packages"),
    db: Session = Depends(get_db),
) -> StandardListResponse[SubscriptionPackageResponse]:
    packages = SubscriptionService.list_packages(db=db, audience=audience, active_only=active_only)
    data = [SubscriptionPackageResponse.model_validate(p) for p in packages]
    return list_response(
        data=data,
        total_items=len(data),
        message=f"Retrieved {len(data)} subscription package(s)",
    )


@router.get(
    "/packages/{package_id}",
    response_model=StandardResponse[SubscriptionPackageResponse],
    summary="Get subscription package by ID",
)
def get_subscription_package(
    package_id: int,
    db: Session = Depends(get_db),
) -> StandardResponse[SubscriptionPackageResponse]:
    pkg = SubscriptionService.get_package(db=db, package_id=package_id)
    return success_response(
        data=SubscriptionPackageResponse.model_validate(pkg),
        message="Subscription package retrieved",
    )


@router.get(
    "/me",
    response_model=StandardListResponse[UserSubscriptionResponse],
    summary="List my subscriptions",
)
def list_my_subscriptions(
    merchant_profile_id: Optional[int] = Query(None, description="Filter merchant shop subscriptions"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StandardListResponse[UserSubscriptionResponse]:
    subs = SubscriptionService.list_user_subscriptions(
        db=db,
        user=current_user,
        merchant_profile_id=merchant_profile_id,
    )
    data = [SubscriptionService._subscription_to_response(s) for s in subs]
    return list_response(data=data, total_items=len(data), message="Subscriptions retrieved")


@router.get(
    "/me/active",
    response_model=StandardResponse[ActiveSubscriptionSummary],
    summary="Active subscription summary",
    description=(
        "Returns active user and merchant subscriptions. "
        "Without a token, returns an empty summary instead of 401."
    ),
)
def get_my_active_subscriptions(
    merchant_profile_id: Optional[int] = Query(None, description="Optional specific shop ID to check merchant subscription"),
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> StandardResponse[ActiveSubscriptionSummary]:
    if current_user is None:
        return success_response(
            data=ActiveSubscriptionSummary(),
            message="No active subscription",
        )
    user_subs, merchant_subs, user = SubscriptionService.get_active_summary(db=db, user=current_user)
    from app.db.models.merchant import MerchantProfile

    shop = None
    if merchant_profile_id:
        shop = db.query(MerchantProfile).filter(MerchantProfile.id == merchant_profile_id).first()
    if shop is None:
        shop = SubscriptionService.merchant_for_account(db, user)

    target_merchant_id = shop.id if shop else merchant_profile_id
    filtered_merchant_subs = (
        [s for s in merchant_subs if s.merchant_profile_id == target_merchant_id]
        if target_merchant_id
        else merchant_subs
    )
    merchant_grants = SubscriptionService.get_merchant_grants(
        db=db,
        merchant_profile_id=shop.id if shop else target_merchant_id,
        user_id=user.id,
        include_user_seller=True,
    )
    merchant_flag = bool(filtered_merchant_subs) or bool(
        shop and shop.has_active_subscription
    )
    summary = ActiveSubscriptionSummary(
        user_subscriptions=[SubscriptionService._subscription_to_response(s) for s in user_subs],
        merchant_subscriptions=[SubscriptionService._subscription_to_response(s) for s in merchant_subs],
        can_sell_products=bool(user.can_sell_products or merchant_grants.get("merchant_product_section")),
        is_subscriber=bool(user.is_subscriber or merchant_grants.get("merchant_product_section")),
        subscription_plan=user.subscription_plan,
        merchant_has_active_subscription=merchant_flag,
        merchant_profile_id=shop.id if shop else target_merchant_id,
        merchant_business_name=shop.business_name if shop else None,
        merchant_grants=merchant_grants,
    )
    return success_response(data=summary, message="Active subscription summary retrieved")


@router.post(
    "/razorpay/order",
    response_model=SubscriptionRazorpayOrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Razorpay checkout order for a subscription package",
)
def create_subscription_razorpay_order(
    payload: SubscriptionRazorpayOrderRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SubscriptionRazorpayOrderResponse:
    res = SubscriptionService.create_razorpay_order(db=db, user=current_user, payload=payload)
    return SubscriptionRazorpayOrderResponse(**res)


@router.post(
    "/razorpay/verify",
    response_model=StandardResponse[UserSubscriptionResponse],
    summary="Verify Razorpay signature and activate subscription",
)
def verify_subscription_razorpay_payment(
    payload: SubscriptionRazorpayVerifyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StandardResponse[UserSubscriptionResponse]:
    sub = SubscriptionService.verify_razorpay_and_subscribe(db=db, user=current_user, payload=payload)
    return success_response(
        data=SubscriptionService._subscription_to_response(sub),
        message="Razorpay payment verified and subscription activated successfully",
    )


@router.post(
    "/subscribe",
    response_model=StandardResponse[UserSubscriptionResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Subscribe to a package",
    description=(
        "Activates a subscription. Send package_id or package_code. "
        "Merchant plans use the caller's shop when merchant_profile_id is omitted."
    ),
)
def subscribe_to_package(
    payload: SubscribeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StandardResponse[UserSubscriptionResponse]:
    sub = SubscriptionService.subscribe(db=db, user=current_user, payload=payload)
    return success_response(
        data=SubscriptionService._subscription_to_response(sub),
        message="Subscription activated successfully",
    )


@router.post(
    "/{subscription_id}/cancel",
    response_model=StandardResponse[UserSubscriptionResponse],
    summary="Cancel my subscription",
)
def cancel_my_subscription(
    subscription_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StandardResponse[UserSubscriptionResponse]:
    sub = SubscriptionService.cancel_subscription(
        db=db, user=current_user, subscription_id=subscription_id
    )
    return success_response(
        data=SubscriptionService._subscription_to_response(sub),
        message="Subscription cancelled",
    )


# ── Admin ────────────────────────────────────────────────────────────────────


@router.post(
    "/admin/packages",
    response_model=StandardResponse[SubscriptionPackageResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Admin: create subscription package",
)
def admin_create_package(
    payload: SubscriptionPackageCreateRequest,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> StandardResponse[SubscriptionPackageResponse]:
    pkg = SubscriptionService.create_package(db=db, data=payload)
    return success_response(
        data=SubscriptionPackageResponse.model_validate(pkg),
        message="Subscription package created",
    )


@router.patch(
    "/admin/packages/{package_id}",
    response_model=StandardResponse[SubscriptionPackageResponse],
    summary="Admin: update subscription package",
)
def admin_update_package(
    package_id: int,
    payload: SubscriptionPackageUpdateRequest,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> StandardResponse[SubscriptionPackageResponse]:
    pkg = SubscriptionService.update_package(db=db, package_id=package_id, data=payload)
    return success_response(
        data=SubscriptionPackageResponse.model_validate(pkg),
        message="Subscription package updated",
    )


@router.post(
    "/admin/packages/{package_id}/duplicate",
    response_model=StandardResponse[SubscriptionPackageResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Admin: duplicate subscription package",
)
def admin_duplicate_package(
    package_id: int,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> StandardResponse[SubscriptionPackageResponse]:
    pkg = SubscriptionService.duplicate_package(db=db, package_id=package_id)
    return success_response(
        data=SubscriptionPackageResponse.model_validate(pkg),
        message="Subscription package duplicated",
    )


@router.post(
    "/admin/assign",
    response_model=StandardResponse[UserSubscriptionResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Admin: assign subscription to user/merchant",
)
def admin_assign_subscription(
    payload: AdminAssignSubscriptionRequest,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> StandardResponse[UserSubscriptionResponse]:
    sub = SubscriptionService.admin_assign(db=db, data=payload)
    return success_response(
        data=SubscriptionService._subscription_to_response(sub),
        message="Subscription assigned successfully",
    )
