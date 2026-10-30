from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.models.user import UserRole


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

    @field_validator("role", mode="before")
    @classmethod
    def role_to_str(cls, v):
        if isinstance(v, UserRole):
            return v.value
        return UserRole.coerce(v).value if v is not None else UserRole.FIELD_STAFF.value

    @field_validator("latitude", "longitude", mode="before")
    @classmethod
    def decimal_to_float(cls, v):
        if v is None or isinstance(v, float):
            return v
        if isinstance(v, Decimal):
            return float(v)
        return float(v)
