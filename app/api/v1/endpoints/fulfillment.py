from typing import Optional

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.db.database import get_db
from app.db.models.user import User
from app.schemas.fulfillment import (
    RefundCreateRequest,
    RefundResponse,
    RefundStatusRequest,
    ReplacementCreateRequest,
    ReplacementResponse,
    ReturnActionRequest,
    ReturnCreateRequest,
    ReturnInspectRequest,
    ReturnPickupRequest,
    ReturnResponse,
    ReturnSettingsRequest,
    ReturnShippingRequest,
    ReturnStatsResponse,
    ReturnStatusRequest,
    ShipmentCreateRequest,
    ShipmentDetailsRequest,
    ShipmentHistoryItem,
    ShipmentResponse,
    ShipmentStatusRequest,
)
from app.schemas.response import StandardListResponse, StandardResponse, list_response, success_response
from app.services.fulfillment_service import FulfillmentService

router = APIRouter(tags=["Order tracking and returns"])


@router.post("/shipments", response_model=StandardResponse[ShipmentResponse], status_code=status.HTTP_201_CREATED, summary="Dispatch an order")
def create_shipment(
    data: ShipmentCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shipment = FulfillmentService.create_shipment(db, current_user, data)
    return success_response(FulfillmentService._shipment_response(shipment), "Shipment created")


@router.get("/shipments/order/{order_id}", response_model=StandardResponse[ShipmentResponse], summary="Shipment for an order")
def get_shipment_by_order(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shipment = FulfillmentService.shipment_for_order(db, current_user, order_id)
    return success_response(FulfillmentService._shipment_response(shipment), "Shipment retrieved")


@router.put("/shipments/{shipment_id}/status", response_model=StandardResponse[ShipmentResponse], summary="Update shipment status")
def update_shipment_status(
    shipment_id: int,
    data: ShipmentStatusRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shipment = FulfillmentService.update_shipment_status(db, current_user, shipment_id, data)
    return success_response(FulfillmentService._shipment_response(shipment), "Shipment status updated")


@router.put("/shipments/{shipment_id}/details", response_model=StandardResponse[ShipmentResponse], summary="Update courier details")
def update_shipment_details(
    shipment_id: int,
    data: ShipmentDetailsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shipment = FulfillmentService.update_shipment_details(db, current_user, shipment_id, data)
    return success_response(FulfillmentService._shipment_response(shipment), "Shipment details updated")


@router.get("/shipments/{shipment_id}/history", response_model=StandardListResponse[ShipmentHistoryItem], summary="Shipment history")
def shipment_history(
    shipment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = FulfillmentService.shipment_history(db, current_user, shipment_id)
    data = [ShipmentHistoryItem.model_validate(row) for row in rows]
    return list_response(data, total_items=len(data), page_size=max(len(data), 1), message="Shipment history retrieved")


@router.get("/returns/settings", response_model=StandardResponse[dict], summary="Return window")
def get_return_settings(current_user: User = Depends(require_admin), db: Session = Depends(get_db)):
    return success_response({"return_window_days": FulfillmentService.return_window_days(db)}, "Return settings retrieved")


@router.put("/returns/settings", response_model=StandardResponse[dict], summary="Update return window")
def update_return_settings(
    data: ReturnSettingsRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    days = FulfillmentService.set_return_window(db, data.return_window_days)
    return success_response({"return_window_days": days}, "Return settings updated")


@router.get("/returns/stats", response_model=StandardResponse[ReturnStatsResponse], summary="Return dashboard totals")
def return_stats(current_user: User = Depends(require_admin), db: Session = Depends(get_db)):
    return success_response(ReturnStatsResponse(**FulfillmentService.stats(db)), "Return stats retrieved")


@router.get("/returns/my-returns", response_model=StandardListResponse[ReturnResponse], summary="My return requests")
def my_returns(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = FulfillmentService.my_returns(db, current_user)
    return list_response(rows, total_items=len(rows), page_size=max(len(rows), 1), message="Returns retrieved")


@router.post("/returns/images", response_model=StandardResponse[dict], summary="Upload a return photo")
def upload_return_image(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    url = FulfillmentService.save_return_image(file)
    return success_response({"url": url}, "Image uploaded")


@router.post("/returns", response_model=StandardResponse[ReturnResponse], status_code=status.HTTP_201_CREATED, summary="Request a return")
def create_return(
    data: ReturnCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    payload = FulfillmentService.create_return(db, current_user, data)
    return success_response(payload, "Return requested")


@router.get("/returns", response_model=StandardListResponse[ReturnResponse], summary="List return requests")
def list_returns(
    status_filter: Optional[str] = Query(None, alias="status"),
    q: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    rows, total = FulfillmentService.list_returns(db, status_filter, q, page, page_size)
    return list_response(rows, total_items=total, page=page, page_size=page_size, message="Returns retrieved")


@router.get("/returns/{return_id}", response_model=StandardResponse[ReturnResponse], summary="Return request details")
def get_return(return_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return success_response(FulfillmentService.get_return(db, current_user, return_id), "Return retrieved")


@router.put("/returns/{return_id}/approve", response_model=StandardResponse[ReturnResponse], summary="Approve a return")
def approve_return(
    return_id: int,
    data: ReturnActionRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return success_response(FulfillmentService.approve_return(db, current_user, return_id, data.remarks), "Return approved")


@router.put("/returns/{return_id}/reject", response_model=StandardResponse[ReturnResponse], summary="Reject a return")
def reject_return(
    return_id: int,
    data: ReturnActionRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return success_response(FulfillmentService.reject_return(db, current_user, return_id, data.reason or ""), "Return rejected")


@router.put("/returns/{return_id}/status", response_model=StandardResponse[ReturnResponse], summary="Update return status")
def update_return_status(
    return_id: int,
    data: ReturnStatusRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return success_response(
        FulfillmentService.set_return_status(db, current_user, return_id, data.return_status, data.remarks),
        "Return status updated",
    )


@router.post("/returns/{return_id}/pickup", response_model=StandardResponse[ReturnResponse], summary="Schedule a manual pickup")
def schedule_pickup(
    return_id: int,
    data: ReturnPickupRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return success_response(
        FulfillmentService.schedule_pickup(db, current_user, return_id, data.pickup_date, data.pickup_remarks),
        "Pickup scheduled",
    )


@router.post("/returns/{return_id}/shipping", response_model=StandardResponse[ReturnResponse], summary="Customer self-shipping details")
def customer_shipping(
    return_id: int,
    data: ReturnShippingRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return success_response(FulfillmentService.customer_shipping(db, current_user, return_id, data), "Return shipment recorded")


@router.post("/returns/{return_id}/receive", response_model=StandardResponse[ReturnResponse], summary="Confirm the return was received")
def receive_return(
    return_id: int,
    data: ReturnActionRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return success_response(FulfillmentService.receive_return(db, current_user, return_id, data.remarks), "Return received")


@router.post("/returns/{return_id}/inspect", response_model=StandardResponse[ReturnResponse], summary="Inspect the returned product")
def inspect_return(
    return_id: int,
    data: ReturnInspectRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return success_response(
        FulfillmentService.inspect_return(db, current_user, return_id, data.product_condition, data.remarks),
        "Return inspected",
    )


@router.post("/returns/{return_id}/refund", response_model=StandardResponse[RefundResponse], status_code=status.HTTP_201_CREATED, summary="Record a refund")
def create_refund(
    return_id: int,
    data: RefundCreateRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    refund = FulfillmentService.create_refund(db, current_user, return_id, data)
    return success_response(RefundResponse.model_validate(refund), "Refund recorded as pending")


@router.get("/returns/{return_id}/refunds", response_model=StandardListResponse[RefundResponse], summary="Refund history")
def list_refunds(return_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = FulfillmentService.list_refunds(db, current_user, return_id)
    data = [RefundResponse.model_validate(row) for row in rows]
    return list_response(data, total_items=len(data), page_size=max(len(data), 1), message="Refunds retrieved")


@router.put("/refunds/{refund_id}/status", response_model=StandardResponse[RefundResponse], summary="Confirm refund status")
def update_refund_status(
    refund_id: int,
    data: RefundStatusRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    refund = FulfillmentService.update_refund_status(db, current_user, refund_id, data)
    return success_response(RefundResponse.model_validate(refund), "Refund status updated")


@router.post("/returns/{return_id}/replace", response_model=StandardResponse[ReplacementResponse], status_code=status.HTTP_201_CREATED, summary="Create a replacement order")
def create_replacement(
    return_id: int,
    data: ReplacementCreateRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    link = FulfillmentService.create_replacement(db, current_user, return_id, data)
    payload = FulfillmentService.replacement_for_return(db, current_user, return_id)
    payload["id"] = link.id
    return success_response(payload, "Replacement order created")


@router.get("/returns/{return_id}/replacement", response_model=StandardResponse[ReplacementResponse], summary="Replacement linked to a return")
def get_replacement(return_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return success_response(FulfillmentService.replacement_for_return(db, current_user, return_id), "Replacement retrieved")
