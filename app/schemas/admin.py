from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field

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
    total_public_users: int
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


class AdminUserListItem(BaseModel):
    id: int
    name: str
    email: str
    phone: Optional[str] = None
    role: UserRole
    is_active: bool
    is_verified: bool
    address: Optional[str] = None
    profile_picture: Optional[str] = None
    created_at: datetime
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
    name: str
    email: str
    phone: Optional[str] = None
    role: UserRole
    is_active: bool
    is_verified: bool
    address: Optional[str] = None
    profile_picture: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    submitted_logos_count: int = 0
    favorite_logos_count: int = 0
    merchant_profile: Optional[dict] = None

    model_config = ConfigDict(from_attributes=True)


class AdminUserRoleUpdateRequest(BaseModel):
    role: UserRole = Field(..., json_schema_extra={"example": "ADMIN"})


class AdminUserStatusUpdateRequest(BaseModel):
    is_active: bool = Field(..., json_schema_extra={"example": False})
