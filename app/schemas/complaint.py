from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class ComplaintCreateRequest(BaseModel):
    user: Optional[str] = Field(None, max_length=255)
    merchant: str = Field(..., min_length=1, max_length=255)
    subject: str = Field(..., min_length=1, max_length=255)
    category: Optional[str] = "Service Quality"
    priority: Optional[str] = "medium"  # high, medium, low
    status: Optional[str] = "open"  # open, in-progress, resolved
    date: Optional[str] = None
    description: Optional[str] = None
    user_email: Optional[str] = None
    user_phone: Optional[str] = None


class ComplaintUpdateRequest(BaseModel):
    user: Optional[str] = None
    user_email: Optional[str] = None
    user_phone: Optional[str] = None
    merchant: Optional[str] = None
    subject: Optional[str] = None
    category: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    description: Optional[str] = None
    admin_response: Optional[str] = None


class ComplaintResolveRequest(BaseModel):
    admin_response: Optional[str] = None
    status: Optional[str] = "resolved"


ComplaintFixRequest = ComplaintResolveRequest


class ComplaintStatusUpdateRequest(BaseModel):
    status: str = Field(..., description="open, in-progress, resolved, closed")
    admin_response: Optional[str] = None


class ComplaintResponse(BaseModel):
    id: int
    complaint_code: Optional[str] = None
    user: str
    user_email: Optional[str] = None
    user_phone: Optional[str] = None
    merchant: str
    subject: str
    category: str
    priority: str
    status: str
    date: Optional[str] = None
    description: Optional[str] = None
    admin_response: Optional[str] = None
    resolved_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
