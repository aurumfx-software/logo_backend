import re
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.schemas.auth import SafeUserResponse

EMAIL_REGEX = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"


class MerchantRegisterRequest(BaseModel):
    # Account login details
    name: str = Field(..., min_length=2, max_length=100, json_schema_extra={"example": "Rajesh Kumar"})
    email: str = Field(..., json_schema_extra={"example": "rajesh.salon@example.com"})
    password: str = Field(..., min_length=8, max_length=100, json_schema_extra={"example": "MerchantPass123"})

    # Merchant business details
    business_name: str = Field(..., min_length=2, max_length=255, json_schema_extra={"example": "Royal Unisex Salon & Spa"})
    categories: List[str] = Field(..., min_length=1, json_schema_extra={"example": ["Salon", "Spa", "Beauty & Wellness"]})
    location: str = Field(..., min_length=2, max_length=255, json_schema_extra={"example": "Edappally, Kochi"})
    services: List[str] = Field(..., min_length=1, json_schema_extra={"example": ["Haircut", "Hair Spa", "Facial", "Beard Styling"]})
    service_timing: str = Field(..., max_length=255, json_schema_extra={"example": "Mon-Sun: 09:00 AM - 09:00 PM"})
    merchant_photos: Optional[List[str]] = Field(default_factory=list, json_schema_extra={"example": ["https://example.com/photos/store1.jpg"]})
    contact_number: str = Field(..., min_length=7, max_length=50, json_schema_extra={"example": "9876543210"})
    address: str = Field(..., min_length=5, max_length=500, json_schema_extra={"example": "Door No 14/204, Toll Junction, Edappally, Kochi - 682024"})

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        clean_email = v.strip().lower()
        if not re.match(EMAIL_REGEX, clean_email):
            raise ValueError("Invalid email format")
        return clean_email

    @field_validator("contact_number")
    @classmethod
    def validate_contact(cls, v: str) -> str:
        cleaned = re.sub(r"[\s\-()]", "", v)
        if not cleaned.isdigit():
            raise ValueError("Contact number must contain only digits")
        return cleaned


from datetime import datetime


class MerchantProfileResponse(BaseModel):
    id: int
    user_id: int
    business_name: str
    categories: List[str]
    location: str
    services: List[str]
    service_timing: str
    merchant_photos: List[str]
    contact_number: str
    address: str
    is_verified: bool
    approval_status: str = "PENDING"
    rejection_reason: Optional[str] = None
    approved_by_id: Optional[int] = None
    approved_at: Optional[datetime] = None
    is_active: bool = True

    model_config = ConfigDict(from_attributes=True)


class MerchantRejectRequest(BaseModel):
    rejection_reason: str = Field(
        ...,
        min_length=3,
        max_length=500,
        json_schema_extra={"example": "Invalid business license or contact details not reachable."},
    )


class LocationCountItem(BaseModel):
    location: str
    count: int


class CategoryCountItem(BaseModel):
    category: str
    count: int


class ServiceCountItem(BaseModel):
    service: str
    count: int


class MerchantStatsResponse(BaseModel):
    total_merchants: int
    active_merchants: int
    inactive_merchants: int
    pending_merchants: int
    approved_merchants: int
    rejected_merchants: int
    verified_merchants: int
    unverified_merchants: int
    top_locations: List[LocationCountItem] = []
    top_categories: List[CategoryCountItem] = []
    recent_registrations_7d: int = 0
    recent_registrations_30d: int = 0


class MerchantDiscoveryMetaResponse(BaseModel):
    locations: List[str]
    services: List[str]
    categories: List[str]


class MerchantRegisterResponse(BaseModel):
    message: str
    user: SafeUserResponse
    merchant: MerchantProfileResponse


class MerchantUpdateRequest(BaseModel):
    business_name: Optional[str] = Field(None, min_length=2, max_length=255)
    categories: Optional[List[str]] = None
    location: Optional[str] = Field(None, min_length=2, max_length=255)
    services: Optional[List[str]] = None
    service_timing: Optional[str] = Field(None, max_length=255)
    merchant_photos: Optional[List[str]] = None
    contact_number: Optional[str] = None
    address: Optional[str] = Field(None, min_length=5, max_length=500)


class MerchantPhotosUploadResponse(BaseModel):
    message: str
    uploaded_photo_urls: List[str]
    total_photos: List[str]


# ── Merchant OTP Login ──────────────────────────────────────────────────────

class MerchantLoginOTPRequest(BaseModel):
    """Step 1: Merchant requests an OTP to log in."""
    email: str = Field(..., json_schema_extra={"example": "rajesh.salon@example.com"})

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        clean_email = v.strip().lower()
        if not re.match(EMAIL_REGEX, clean_email):
            raise ValueError("Invalid email format")
        return clean_email


class MerchantLoginOTPResponse(BaseModel):
    """Response after a successful OTP dispatch."""
    message: str
    expires_in_minutes: int
    dev_otp: Optional[str] = None  # Only populated in development environment


class MerchantVerifyOTPLoginRequest(BaseModel):
    """Step 2: Merchant submits OTP to complete login and receive JWT tokens."""
    email: str = Field(..., json_schema_extra={"example": "rajesh.salon@example.com"})
    otp: str = Field(..., min_length=6, max_length=6, json_schema_extra={"example": "482910"})

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        clean_email = v.strip().lower()
        if not re.match(EMAIL_REGEX, clean_email):
            raise ValueError("Invalid email format")
        return clean_email

