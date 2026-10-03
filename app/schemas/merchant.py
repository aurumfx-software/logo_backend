import re
from typing import Any, List, Optional, Union
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
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


class MerchantCreatorSummary(BaseModel):
    id: int
    user_code: Optional[str] = None
    name: str
    email: str
    phone: Optional[str] = None
    role: str

    model_config = ConfigDict(from_attributes=True)


class MerchantProfileResponse(BaseModel):
    id: int
    user_id: int
    user_code: Optional[str] = None
    business_name: str
    owner: Optional[str] = None
    owner_name: Optional[str] = None
    category: Optional[str] = None
    categories: List[str] = []
    district: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    location: Optional[str] = None
    landmark: Optional[str] = None
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    phone: Optional[str] = None
    whatsapp: Optional[str] = None
    landline: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    facebook: Optional[str] = None
    instagram: Optional[str] = None
    twitter: Optional[str] = None
    youtube: Optional[str] = None
    photo_1: Optional[str] = None
    photo_2: Optional[str] = None
    photo_3: Optional[str] = None
    photo_4: Optional[str] = None
    photo_5: Optional[str] = None
    photo_6: Optional[str] = None
    about: Optional[str] = None
    rating: Optional[float] = 0.0
    reviews_count: Optional[int] = 0
    key_highlights: Optional[List[str]] = []
    video_url: Optional[str] = None
    status: str = "PENDING"
    approval_status: str = "PENDING"
    contact_number: Optional[str] = None
    services: Optional[List[str]] = []
    service_timing: Optional[str] = None
    merchant_photos: List[str] = []
    merchant_videos: List[str] = []
    verification_documents: List[str] = []
    is_verified: bool = False
    rejection_reason: Optional[str] = None
    approved_by_id: Optional[int] = None
    approved_at: Optional[datetime] = None
    onboarded_by_id: Optional[int] = None
    creator: Optional[MerchantCreatorSummary] = None
    created_by: Optional[MerchantCreatorSummary] = None
    is_active: bool = True

    model_config = ConfigDict(from_attributes=True)


class MerchantOnboardingRequest(BaseModel):
    user_id: Optional[Union[int, str]] = Field(None, description="Creator user ID (Field Staff / Admin)", json_schema_extra={"example": 1})
    user_code: Optional[str] = Field(None, description="Creator user code (e.g. FLS_1, ADM_1)", json_schema_extra={"example": "FLS_1"})
    # Form fields matching new schema
    business_name: str = Field(..., min_length=2, max_length=255, json_schema_extra={"example": "Royal Grand Bakery"})
    owner: Optional[str] = Field(None, max_length=255, json_schema_extra={"example": "Rajesh Sharma"})
    owner_name: Optional[str] = Field(None, max_length=255, json_schema_extra={"example": "Rajesh Sharma"})
    contact_person: Optional[str] = Field(None, json_schema_extra={"example": "Rajesh Sharma"})
    category: Optional[str] = Field(None, max_length=150, json_schema_extra={"example": "Food & Dining"})
    categories: Optional[List[str]] = Field(None, json_schema_extra={"example": ["Food & Dining"]})

    # Location fields
    address: Optional[str] = Field(None, max_length=500, json_schema_extra={"example": "Shop #12, 100ft Road, Near Metro Station"})
    city: Optional[str] = Field(None, max_length=100, json_schema_extra={"example": "Bangalore"})
    district: Optional[str] = Field(None, max_length=100, json_schema_extra={"example": "Bangalore Urban"})
    state: Optional[str] = Field(None, max_length=100, json_schema_extra={"example": "Karnataka"})
    location: Optional[str] = Field(None, max_length=255, json_schema_extra={"example": "Indiranagar"})
    city_region: Optional[str] = Field(None, max_length=255, json_schema_extra={"example": "Bangalore"})
    landmark: Optional[str] = Field(None, max_length=255, json_schema_extra={"example": "Near Metro Station"})

    # Geo coordinates
    latitude: Optional[float] = Field(None, json_schema_extra={"example": 12.9716})
    longitude: Optional[float] = Field(None, json_schema_extra={"example": 77.5946})

    # Contact fields
    phone: Optional[str] = Field(None, max_length=20, json_schema_extra={"example": "9876543210"})
    phone_number: Optional[str] = Field(None, json_schema_extra={"example": "+91 98765 43210"})
    contact_number: Optional[str] = Field(None, json_schema_extra={"example": "9876543210"})
    whatsapp: Optional[str] = Field(None, max_length=20, json_schema_extra={"example": "9876543210"})
    landline: Optional[str] = Field(None, max_length=20, json_schema_extra={"example": "0484234567"})
    email: Optional[str] = Field(None, max_length=255, json_schema_extra={"example": "owner@business.com"})

    # Social & Web links
    website: Optional[str] = Field(None, max_length=255, json_schema_extra={"example": "https://example.com"})
    facebook: Optional[str] = Field(None, max_length=255, json_schema_extra={"example": "https://facebook.com/business"})
    instagram: Optional[str] = Field(None, max_length=255, json_schema_extra={"example": "https://instagram.com/business"})
    twitter: Optional[str] = Field(None, max_length=255, json_schema_extra={"example": "https://twitter.com/business"})
    youtube: Optional[str] = Field(None, max_length=255, json_schema_extra={"example": "https://youtube.com/@business"})

    # About, Rating & Highlights
    about: Optional[str] = None
    description: Optional[str] = None
    rating: Optional[float] = None
    reviews_count: Optional[int] = None
    key_highlights: Optional[List[str]] = Field(default_factory=list)
    google_maps_url: Optional[str] = None

    # Media fields
    photo_1: Optional[str] = None
    photo_2: Optional[str] = None
    photo_3: Optional[str] = None
    photo_4: Optional[str] = None
    photo_5: Optional[str] = None
    photo_6: Optional[str] = None
    photos: Optional[List[str]] = Field(default_factory=list)
    video_url: Optional[str] = None
    merchant_photos: Optional[List[str]] = Field(default_factory=list)
    verification_documents: Optional[List[str]] = Field(default_factory=list)
    merchant_videos: Optional[List[str]] = Field(default_factory=list)

    # Status & Auxiliary
    status: Optional[str] = Field("PENDING", max_length=50)
    services: Optional[List[str]] = Field(default_factory=list)
    service_timing: Optional[str] = Field("General Store Hours")

    @model_validator(mode="before")
    @classmethod
    def normalize_onboarding_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Normalize business_name / name
            if not data.get("business_name") and data.get("name"):
                data["business_name"] = str(data["name"]).strip()
            elif not data.get("name") and data.get("business_name"):
                data["name"] = str(data["business_name"]).strip()

            # Normalize user_id
            if "user_id" in data and data["user_id"] is not None:
                try:
                    data["user_id"] = int(str(data["user_id"]).strip())
                except (ValueError, TypeError):
                    if not data.get("user_code"):
                        data["user_code"] = str(data["user_id"]).strip()
                    data["user_id"] = None

            # Normalize owner
            if not data.get("owner"):
                data["owner"] = data.get("owner_name") or data.get("contact_person") or "Business Owner"
            if not data.get("owner_name"):
                data["owner_name"] = data["owner"]

            # Normalize phone
            phone_val = data.get("phone") or data.get("phone_number") or data.get("contact_number") or "0000000000"
            data["phone"] = phone_val
            data["phone_number"] = phone_val
            data["contact_number"] = phone_val

            # Normalize about / description
            if not data.get("about") and data.get("description"):
                data["about"] = data["description"]
            elif not data.get("description") and data.get("about"):
                data["description"] = data["about"]

            # Normalize photos
            if data.get("photos") and not data.get("merchant_photos"):
                data["merchant_photos"] = data["photos"]
            elif data.get("merchant_photos") and not data.get("photos"):
                data["photos"] = data["merchant_photos"]

            if data.get("google_maps_url") and not data.get("location"):
                data["location"] = data["google_maps_url"]

            # Normalize category
            if not data.get("category") and data.get("categories"):
                cats = data.get("categories")
                if isinstance(cats, list) and len(cats) > 0:
                    data["category"] = cats[0]
            elif data.get("category") and not data.get("categories"):
                data["categories"] = [data["category"]]

            # Normalize photos
            photos = data.get("merchant_photos") or []
            if photos and isinstance(photos, list):
                if not data.get("photo_1") and len(photos) > 0:
                    data["photo_1"] = photos[0]
                if not data.get("photo_2") and len(photos) > 1:
                    data["photo_2"] = photos[1]
                if not data.get("photo_3") and len(photos) > 2:
                    data["photo_3"] = photos[2]
                if not data.get("photo_4") and len(photos) > 3:
                    data["photo_4"] = photos[3]
            else:
                p_list = [p for p in [data.get("photo_1"), data.get("photo_2"), data.get("photo_3"), data.get("photo_4")] if p]
                if p_list:
                    data["merchant_photos"] = p_list

            # Normalize video
            if not data.get("video_url") and data.get("merchant_videos"):
                vids = data.get("merchant_videos")
                if isinstance(vids, list) and len(vids) > 0:
                    data["video_url"] = vids[0]

            if not data.get("address"):
                data["address"] = data.get("location") or "Kerala, India"
        return data

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: Optional[str]) -> Optional[str]:
        if v:
            clean = v.strip().lower()
            if not re.match(EMAIL_REGEX, clean):
                raise ValueError("Invalid email format")
            return clean
        return None

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> str:
        if not v:
            return "0000000000"
        cleaned = re.sub(r"[\s\-()]", "", v)
        if not cleaned.replace("+", "").isdigit():
            raise ValueError("Phone number must contain only digits")
        return cleaned


class MerchantOnboardingResponse(BaseModel):
    message: str
    merchant: MerchantProfileResponse
    user: Optional[SafeUserResponse] = None


class MerchantMediaUploadResponse(BaseModel):
    message: str
    photos: List[str] = []
    videos: List[str] = []
    documents: List[str] = []
    all_urls: List[str] = []
    total_files: int = 0


class MerchantRegionResponse(BaseModel):
    districts: List[str] = []
    cities: List[str] = []
    locations: List[str] = []


class MerchantRejectRequest(BaseModel):
    rejection_reason: Optional[str] = Field(
        "Application rejected by administration.",
        max_length=500,
        json_schema_extra={"example": "Invalid business license or contact details not reachable."},
    )
    reason: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def populate_rejection_reason(cls, data: Any) -> Any:
        if isinstance(data, dict):
            reason_val = data.get("rejection_reason") or data.get("reason") or "Application rejected by administration."
            data["rejection_reason"] = str(reason_val).strip()
            data["reason"] = str(reason_val).strip()
        elif isinstance(data, str):
            data = {"rejection_reason": data.strip(), "reason": data.strip()}
        return data



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
    business_name: Optional[str] = Field(None, max_length=255)
    name: Optional[str] = Field(None, max_length=255)
    owner: Optional[str] = Field(None, max_length=255)
    owner_name: Optional[str] = Field(None, max_length=255)
    contact_person: Optional[str] = None
    category: Optional[str] = Field(None, max_length=150)
    categories: Optional[List[str]] = None
    address: Optional[str] = Field(None, max_length=500)
    city: Optional[str] = Field(None, max_length=100)
    district: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    location: Optional[str] = Field(None, max_length=255)
    city_region: Optional[str] = Field(None, max_length=255)
    landmark: Optional[str] = Field(None, max_length=255)
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    phone: Optional[str] = None
    phone_number: Optional[str] = None
    contact_number: Optional[str] = None
    whatsapp: Optional[str] = None
    landline: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    facebook: Optional[str] = None
    instagram: Optional[str] = None
    twitter: Optional[str] = None
    youtube: Optional[str] = None
    about: Optional[str] = None
    description: Optional[str] = None
    rating: Optional[float] = None
    reviews_count: Optional[int] = None
    key_highlights: Optional[List[str]] = None
    photo_1: Optional[str] = None
    photo_2: Optional[str] = None
    photo_3: Optional[str] = None
    photo_4: Optional[str] = None
    photo_5: Optional[str] = None
    photo_6: Optional[str] = None
    photos: Optional[List[str]] = None
    merchant_photos: Optional[List[str]] = None
    video_url: Optional[str] = None
    merchant_videos: Optional[List[str]] = None
    verification_documents: Optional[List[str]] = None
    services: Optional[List[str]] = None
    service_timing: Optional[str] = None
    status: Optional[str] = None

    model_config = ConfigDict(extra="ignore")


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

