from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator


class AdvertisementCreateRequest(BaseModel):
    title: str = Field(..., min_length=2, max_length=255)
    description: Optional[str] = None
    image_url: Optional[str] = None
    video_url: Optional[str] = None
    link_url: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    status: Optional[str] = "active"

    @model_validator(mode="before")
    @classmethod
    def status_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict) and "is_active" in data and not data.get("status"):
            data["status"] = "active" if data.get("is_active") else "inactive"
        return data


class AdvertisementUpdateRequest(BaseModel):
    title: Optional[str] = Field(None, min_length=2, max_length=255)
    description: Optional[str] = None
    image_url: Optional[str] = None
    video_url: Optional[str] = None
    link_url: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    status: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def status_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict) and "is_active" in data and not data.get("status"):
            data["status"] = "active" if data.get("is_active") else "inactive"
        return data


class AdvertisementResponse(BaseModel):
    id: int
    merchant_id: int
    title: str
    description: Optional[str] = None
    image_url: Optional[str] = None
    video_url: Optional[str] = None
    link_url: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    status: str
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
