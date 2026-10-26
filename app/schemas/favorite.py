from datetime import datetime
from typing import List
from pydantic import BaseModel, ConfigDict
from app.schemas.logo import LogoResponse
from app.schemas.merchant import MerchantProfileResponse


class FavoriteToggleResponse(BaseModel):
    message: str
    is_favorite: bool
    logo_id: int
    favorites_count: int


class FavoriteCheckResponse(BaseModel):
    logo_id: int
    is_favorite: bool


class FavoriteListResponse(BaseModel):
    items: List[LogoResponse]
    total: int
    skip: int
    limit: int


class MerchantFavoriteListResponse(BaseModel):
    success: bool = True
    message: str = "Favorite merchants retrieved"
    items: List[MerchantProfileResponse] = []
    total: int = 0


class MerchantFavoriteSaveResponse(BaseModel):
    success: bool = True
    message: str
    merchant_id: int
    merchant: MerchantProfileResponse
