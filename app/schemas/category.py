from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator


class CategoryCreateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100, json_schema_extra={"example": "Restaurant & Dining"})
    category_name: Optional[str] = Field(None, min_length=2, max_length=100, json_schema_extra={"example": "Restaurant & Dining"})
    slug: Optional[str] = Field(None, max_length=120, json_schema_extra={"example": "restaurant-and-dining"})
    description: Optional[str] = Field(None, max_length=500, json_schema_extra={"example": "Logos for dining and hospitality brands"})
    icon: Optional[str] = Field(None, max_length=500, json_schema_extra={"example": "🍔"})
    icon_url: Optional[str] = Field(None, max_length=500, json_schema_extra={"example": "/static/categories/icons/dining.png"})
    status: Optional[str] = Field(None, json_schema_extra={"example": "Active"})
    is_active: Optional[bool] = Field(None, json_schema_extra={"example": True})

    @model_validator(mode="after")
    def validate_category_fields(self):
        # Resolve name
        if not self.name and self.category_name:
            self.name = self.category_name
        if not self.name or not self.name.strip():
            raise ValueError("Category name is required")
        self.name = self.name.strip()

        # Resolve icon
        if not self.icon_url and self.icon:
            self.icon_url = self.icon

        # Resolve is_active from status
        if self.is_active is None:
            if self.status is not None:
                self.is_active = self.status.strip().lower() in ["active", "true", "1"]
            else:
                self.is_active = True

        return self


class CategoryUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    category_name: Optional[str] = Field(None, min_length=2, max_length=100)
    slug: Optional[str] = Field(None, max_length=120)
    description: Optional[str] = Field(None, max_length=500)
    icon: Optional[str] = Field(None, max_length=500)
    icon_url: Optional[str] = Field(None, max_length=500)
    status: Optional[str] = None
    is_active: Optional[bool] = None

    @model_validator(mode="after")
    def validate_update_fields(self):
        if not self.name and self.category_name:
            self.name = self.category_name
        if self.name:
            self.name = self.name.strip()

        if not self.icon_url and self.icon:
            self.icon_url = self.icon

        if self.is_active is None and self.status is not None:
            self.is_active = self.status.strip().lower() in ["active", "true", "1"]

        return self


class CategoryResponse(BaseModel):
    id: int
    name: str
    category_name: Optional[str] = None
    slug: str
    description: Optional[str] = None
    icon: Optional[str] = None
    icon_url: Optional[str] = None
    is_active: bool
    status: str = "Active"
    logo_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def populate_aliases(self):
        if not self.category_name:
            self.category_name = self.name
        if not self.icon:
            self.icon = self.icon_url
        if not self.icon_url:
            self.icon_url = self.icon
        self.status = "Active" if self.is_active else "Inactive"
        return self


class CategoryListResponse(BaseModel):
    items: List[CategoryResponse]
    total: int


class CategoryIconUploadResponse(BaseModel):
    message: str
    icon_url: str
