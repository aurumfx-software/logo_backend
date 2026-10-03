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

    # Registration & merchant metrics
    pending_approvals: int = 0
    approved_merchants: int = 0
    rejected_merchants: int = 0
    active_staff: int = 0
    total_staff: int = 0
    total_searches: int = 0
    total_revenue: float = 0.0

    # Growth % metrics
    merchants_growth: float = 12.5
    users_growth: float = 8.3
    approvals_growth: float = 15.0
    searches_growth: float = 22.4
    revenue_growth: float = 10.0

    # CamelCase aliases for flexible frontend consumption
    totalMerchants: Optional[int] = None
    pendingApprovals: Optional[int] = None
    totalUsers: Optional[int] = None
    activeStaff: Optional[int] = None
    totalSearches: Optional[int] = None
    merchantGrowth: Optional[float] = None
    userGrowth: Optional[float] = None
    searchGrowth: Optional[float] = None

    # Legacy & platform items
    total_logos: int = 0
    approved_logos: int = 0
    pending_logos: int = 0
    rejected_logos: int = 0
    total_categories: int = 0
    total_views: int = 0
    total_favorites: int = 0

    recent_pending_logos: List[LogoResponse] = []
    recent_users: List[SafeUserResponse] = []
    trending_logos: List[LogoResponse] = []
    category_distribution: List[AdminCategoryDistributionItem] = []
    growth: Optional[dict] = None

    model_config = ConfigDict(extra="ignore")


class MonthlyTrendItem(BaseModel):
    month: str
    signups: int = 0
    searches: int = 0
    merchants: int = 0
    revenue: float = 0.0


class DashboardCategoryItem(BaseModel):
    name: str
    count: int = 0
    percentage: float = 0.0
    color: str = "#6C63FF"


class DashboardChartsData(BaseModel):
    monthly_trends: List[MonthlyTrendItem] = []
    category_distribution: List[DashboardCategoryItem] = []
    status_distribution: dict = {}


class DashboardChartsResponse(BaseModel):
    success: bool = True
    data: DashboardChartsData
    monthly_trends: List[MonthlyTrendItem] = []
    category_distribution: List[DashboardCategoryItem] = []


class RecentActivityItem(BaseModel):
    id: int
    action: str
    title: str
    description: str
    entity_type: str = "MERCHANT"
    entity_id: Optional[int] = None
    user_name: Optional[str] = None
    user_role: Optional[str] = None
    time: str = ""
    time_ago: str = ""
    created_at: Optional[datetime] = None


class RecentActivityResponse(BaseModel):
    success: bool = True
    total: int = 0
    data: List[RecentActivityItem] = []
    recent_activity: List[RecentActivityItem] = []


class RegistrationRequestItem(BaseModel):
    id: int
    merchant_id: int
    business_name: str
    name: str
    owner_name: Optional[str] = None
    owner: Optional[str] = None
    category: Optional[str] = None
    categories: List[str] = []
    phone: Optional[str] = None
    contact_number: Optional[str] = None
    email: Optional[str] = None
    district: Optional[str] = None
    city: Optional[str] = None
    location: Optional[str] = None
    address: Optional[str] = None
    landmark: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    status: str = "PENDING"
    approval_status: str = "PENDING"
    is_verified: bool = False
    is_active: bool = True
    rejection_reason: Optional[str] = None
    created_at: Optional[datetime] = None
    submitted_at: Optional[datetime] = None
    joined: Optional[str] = None
    photo_1: Optional[str] = None
    merchant_photos: List[str] = []
    photos: List[str] = []
    verification_documents: List[str] = []
    documents: List[str] = []
    merchant_videos: List[str] = []
    video_url: Optional[str] = None
    user_code: Optional[str] = None
    onboarded_by: Optional[str] = None

    model_config = ConfigDict(from_attributes=True, extra="ignore")


class RegistrationRequestsResponse(BaseModel):
    success: bool = True
    total: int = 0
    items: List[RegistrationRequestItem] = []
    requests: List[RegistrationRequestItem] = []
    data: List[RegistrationRequestItem] = []


class SingleRegistrationRequestResponse(BaseModel):
    success: bool = True
    data: RegistrationRequestItem



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
    is_suspended: bool = False
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
    is_suspended: bool = False
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
    is_active: Optional[bool] = Field(None, json_schema_extra={"example": False})
    is_suspended: Optional[bool] = Field(None, json_schema_extra={"example": True})
    status: Optional[str] = Field(None, json_schema_extra={"example": "INACTIVE"})

    model_config = ConfigDict(extra="ignore")


class AdminUserUpdateRequest(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[UserRole] = None
    district: Optional[str] = None
    regions: Optional[List[str]] = None
    city: Optional[str] = None
    module_access: Optional[List[str]] = None
    send_email: Optional[bool] = None
    status: Optional[str] = None
    is_active: Optional[bool] = None
    is_suspended: Optional[bool] = None
    address: Optional[str] = None
    profile_picture: Optional[str] = None
    password: Optional[str] = None

    model_config = ConfigDict(extra="ignore")

    @field_validator("role", mode="before")
    @classmethod
    def validate_role(cls, v):
        if v is None:
            return None
        if isinstance(v, str):
            v_clean = v.strip().upper().replace(" ", "_").replace("-", "_")
            if v_clean in ("PUBLIC_USER", "PUBLICUSER", "USER", "FIELDSTAFF"):
                return UserRole.FIELD_STAFF
            if v_clean in ("SUPERADMIN", "SUPER_ADMIN"):
                return UserRole.SUPER_ADMIN
            if v_clean in ("ADMIN", "ADMINISTRATOR"):
                return UserRole.ADMIN
            return UserRole(v_clean)
        return v

