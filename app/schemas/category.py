from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class CategoryCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100, json_schema_extra={"example": "Restaurant & Dining"})
    slug: Optional[str] = Field(None, max_length=120, json_schema_extra={"example": "restaurant-and-dining"})
    description: Optional[str] = Field(None, max_length=500, json_schema_extra={"example": "Logos for dining and hospitality brands"})
    icon_url: Optional[str] = Field(None, max_length=500, json_schema_extra={"example": "https://example.com/icons/dining.svg"})
    is_active: bool = Field(True, json_schema_extra={"example": True})


class CategoryUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    slug: Optional[str] = Field(None, max_length=120)
    description: Optional[str] = Field(None, max_length=500)
    icon_url: Optional[str] = Field(None, max_length=500)
    is_active: Optional[bool] = None


class CategoryResponse(BaseModel):
    id: int
    name: str
    slug: str
    description: Optional[str] = None
    icon_url: Optional[str] = None
    is_active: bool
    logo_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CategoryListResponse(BaseModel):
    items: List[CategoryResponse]
    total: int
