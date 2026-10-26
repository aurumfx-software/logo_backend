from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class PromotionResponse(BaseModel):
    id: int
    title: str
    subtitle: Optional[str] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    link_url: Optional[str] = None
    discount_label: Optional[str] = None
    promo_code: Optional[str] = None
    merchant_profile_id: Optional[int] = None
    status: str
    is_active: bool
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    priority: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PromotionListResponse(BaseModel):
    items: List[PromotionResponse]
    total: int
