from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field


class ShipmentCreateRequest(BaseModel):
    order_id: int
    courier_name: Optional[str] = None
    tracking_number: Optional[str] = None
    tracking_url: Optional[str] = None
    shipment_status: str = "DISPATCHED"
    remarks: Optional[str] = None
    location: Optional[str] = None
    dispatched_at: Optional[datetime] = None
    estimated_delivery: Optional[datetime] = None


class ShipmentStatusRequest(BaseModel):
    shipment_status: str
    location: Optional[str] = None
    description: Optional[str] = None


class ShipmentDetailsRequest(BaseModel):
    courier_name: Optional[str] = None
    tracking_number: Optional[str] = None
    tracking_url: Optional[str] = None
    remarks: Optional[str] = None
    dispatched_at: Optional[datetime] = None
    estimated_delivery: Optional[datetime] = None


class ShipmentHistoryItem(BaseModel):
    id: int
    status: str
    location: Optional[str] = None
    description: Optional[str] = None
    event_time: Optional[datetime] = None
    updated_by: Optional[int] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ShipmentResponse(BaseModel):
    id: int
    order_id: int
    order_code: Optional[str] = None
    product_name: Optional[str] = None
    product_image: Optional[str] = None
    quantity: Optional[int] = None
    order_date: Optional[datetime] = None
    courier_name: Optional[str] = None
    tracking_number: Optional[str] = None
    awb_number: Optional[str] = None
    tracking_url: Optional[str] = None
    label_url: Optional[str] = None
    shiprocket_order_id: Optional[str] = None
    shiprocket_shipment_id: Optional[str] = None
    shipment_status: str
    remarks: Optional[str] = None
    dispatched_at: Optional[datetime] = None
    estimated_delivery: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    history: List[ShipmentHistoryItem] = []

    model_config = {"from_attributes": True}


class ReturnCreateRequest(BaseModel):
    order_id: int
    quantity: int = Field(..., ge=1)
    return_reason: str
    description: Optional[str] = None
    return_type: str
    image_urls: List[str] = []
    courier_name: Optional[str] = None
    awb_number: Optional[str] = None
    shipping_date: Optional[str] = None
    receipt_url: Optional[str] = None


class ReturnActionRequest(BaseModel):
    remarks: Optional[str] = None
    reason: Optional[str] = None


class ReturnStatusRequest(BaseModel):
    return_status: str
    remarks: Optional[str] = None


class ReturnPickupRequest(BaseModel):
    pickup_date: str
    pickup_remarks: Optional[str] = None


class ReturnShippingRequest(BaseModel):
    courier_name: str
    awb_number: str
    shipping_date: str
    receipt_url: Optional[str] = None


class ReturnInspectRequest(BaseModel):
    product_condition: str
    remarks: Optional[str] = None


class ReturnItemResponse(BaseModel):
    id: int
    order_item_id: int
    product_id: Optional[int] = None
    quantity: int
    product_condition: Optional[str] = None
    image_urls: List[str] = []

    model_config = {"from_attributes": True}


class ReturnHistoryItem(BaseModel):
    id: int
    status: str
    remarks: Optional[str] = None
    updated_by: Optional[int] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class RefundResponse(BaseModel):
    id: int
    return_id: int
    refund_amount: Decimal
    refund_method: str
    transaction_reference: Optional[str] = None
    refund_status: str
    admin_remarks: Optional[str] = None
    refund_date: Optional[str] = None
    processed_by: Optional[int] = None
    processed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ReplacementResponse(BaseModel):
    id: int
    original_order_id: int
    return_id: int
    replacement_order_id: int
    replacement_order_code: Optional[str] = None
    status: str
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ReturnResponse(BaseModel):
    id: int
    return_number: str
    order_id: int
    order_code: Optional[str] = None
    user_id: int
    customer_name: Optional[str] = None
    return_reason: str
    description: Optional[str] = None
    return_type: str
    return_status: str
    courier_name: Optional[str] = None
    awb_number: Optional[str] = None
    shiprocket_order_id: Optional[str] = None
    shiprocket_shipment_id: Optional[str] = None
    tracking_url: Optional[str] = None
    inspection_status: Optional[str] = None
    refund_amount: Optional[Decimal] = None
    refund_status: Optional[str] = None
    shipping_date: Optional[str] = None
    receipt_url: Optional[str] = None
    pickup_date: Optional[str] = None
    pickup_remarks: Optional[str] = None
    admin_notes: Optional[str] = None
    rejection_reason: Optional[str] = None
    items: List[ReturnItemResponse] = []
    history: List[ReturnHistoryItem] = []
    refunds: List[RefundResponse] = []
    replacement: Optional[ReplacementResponse] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class RefundCreateRequest(BaseModel):
    refund_amount: Decimal = Field(..., gt=0)
    refund_method: str
    transaction_reference: Optional[str] = None
    refund_date: Optional[str] = None
    admin_remarks: Optional[str] = None


class RefundStatusRequest(BaseModel):
    refund_status: str
    transaction_reference: Optional[str] = None
    admin_remarks: Optional[str] = None
    refund_date: Optional[str] = None


class ReplacementCreateRequest(BaseModel):
    product_id: Optional[int] = None
    quantity: int = Field(..., ge=1)
    price_difference: Decimal = Field(default=Decimal("0"))
    remarks: Optional[str] = None


class ReturnSettingsRequest(BaseModel):
    return_window_days: int = Field(..., ge=0, le=365)


class ReturnStatsResponse(BaseModel):
    total: int
    pending: int
    approved: int
    rejected: int
    awaiting_pickup: int
    awaiting_inspection: int
    refunds_pending: int
    completed: int
