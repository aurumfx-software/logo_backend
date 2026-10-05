from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class GeographyRegionCreateRequest(BaseModel):
    city: str = Field(..., min_length=2, max_length=100)
    state: str = Field(..., min_length=2, max_length=100)
    zones: Optional[int] = 1
    merchants: Optional[int] = 0
    users: Optional[int] = 0
    status: Optional[str] = "active"  # active, pending, inactive


class GeographyRegionUpdateRequest(BaseModel):
    city: Optional[str] = None
    state: Optional[str] = None
    zones: Optional[int] = None
    merchants: Optional[int] = None
    users: Optional[int] = None
    status: Optional[str] = None


class GeographyRegionResponse(BaseModel):
    id: int
    geo_code: Optional[str] = None
    city: str
    state: str
    zones: int
    merchants: int
    users: int
    status: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class GeographySummaryResponse(BaseModel):
    total_cities: int
    active_cities: int
    total_zones: int
