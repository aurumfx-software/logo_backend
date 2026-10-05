from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_admin_user_flexible
from app.db.database import get_db
from app.db.models.user import User
from app.schemas.content import (
    AnnouncementCreateRequest,
    AnnouncementResponse,
    AnnouncementUpdateRequest,
    AppPolicyResponse,
    AppPolicyUpdateRequest,
    PushNotificationCreateRequest,
    PushNotificationResponse,
)
from app.schemas.response import (
    StandardListResponse,
    StandardResponse,
    list_response,
    success_response,
)
from app.services.content_service import ContentService

router = APIRouter(prefix="/content", tags=["Content Management"])


# --- App Policies (Terms, Privacy, etc.) ---
@router.get("/policies", response_model=StandardListResponse[AppPolicyResponse], summary="List all static policies")
def list_policies(
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user_flexible),
):
    policies = ContentService.get_all_policies(db)
    return list_response(
        data=[AppPolicyResponse.model_validate(p) for p in policies],
        total_items=len(policies),
        message="Policies retrieved successfully",
    )


@router.get("/policies/{key}", response_model=StandardResponse[AppPolicyResponse], summary="Get policy by key")
def get_policy(
    key: str,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user_flexible),
):
    policy = ContentService.get_policy(db, key)
    return success_response(
        data=AppPolicyResponse.model_validate(policy),
        message="Policy retrieved successfully",
    )


@router.put("/policies/{key}", response_model=StandardResponse[AppPolicyResponse], summary="Update policy by key")
def update_policy(
    key: str,
    payload: AppPolicyUpdateRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user_flexible),
):
    policy = ContentService.update_policy(db, key, payload)
    return success_response(
        data=AppPolicyResponse.model_validate(policy),
        message="Policy updated successfully",
    )


# --- Push Notifications ---
@router.get("/notifications", response_model=StandardListResponse[PushNotificationResponse], summary="List push notifications")
def list_notifications(
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user_flexible),
):
    notifications = ContentService.get_all_notifications(db)
    return list_response(
        data=[PushNotificationResponse.model_validate(n) for n in notifications],
        total_items=len(notifications),
        message="Notifications retrieved successfully",
    )


@router.post("/notifications", response_model=StandardResponse[PushNotificationResponse], status_code=status.HTTP_201_CREATED, summary="Create push notification")
def create_notification(
    payload: PushNotificationCreateRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user_flexible),
):
    notification = ContentService.create_notification(db, payload)
    return success_response(
        data=PushNotificationResponse.model_validate(notification),
        message="Notification created successfully",
    )


@router.delete("/notifications/{notification_id}", response_model=StandardResponse[bool], summary="Delete push notification")
def delete_notification(
    notification_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user_flexible),
):
    ContentService.delete_notification(db, notification_id)
    return success_response(
        data=True,
        message="Notification deleted successfully",
    )


# --- Announcements ---
@router.get("/announcements", response_model=StandardListResponse[AnnouncementResponse], summary="List announcements")
def list_announcements(
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user_flexible),
):
    announcements = ContentService.get_all_announcements(db)
    return list_response(
        data=[AnnouncementResponse.model_validate(a) for a in announcements],
        total_items=len(announcements),
        message="Announcements retrieved successfully",
    )


@router.post("/announcements", response_model=StandardResponse[AnnouncementResponse], status_code=status.HTTP_201_CREATED, summary="Create announcement")
def create_announcement(
    payload: AnnouncementCreateRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user_flexible),
):
    announcement = ContentService.create_announcement(db, payload)
    return success_response(
        data=AnnouncementResponse.model_validate(announcement),
        message="Announcement created successfully",
    )


@router.put("/announcements/{announcement_id}", response_model=StandardResponse[AnnouncementResponse], summary="Update announcement")
def update_announcement(
    announcement_id: int,
    payload: AnnouncementUpdateRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user_flexible),
):
    announcement = ContentService.update_announcement(db, announcement_id, payload)
    return success_response(
        data=AnnouncementResponse.model_validate(announcement),
        message="Announcement updated successfully",
    )


@router.delete("/announcements/{announcement_id}", response_model=StandardResponse[bool], summary="Delete announcement")
def delete_announcement(
    announcement_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user_flexible),
):
    ContentService.delete_announcement(db, announcement_id)
    return success_response(
        data=True,
        message="Announcement deleted successfully",
    )
