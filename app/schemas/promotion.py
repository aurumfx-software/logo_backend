from datetime import datetime
from typing import Any, List, Optional
from pydantic import BaseModel, Field, model_validator


PROMOTION_TYPE_OPTIONS: List[str] = [
    "Featured",
    "Sponsored",
    "Banner",
    "Promotion",
    "Text Carousel",
]

PROMOTION_PLACEMENT_OPTIONS: List[str] = [
    "Home Top",
    "Middle Banner",
    "Footer Strip",
    "Category Page",
    "Moving Ticker",
    "Merchant Store",
]

PROMOTION_MEDIA_TYPE_OPTIONS: List[str] = ["image", "video", "text"]


def _normalize_promotion_type_aliases(data: Any) -> Any:
    if isinstance(data, dict):
        for alias in ("option_type", "optionType", "promotion_type", "promotionType"):
            if alias in data and not data.get("type"):
                data["type"] = data[alias]
        camel_map = {
            "mediaType": "media_type",
            "imageUrl": "image_url",
            "videoUrl": "video_url",
            "thumbnailUrl": "thumbnail_url",
            "targetUrl": "target_url",
            "merchantId": "merchant_id",
            "merchantName": "merchant_name",
            "bgColor": "bg_color",
            "textColor": "text_color",
            "startDate": "start_date",
            "endDate": "end_date",
        }
        for camel, snake in camel_map.items():
            if camel in data and data.get(snake) is None:
                data[snake] = data[camel]
    return data


class PromotionOptionTypesResponse(BaseModel):
    types: List[str]
    option_types: List[str]
    placements: List[str]
    media_types: List[str]


class PromotionCreateRequest(BaseModel):
    title: str = Field(..., min_length=2, max_length=255)
    category: Optional[str] = "Solar & Electricals"
    type: Optional[str] = "Featured"  # Featured, Sponsored, Banner, Promotion

    @model_validator(mode="before")
    @classmethod
    def normalize_type_aliases(cls, data: Any) -> Any:
        return _normalize_promotion_type_aliases(data)
    placement: Optional[str] = "Home Top"
    location: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    status: Optional[str] = "active"
    impressions: Optional[int] = 0
    clicks: Optional[int] = 0
    image_url: Optional[str] = None
    video_url: Optional[str] = None
    media_type: Optional[str] = "image"  # image, video, text
    bg_color: Optional[str] = None
    text_color: Optional[str] = None
    thumbnail_url: Optional[str] = None
    target_url: Optional[str] = None
    description: Optional[str] = None
    merchant_id: Optional[int] = None
    merchant_name: Optional[str] = None


class PromotionUpdateRequest(BaseModel):
    title: Optional[str] = None
    category: Optional[str] = None
    type: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_type_aliases(cls, data: Any) -> Any:
        return _normalize_promotion_type_aliases(data)
    placement: Optional[str] = None
    location: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    status: Optional[str] = None
    impressions: Optional[int] = None
    clicks: Optional[int] = None
    image_url: Optional[str] = None
    video_url: Optional[str] = None
    media_type: Optional[str] = None
    bg_color: Optional[str] = None
    text_color: Optional[str] = None
    thumbnail_url: Optional[str] = None
    target_url: Optional[str] = None
    description: Optional[str] = None
    merchant_id: Optional[int] = None
    merchant_name: Optional[str] = None
    rejection_reason: Optional[str] = None


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
    video_url: Optional[str] = None
    media_type: Optional[str] = "image"
    bg_color: Optional[str] = None
    text_color: Optional[str] = None
    thumbnail_url: Optional[str] = None
    target_url: Optional[str] = None
    description: Optional[str] = None
    merchant_id: Optional[int] = None
    merchant_name: Optional[str] = None
    rejection_reason: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
