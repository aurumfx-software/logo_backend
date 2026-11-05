import re
from datetime import datetime
from typing import Any, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from app.db.models.user import UserRole
from app.db.models.otp import OTPPurpose


EMAIL_REGEX = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"

OTP_PURPOSE_ALIASES = {
    "VERIFY": OTPPurpose.ACCOUNT_VERIFICATION,
    "ACCOUNT_VERIFY": OTPPurpose.ACCOUNT_VERIFICATION,
    "SIGNUP": OTPPurpose.ACCOUNT_VERIFICATION,
    "REGISTER": OTPPurpose.ACCOUNT_VERIFICATION,
    "RESET": OTPPurpose.PASSWORD_RESET,
    "FORGOT_PASSWORD": OTPPurpose.PASSWORD_RESET,
    "PASSWORD": OTPPurpose.PASSWORD_RESET,
    "MERCHANT": OTPPurpose.MERCHANT_LOGIN,
    "MERCHANT_OTP": OTPPurpose.MERCHANT_LOGIN,
    "CUSTOMER": OTPPurpose.CUSTOMER_LOGIN,
    "LOGIN": OTPPurpose.CUSTOMER_LOGIN,
}


def coerce_otp_purpose(value: Any) -> OTPPurpose:
    if isinstance(value, OTPPurpose):
        return value
    if value is None or (isinstance(value, str) and not value.strip()):
        return OTPPurpose.ACCOUNT_VERIFICATION
    raw = str(value).strip().upper().replace("-", "_").replace(" ", "_")
    if raw in OTP_PURPOSE_ALIASES:
        return OTP_PURPOSE_ALIASES[raw]
    try:
        return OTPPurpose(raw)
    except ValueError as exc:
        allowed = ", ".join(p.value for p in OTPPurpose)
        raise ValueError(f"Invalid OTP purpose '{value}'. Allowed: {allowed}") from exc


def normalize_otp_request_payload(data: Any) -> Any:
    if isinstance(data, dict):
        for alias in ("type", "otp_type", "otpType", "option_type", "optionType"):
            if alias in data and "purpose" not in data:
                data["purpose"] = data[alias]
    return data


class OTPPurposeOption(BaseModel):
    value: str
    label: str


class OTPPurposeListResponse(BaseModel):
    purposes: List[OTPPurposeOption]
    types: List[OTPPurposeOption]


class UserBase(BaseModel):
    email: str = Field(..., json_schema_extra={"example": "test@example.com"})

    @field_validator("email")
    @classmethod
    def validate_email_format(cls, v: str) -> str:
        clean_email = v.strip().lower()
        if not re.match(EMAIL_REGEX, clean_email):
            raise ValueError("Invalid email format")
        return clean_email


class UserRegisterRequest(UserBase):
    name: str = Field(..., min_length=2, max_length=100, json_schema_extra={"example": "Test User"})
    phone: Optional[str] = Field(None, json_schema_extra={"example": "9876543210"})
    password: str = Field(..., min_length=8, max_length=100, json_schema_extra={"example": "TestPassword123"})
    role: Optional[UserRole] = Field(
        None,
        description="User role: SUPER_ADMIN, ADMIN, or FIELD_STAFF (defaults to FIELD_STAFF if omitted)",
        json_schema_extra={"example": "FIELD_STAFF"},
    )
    district: Optional[str] = Field(None, max_length=100, json_schema_extra={"example": "Ernakulam"})
    regions: Optional[List[str]] = Field(default_factory=list, json_schema_extra={"example": ["Central Kerala", "Kochi Zone"]})
    city: Optional[str] = Field(None, max_length=100, json_schema_extra={"example": "Kochi"})
    module_access: Optional[List[str]] = Field(default_factory=list, json_schema_extra={"example": ["merchants", "users", "categories"]})
    send_email: Optional[bool] = Field(False, description="Send welcome email / notifications (true/false binary)", json_schema_extra={"example": True})
    status: Optional[str] = Field("ACTIVE", max_length=50, json_schema_extra={"example": "ACTIVE"})
    created_by: Optional[str] = Field(None, max_length=50, json_schema_extra={"example": "ADM_1"})
    address: Optional[str] = Field(None, max_length=500, json_schema_extra={"example": "123 MG Road, Kochi, Kerala"})
    profile_picture: Optional[str] = Field(None, max_length=500, json_schema_extra={"example": "https://example.com/avatar.jpg"})

    @field_validator("role", mode="before")
    @classmethod
    def validate_role(cls, v: Optional[str | UserRole]) -> Optional[UserRole]:
        if v is None:
            return None
        if isinstance(v, str):
            v_clean = v.strip().upper().replace(" ", "_").replace("-", "_")
            if v_clean in ("PUBLIC_USER", "PUBLICUSER", "USER", "FIELDSTAFF"):
                return UserRole.FIELD_STAFF
            try:
                return UserRole(v_clean)
            except ValueError:
                valid_roles = [r.value for r in UserRole]
                raise ValueError(f"Invalid role '{v}'. Allowed roles: {valid_roles}")
        return v

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            cleaned = re.sub(r"[\s\-()]", "", v)
            if cleaned and not cleaned.isdigit():
                raise ValueError("Phone number must contain only digits")
            return cleaned or None
        return None

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        return v


class UserLoginRequest(UserBase):
    password: str = Field(..., json_schema_extra={"example": "TestPassword123"})


class UserPhoneLoginRequest(BaseModel):
    """Customer quick sign-in with mobile number + password."""
    phone: str = Field(..., min_length=10, max_length=15, json_schema_extra={"example": "9876543210"})
    password: str = Field(..., min_length=6, json_schema_extra={"example": "TestPassword123"})

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        cleaned = re.sub(r"[\s\-()]", "", v.strip())
        if cleaned.startswith("+91"):
            cleaned = cleaned[3:]
        elif cleaned.startswith("91") and len(cleaned) > 10:
            cleaned = cleaned[2:]
        if not cleaned.isdigit() or len(cleaned) < 10:
            raise ValueError("Invalid phone number")
        return cleaned


class CustomerLoginOTPSendRequest(BaseModel):
    """Send OTP for customer mobile login (email only)."""
    email: str = Field(..., json_schema_extra={"example": "customer@example.com"})
    phone: Optional[Any] = Field(None, json_schema_extra={"example": None})

    @field_validator("phone")
    @classmethod
    def reject_phone(cls, v: Optional[Any]) -> Optional[Any]:
        if v is not None and str(v).strip():
            raise ValueError("Phone number is not supported on this route. Use email.")
        return None

    @field_validator("email")
    @classmethod
    def validate_email_required(cls, v: str) -> str:
        if not v or not str(v).strip():
            raise ValueError("Email is required")
        clean_email = str(v).strip().lower()
        if not re.match(EMAIL_REGEX, clean_email):
            raise ValueError("Invalid email format")
        return clean_email


class CustomerLoginOTPVerifyRequest(BaseModel):
    email: str = Field(..., json_schema_extra={"example": "customer@example.com"})
    otp: str = Field(..., min_length=6, max_length=6, json_schema_extra={"example": "123456"})
    phone: Optional[Any] = Field(None, json_schema_extra={"example": None})

    @field_validator("phone")
    @classmethod
    def reject_phone(cls, v: Optional[Any]) -> Optional[Any]:
        if v is not None and str(v).strip():
            raise ValueError("Phone number is not supported on this route. Use email.")
        return None

    @field_validator("email")
    @classmethod
    def validate_email_required(cls, v: str) -> str:
        if not v or not str(v).strip():
            raise ValueError("Email is required")
        clean_email = str(v).strip().lower()
        if not re.match(EMAIL_REGEX, clean_email):
            raise ValueError("Invalid email format")
        return clean_email


class CustomerRegisterRequest(BaseModel):
    """Logo App customer (mobile) registration — stored in users table."""

    name: str = Field(..., min_length=2, max_length=100, json_schema_extra={"example": "Anjali Nair"})
    phone: str = Field(..., min_length=10, max_length=15, json_schema_extra={"example": "9876543210"})
    password: str = Field(..., min_length=6, max_length=100, json_schema_extra={"example": "SecurePass1"})
    district: str = Field(..., min_length=2, max_length=100, json_schema_extra={"example": "Ernakulam"})
    city: str = Field(..., min_length=2, max_length=100, json_schema_extra={"example": "Kochi"})
    email: Optional[str] = Field(
        None,
        description="Optional; if omitted a unique placeholder email is generated for login.",
        json_schema_extra={"example": "anjali@gmail.com"},
    )

    @field_validator("email")
    @classmethod
    def validate_email_optional(cls, v: Optional[str]) -> Optional[str]:
        if v is None or not str(v).strip():
            return None
        clean_email = v.strip().lower()
        if not re.match(EMAIL_REGEX, clean_email):
            raise ValueError("Invalid email format")
        return clean_email

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        cleaned = re.sub(r"[\s\-()]", "", v.strip())
        if cleaned.startswith("+91"):
            cleaned = cleaned[3:]
        elif cleaned.startswith("91") and len(cleaned) > 10:
            cleaned = cleaned[2:]
        if not cleaned.isdigit() or len(cleaned) < 10:
            raise ValueError("Invalid phone number")
        return cleaned


class SafeUserResponse(BaseModel):
    id: int
    user_code: Optional[str] = Field(None, description="Formatted user code, e.g. ADM_1, FLS_1, SAD_1", json_schema_extra={"example": "ADM_1"})
    name: str
    email: str
    phone: Optional[str] = None
    role: UserRole
    district: Optional[str] = None
    regions: Optional[List[str]] = Field(default_factory=list)
    city: Optional[str] = None
    module_access: Optional[List[str]] = Field(default_factory=list)
    send_email: bool = False
    status: Optional[str] = "ACTIVE"
    last_active: Optional[datetime] = None
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    address: Optional[str] = None
    profile_picture: Optional[str] = None
    is_active: bool = True
    is_verified: bool = False

    model_config = ConfigDict(from_attributes=True)

    @field_validator("role", mode="before")
    @classmethod
    def normalize_role(cls, v):
        return UserRole.coerce(v)

    @field_validator("regions", "module_access", mode="before")
    @classmethod
    def none_to_list(cls, v):
        return v if v is not None else []


class UserProfileUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100, json_schema_extra={"example": "Updated Name"})
    phone: Optional[str] = Field(None, json_schema_extra={"example": "9876543210"})
    email: Optional[str] = Field(None, json_schema_extra={"example": "updated@example.com"})
    address: Optional[str] = Field(None, max_length=500, json_schema_extra={"example": "Updated Address"})
    district: Optional[str] = Field(None, max_length=100, json_schema_extra={"example": "Ernakulam"})
    city: Optional[str] = Field(None, max_length=100, json_schema_extra={"example": "Kochi"})
    profile_picture: Optional[str] = Field(None, max_length=500, json_schema_extra={"example": "https://example.com/new_avatar.jpg"})

    @field_validator("email")
    @classmethod
    def validate_email_optional(cls, v: Optional[str]) -> Optional[str]:
        if v is None or not str(v).strip():
            return None
        clean_email = str(v).strip().lower()
        if not re.match(EMAIL_REGEX, clean_email):
            raise ValueError("Invalid email format")
        return clean_email

    @field_validator("phone")
    @classmethod
    def validate_phone_optional(cls, v: Optional[str]) -> Optional[str]:
        if v is None or not str(v).strip():
            return None
        cleaned = re.sub(r"[\s\-()]", "", str(v).strip())
        if cleaned.startswith("+91"):
            cleaned = cleaned[3:]
        elif cleaned.startswith("91") and len(cleaned) > 10:
            cleaned = cleaned[2:]
        if cleaned and not cleaned.isdigit():
            raise ValueError("Phone number must contain only digits")
        return cleaned or None

    @field_validator("district", "city", "address", "profile_picture")
    @classmethod
    def empty_str_to_none(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        stripped = str(v).strip()
        return stripped or None


class AvatarUploadResponse(BaseModel):
    message: str
    profile_picture_url: str


class RegisterResponse(BaseModel):
    message: str
    user: SafeUserResponse


class CustomerRegisterResponse(BaseModel):
    message: str
    user: SafeUserResponse
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_code: Optional[str] = None
    role: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_code: Optional[str] = Field(None, description="Formatted user code, e.g. ADM_1, FLS_1, SAD_1", json_schema_extra={"example": "FLS_1"})
    role: Optional[str] = Field(None, description="User role: SUPER_ADMIN, ADMIN, FIELD_STAFF", json_schema_extra={"example": "FIELD_STAFF"})
    user: Optional[SafeUserResponse] = None


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(..., json_schema_extra={"example": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."})


def _normalize_phone(value: str) -> str:
    cleaned = re.sub(r"[\s\-()]", "", value.strip())
    if cleaned.startswith("+91"):
        cleaned = cleaned[3:]
    elif cleaned.startswith("91") and len(cleaned) > 10:
        cleaned = cleaned[2:]
    if not cleaned.isdigit() or len(cleaned) < 10:
        raise ValueError("Invalid phone number")
    return cleaned


class OTPChannelRequest(BaseModel):
    """Send or check an OTP for an email address or a mobile number."""

    email: Optional[str] = Field(None, json_schema_extra={"example": "user@example.com"})
    phone: Optional[str] = Field(None, json_schema_extra={"example": "9876543210"})
    purpose: OTPPurpose = Field(
        default=OTPPurpose.ACCOUNT_VERIFICATION,
        json_schema_extra={"example": "ACCOUNT_VERIFICATION"},
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_purpose_aliases(cls, data: Any) -> Any:
        data = normalize_otp_request_payload(data)
        if isinstance(data, dict) and "purpose" in data:
            data["purpose"] = coerce_otp_purpose(data["purpose"])
        return data

    @field_validator("email")
    @classmethod
    def validate_email_optional(cls, v: Optional[str]) -> Optional[str]:
        if v is None or not str(v).strip():
            return None
        clean_email = v.strip().lower()
        if not re.match(EMAIL_REGEX, clean_email):
            raise ValueError("Invalid email format")
        return clean_email

    @field_validator("phone")
    @classmethod
    def validate_phone_optional(cls, v: Optional[str]) -> Optional[str]:
        if v is None or not str(v).strip():
            return None
        return _normalize_phone(str(v))

    @model_validator(mode="after")
    def require_one_channel(self) -> "OTPChannelRequest":
        if not self.email and not self.phone:
            raise ValueError("Provide either email or phone")
        if self.email and self.phone:
            raise ValueError("Provide only one of email or phone")
        return self

    @property
    def identifier(self) -> str:
        return self.email or self.phone or ""


class OTPVerifyChannelRequest(OTPChannelRequest):
    otp: str = Field(..., min_length=6, max_length=6, json_schema_extra={"example": "482910"})


class SendOTPRequest(UserBase):
    purpose: OTPPurpose = Field(
        default=OTPPurpose.ACCOUNT_VERIFICATION,
        json_schema_extra={"example": "ACCOUNT_VERIFICATION"},
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_purpose_aliases(cls, data: Any) -> Any:
        data = normalize_otp_request_payload(data)
        if isinstance(data, dict) and "purpose" in data:
            data["purpose"] = coerce_otp_purpose(data["purpose"])
        return data


class SendOTPResponse(BaseModel):
    message: str
    expires_in_minutes: int
    dev_otp: Optional[str] = None  # Returned ONLY in development mode for easy local testing


class VerifyOTPRequest(UserBase):
    otp: str = Field(..., min_length=6, max_length=6, json_schema_extra={"example": "123456"})
    purpose: OTPPurpose = Field(
        default=OTPPurpose.ACCOUNT_VERIFICATION,
        json_schema_extra={"example": "ACCOUNT_VERIFICATION"},
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_purpose_aliases(cls, data: Any) -> Any:
        data = normalize_otp_request_payload(data)
        if isinstance(data, dict) and "purpose" in data:
            data["purpose"] = coerce_otp_purpose(data["purpose"])
        return data


class VerifyOTPResponse(BaseModel):
    message: str
    is_verified: bool


class ForgotPasswordRequest(BaseModel):
    """Send a password-reset OTP to a registered email."""

    email: str = Field(..., json_schema_extra={"example": "user@example.com"})
    phone: Optional[Any] = Field(None, json_schema_extra={"example": None})

    @field_validator("phone")
    @classmethod
    def reject_phone(cls, v: Optional[Any]) -> Optional[Any]:
        if v is not None and str(v).strip():
            raise ValueError("Phone number is not supported on this route. Use email.")
        return None

    @field_validator("email")
    @classmethod
    def validate_email_required(cls, v: str) -> str:
        if not v or not str(v).strip():
            raise ValueError("Email is required")
        clean_email = str(v).strip().lower()
        if not re.match(EMAIL_REGEX, clean_email):
            raise ValueError("Invalid email format")
        return clean_email

    @property
    def identifier(self) -> str:
        return self.email


class ResetPasswordRequest(BaseModel):
    email: str = Field(..., json_schema_extra={"example": "user@example.com"})
    otp: str = Field(..., min_length=6, max_length=6, json_schema_extra={"example": "123456"})
    new_password: str = Field(..., min_length=8, max_length=100, json_schema_extra={"example": "NewPassword123"})
    phone: Optional[Any] = Field(None, json_schema_extra={"example": None})

    @field_validator("phone")
    @classmethod
    def reject_phone(cls, v: Optional[Any]) -> Optional[Any]:
        if v is not None and str(v).strip():
            raise ValueError("Phone number is not supported on this route. Use email.")
        return None

    @field_validator("email")
    @classmethod
    def validate_email_required(cls, v: str) -> str:
        if not v or not str(v).strip():
            raise ValueError("Email is required")
        clean_email = str(v).strip().lower()
        if not re.match(EMAIL_REGEX, clean_email):
            raise ValueError("Invalid email format")
        return clean_email

    @property
    def identifier(self) -> str:
        return self.email


class LogoutRequest(BaseModel):
    refresh_token: Optional[str] = Field(
        None,
        description="Optional refresh token to revoke on logout",
    )


class LogoutResponse(BaseModel):
    success: bool = True
    message: str
    user_id: Optional[int] = None
    logged_out_at: datetime


class GenericMessageResponse(BaseModel):
    message: str
