from datetime import datetime
from typing import List, Optional, Any
from pydantic import BaseModel, ConfigDict, Field


class ProductCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=255, description="Product Name")
    description: Optional[str] = Field(None, description="Product Details")
    category: str = Field("General", max_length=100)
    price: float = Field(..., gt=0, description="Selling Price (₹)")
    original_price: Optional[float] = Field(None, description="Strike-through / MRP Price (₹)")
    images: List[str] = Field(default_factory=list, description="List of product photo URLs")
    sizes: List[str] = Field(default_factory=list, description="Available sizes e.g. ['S', 'M', 'L'] or ['Free Size']")
    stock_status: str = Field("IN_STOCK", description="IN_STOCK or OUT_OF_STOCK")
    district: Optional[str] = Field(None, max_length=100)
    city: Optional[str] = Field(None, max_length=100)
    location: Optional[str] = Field(None, max_length=255)
    seller_name: Optional[str] = Field(None, max_length=255)
    seller_phone: Optional[str] = Field(None, max_length=50)
    seller_whatsapp: Optional[str] = Field(None, max_length=50)


class ProductUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = None
    original_price: Optional[float] = None
    images: Optional[List[str]] = None
    sizes: Optional[List[str]] = None
    stock_status: Optional[str] = None
    district: Optional[str] = None
    city: Optional[str] = None
    location: Optional[str] = None
    seller_name: Optional[str] = None
    seller_phone: Optional[str] = None
    seller_whatsapp: Optional[str] = None
    is_active: Optional[bool] = None


class ProductAdminStatusUpdate(BaseModel):
    is_active: Optional[bool] = Field(None, description="Toggle On/Off product visibility")
    approval_status: Optional[str] = Field(None, description="APPROVED, DENIED, or PENDING")
    rejection_reason: Optional[str] = None


class ProductResponse(BaseModel):
    id: int
    seller_id: int
    seller_name: Optional[str] = None
    seller_phone: Optional[str] = None
    seller_whatsapp: Optional[str] = None
    name: str
    description: Optional[str] = None
    category: str
    price: float
    original_price: Optional[float] = None
    images: List[str] = []
    sizes: List[str] = []
    stock_status: str
    district: Optional[str] = None
    city: Optional[str] = None
    location: Optional[str] = None
    is_active: bool
    approval_status: str
    rejection_reason: Optional[str] = None
    views_count: int = 0
    orders_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class OrderCreateRequest(BaseModel):
    product_id: int
    buyer_name: str = Field(..., min_length=2, max_length=255)
    buyer_phone: str = Field(..., min_length=7, max_length=50)
    buyer_address: str = Field(..., min_length=5)
    buyer_location: Optional[str] = Field(None, max_length=255)
    buyer_city: Optional[str] = Field(None, max_length=100)
    buyer_district: Optional[str] = Field(None, max_length=100)
    buyer_pincode: str = Field(..., min_length=5, max_length=10)
    selected_size: Optional[str] = Field(None, max_length=50)
    quantity: int = Field(1, ge=1, le=100)
    notes: Optional[str] = None


class OrderResponse(BaseModel):
    id: int
    order_code: str
    product_id: int
    seller_id: int
    product_name: Optional[str] = None
    product_image: Optional[str] = None
    seller_name: Optional[str] = None
    seller_phone: Optional[str] = None
    seller_whatsapp: Optional[str] = None
    whatsapp_url: Optional[str] = None
    buyer_name: str
    buyer_phone: str
    buyer_address: str
    buyer_location: Optional[str] = None
    buyer_city: Optional[str] = None
    buyer_district: Optional[str] = None
    buyer_pincode: str
    selected_size: Optional[str] = None
    quantity: int
    unit_price: float
    total_price: float
    status: str
    notes: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class SellerPermissionToggleRequest(BaseModel):
    can_sell_products: bool
    is_subscriber: Optional[bool] = None
    subscription_plan: Optional[str] = "500_SELLER"
