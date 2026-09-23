from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import require_admin, require_any_authenticated
from app.db.database import get_db
from app.db.models.user import User
from app.schemas.admin import (
    AdminDashboardStats,
    AdminUserDetailResponse,
    AdminUserListResponse,
    AdminUserRoleUpdateRequest,
    AdminUserStatusUpdateRequest,
)
from app.schemas.activity_log import ActivityLogListResponse, ActivityLogResponse
from app.schemas.auth import GenericMessageResponse
from app.schemas.logo import LogoListResponse, LogoRejectRequest, LogoResponse
from app.schemas.merchant import (
    MerchantProfileResponse,
    MerchantRejectRequest,
    MerchantStatsResponse,
)
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

router = APIRouter(prefix="/admin", tags=["Admin Operations"])


# --- Admin Dashboard ---
@router.get(
    "/dashboard/stats",
    response_model=AdminDashboardStats,
    summary="Get admin dashboard statistics",
    description="Returns high-level platform statistics including user counts, logo counts, views, favorites, pending items, and category distribution.",
)
def get_dashboard_stats(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminDashboardStats:
    return AdminService.get_dashboard_stats(db=db)


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


@router.get(
    "/users/{user_id}",
    response_model=AdminUserDetailResponse,
    summary="Get user details",
    description="Returns detailed profile, merchant details, submission count, and favorites count for a specific user. Accessible to Super Admin, Admin, and Users.",
)
def get_user_details(
    user_id: int,
    current_user: User = Depends(require_any_authenticated),
    db: Session = Depends(get_db),
) -> AdminUserDetailResponse:
    return AdminService.get_user_details(db=db, user_id=user_id)


@router.patch(
    "/users/{user_id}/role",
    response_model=AdminUserDetailResponse,
    summary="Update user role",
    description="Modifies a user's role (SUPER_ADMIN, ADMIN, FIELD_STAFF). Admins cannot demote their own account.",
)
def update_user_role(
    user_id: int,
    data: AdminUserRoleUpdateRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminUserDetailResponse:
    return AdminService.update_user_role(
        db=db,
        user_id=user_id,
        new_role=data.role,
        current_admin=current_admin,
    )


@router.patch(
    "/users/{user_id}/status",
    response_model=AdminUserDetailResponse,
    summary="Activate or ban user",
    description="Sets the active state of a user. Inactive users cannot log in. Admins cannot ban their own account.",
)
def update_user_status(
    user_id: int,
    data: AdminUserStatusUpdateRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminUserDetailResponse:
    return AdminService.update_user_status(
        db=db,
        user_id=user_id,
        is_active=data.is_active,
        current_admin=current_admin,
    )


@router.delete(
    "/users/{user_id}",
    response_model=GenericMessageResponse,
    summary="Delete user account",
    description="Permanently deletes a user account and cascading data. Admins cannot delete their own account.",
)
def delete_user(
    user_id: int,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> GenericMessageResponse:
    AdminService.delete_user(db=db, user_id=user_id, current_admin=current_admin)
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
    description="Returns all merchant accounts with PENDING approval status awaiting administrator review.",
)
def list_pending_merchants(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> StandardListResponse[MerchantProfileResponse]:
    results, total = MerchantService.search_merchants(
        db=db,
        approval_status="PENDING",
        skip=skip,
        limit=limit,
        public_only=False,
    )
    page = (skip // limit) + 1
    return list_response(
        data=[MerchantProfileResponse.model_validate(m) for m in results],
        total_items=total,
        page=page,
        page_size=limit,
        message=f"Retrieved {len(results)} pending merchant(s)",
    )


@router.get(
    "/merchants",
    response_model=StandardListResponse[MerchantProfileResponse],
    summary="List all merchants (admin view)",
    description="Admin endpoint to list all merchants with filtering by approval status, active state, location, and keywords.",
)
def list_all_merchants_admin(
    approval_status: Optional[str] = Query(None, description="PENDING, APPROVED, or REJECTED"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    is_verified: Optional[bool] = Query(None, description="Filter by verified status"),
    location: Optional[str] = Query(None, description="Filter by location"),
    search: Optional[str] = Query(None, description="Keyword search"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_admin: User = Depends(require_admin),
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
    )
    page = (skip // limit) + 1
    return list_response(
        data=[MerchantProfileResponse.model_validate(m) for m in results],
        total_items=total,
        page=page,
        page_size=limit,
        message=f"Retrieved {len(results)} merchant(s)",
    )


@router.post(
    "/merchants/{merchant_id}/approve",
    response_model=StandardResponse[MerchantProfileResponse],
    summary="Approve a merchant application",
    description="Approves a merchant profile, sets approval_status=APPROVED, is_verified=True, and sends an in-app notification to the merchant.",
)
def approve_merchant(
    merchant_id: int,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> StandardResponse[MerchantProfileResponse]:
    approved = MerchantService.approve_merchant(
        db=db, merchant_id=merchant_id, admin_user=current_admin
    )
    return success_response(
        data=MerchantProfileResponse.model_validate(approved),
        message=f"Merchant '{approved.business_name}' approved successfully",
    )


@router.post(
    "/merchants/{merchant_id}/reject",
    response_model=StandardResponse[MerchantProfileResponse],
    summary="Reject a merchant application",
    description="Rejects a merchant profile with a mandatory reason and sends an in-app notification to the merchant.",
)
def reject_merchant(
    merchant_id: int,
    data: MerchantRejectRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> StandardResponse[MerchantProfileResponse]:
    rejected = MerchantService.reject_merchant(
        db=db,
        merchant_id=merchant_id,
        reason=data.rejection_reason,
        admin_user=current_admin,
    )
    return success_response(
        data=MerchantProfileResponse.model_validate(rejected),
        message=f"Merchant '{rejected.business_name}' rejected",
    )


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
