import re
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from app.db.models.user import UserRole
from app.db.models.otp import OTPPurpose


EMAIL_REGEX = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"


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
    password: str = Field(..., min_length=4, max_length=100, json_schema_extra={"example": "TestPassword123"})
    role: Optional[UserRole] = Field(
        None,
        description="User role: SUPER_ADMIN, ADMIN, FIELD_STAFF, CUSTOMER, or MERCHANT (defaults to FIELD_STAFF if omitted)",
        json_schema_extra={"example": "CUSTOMER"},
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
            if v_clean in ("CUSTOMER", "CLIENT", "CONSUMER"):
                return UserRole.CUSTOMER
            if v_clean in ("MERCHANT", "MERCH", "VENDOR", "SELLER"):
                return UserRole.MERCHANT
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
        if len(v) < 4:
            raise ValueError("Password must be at least 4 characters long")
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
    """Send OTP for customer mobile login (email or phone)."""
    email: Optional[str] = Field(None, json_schema_extra={"example": "customer@example.com"})
    phone: Optional[str] = Field(None, json_schema_extra={"example": "9876543210"})

    @field_validator("email")
    @classmethod
    def validate_email_optional(cls, v: Optional[str]) -> Optional[str]:
        if v is None or not v.strip():
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
        cleaned = re.sub(r"[\s\-()]", "", str(v).strip())
        if cleaned.startswith("+91"):
            cleaned = cleaned[3:]
        elif cleaned.startswith("91") and len(cleaned) > 10:
            cleaned = cleaned[2:]
        if not cleaned.isdigit() or len(cleaned) < 10:
            raise ValueError("Invalid phone number")
        return cleaned

    @model_validator(mode="after")
    def require_email_or_phone(self) -> "CustomerLoginOTPSendRequest":
        if not self.email and not self.phone:
            raise ValueError("Provide either email or phone")
        if self.email and self.phone:
            raise ValueError("Provide only one of email or phone")
        return self


class CustomerLoginOTPVerifyRequest(CustomerLoginOTPSendRequest):
    otp: str = Field(..., min_length=6, max_length=6, json_schema_extra={"example": "482910"})


class CustomerRegisterRequest(BaseModel):
    """Logo App customer (mobile) registration — stored in users table."""

    name: str = Field(..., min_length=2, max_length=100, json_schema_extra={"example": "Anjali Nair"})
    phone: str = Field(..., min_length=10, max_length=15, json_schema_extra={"example": "9876543210"})
    password: str = Field(..., min_length=4, max_length=100, json_schema_extra={"example": "SecurePass1"})
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


class UserProfileUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100, json_schema_extra={"example": "Updated Name"})
    phone: Optional[str] = Field(None, json_schema_extra={"example": "9876543210"})
    address: Optional[str] = Field(None, max_length=500, json_schema_extra={"example": "Updated Address"})
    profile_picture: Optional[str] = Field(None, max_length=500, json_schema_extra={"example": "https://example.com/new_avatar.jpg"})


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


class SendOTPRequest(UserBase):
    purpose: OTPPurpose = Field(
        default=OTPPurpose.ACCOUNT_VERIFICATION,
        json_schema_extra={"example": "ACCOUNT_VERIFICATION"},
    )


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


class VerifyOTPResponse(BaseModel):
    message: str
    is_verified: bool


class ForgotPasswordRequest(UserBase):
    pass


class ResetPasswordRequest(UserBase):
    otp: str = Field(..., min_length=6, max_length=6, json_schema_extra={"example": "123456"})
    new_password: str = Field(..., min_length=8, max_length=100, json_schema_extra={"example": "NewPassword123"})


class GenericMessageResponse(BaseModel):
    message: str
