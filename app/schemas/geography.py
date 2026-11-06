from typing import List, Optional

from pydantic import BaseModel, Field


class GeographyCards(BaseModel):
    kerala_districts_covered: int = 14
    kerala_districts_total: int = 14
    kerala_districts_percent: float = 100
    districts_with_merchants: int = 0
    active_municipalities: int = 0
    real_merchants: int = 0
    verified_merchants: int = 0
    active_users_reach: int = 0


class GeographyDistrictItem(BaseModel):
    name: str
    merchants: int = 0
    customers: int = 0
    towns: int = 0
    covered: bool = False


class GeographyTownItem(BaseModel):
    id: Optional[int] = None
    district: str
    town: str
    zones: List[str] = Field(default_factory=list)
    registered_merchants: int = 0
    customer_reach: int = 0
    coverage_status: str


class GeographyTownCreateRequest(BaseModel):
    district: str = Field(..., min_length=2, max_length=100)
    town: str = Field(..., min_length=2, max_length=150)
    zones: List[str] = Field(default_factory=list)


class GeographyResponse(BaseModel):
    success: bool = True
    message: str = "Geography retrieved"
    cards: GeographyCards
    districts: List[GeographyDistrictItem] = Field(default_factory=list)
    towns: List[GeographyTownItem] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20
