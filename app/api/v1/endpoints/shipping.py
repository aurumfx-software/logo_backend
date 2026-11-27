from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Header, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.db.database import get_db
from app.db.models.user import User
from app.schemas.fulfillment import ReturnResponse
from app.schemas.response import StandardResponse, list_response, success_response
from app.services.fulfillment_service import FulfillmentService
from app.services.shipping_service import ShippingService

router = APIRouter(tags=["Shiprocket shipping"])


class DispatchRequest(BaseModel):
    courier_id: Optional[int] = None
    schedule_pickup: bool = True


class CourierChoice(BaseModel):
    courier_id: Optional[int] = None


class RefundRecordRequest(BaseModel):
    refund_amount: Decimal = Field(..., gt=0)
    refund_method: str
    transaction_reference: Optional[str] = None
    admin_remarks: Optional[str] = None
    refund_status: str = "PROCESSING"


class ReceiveRequest(BaseModel):
    remarks: Optional[str] = None
    inspection_status: Optional[str] = None


def _secret(request: Request, x_api_key: Optional[str], x_shiprocket_secret: Optional[str]) -> Optional[str]:
    return x_api_key or x_shiprocket_secret or request.query_params.get("token")


@router.get("/shipping/orders", summary="Orders with shipment summary")
def list_shipments(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = ShippingService.list_orders(db, current_user)
    return list_response(rows, total_items=len(rows), page_size=max(len(rows), 1), message="Shipments retrieved")


@router.get("/shipping/couriers/{order_id}", summary="Couriers for an order")
def list_couriers(order_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = ShippingService.couriers(db, current_user, order_id)
    return list_response(rows, total_items=len(rows), page_size=max(len(rows), 1), message="Couriers retrieved")


@router.post("/shipping/dispatch/{order_id}", summary="Create a Shiprocket shipment and AWB")
def dispatch_order(
    order_id: int,
    data: DispatchRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    payload = ShippingService.dispatch(db, current_user, order_id, data.courier_id, data.schedule_pickup)
    return success_response(payload, "Shipment dispatched")


@router.post("/shipping/{order_id}/cancel", summary="Cancel a Shiprocket shipment")
def cancel_shipment(order_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return success_response(ShippingService.cancel(db, current_user, order_id), "Shipment cancelled")


@router.get("/shipping/track/{order_id}", summary="Track an order")
def track_order(
    order_id: int,
    refresh: bool = Query(True),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return success_response(ShippingService.track(db, current_user, order_id, refresh=refresh), "Tracking retrieved")


@router.post("/shipping/webhook", summary="Shiprocket tracking webhook")
async def shiprocket_webhook(
    request: Request,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
    x_shiprocket_secret: Optional[str] = Header(None),
):
    payload = await request.json()
    if not isinstance(payload, dict):
        payload = {}
    result = ShippingService.apply_webhook(db, payload, _secret(request, x_api_key, x_shiprocket_secret))
    return {"success": True, "data": result}


@router.post("/returns/{return_id}/create-shipment", response_model=StandardResponse[ReturnResponse], summary="Create a reverse Shiprocket shipment")
def create_return_shipment(
    return_id: int,
    data: CourierChoice,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    payload = ShippingService.create_return_shipment(db, current_user, return_id, data.courier_id)
    return success_response(payload, "Return shipment created")


@router.put("/returns/{return_id}/receive", response_model=StandardResponse[ReturnResponse], summary="Confirm a returned product was received")
def receive_return(
    return_id: int,
    data: ReceiveRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    payload = FulfillmentService.receive_return(db, current_user, return_id, data.remarks)
    if data.inspection_status:
        payload = FulfillmentService.inspect_return(db, current_user, return_id, data.inspection_status, data.remarks)
    return success_response(payload, "Return updated")


@router.put("/returns/{return_id}/refund", response_model=StandardResponse[ReturnResponse], summary="Record or update a manual refund")
def refund_return(
    return_id: int,
    data: RefundRecordRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    method = data.refund_method.strip().upper().replace(" ", "_").replace("-", "_")
    if method in {"BANK", "BANK_TRANSFER"}:
        method = "BANK_TRANSFER"
    data.refund_method = method
    payload = ShippingService.record_refund(db, current_user, return_id, data)
    return success_response(payload, "Refund updated")
