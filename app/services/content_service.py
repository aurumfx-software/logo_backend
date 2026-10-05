from datetime import datetime, timezone
from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.db.models.content import Announcement, AppPolicy, PushNotification
from app.schemas.content import (
    AnnouncementCreateRequest,
    AnnouncementUpdateRequest,
    AppPolicyUpdateRequest,
    PushNotificationCreateRequest,
)


class ContentService:
    # --- Policies ---
    @staticmethod
    def get_all_policies(db: Session) -> List[AppPolicy]:
        return db.query(AppPolicy).all()

    @staticmethod
    def get_policy(db: Session, key: str) -> AppPolicy:
        policy = db.query(AppPolicy).filter(AppPolicy.key == key).first()
        if not policy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Policy with key '{key}' not found",
            )
        return policy

    @staticmethod
    def update_policy(db: Session, key: str, data: AppPolicyUpdateRequest) -> AppPolicy:
        policy = db.query(AppPolicy).filter(AppPolicy.key == key).first()
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if not policy:
            policy = AppPolicy(
                key=key,
                label=data.label or key.replace("_", " ").title(),
                content=data.content,
                last_updated=now_str,
            )
            db.add(policy)
        else:
            if data.label:
                policy.label = data.label
            policy.content = data.content
            policy.last_updated = now_str

        db.commit()
        db.refresh(policy)
        return policy

    # --- Notifications ---
    @staticmethod
    def get_all_notifications(db: Session) -> List[PushNotification]:
        return db.query(PushNotification).order_by(PushNotification.id.desc()).all()

    @staticmethod
    def create_notification(db: Session, data: PushNotificationCreateRequest) -> PushNotification:
        notification = PushNotification(
            title=data.title,
            message=data.message,
            status=data.status or "active",
            sent=data.sent or "0",
        )
        db.add(notification)
        db.commit()
        db.refresh(notification)
        return notification

    @staticmethod
    def delete_notification(db: Session, notification_id: int) -> bool:
        item = db.query(PushNotification).filter(PushNotification.id == notification_id).first()
        if not item:
            raise HTTPException(status_code=404, detail="Notification not found")
        db.delete(item)
        db.commit()
        return True

    # --- Announcements ---
    @staticmethod
    def get_all_announcements(db: Session) -> List[Announcement]:
        return db.query(Announcement).order_by(Announcement.pinned.desc(), Announcement.id.desc()).all()

    @staticmethod
    def create_announcement(db: Session, data: AnnouncementCreateRequest) -> Announcement:
        date_str = data.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        announcement = Announcement(
            title=data.title,
            message=data.message,
            date=date_str,
            pinned=data.pinned or False,
        )
        db.add(announcement)
        db.commit()
        db.refresh(announcement)
        return announcement

    @staticmethod
    def update_announcement(db: Session, announcement_id: int, data: AnnouncementUpdateRequest) -> Announcement:
        item = db.query(Announcement).filter(Announcement.id == announcement_id).first()
        if not item:
            raise HTTPException(status_code=404, detail="Announcement not found")
        if data.title is not None:
            item.title = data.title
        if data.message is not None:
            item.message = data.message
        if data.date is not None:
            item.date = data.date
        if data.pinned is not None:
            item.pinned = data.pinned
        db.commit()
        db.refresh(item)
        return item

    @staticmethod
    def delete_announcement(db: Session, announcement_id: int) -> bool:
        item = db.query(Announcement).filter(Announcement.id == announcement_id).first()
        if not item:
            raise HTTPException(status_code=404, detail="Announcement not found")
        db.delete(item)
        db.commit()
        return True
