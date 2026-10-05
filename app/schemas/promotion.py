from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class PromotionCreateRequest(BaseModel):
    title: str = Field(..., min_length=2, max_length=255)
    category: Optional[str] = "Solar & Electricals"
    type: Optional[str] = "Featured"  # Featured, Sponsored, Banner, Promotion
    placement: Optional[str] = "Home Top"
    location: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    status: Optional[str] = "active"
    impressions: Optional[int] = 0
    clicks: Optional[int] = 0
    image_url: Optional[str] = None
    target_url: Optional[str] = None


class PromotionUpdateRequest(BaseModel):
    title: Optional[str] = None
    category: Optional[str] = None
    type: Optional[str] = None
    placement: Optional[str] = None
    location: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    status: Optional[str] = None
    impressions: Optional[int] = None
    clicks: Optional[int] = None
    image_url: Optional[str] = None
    target_url: Optional[str] = None


class PromotionResponse(BaseModel):
    id: int
    promo_code: Optional[str] = None
    title: str
    category: Optional[str] = None
    type: str
    placement: Optional[str] = None
    location: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    status: str
    impressions: int
    clicks: int
    image_url: Optional[str] = None
    target_url: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
