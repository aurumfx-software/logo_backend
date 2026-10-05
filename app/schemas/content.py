from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class AppPolicyResponse(BaseModel):
    id: int
    key: str
    label: str
    content: str
    last_updated: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AppPolicyUpdateRequest(BaseModel):
    label: Optional[str] = None
    content: str = Field(..., min_length=5)


class PushNotificationCreateRequest(BaseModel):
    title: str = Field(..., min_length=2, max_length=255)
    message: str = Field(..., min_length=2)
    status: Optional[str] = "active"  # active, scheduled, sent
    sent: Optional[str] = "0"


class PushNotificationResponse(BaseModel):
    id: int
    title: str
    message: str
    status: str
    sent: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AnnouncementCreateRequest(BaseModel):
    title: str = Field(..., min_length=2, max_length=255)
    message: str = Field(..., min_length=2)
    date: Optional[str] = None
    pinned: Optional[bool] = False


class AnnouncementUpdateRequest(BaseModel):
    title: Optional[str] = None
    message: Optional[str] = None
    date: Optional[str] = None
    pinned: Optional[bool] = None


class AnnouncementResponse(BaseModel):
    id: int
    title: str
    message: str
    date: Optional[str] = None
    pinned: bool
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
