from datetime import datetime
from typing import List, Optional, Any
from pydantic import BaseModel, ConfigDict, Field


class CustomerRegisterRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, json_schema_extra={"example": "Rahul Sharma"})
    email: Optional[str] = Field(None, json_schema_extra={"example": "rahul@example.com"})
    phone: Optional[str] = Field(None, json_schema_extra={"example": "+91 98765 43210"})
    password: Optional[str] = Field(None, min_length=1, max_length=100, json_schema_extra={"example": "Customer@123"})
    district: Optional[str] = Field(None, max_length=100, json_schema_extra={"example": "Kannur"})
    city: Optional[str] = Field(None, max_length=100, json_schema_extra={"example": "Payyanur"})
    location: Optional[str] = Field(None, max_length=255, json_schema_extra={"example": "Payyanur Town"})
    address: Optional[str] = Field(None, max_length=500, json_schema_extra={"example": "Near Old Bus Stand, Payyanur, Kannur"})
    latitude: Optional[float] = Field(None, json_schema_extra={"example": 12.1001})
    longitude: Optional[float] = Field(None, json_schema_extra={"example": 75.2012})


class CustomerLoginRequest(BaseModel):
    email: Optional[str] = Field(None, json_schema_extra={"example": "rahul@example.com"})
    phone: Optional[str] = Field(None, json_schema_extra={"example": "+91 98765 43210"})
    password: str = Field(..., min_length=1, json_schema_extra={"example": "Customer@123"})


class CustomerPhoneLoginRequest(BaseModel):
    phone: str = Field(..., min_length=7, max_length=25, json_schema_extra={"example": "9847123456"})
    name: Optional[str] = Field(None, max_length=100, json_schema_extra={"example": "Saranya Sudheer"})
    district: Optional[str] = Field(None, max_length=100, json_schema_extra={"example": "Kannur"})
    city: Optional[str] = Field(None, max_length=100, json_schema_extra={"example": "Payyanur"})
    location: Optional[str] = Field(None, max_length=255, json_schema_extra={"example": "Payyanur Town"})
    latitude: Optional[float] = None
    longitude: Optional[float] = None



class CustomerLocationUpdateRequest(BaseModel):
    district: Optional[str] = Field(None, max_length=100)
    city: Optional[str] = Field(None, max_length=100)
    location: Optional[str] = Field(None, max_length=255)
    address: Optional[str] = Field(None, max_length=500)
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class CustomerProfileResponse(BaseModel):
    id: int
    user_code: Optional[str] = None
    name: str
    email: str
    phone: Optional[str] = None
    role: str
    district: Optional[str] = None
    city: Optional[str] = None
    location: Optional[str] = None
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    profile_picture: Optional[str] = None
    status: Optional[str] = "ACTIVE"
    is_active: bool = True
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class CustomerAuthResponse(BaseModel):
    success: bool = True
    message: str
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    customer: CustomerProfileResponse


class NearbyMerchantItem(BaseModel):
    id: int
    user_code: Optional[str] = None
    business_name: str
    category: Optional[str] = None
    categories: List[str] = []
    owner: Optional[str] = None
    phone: Optional[str] = None
    whatsapp: Optional[str] = None
    email: Optional[str] = None
    district: Optional[str] = None
    city: Optional[str] = None
    location: Optional[str] = None
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    distance_km: Optional[float] = None
    rating: Optional[float] = 4.5
    reviews_count: Optional[int] = 0
    photo_1: Optional[str] = None
    merchant_photos: List[str] = []
    video_url: Optional[str] = None
    services: List[str] = []
    service_timing: Optional[str] = None
    status: str = "APPROVED"


class NearbyMerchantsResponse(BaseModel):
    success: bool = True
    total: int
    customer_location: Optional[dict] = None
    merchants: List[NearbyMerchantItem]


class CustomerFavoriteSyncRequest(BaseModel):
    merchant_ids: List[int] = Field(default_factory=list, description="List of merchant IDs from local storage to sync")


class CustomerFavoriteToggleResponse(BaseModel):
    success: bool = True
    message: str
    merchant_id: int
    is_favorite: bool
    favorite_merchant_ids: List[int] = []


class CustomerFavoriteListResponse(BaseModel):
    success: bool = True
    total: int
    favorite_merchant_ids: List[int] = []
    merchants: List[NearbyMerchantItem] = []

