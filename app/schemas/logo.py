from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class LogoCategoryBrief(BaseModel):
    id: int
    name: str
    slug: str

    model_config = ConfigDict(from_attributes=True)


class LogoUserBrief(BaseModel):
    id: int
    name: str
    email: str
    role: str

    model_config = ConfigDict(from_attributes=True)


class LogoCreateRequest(BaseModel):
    title: str = Field(..., min_length=2, max_length=255, json_schema_extra={"example": "Vertex Modern Tech Logo"})
    description: Optional[str] = Field(None, max_length=1000, json_schema_extra={"example": "A sleek, geometric tech brand logo with gradient tones."})
    image_url: str = Field(..., min_length=5, max_length=500, json_schema_extra={"example": "/static/logos/vertex.png"})
    tags: Optional[List[str]] = Field(default_factory=list, json_schema_extra={"example": ["minimal", "tech", "vector"]})
    category_id: Optional[int] = Field(None, json_schema_extra={"example": 1})


class LogoUpdateRequest(BaseModel):
    title: Optional[str] = Field(None, min_length=2, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    image_url: Optional[str] = Field(None, min_length=5, max_length=500)
    tags: Optional[List[str]] = None
    category_id: Optional[int] = None


class LogoRejectRequest(BaseModel):
    rejection_reason: str = Field(
        ...,
        min_length=3,
        max_length=500,
        json_schema_extra={"example": "Image resolution is below 500x500 px. Please upload high-res asset."},
    )


class LogoResponse(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    image_url: str
    tags: List[str] = []
    category_id: Optional[int] = None
    category: Optional[LogoCategoryBrief] = None
    submitted_by_id: int
    submitted_by: Optional[LogoUserBrief] = None
    status: str
    rejection_reason: Optional[str] = None
    reviewed_by_id: Optional[int] = None
    reviewed_at: Optional[datetime] = None
    views_count: int = 0
    favorites_count: int = 0
    is_favorite: Optional[bool] = False
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LogoListResponse(BaseModel):
    items: List[LogoResponse]
    total: int
    skip: int
    limit: int


class LogoUploadResponse(BaseModel):
    message: str
    image_url: str
