from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.database import get_db
from app.db.models.user import User
from app.schemas.notification import (
    NotificationCountResponse,
    NotificationResponse,
)
from app.schemas.response import (
    StandardListResponse,
    StandardResponse,
    list_response,
    success_response,
)
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get(
    "",
    response_model=StandardListResponse[NotificationResponse],
    summary="List current user notifications",
    description="Returns notifications for the authenticated user, optionally filtered by read status with pagination.",
)
def get_my_notifications(
    is_read: Optional[bool] = Query(None, description="Filter by read status (true/false)"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StandardListResponse[NotificationResponse]:
    items, total, unread_count = NotificationService.get_user_notifications(
        db=db,
        user_id=current_user.id,
        is_read=is_read,
        skip=skip,
        limit=limit,
    )
    page = (skip // limit) + 1 if limit > 0 else 1
    return list_response(
        data=[NotificationResponse.model_validate(n) for n in items],
        total_items=total,
        page=page,
        page_size=limit,
        message=f"Retrieved {len(items)} notification(s)",
    )


@router.get(
    "/unread-count",
    response_model=StandardResponse[NotificationCountResponse],
    summary="Get unread notification count",
    description="Returns the total number of unread notifications for badge indicators.",
)
def get_unread_count(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StandardResponse[NotificationCountResponse]:
    count = NotificationService.get_unread_count(db=db, user_id=current_user.id)
    return success_response(
        data=NotificationCountResponse(unread_count=count),
        message="Unread notification count retrieved",
    )


@router.patch(
    "/{notification_id}/read",
    response_model=StandardResponse[NotificationResponse],
    summary="Mark notification as read",
    description="Marks a specific notification as read for the authenticated user.",
)
def mark_notification_as_read(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StandardResponse[NotificationResponse]:
    notification = NotificationService.mark_as_read(
        db=db,
        notification_id=notification_id,
        user_id=current_user.id,
    )
    return success_response(
        data=NotificationResponse.model_validate(notification),
        message="Notification marked as read",
    )


@router.patch(
    "/read-all",
    response_model=StandardResponse[dict],
    summary="Mark all notifications as read",
    description="Marks all unread notifications as read for the authenticated user.",
)
@router.post(
    "/mark-all-read",
    response_model=StandardResponse[dict],
    summary="Mark all notifications as read (POST alias)",
    description="Marks all unread notifications as read for the authenticated user.",
)
def mark_all_notifications_as_read(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StandardResponse[dict]:
    updated_count = NotificationService.mark_all_as_read(
        db=db,
        user_id=current_user.id,
    )
    return success_response(
        data={"updated_count": updated_count},
        message=f"Marked {updated_count} notification(s) as read",
    )


@router.delete(
    "/{notification_id}",
    response_model=StandardResponse[dict],
    summary="Delete a notification",
    description="Permanently removes a notification belonging to the authenticated user.",
)
def delete_notification(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StandardResponse[dict]:
    NotificationService.delete_notification(
        db=db,
        notification_id=notification_id,
        user_id=current_user.id,
    )
    return success_response(
        data={"deleted_id": notification_id},
        message="Notification successfully deleted",
    )
