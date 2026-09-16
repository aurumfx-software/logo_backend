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

    model_config = ConfigDict(from_attributes=True)


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
