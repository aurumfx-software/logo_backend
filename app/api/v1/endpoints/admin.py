from typing import Optional, Union
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_admin_user_flexible, require_admin, require_any_authenticated
from app.db.database import get_db
from app.db.models.user import User
from app.schemas.admin import (
    AdminDashboardStats,
    AdminUserCreateRequest,
    AdminUserDetailResponse,
    AdminUserListResponse,
    AdminUserRoleUpdateRequest,
    AdminUserStatusUpdateRequest,
    AdminUserUpdateRequest,
    DashboardChartsResponse,
    RecentActivityResponse,
    RegistrationRequestItem,
    RegistrationRequestsResponse,
    SingleRegistrationRequestResponse,
)
from app.schemas.activity_log import ActivityLogListResponse, ActivityLogResponse
from app.schemas.auth import GenericMessageResponse
from app.schemas.logo import LogoListResponse, LogoRejectRequest, LogoResponse
from app.schemas.merchant import (
    MerchantProfileResponse,
    MerchantRejectRequest,
    MerchantStatsResponse,
    MerchantUpdateRequest,
    PromoAccessRequestResponse,
)
from app.db.models.merchant import MerchantProfile, PromoAccessRequest
from app.db.models.notification import Notification
from app.schemas.notification import NotificationResponse
from app.schemas.response import (
    StandardListResponse,
    StandardResponse,
    list_response,
    success_response,
)
from app.services.activity_log_service import ActivityLogService
from app.services.admin_service import AdminService
from app.services.logo_service import LogoService
from app.services.merchant_service import MerchantService
from app.services.notification_service import NotificationService
from datetime import datetime, timezone

router = APIRouter(prefix="/admin", tags=["Admin Operations"])


# --- Admin Dashboard ---
@router.get(
    "/dashboard/stats",
    response_model=AdminDashboardStats,
    summary="Get admin dashboard statistics",
    description="Returns KPI platform stats: Total Merchants, Pending Approvals, Total Users, Active Staff, Total Searches, and growth % metrics.",
)
@router.get(
    "/dashboard",
    response_model=AdminDashboardStats,
    summary="Get admin dashboard statistics (alias)",
)
def get_dashboard_stats(
    current_admin: User = Depends(get_admin_user_flexible),
    db: Session = Depends(get_db),
) -> AdminDashboardStats:
    return AdminService.get_dashboard_stats(db=db)


@router.get(
    "/dashboard/charts",
    response_model=DashboardChartsResponse,
    summary="Get dashboard charts & growth analytics",
    description="Returns monthly time-series data for signup/search trends and merchant category distribution breakdown.",
)
def get_dashboard_charts(
    current_admin: User = Depends(get_admin_user_flexible),
    db: Session = Depends(get_db),
) -> DashboardChartsResponse:
    return AdminService.get_dashboard_charts(db=db)


@router.get(
    "/dashboard/recent-activity",
    response_model=RecentActivityResponse,
    summary="Get recent activity feed",
    description="Returns last 10 audit logs (onboardings, approvals, user signups).",
)
def get_dashboard_recent_activity(
    limit: int = Query(10, ge=1, le=50),
    current_admin: User = Depends(get_admin_user_flexible),
    db: Session = Depends(get_db),
) -> RecentActivityResponse:
    return AdminService.get_dashboard_recent_activity(db=db, limit=limit)



# --- Logo Moderation & Approval ---
@router.get(
    "/logos/pending",
    response_model=LogoListResponse,
    summary="List pending logos for moderation",
    description="Returns all logos awaiting administrator review with status PENDING.",
)
def list_pending_logos(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> LogoListResponse:
    return LogoService.search_logos(
        db=db,
        logo_status="PENDING",
        skip=skip,
        limit=limit,
        current_user=current_admin,
    )


@router.post(
    "/logos/{logo_id}/approve",
    response_model=LogoResponse,
    summary="Approve a logo",
    description="Approves a pending logo submission, making it publicly searchable and visible.",
)
def approve_logo(
    logo_id: int,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> LogoResponse:
    return LogoService.approve_logo(db=db, admin_user=current_admin, logo_id=logo_id)


@router.post(
    "/logos/{logo_id}/reject",
    response_model=LogoResponse,
    summary="Reject a logo",
    description="Rejects a logo with an official rejection reason, hiding it from public search.",
)
def reject_logo(
    logo_id: int,
    data: LogoRejectRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> LogoResponse:
    return LogoService.reject_logo(
        db=db,
        admin_user=current_admin,
        logo_id=logo_id,
        rejection_reason=data.rejection_reason,
    )


# --- User Management ---
@router.get(
    "/users",
    response_model=AdminUserListResponse,
    summary="List all users with filters",
    description="Search, filter by role or status, and paginate all registered users in the platform. Accessible to Super Admin, Admin, and Users.",
)
def list_users(
    role: Optional[str] = Query(None, description="Filter by role: SUPER_ADMIN, ADMIN, FIELD_STAFF"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    search: Optional[str] = Query(None, description="Search by name, email, or phone"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    sort: str = Query("asc", description="Sort order by user ID: 'asc' (1, 2, 3...) or 'desc' (7, 6, 5...)"),
    current_user: User = Depends(require_any_authenticated),
    db: Session = Depends(get_db),
) -> AdminUserListResponse:
    return AdminService.list_users(
        db=db,
        role=role,
        is_active=is_active,
        search=search,
        skip=skip,
        limit=limit,
        sort=sort,
    )


@router.post(
    "/users",
    response_model=AdminUserDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new user with modules, region, and access controls",
    description="Allows administrator to create a user account specifying role, district, regions, city, module_access list, send_email binary flag, status, and created_by.",
)

def create_user(
    data: AdminUserCreateRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminUserDetailResponse:
    user = AdminService.create_user(db=db, user_data=data, current_admin=current_admin)
    return AdminService.get_user_details(db=db, user_id=user.id)


def _parse_user_id(db: Session, uid: Union[str, int]) -> int:
    val = str(uid).strip()
    if val.isdigit():
        return int(val)
    user = db.query(User).filter(User.user_code.ilike(val)).first()
    if user:
        return user.id
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"User with ID or code '{uid}' not found.",
    )


@router.get(
    "/users/{user_id}",
    response_model=AdminUserDetailResponse,
    summary="Get user details",
    description="Returns detailed profile, merchant details, submission count, and favorites count for a specific user by ID or code (e.g. 1 or ADM_1). Accessible to Super Admin, Admin, and Users.",
)
def get_user_details(
    user_id: str,
    current_user: User = Depends(require_any_authenticated),
    db: Session = Depends(get_db),
) -> AdminUserDetailResponse:
    numeric_id = _parse_user_id(db, user_id)
    return AdminService.get_user_details(db=db, user_id=numeric_id)


@router.patch(
    "/users/{user_id}/role",
    response_model=AdminUserDetailResponse,
    summary="Update user role",
    description="Modifies a user's role (SUPER_ADMIN, ADMIN, FIELD_STAFF). Admins cannot demote their own account.",
)
def update_user_role(
    user_id: str,
    data: AdminUserRoleUpdateRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminUserDetailResponse:
    numeric_id = _parse_user_id(db, user_id)
    return AdminService.update_user_role(
        db=db,
        user_id=numeric_id,
        new_role=data.role,
        current_admin=current_admin,
    )


@router.put(
    "/users/{user_id}",
    response_model=AdminUserDetailResponse,
    summary="Update user details, active/inactive, or suspended status",
    description="Updates user profile, role, status, is_active, and is_suspended flag.",
)
@router.patch(
    "/users/{user_id}",
    response_model=AdminUserDetailResponse,
    summary="Partially update user details, active/inactive, or suspended status",
)
def update_user(
    user_id: str,
    data: AdminUserUpdateRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminUserDetailResponse:
    numeric_id = _parse_user_id(db, user_id)
    return AdminService.update_user(
        db=db,
        user_id=numeric_id,
        data=data,
        current_admin=current_admin,
    )


@router.put(
    "/users/{user_id}/status",
    response_model=AdminUserDetailResponse,
    summary="Activate or suspend user via PUT",
)
@router.patch(
    "/users/{user_id}/status",
    response_model=AdminUserDetailResponse,
    summary="Activate or ban user",
    description="Sets the active state of a user. Inactive users cannot log in. Admins cannot ban their own account.",
)
def update_user_status(
    user_id: str,
    data: AdminUserStatusUpdateRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminUserDetailResponse:
    numeric_id = _parse_user_id(db, user_id)
    return AdminService.update_user_status(
        db=db,
        user_id=numeric_id,
        is_active=data.is_active,
        current_admin=current_admin,
        status_text=data.status,
        is_suspended=data.is_suspended,
    )


@router.delete(
    "/users/{user_id}",
    response_model=GenericMessageResponse,
    summary="Delete user account",
    description="Permanently deletes a user account and cascading data. Admins cannot delete their own account.",
)
def delete_user(
    user_id: str,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> GenericMessageResponse:
    numeric_id = _parse_user_id(db, user_id)
    AdminService.delete_user(db=db, user_id=numeric_id, current_admin=current_admin)
    return GenericMessageResponse(message=f"User {user_id} successfully deleted.")


# --- Merchant Moderation & Statistics ---

@router.get(
    "/merchants/stats",
    response_model=StandardResponse[MerchantStatsResponse],
    summary="Get active/inactive merchant statistics",
    description="Returns comprehensive counts of active, inactive, pending, approved, rejected, and verified merchants with top locations and categories.",
)
def get_merchant_statistics(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> StandardResponse[MerchantStatsResponse]:
    stats = MerchantService.get_merchant_stats(db=db)
    return success_response(
        data=MerchantStatsResponse(**stats),
        message="Merchant statistics retrieved successfully",
    )


@router.get(
    "/merchants/stats",
    response_model=StandardResponse[MerchantStatsResponse],
    summary="Get merchant statistics (active, inactive, pending, etc.)",
    description="Aggregates active, inactive, pending, approved, and rejected merchant counts for administrator overview.",
)
def get_admin_merchant_stats(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> StandardResponse[MerchantStatsResponse]:
    stats = MerchantService.get_merchant_stats(db=db)
    return success_response(
        data=MerchantStatsResponse(**stats),
        message="Merchant statistics retrieved successfully.",
    )


@router.get(
    "/merchants/pending",
    response_model=StandardListResponse[MerchantProfileResponse],
    summary="List pending merchants for review",
    description="Returns all merchant accounts with PENDING approval status awaiting review. Scoped to current user if Field Staff.",
)
def list_pending_merchants(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    user_code: Optional[str] = Query(None, description="Filter by creator user code (e.g. FLS_1)"),
    current_user: User = Depends(require_any_authenticated),
    db: Session = Depends(get_db),
) -> StandardListResponse[MerchantProfileResponse]:
    results, total = MerchantService.search_merchants(
        db=db,
        approval_status="PENDING",
        skip=skip,
        limit=limit,
        public_only=False,
        current_user=current_user,
        user_code=user_code,
    )
    page = (skip // limit) + 1
    return list_response(
        data=[MerchantService.build_merchant_response(m) for m in results],
        total_items=total,
        page=page,
        page_size=limit,
        message=f"Retrieved {len(results)} pending merchant(s)",
    )


@router.get(
    "/merchants",
    response_model=StandardListResponse[MerchantProfileResponse],
    summary="List all merchants (admin & staff view)",
    description="Endpoint to list merchants with filtering by approval status, active state, location, and keywords. Scoped to current user if Field Staff.",
)
def list_all_merchants_admin(
    approval_status: Optional[str] = Query(None, description="PENDING, APPROVED, or REJECTED"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    is_verified: Optional[bool] = Query(None, description="Filter by verified status"),
    location: Optional[str] = Query(None, description="Filter by location"),
    user_code: Optional[str] = Query(None, description="Filter by creator user code (e.g. FLS_1)"),
    search: Optional[str] = Query(None, description="Keyword search"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(require_any_authenticated),
    db: Session = Depends(get_db),
) -> StandardListResponse[MerchantProfileResponse]:
    results, total = MerchantService.search_merchants(
        db=db,
        query=search,
        location=location,
        approval_status=approval_status,
        is_active=is_active,
        is_verified=is_verified,
        skip=skip,
        limit=limit,
        public_only=False,
        current_user=current_user,
        user_code=user_code,
    )
    page = (skip // limit) + 1
    return list_response(
        data=[MerchantService.build_merchant_response(m) for m in results],
        total_items=total,
        page=page,
        page_size=limit,
        message=f"Retrieved {len(results)} merchant(s)",
    )


# --- Merchant Registration Requests ---
@router.get(
    "/merchants/registration-requests",
    response_model=RegistrationRequestsResponse,
    summary="List merchant registration applications",
    description="Returns list of onboarding requests filtered by status (pending, approved, rejected, all), with search (business_name, owner, city, phone) and location filters.",
)
def list_registration_requests(
    status: Optional[str] = Query(None, description="Filter by status: pending, approved, rejected, all"),
    search: Optional[str] = Query(None, description="Search keyword for business name, owner, city, phone, email"),
    district: Optional[str] = Query(None, description="Filter by district"),
    city: Optional[str] = Query(None, description="Filter by city"),
    location: Optional[str] = Query(None, description="Filter by location/address"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_admin: User = Depends(get_admin_user_flexible),
    db: Session = Depends(get_db),
) -> RegistrationRequestsResponse:
    return AdminService.list_registration_requests(
        db=db,
        status=status,
        search=search,
        district=district,
        city=city,
        location=location,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/merchants/registration-requests/{request_id}",
    response_model=RegistrationRequestItem,
    summary="Get single merchant registration application details",
    description="Returns full application profile details including photos, documents, and coordinates.",
)
def get_single_registration_request(
    request_id: int,
    current_admin: User = Depends(get_admin_user_flexible),
    db: Session = Depends(get_db),
) -> RegistrationRequestItem:
    return AdminService.get_registration_request_by_id(db=db, request_id=request_id)


@router.post(
    "/merchants/{merchant_id}/approve",
    response_model=StandardResponse[MerchantProfileResponse],
    summary="Approve a merchant application",
    description="Updates status to APPROVED/ACTIVE, logs approved_at timestamp & admin ID, sets is_verified = true, and triggers notification SMS/Email to merchant.",
)
def approve_merchant(
    merchant_id: int,
    current_admin: User = Depends(get_admin_user_flexible),
    db: Session = Depends(get_db),
) -> StandardResponse[MerchantProfileResponse]:
    approved = MerchantService.approve_merchant(
        db=db, merchant_id=merchant_id, admin_user=current_admin
    )
    return success_response(
        data=MerchantService.build_merchant_response(approved),
        message=f"Merchant '{approved.business_name}' approved successfully",
    )


@router.post(
    "/merchants/{merchant_id}/reject",
    response_model=StandardResponse[MerchantProfileResponse],
    summary="Reject a merchant application",
    description="Accepts { rejection_reason: string }, updates status to REJECTED, logs reason & admin ID, and triggers rejection notice to merchant.",
)
def reject_merchant(
    merchant_id: int,
    data: Optional[MerchantRejectRequest] = None,
    current_admin: User = Depends(get_admin_user_flexible),
    db: Session = Depends(get_db),
) -> StandardResponse[MerchantProfileResponse]:
    reason = (data.rejection_reason or data.reason) if data else "Application rejected by administration."
    rejected = MerchantService.reject_merchant(
        db=db,
        merchant_id=merchant_id,
        reason=reason,
        admin_user=current_admin,
    )
    return success_response(
        data=MerchantService.build_merchant_response(rejected),
        message=f"Merchant '{rejected.business_name}' rejected",
    )


@router.patch(
    "/merchants/{merchant_id}/promotion-access",
    response_model=StandardResponse[MerchantProfileResponse],
    summary="Toggle promotion access for a merchant",
    description="Enables or disables a merchant's ability to create and manage promotions. Enforced in UI and backend.",
)
@router.put(
    "/merchants/{merchant_id}/promotion-access",
    response_model=StandardResponse[MerchantProfileResponse],
    summary="Toggle promotion access for a merchant (PUT alias)",
)
def toggle_merchant_promotion_access(
    merchant_id: int,
    data: dict,
    current_admin: User = Depends(get_admin_user_flexible),
    db: Session = Depends(get_db),
) -> StandardResponse[MerchantProfileResponse]:
    merchant = MerchantService.get_merchant_by_id(db=db, merchant_id=merchant_id)
    enabled = bool(
        data.get("can_create_promotions")
        if "can_create_promotions" in data
        else data.get("promotion_access", False)
    )
    merchant.can_create_promotions = enabled
    db.commit()
    db.refresh(merchant)

    now = datetime.now(timezone.utc)
    if not enabled:
        # Revoke existing promo requests for this merchant so it reverts to locked and can be re-requested
        db.query(PromoAccessRequest).filter(
            PromoAccessRequest.merchant_id == merchant.id,
            PromoAccessRequest.status.in_(["APPROVED", "PENDING"])
        ).update({"status": "REVOKED", "updated_at": now})
        db.commit()

        if merchant.user_id:
            try:
                NotificationService.create_notification(
                    db=db,
                    user_id=merchant.user_id,
                    title="Promotion Access Disabled",
                    message="Promotion creation privileges have been turned OFF by Logo Admin.",
                    type="PROMO_ACCESS_REVOKED",
                    data={"merchant_id": merchant.id, "can_create_promotions": False},
                )
            except Exception as err:
                print("Notification error on promo revoke:", err)
    else:
        # If toggled ON, mark pending promo request as APPROVED
        db.query(PromoAccessRequest).filter(
            PromoAccessRequest.merchant_id == merchant.id,
            PromoAccessRequest.status == "PENDING"
        ).update({
            "status": "APPROVED",
            "reviewed_by_id": current_admin.id if current_admin else None,
            "reviewed_at": now,
            "updated_at": now
        })
        db.commit()

        if merchant.user_id:
            try:
                NotificationService.create_notification(
                    db=db,
                    user_id=merchant.user_id,
                    title="Promotion Access Enabled! ⚡",
                    message="Logo Admin has enabled promotion publishing for your business.",
                    type="PROMO_ACCESS_APPROVED",
                    data={"merchant_id": merchant.id, "can_create_promotions": True},
                )
            except Exception as err:
                print("Notification error on promo enable:", err)

    status_str = "enabled" if enabled else "disabled"
    return success_response(
        data=MerchantService.build_merchant_response(merchant),
        message=f"Promotion access {status_str} for '{merchant.business_name}'",
    )


@router.put(
    "/merchants/{merchant_id}",
    response_model=MerchantProfileResponse,
    status_code=status.HTTP_200_OK,
    summary="Update merchant profile by ID",
    description="Updates business details, location, contact, social, media, or services for a specific merchant.",
)
@router.patch(
    "/merchants/{merchant_id}",
    response_model=MerchantProfileResponse,
    status_code=status.HTTP_200_OK,
    summary="Partially update merchant profile by ID",
)
def admin_update_merchant(
    merchant_id: int,
    data: MerchantUpdateRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> MerchantProfileResponse:
    merchant = MerchantService.get_merchant_by_id(db=db, merchant_id=merchant_id)
    updated = MerchantService.update_merchant(db=db, merchant=merchant, data=data)
    return MerchantService.build_merchant_response(updated)


@router.delete(
    "/merchants/{merchant_id}",
    response_model=GenericMessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Delete merchant profile by ID",
    description="Permanently deletes a merchant profile from the database.",
)
def admin_delete_merchant(
    merchant_id: int,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> GenericMessageResponse:
    MerchantService.delete_merchant(db=db, merchant_id=merchant_id)
    return GenericMessageResponse(message=f"Merchant {merchant_id} deleted successfully.")


# --- Activity Audit Logs ---

@router.get(
    "/activity-logs",
    response_model=StandardListResponse[ActivityLogResponse],
    summary="List activity audit logs",
    description="Audit logs for system and admin actions (approvals, rejections, user updates, registrations).",
)
def list_activity_logs(
    action: Optional[str] = Query(None, description="Filter by action name (e.g. MERCHANT_APPROVED)"),
    entity_type: Optional[str] = Query(None, description="Filter by entity type (e.g. MERCHANT, USER)"),
    user_id: Optional[int] = Query(None, description="Filter by performing user ID"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> StandardListResponse[ActivityLogResponse]:
    items, total = ActivityLogService.list_activity_logs(
        db=db,
        action=action,
        entity_type=entity_type,
        user_id=user_id,
        skip=skip,
        limit=limit,
    )
    page = (skip // limit) + 1
    return list_response(
        data=[ActivityLogResponse(**item) for item in items],
        total_items=total,
        page=page,
        page_size=limit,
        message=f"Retrieved {len(items)} activity log(s)",
    )


@router.get(
    "/activity-logs/actions",
    response_model=StandardResponse[list],
    summary="Get distinct activity log action types",
    description="Returns a list of all distinct action types present in the activity logs for filter dropdowns.",
)
def get_activity_log_actions(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> StandardResponse[list]:
    actions = ActivityLogService.get_action_types(db=db)
    return success_response(
        data=actions,
        message="Action types retrieved successfully",
    )


# --- Promo Access Requests Management ---

@router.get(
    "/merchants/promo-access-requests",
    response_model=StandardListResponse[PromoAccessRequestResponse],
    summary="List merchant promo access requests",
    description="Returns all promotion access requests submitted by merchants.",
)
def list_promo_access_requests(
    status: Optional[str] = Query(None, description="Filter by status: pending, approved, rejected, all"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_admin: User = Depends(get_admin_user_flexible),
    db: Session = Depends(get_db),
):
    query = db.query(PromoAccessRequest)
    if status and status.lower() != "all":
        query = query.filter(PromoAccessRequest.status == status.upper())

    total = query.count()
    items = (
        query.order_by(
            PromoAccessRequest.status == "PENDING",  # Pending first
            PromoAccessRequest.created_at.desc(),
        )
        .offset(skip)
        .limit(limit)
        .all()
    )
    page = (skip // limit) + 1 if limit > 0 else 1
    return list_response(
        data=[PromoAccessRequestResponse.model_validate(r) for r in items],
        total_items=total,
        page=page,
        page_size=limit,
        message=f"Retrieved {len(items)} promo access request(s)",
    )


@router.post(
    "/merchants/promo-access-requests/{request_id}/approve",
    response_model=StandardResponse[PromoAccessRequestResponse],
    summary="Approve merchant promo access request",
)
def approve_promo_access_request(
    request_id: int,
    current_admin: User = Depends(get_admin_user_flexible),
    db: Session = Depends(get_db),
):
    req = db.query(PromoAccessRequest).filter(PromoAccessRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail=f"Request #{request_id} not found.")

    req.status = "APPROVED"
    req.reviewed_by_id = current_admin.id
    req.reviewed_at = datetime.now(timezone.utc)

    # Enable promotion creation access on merchant
    merchant = db.query(MerchantProfile).filter(MerchantProfile.id == req.merchant_id).first()
    if merchant:
        merchant.can_create_promotions = True

    db.commit()
    db.refresh(req)

    # Notify merchant user
    try:
        if req.user_id:
            NotificationService.create_notification(
                db=db,
                user_id=req.user_id,
                title="Promotion Access Approved! 🎉",
                message=f"Your promotion creation access for '{req.merchant_name}' has been approved by admin. You can now create and submit promotions!",
                type="PROMO_ACCESS_APPROVED",
                data={"merchant_id": req.merchant_id, "request_id": req.id},
            )
    except Exception as err:
        print("Notification error on promo access approve:", err)

    return success_response(
        data=PromoAccessRequestResponse.model_validate(req),
        message=f"Promotion access approved for '{req.merchant_name}'",
    )


@router.post(
    "/merchants/promo-access-requests/{request_id}/reject",
    response_model=StandardResponse[PromoAccessRequestResponse],
    summary="Reject merchant promo access request",
)
def reject_promo_access_request(
    request_id: int,
    data: Optional[dict] = None,
    current_admin: User = Depends(get_admin_user_flexible),
    db: Session = Depends(get_db),
):
    req = db.query(PromoAccessRequest).filter(PromoAccessRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail=f"Request #{request_id} not found.")

    reason = (data or {}).get("reason") if isinstance(data, dict) else "Promotion access request declined by administration."
    req.status = "REJECTED"
    req.rejection_reason = reason
    req.reviewed_by_id = current_admin.id
    req.reviewed_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(req)

    # Notify merchant user
    try:
        if req.user_id:
            NotificationService.create_notification(
                db=db,
                user_id=req.user_id,
                title="Promotion Access Request Update",
                message=f"Your promotion access request for '{req.merchant_name}' was declined: {reason}",
                type="PROMO_ACCESS_REJECTED",
                data={"merchant_id": req.merchant_id, "request_id": req.id},
            )
    except Exception as err:
        print("Notification error on promo access reject:", err)

    return success_response(
        data=PromoAccessRequestResponse.model_validate(req),
        message=f"Promotion access rejected for '{req.merchant_name}'",
    )


# --- Admin Notifications ---

@router.get(
    "/notifications",
    summary="Get all admin notifications",
)
def get_admin_notifications(
    limit: int = Query(30, ge=1, le=100),
    current_admin: User = Depends(get_admin_user_flexible),
    db: Session = Depends(get_db),
):
    query = db.query(Notification).filter(Notification.user_id == current_admin.id)
    unread_count = query.filter(Notification.is_read == False).count()
    items = query.order_by(Notification.created_at.desc()).limit(limit).all()

    return {
        "success": True,
        "unread_count": unread_count,
        "total": len(items),
        "notifications": [
            {
                "id": n.id,
                "title": n.title,
                "message": n.message,
                "type": n.type,
                "is_read": n.is_read,
                "data": n.data,
                "created_at": n.created_at.isoformat() if n.created_at else None,
            }
            for n in items
        ],
    }


@router.patch(
    "/notifications/{notification_id}/read",
    summary="Mark admin notification as read",
)
def mark_admin_notification_read(
    notification_id: int,
    current_admin: User = Depends(get_admin_user_flexible),
    db: Session = Depends(get_db),
):
    notif = db.query(Notification).filter(
        Notification.id == notification_id,
        Notification.user_id == current_admin.id,
    ).first()
    if notif:
        notif.is_read = True
        db.commit()
    return {"success": True, "message": "Notification marked as read"}


@router.post(
    "/notifications/mark-all-read",
    summary="Mark all admin notifications as read",
)
def mark_all_admin_notifications_read(
    current_admin: User = Depends(get_admin_user_flexible),
    db: Session = Depends(get_db),
):
    db.query(Notification).filter(
        Notification.user_id == current_admin.id,
        Notification.is_read == False,
    ).update({Notification.is_read: True})
    db.commit()
    return {"success": True, "message": "All notifications marked as read"}

