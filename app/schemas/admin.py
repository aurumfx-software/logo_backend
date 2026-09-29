from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.models.user import UserRole
from app.schemas.auth import SafeUserResponse
from app.schemas.logo import LogoResponse


class AdminCategoryDistributionItem(BaseModel):
    category_id: int
    name: str
    slug: str
    logo_count: int


class AdminDashboardStats(BaseModel):
    total_users: int
    total_merchants: int
    total_field_staff: int
    total_admins: int
    active_users: int

    total_logos: int
    approved_logos: int
    pending_logos: int
    rejected_logos: int

    total_categories: int
    total_views: int
    total_favorites: int

    recent_pending_logos: List[LogoResponse] = []
    recent_users: List[SafeUserResponse] = []
    trending_logos: List[LogoResponse] = []
    category_distribution: List[AdminCategoryDistributionItem] = []


class AdminUserCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100, json_schema_extra={"example": "Test Staff"})
    email: str = Field(..., json_schema_extra={"example": "staff@example.com"})
    phone: Optional[str] = Field(None, json_schema_extra={"example": "9876543210"})
    password: str = Field(..., min_length=6, max_length=100, json_schema_extra={"example": "StaffPass123"})
    role: Optional[UserRole] = Field(UserRole.FIELD_STAFF, json_schema_extra={"example": "FIELD_STAFF"})
    district: Optional[str] = Field(None, max_length=100, json_schema_extra={"example": "Ernakulam"})
    regions: Optional[List[str]] = Field(default_factory=list, json_schema_extra={"example": ["Central Kerala", "Kochi Zone"]})
    city: Optional[str] = Field(None, max_length=100, json_schema_extra={"example": "Kochi"})
    module_access: Optional[List[str]] = Field(default_factory=list, json_schema_extra={"example": ["merchants", "users", "categories"]})
    send_email: bool = Field(False, description="Send welcome email / notifications (true/false binary)", json_schema_extra={"example": True})
    status: Optional[str] = Field("ACTIVE", max_length=50, json_schema_extra={"example": "ACTIVE"})
    created_by: Optional[str] = Field(None, max_length=50, json_schema_extra={"example": "ADM_1"})
    address: Optional[str] = Field(None, max_length=500, json_schema_extra={"example": "123 MG Road, Kochi"})
    profile_picture: Optional[str] = Field(None, max_length=500)

    @field_validator("role", mode="before")
    @classmethod
    def validate_role(cls, v):
        if v is None:
            return UserRole.FIELD_STAFF
        if isinstance(v, str):
            v_clean = v.strip().upper().replace(" ", "_").replace("-", "_")
            if v_clean in ("PUBLIC_USER", "PUBLICUSER", "USER", "FIELDSTAFF"):
                return UserRole.FIELD_STAFF
            return UserRole(v_clean)
        return v


class AdminUserListItem(BaseModel):
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
    is_active: bool = True
    is_verified: bool = False
    address: Optional[str] = None
    profile_picture: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    submitted_logos_count: int = 0
    favorite_logos_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class AdminUserListResponse(BaseModel):
    items: List[AdminUserListItem]
    total: int
    skip: int
    limit: int


class AdminUserDetailResponse(BaseModel):
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
    is_active: bool = True
    is_verified: bool = False
    address: Optional[str] = None
    profile_picture: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    submitted_logos_count: int = 0
    favorite_logos_count: int = 0
    merchant_profile: Optional[dict] = None

    model_config = ConfigDict(from_attributes=True)


class AdminUserRoleUpdateRequest(BaseModel):
    role: UserRole = Field(..., json_schema_extra={"example": "ADMIN"})


class AdminUserStatusUpdateRequest(BaseModel):
    is_active: bool = Field(..., json_schema_extra={"example": False})
    status: Optional[str] = Field(None, json_schema_extra={"example": "INACTIVE"})

