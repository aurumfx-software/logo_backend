"""Create, track, and reverse Shiprocket shipments using the existing order tables."""

import hashlib
import hmac
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.db.models.fulfillment import OrderReturn, Shipment, ShipmentHistory
from app.db.models.merchant import MerchantProfile
from app.db.models.product import ProductOrder
from app.db.models.user import User
from app.services.fulfillment_service import FulfillmentService
from app.services.shiprocket_client import ShiprocketClient

FORWARD = "FORWARD"


def _digits(value: Optional[str]) -> str:
    digits = re.sub(r"\D", "", value or "")
    if digits.startswith("91") and len(digits) > 10:
        digits = digits[-10:]
    return digits[-10:] if len(digits) >= 10 else digits


def _split_name(value: Optional[str]) -> tuple[str, str]:
    parts = [part for part in (value or "Customer").split() if part]
    first = parts[0] if parts else "Customer"
    last = " ".join(parts[1:]) if len(parts) > 1 else "."
    return first[:50], last[:50]


def _parse_dt(value) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip().replace("Z", "")
    for fmt, size in (("%Y-%m-%d %H:%M:%S", 19), ("%Y-%m-%dT%H:%M:%S", 19), ("%d %b %Y", 11), ("%Y-%m-%d", 10)):
        try:
            return datetime.strptime(text[:size], fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def map_shiprocket_status(raw: Optional[str]) -> str:
    text = (raw or "").upper().replace("-", " ")
    if "CANCEL" in text:
        return "CANCELLED"
    if "RTO" in text or "RETURN TO" in text:
        return "RETURN_TO_ORIGIN"
    if "OUT FOR DELIVERY" in text:
        return "OUT_FOR_DELIVERY"
    if "DELIVER" in text:
        return "DELIVERED"
    if any(word in text for word in ("TRANSIT", "PICKED", "SHIPPED", "IN TRANSIT")):
        return "IN_TRANSIT"
    if any(word in text for word in ("AWB", "MANIFEST", "PICKUP", "READY")):
        return "DISPATCHED"
    return "PROCESSING"


class ShippingService:
    @staticmethod
    def _client() -> ShiprocketClient:
        return ShiprocketClient()

    @staticmethod
    def list_orders(db: Session, user: User) -> list:
        FulfillmentService.ensure_tables(db)
        query = db.query(ProductOrder).options(joinedload(ProductOrder.product), joinedload(ProductOrder.shipment))
        if not FulfillmentService._is_admin(user):
            query = query.filter(ProductOrder.seller_id == user.id)
        orders = query.order_by(ProductOrder.id.desc()).limit(100).all()
        rows = []
        for order in orders:
            shipment = order.shipment
            rows.append(
                {
                    "order_id": order.id,
                    "order_code": order.order_code,
                    "status": order.status,
                    "product_name": order.product.name if order.product else None,
                    "quantity": order.quantity,
                    "buyer_name": order.buyer_name,
                    "buyer_phone": order.buyer_phone,
                    "buyer_city": order.buyer_city,
                    "buyer_pincode": order.buyer_pincode,
                    "total_price": order.total_price,
                    "awb_number": (shipment.awb_number or shipment.tracking_number) if shipment else None,
                    "courier_name": shipment.courier_name if shipment else None,
                    "shipment_status": shipment.shipment_status if shipment else None,
                    "tracking_url": shipment.tracking_url if shipment else None,
                    "label_url": shipment.label_url if shipment else None,
                    "shiprocket_shipment_id": shipment.shiprocket_shipment_id if shipment else None,
                }
            )
        return rows

    @staticmethod
    def couriers(db: Session, user: User, order_id: int) -> list:
        order = ShippingService._manage_order(db, user, order_id)
        pickup_pin, _location, _seller = ShippingService._pickup(db, order)
        payload = ShippingService._client().request(
            "GET",
            "/courier/serviceability/",
            params={
                "pickup_postcode": pickup_pin,
                "delivery_postcode": order.buyer_pincode,
                "cod": 1 if _is_cod(order) else 0,
                "weight": 0.5,
            },
        )
        data = payload.get("data") or {}
        companies = data.get("available_courier_companies") or []
        return [
            {
                "courier_id": item.get("courier_company_id"),
                "courier_name": item.get("courier_name"),
                "rate": item.get("rate"),
                "etd": item.get("etd"),
                "estimated_delivery_days": item.get("estimated_delivery_days"),
            }
            for item in companies
            if item.get("courier_company_id")
        ]

    @staticmethod
    def dispatch(db: Session, user: User, order_id: int, courier_id: Optional[int], schedule_pickup: bool) -> dict:
        order = ShippingService._manage_order(db, user, order_id)
        if (order.status or "").upper() == "CANCELLED":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A cancelled order cannot be dispatched.")
        shipment = db.query(Shipment).filter(Shipment.order_id == order.id).first()
        client = ShippingService._client()
        if shipment and shipment.shiprocket_shipment_id and shipment.awb_number:
            ShippingService._label(client, shipment)
            if schedule_pickup:
                ShippingService._schedule_pickup(client, shipment)
            db.commit()
            return ShippingService.track(db, user, order.id, refresh=False)

        pickup_pin, pickup_name, seller = ShippingService._pickup(db, order)
        if not shipment or not shipment.shiprocket_shipment_id:
            created = ShippingService._create_forward_order(db, client, order, seller, pickup_name, pickup_pin)
            if not shipment:
                shipment = Shipment(order_id=order.id, shipment_status="PROCESSING")
                db.add(shipment)
                db.flush()
            shipment.shiprocket_order_id = str(created.get("order_id") or "")
            shipment.shiprocket_shipment_id = str(created.get("shipment_id") or "")
            shipment.shipment_status = "PROCESSING"
            db.flush()
        if not shipment.shiprocket_shipment_id:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Shiprocket did not return a shipment id.")

        if not shipment.awb_number:
            chosen = courier_id or ShippingService._recommended_courier(client, order, pickup_pin)
            assigned = client.request(
                "POST",
                "/courier/assign/awb",
                json={"shipment_id": int(shipment.shiprocket_shipment_id), "courier_id": int(chosen)},
            )
            if assigned.get("awb_assign_status") not in (1, "1", True):
                detail = assigned.get("response") or assigned.get("message") or "Shiprocket could not assign an AWB."
                raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(detail)[:500])
            info = ((assigned.get("response") or {}).get("data") or {})
            awb = str(info.get("awb_code") or "")
            if not awb:
                raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Shiprocket did not return an AWB number.")
            shipment.awb_number = awb
            shipment.tracking_number = awb
            shipment.courier_name = info.get("courier_name")
            shipment.courier_id = str(info.get("courier_company_id") or chosen)
            shipment.tracking_url = f"https://shiprocket.co/tracking/{awb}"
            shipment.shipment_status = "DISPATCHED"
            shipment.dispatched_at = shipment.dispatched_at or datetime.now(timezone.utc)
            ShippingService._history(db, shipment, "DISPATCHED", None, f"AWB {awb} assigned", f"awb:{awb}", user.id)
            FulfillmentService._copy_tracking(order, shipment)
            FulfillmentService._advance_order(order, "DISPATCHED", shipment.courier_name)

        ShippingService._label(client, shipment)
        if schedule_pickup:
            ShippingService._schedule_pickup(client, shipment)
        db.commit()
        FulfillmentService._notify(
            db,
            order.buyer_user_id,
            "Order dispatched",
            f"Order {order.order_code} is with {shipment.courier_name or 'the courier'}. AWB {shipment.awb_number}.",
            {"order_id": order.id},
        )
        return ShippingService.track(db, user, order.id, refresh=False)

    @staticmethod
    def cancel(db: Session, user: User, order_id: int) -> dict:
        order = ShippingService._manage_order(db, user, order_id)
        shipment = ShippingService._shipment(db, order.id)
        if shipment.shipment_status in {"DELIVERED", "CANCELLED"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This shipment can no longer be cancelled.")
        if not shipment.shiprocket_order_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This shipment is not booked with Shiprocket.")
        ShippingService._client().request("POST", "/orders/cancel", json={"ids": [int(shipment.shiprocket_order_id)]})
        shipment.shipment_status = "CANCELLED"
        ShippingService._history(db, shipment, "CANCELLED", None, "Shipment cancelled", f"cancel:{shipment.id}", user.id)
        db.commit()
        return ShippingService.track(db, user, order.id, refresh=False)

    @staticmethod
    def track(db: Session, user: User, order_id: int, refresh: bool = True) -> dict:
        FulfillmentService.ensure_tables(db)
        order = FulfillmentService._order(db, order_id)
        if not FulfillmentService._can_view_order(user, order):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot view this order.")
        shipment = (
            db.query(Shipment)
            .options(joinedload(Shipment.history), joinedload(Shipment.order))
            .filter(Shipment.order_id == order.id)
            .first()
        )
        if shipment and refresh and shipment.awb_number and ShippingService._client().configured():
            ShippingService._refresh_awb(db, shipment, shipment.awb_number, is_return=False)
            db.commit()
            db.refresh(shipment)
        return _track_payload(order, shipment)

    @staticmethod
    def apply_webhook(db: Session, payload: dict, secret: Optional[str]) -> dict:
        expected = (settings.SHIPROCKET_WEBHOOK_SECRET or "").strip().encode()
        provided = (secret or "").strip().encode()
        if not expected or not provided or not hmac.compare_digest(provided, expected):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook secret.")
        FulfillmentService.ensure_tables(db)
        awb = str(payload.get("awb") or payload.get("awb_code") or "").strip()
        if not awb and isinstance(payload.get("shipment"), dict):
            awb = str(payload["shipment"].get("awb") or "").strip()
        if not awb:
            return {"ignored": True}
        shipment = (
            db.query(Shipment)
            .filter((Shipment.awb_number == awb) | (Shipment.tracking_number == awb))
            .first()
        )
        order_return = None if shipment else db.query(OrderReturn).filter(OrderReturn.awb_number == awb).first()
        if not shipment and not order_return:
            return {"ignored": True, "awb": awb}
        if shipment:
            ShippingService._apply_events(db, shipment, payload, is_return=False)
        else:
            ShippingService._apply_return_events(db, order_return, payload)
        db.commit()
        return {"ok": True, "awb": awb}

    @staticmethod
    def create_return_shipment(db: Session, user: User, return_id: int, courier_id: Optional[int]) -> dict:
        row = FulfillmentService._admin_return(db, user, return_id)
        if row.return_status not in {"APPROVED", "PICKUP_SCHEDULED", "RETURN_SHIPPED"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Approve the return before creating a reverse shipment.")
        order = FulfillmentService._order(db, row.order_id)
        if row.awb_number and row.shiprocket_shipment_id:
            return FulfillmentService.get_return(db, user, row.id)
        client = ShippingService._client()
        pickup_pin, _name, seller = ShippingService._pickup(db, order)
        created = ShippingService._create_return_order(db, client, order, seller, row, pickup_pin)
        row.shiprocket_order_id = str(created.get("order_id") or "")
        row.shiprocket_shipment_id = str(created.get("shipment_id") or "")
        if not row.shiprocket_shipment_id:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Shiprocket did not return a reverse shipment id.")
        chosen = courier_id or ShippingService._recommended_courier(client, order, order.buyer_pincode, delivery_pin=pickup_pin)
        assigned = client.request(
            "POST",
            "/courier/assign/awb",
            json={"shipment_id": int(row.shiprocket_shipment_id), "courier_id": int(chosen)},
        )
        if assigned.get("awb_assign_status") not in (1, "1", True):
            db.commit()
            detail = assigned.get("response") or assigned.get("message") or "Shiprocket could not assign a return AWB."
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(detail)[:500])
        info = ((assigned.get("response") or {}).get("data") or {})
        awb = str(info.get("awb_code") or "")
        row.awb_number = awb or row.awb_number
        row.courier_name = info.get("courier_name") or row.courier_name
        row.tracking_url = f"https://shiprocket.co/tracking/{awb}" if awb else row.tracking_url
        row.return_type = "MANUAL_PICKUP"
        try:
            client.request("POST", "/courier/generate/pickup", json={"shipment_id": [int(row.shiprocket_shipment_id)]})
            row.pickup_date = datetime.now(timezone.utc).date().isoformat()
            FulfillmentService._record_return(db, row, "PICKUP_SCHEDULED", user, awb)
        except HTTPException:
            FulfillmentService._record_return(db, row, "RETURN_SHIPPED", user, awb or "Reverse shipment created")
        db.commit()
        return FulfillmentService.get_return(db, user, row.id)

    @staticmethod
    def record_refund(db: Session, user: User, return_id: int, data) -> dict:
        from app.schemas.fulfillment import RefundCreateRequest, RefundStatusRequest

        raw_status = (getattr(data, "refund_status", None) or "PROCESSING").strip().upper()
        if raw_status == "COMPLETED":
            raw_status = "SUCCESS"
        if raw_status not in {"PENDING", "PROCESSING", "SUCCESS", "FAILED"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown refund status.")
        row = FulfillmentService._admin_return(db, user, return_id)
        existing = row.refunds[0] if row.refunds else None
        if not existing:
            existing = FulfillmentService.create_refund(
                db,
                user,
                return_id,
                RefundCreateRequest(
                    refund_amount=data.refund_amount,
                    refund_method=data.refund_method,
                    transaction_reference=data.transaction_reference,
                    admin_remarks=data.admin_remarks,
                ),
            )
            row = FulfillmentService._load_return(db, return_id)
        if raw_status != existing.refund_status:
            FulfillmentService.update_refund_status(
                db,
                user,
                existing.id,
                RefundStatusRequest(
                    refund_status=raw_status,
                    transaction_reference=data.transaction_reference,
                    admin_remarks=data.admin_remarks,
                ),
            )
        return FulfillmentService.get_return(db, user, return_id)

    @staticmethod
    def _manage_order(db: Session, user: User, order_id: int) -> ProductOrder:
        FulfillmentService.ensure_tables(db)
        order = FulfillmentService._order(db, order_id)
        if not FulfillmentService._can_manage_shipment(user, order):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only an admin or the seller can manage this shipment.")
        return order

    @staticmethod
    def _shipment(db: Session, order_id: int) -> Shipment:
        shipment = db.query(Shipment).filter(Shipment.order_id == order_id).first()
        if not shipment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This order has no shipment yet.")
        return shipment

    @staticmethod
    def _pickup(db: Session, order: ProductOrder):
        seller = db.query(User).filter(User.id == order.seller_id).first()
        profile = (
            db.query(MerchantProfile)
            .filter(MerchantProfile.user_id == order.seller_id)
            .order_by(MerchantProfile.id.desc())
            .first()
        )
        address = (profile.address if profile else None) or ""
        pin_match = re.search(r"\b(\d{6})\b", address)
        pickup_pin = (pin_match.group(1) if pin_match else None) or (settings.SHIPROCKET_PICKUP_PINCODE or "").strip()
        if not pickup_pin:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Set SHIPROCKET_PICKUP_PINCODE or add a 6-digit PIN to the seller address.",
            )
        location = (settings.SHIPROCKET_PICKUP_LOCATION or f"logo-{order.seller_id}").strip() or f"logo-{order.seller_id}"
        return pickup_pin, location, seller

    @staticmethod
    def _seller_profile(db: Session, seller_id: int) -> Optional[MerchantProfile]:
        return (
            db.query(MerchantProfile)
            .filter(MerchantProfile.user_id == seller_id)
            .order_by(MerchantProfile.id.desc())
            .first()
        )

    @staticmethod
    def _create_forward_order(db: Session, client: ShiprocketClient, order: ProductOrder, seller: Optional[User], pickup_name: str, pickup_pin: str) -> dict:
        body = _order_body(order, seller, pickup_name)
        try:
            return _created(client.request("POST", "/orders/create/adhoc", json=body))
        except HTTPException as exc:
            detail = str(exc.detail).lower()
            if "pickup" not in detail:
                raise
            ShippingService._add_pickup(db, client, order, seller, pickup_name, pickup_pin)
            return _created(client.request("POST", "/orders/create/adhoc", json=body))

    @staticmethod
    def _create_return_order(db: Session, client: ShiprocketClient, order: ProductOrder, seller: Optional[User], row: OrderReturn, warehouse_pin: str) -> dict:
        first, last = _split_name(order.buyer_name)
        seller_first, seller_last = _split_name(seller.name if seller else "Seller")
        profile = ShippingService._seller_profile(db, order.seller_id)
        buyer_email = order.buyer.email if order.buyer and order.buyer.email else (seller.email if seller else "orders@localhost")
        qty = sum(item.quantity for item in row.items) or 1
        amount = float(Decimal(order.unit_price or 0) * qty)
        body = {
            "order_id": f"RET-{row.return_number}",
            "order_date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
            "pickup_customer_name": first,
            "pickup_last_name": last,
            "pickup_address": (order.buyer_address or "Address")[:180],
            "pickup_city": order.buyer_city or order.buyer_district or "Kochi",
            "pickup_state": settings.SHIPROCKET_PICKUP_STATE or "Kerala",
            "pickup_country": "India",
            "pickup_pincode": order.buyer_pincode,
            "pickup_email": buyer_email,
            "pickup_phone": _digits(order.buyer_phone) or "9999999999",
            "pickup_isd_code": "91",
            "shipping_customer_name": seller_first,
            "shipping_last_name": seller_last,
            "shipping_address": ((profile.address if profile else None) or "Seller warehouse")[:180],
            "shipping_city": (profile.city if profile else None) or order.buyer_city or "Kochi",
            "shipping_state": (profile.state if profile else None) or settings.SHIPROCKET_PICKUP_STATE or "Kerala",
            "shipping_country": "India",
            "shipping_pincode": warehouse_pin,
            "shipping_email": seller.email if seller else "orders@localhost",
            "shipping_phone": _digits((profile.phone if profile else None) or (seller.phone if seller else "")) or "9999999999",
            "shipping_isd_code": "91",
            "order_items": [
                {
                    "name": (order.product.name if order.product else "Product")[:80],
                    "sku": f"SKU-{order.product_id}",
                    "units": qty,
                    "selling_price": float(order.unit_price or 0),
                }
            ],
            "payment_method": "Prepaid",
            "sub_total": amount,
            "length": 10,
            "breadth": 10,
            "height": 10,
            "weight": 0.5,
        }
        return _created(client.request("POST", "/orders/create/return", json=body))

    @staticmethod
    def _add_pickup(db: Session, client: ShiprocketClient, order: ProductOrder, seller: Optional[User], pickup_name: str, pickup_pin: str) -> None:
        profile = ShippingService._seller_profile(db, order.seller_id)
        client.request(
            "POST",
            "/settings/company/addpickup",
            json={
                "pickup_location": pickup_name,
                "name": (seller.name if seller else "Seller")[:40],
                "email": seller.email if seller else "orders@localhost",
                "phone": _digits(seller.phone if seller else "") or "9999999999",
                "address": ((profile.address if profile else None) or "Warehouse")[:80],
                "address_2": "",
                "city": (profile.city if profile else None) or order.buyer_city or "Kochi",
                "state": (profile.state if profile else None) or settings.SHIPROCKET_PICKUP_STATE or "Kerala",
                "country": "India",
                "pin_code": pickup_pin,
            },
        )

    @staticmethod
    def _recommended_courier(client: ShiprocketClient, order: ProductOrder, pickup_pin: str, delivery_pin: Optional[str] = None) -> int:
        payload = client.request(
            "GET",
            "/courier/serviceability/",
            params={
                "pickup_postcode": pickup_pin,
                "delivery_postcode": delivery_pin or order.buyer_pincode,
                "cod": 1 if _is_cod(order) else 0,
                "weight": 0.5,
            },
        )
        data = payload.get("data") or {}
        recommended = data.get("recommended_courier_company_id")
        if recommended:
            return int(recommended)
        companies = data.get("available_courier_companies") or []
        if not companies:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No Shiprocket courier is available for this route.")
        return int(companies[0]["courier_company_id"])

    @staticmethod
    def _schedule_pickup(client: ShiprocketClient, shipment: Shipment) -> None:
        try:
            client.request("POST", "/courier/generate/pickup", json={"shipment_id": [int(shipment.shiprocket_shipment_id)]})
        except HTTPException as exc:
            shipment.remarks = str(exc.detail)[:500]

    @staticmethod
    def _label(client: ShiprocketClient, shipment: Shipment) -> None:
        if not shipment.shiprocket_shipment_id:
            return
        try:
            label = client.request("POST", "/courier/generate/label", json={"shipment_id": [int(shipment.shiprocket_shipment_id)]})
            shipment.label_url = label.get("label_url") or shipment.label_url
        except HTTPException:
            pass

    @staticmethod
    def _refresh_awb(db: Session, shipment: Shipment, awb: str, is_return: bool) -> None:
        try:
            payload = ShippingService._client().request("GET", f"/courier/track/awb/{awb}")
        except HTTPException:
            return
        tracking = payload.get("tracking_data") or payload
        ShippingService._apply_events(db, shipment, _normalize_track(tracking, awb), is_return=is_return)

    @staticmethod
    def _apply_events(db: Session, shipment: Shipment, payload: dict, is_return: bool) -> None:
        current = payload.get("current_status") or payload.get("shipment_status") or ""
        mapped = map_shiprocket_status(str(current))
        etd = _parse_dt(payload.get("etd") or payload.get("edd"))
        if etd:
            shipment.estimated_delivery = etd
            if shipment.order:
                shipment.order.estimated_delivery_at = etd
        scans = payload.get("scans") or payload.get("shipment_track_activities") or []
        if not scans and current:
            scans = [
                {
                    "status": current,
                    "activity": payload.get("activity") or current,
                    "location": payload.get("location") or "",
                    "date": payload.get("current_timestamp") or payload.get("date"),
                }
            ]
        for scan in scans:
            status_text = str(scan.get("status") or scan.get("sr-status-label") or current or "UPDATE")
            when = str(scan.get("date") or scan.get("current_timestamp") or "")
            location = str(scan.get("location") or "")[:255]
            activity = str(scan.get("activity") or status_text)[:500]
            key = hashlib.sha1(f"{shipment.awb_number}|{status_text}|{when}|{location}|{activity}".encode()).hexdigest()
            if db.query(ShipmentHistory.id).filter(ShipmentHistory.event_key == key).first():
                continue
            mapped_scan = map_shiprocket_status(status_text)
            ShippingService._history(db, shipment, mapped_scan, location or None, activity, key, None, _parse_dt(when))
            mapped = mapped_scan
        if mapped and shipment.shipment_status != mapped:
            shipment.shipment_status = mapped
            if mapped == "DELIVERED":
                shipment.delivered_at = shipment.delivered_at or datetime.now(timezone.utc)
            if shipment.order and not is_return:
                FulfillmentService._copy_tracking(shipment.order, shipment)
                FulfillmentService._advance_order(shipment.order, mapped, current)

    @staticmethod
    def _apply_return_events(db: Session, row: OrderReturn, payload: dict) -> None:
        current = str(payload.get("current_status") or payload.get("shipment_status") or "")
        mapped = map_shiprocket_status(current)
        scans = payload.get("scans") or []
        stamp = str(payload.get("current_timestamp") or "")
        key = f"sr:{hashlib.sha1(f'{row.awb_number}|{current}|{stamp}'.encode()).hexdigest()}"
        if not any((item.remarks or "") == key for item in row.history):
            target = "RECEIVED" if mapped == "DELIVERED" else "RETURN_SHIPPED"
            if row.return_status not in {"REFUNDED", "COMPLETED", "REJECTED", "INSPECTED"}:
                FulfillmentService._record_return(db, row, target, None, key)
        if payload.get("etd"):
            row.pickup_remarks = str(payload.get("etd"))[:500]

    @staticmethod
    def _history(db, shipment, status_value, location, description, event_key, user_id, event_time=None) -> None:
        db.add(
            ShipmentHistory(
                shipment_id=shipment.id,
                status=status_value,
                location=location,
                description=description,
                event_time=event_time or datetime.now(timezone.utc),
                event_key=event_key,
                updated_by=user_id,
            )
        )
        db.flush()


def _is_cod(order: ProductOrder) -> bool:
    method = (order.payment_method or "").upper()
    payment = (order.payment_status or "").upper()
    return "COD" in method or payment == "COD"


def _order_body(order: ProductOrder, seller: Optional[User], pickup_name: str) -> dict:
    first, last = _split_name(order.buyer_name)
    email = "orders@localhost"
    if order.buyer and order.buyer.email:
        email = order.buyer.email
    elif seller and seller.email:
        email = seller.email
    return {
        "order_id": order.order_code,
        "order_date": (order.created_at or datetime.now(timezone.utc)).strftime("%Y-%m-%d %H:%M"),
        "pickup_location": pickup_name,
        "billing_customer_name": first,
        "billing_last_name": last,
        "billing_address": (order.buyer_address or "Address")[:180],
        "billing_address_2": "",
        "billing_city": order.buyer_city or order.buyer_district or "Kochi",
        "billing_pincode": str(order.buyer_pincode),
        "billing_state": settings.SHIPROCKET_PICKUP_STATE or "Kerala",
        "billing_country": "India",
        "billing_email": email,
        "billing_phone": _digits(order.buyer_phone) or "9999999999",
        "shipping_is_billing": True,
        "order_items": [
            {
                "name": (order.product.name if order.product else "Product")[:80],
                "sku": f"SKU-{order.product_id}",
                "units": int(order.quantity or 1),
                "selling_price": float(order.unit_price or 0),
            }
        ],
        "payment_method": "COD" if _is_cod(order) else "Prepaid",
        "sub_total": float(order.total_price or 0),
        "length": 10,
        "breadth": 10,
        "height": 10,
        "weight": 0.5,
    }


def _created(payload: dict) -> dict:
    if payload.get("shipment_id") or payload.get("order_id"):
        return payload
    message = payload.get("message") or "Shiprocket did not create the shipment."
    raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(message)[:500])


def _normalize_track(tracking: dict, awb: str) -> dict:
    tracks = tracking.get("shipment_track") or []
    head = tracks[0] if tracks else {}
    return {
        "awb": awb,
        "current_status": head.get("current_status") or tracking.get("shipment_status"),
        "etd": head.get("edd") or head.get("etd"),
        "courier_name": head.get("courier_company_name") or head.get("courier_name"),
        "scans": tracking.get("shipment_track_activities") or [],
    }


def _track_payload(order: ProductOrder, shipment: Optional[Shipment]) -> dict:
    product = order.product
    images = (product.images or []) if product else []
    history = []
    if shipment:
        for item in shipment.history or []:
            history.append(
                {
                    "id": item.id,
                    "status": item.status,
                    "location": item.location,
                    "description": item.description,
                    "event_time": item.event_time or item.created_at,
                }
            )
    return {
        "order_id": order.id,
        "order_code": order.order_code,
        "product_name": product.name if product else None,
        "product_image": images[0] if images else None,
        "quantity": order.quantity,
        "unit_price": order.unit_price,
        "total_price": order.total_price,
        "buyer_name": order.buyer_name,
        "courier_name": shipment.courier_name if shipment else order.courier_partner,
        "awb_number": (shipment.awb_number or shipment.tracking_number) if shipment else order.tracking_number,
        "estimated_delivery": (shipment.estimated_delivery if shipment else None) or order.estimated_delivery_at,
        "current_status": shipment.shipment_status if shipment else order.status,
        "tracking_url": (shipment.tracking_url if shipment else None) or order.tracking_url,
        "label_url": shipment.label_url if shipment else None,
        "shiprocket_order_id": shipment.shiprocket_order_id if shipment else None,
        "shiprocket_shipment_id": shipment.shiprocket_shipment_id if shipment else None,
        "history": history,
    }
