from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class AddressRequest(BaseModel):
    label: str = Field("Home", max_length=50)
    recipient_name: str = Field(..., min_length=2, max_length=255)
    phone: str = Field(..., min_length=7, max_length=50)
    address_line: str = Field(..., min_length=5)
    location: Optional[str] = Field(None, max_length=255)
    city: Optional[str] = Field(None, max_length=100)
    district: Optional[str] = Field(None, max_length=100)
    pincode: str = Field(..., min_length=5, max_length=10)
    is_default: bool = False


class AddressUpdateRequest(BaseModel):
    label: Optional[str] = Field(None, max_length=50)
    recipient_name: Optional[str] = Field(None, min_length=2, max_length=255)
    phone: Optional[str] = Field(None, min_length=7, max_length=50)
    address_line: Optional[str] = Field(None, min_length=5)
    location: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    pincode: Optional[str] = Field(None, min_length=5, max_length=10)
    is_default: Optional[bool] = None


class AddressResponse(BaseModel):
    id: int
    label: str
    recipient_name: str
    phone: str
    address_line: str
    location: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    pincode: str
    is_default: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class WishlistItemResponse(BaseModel):
    product_id: int
    name: str
    price: float
    image: Optional[str] = None
    in_stock: bool = True
    saved_at: Optional[datetime] = None


class WishlistResponse(BaseModel):
    items: List[WishlistItemResponse] = []
    total: int = 0


class CartItemInput(BaseModel):
    product_id: int
    quantity: int = Field(1, ge=1, le=100)
    selected_size: Optional[str] = Field(None, max_length=50)


class CartSyncRequest(BaseModel):
    items: List[CartItemInput] = Field(default_factory=list)


class CartLineResponse(BaseModel):
    id: int
    product_id: int
    product_name: str
    product_image: Optional[str] = None
    unit_price: float
    quantity: int
    selected_size: Optional[str] = None
    line_total: float
    in_stock: bool = True


class CartResponse(BaseModel):
    items: List[CartLineResponse] = []
    item_count: int = 0
    subtotal: float = 0
    unavailable: List[str] = []


class CartCheckoutRequest(BaseModel):
    address_id: int
    notes: Optional[str] = None


class ReviewCreateRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    title: Optional[str] = Field(None, max_length=120)
    comment: Optional[str] = Field(None, max_length=1000)


class ReviewResponse(BaseModel):
    id: int
    product_id: int
    order_id: Optional[int] = None
    buyer_user_id: int
    buyer_name: Optional[str] = None
    rating: int
    title: Optional[str] = None
    comment: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ReviewListResponse(BaseModel):
    reviews: List[ReviewResponse] = []
    total: int = 0
    rating_average: float = 0
    rating_count: int = 0


class OrderPaymentRequest(BaseModel):
    method: str = Field(..., description="RAZORPAY, UPI, or COD")


class OrderPaymentVerifyRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class OrderPaymentResponse(BaseModel):
    order_id: int
    order_code: str
    payment_status: str
    payment_method: Optional[str] = None
    amount: float
    amount_paise: int
    currency: str = "INR"
    razorpay_key_id: Optional[str] = None
    razorpay_order_id: Optional[str] = None
    razorpay_payment_id: Optional[str] = None


class CourierEventResponse(BaseModel):
    event: str
    note: Optional[str] = None
    at: Optional[datetime] = None


class DispatchUpdateRequest(BaseModel):
    courier_partner: str = Field(..., min_length=2, max_length=100)
    tracking_number: str = Field(..., min_length=3, max_length=64)
    tracking_url: Optional[str] = Field(None, max_length=500)
    estimated_delivery_at: Optional[datetime] = None
    event: str = Field(
        "IN_TRANSIT",
        description="PICKED_UP, IN_TRANSIT, OUT_FOR_DELIVERY, DELIVERED, or EXCEPTION",
    )
    note: Optional[str] = Field(None, max_length=300)


class OrderTrackingResponse(BaseModel):
    order_id: int
    order_code: str
    status: str
    status_label: str
    payment_status: str
    payment_method: Optional[str] = None
    headline: str
    detail: Optional[str] = None
    updated_at: Optional[datetime] = None
    courier_partner: Optional[str] = None
    tracking_number: Optional[str] = None
    tracking_url: Optional[str] = None
    estimated_delivery_at: Optional[datetime] = None
    events: List[CourierEventResponse] = []
    delivery_steps: list = []
