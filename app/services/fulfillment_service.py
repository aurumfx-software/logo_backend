import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import List, Optional

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import inspect, or_
from sqlalchemy.orm import Session, joinedload

from app.db.models.fulfillment import (
    OrderReturn,
    PlatformSetting,
    RefundTransaction,
    ReplacementOrder,
    ReturnHistory,
    ReturnItem,
    Shipment,
    ShipmentHistory,
)
from app.db.models.product import CustomerProduct, ProductOrder
from app.db.models.user import User, UserRole
from app.db.models.wallet import WalletLedgerDirection, WalletTransaction, WalletTransactionType
from app.services.product_service import DELIVERY_FLOW, ProductService, generate_order_code, normalize_order_status
from app.services.wallet_service import WalletService

SHIPMENT_STATUSES = {
    "ORDER_PLACED",
    "CONFIRMED",
    "PROCESSING",
    "PACKED",
    "DISPATCHED",
    "IN_TRANSIT",
    "ARRIVED_AT_HUB",
    "OUT_FOR_DELIVERY",
    "DELIVERED",
    "DELIVERY_FAILED",
    "CANCELLED",
    "RETURN_TO_ORIGIN",
}
SHIPMENT_TO_ORDER = {
    "ORDER_PLACED": "PLACED",
    "CONFIRMED": "CONFIRMED",
    "PROCESSING": "CONFIRMED",
    "PACKED": "CONFIRMED",
    "DISPATCHED": "SHIPPED",
    "IN_TRANSIT": "SHIPPED",
    "ARRIVED_AT_HUB": "SHIPPED",
    "OUT_FOR_DELIVERY": "OUT_FOR_DELIVERY",
    "DELIVERY_FAILED": "OUT_FOR_DELIVERY",
    "DELIVERED": "DELIVERED",
}
RETURN_REASONS = {
    "PRODUCT_DAMAGED",
    "WRONG_PRODUCT",
    "NOT_AS_DESCRIBED",
    "QUALITY_ISSUE",
    "MISSING_ACCESSORIES",
    "SIZE_OR_FIT",
    "OTHER",
}
RETURN_REASON_ALIASES = {
    "PRODUCT DAMAGED": "PRODUCT_DAMAGED",
    "DAMAGED PRODUCT": "PRODUCT_DAMAGED",
    "WRONG PRODUCT": "WRONG_PRODUCT",
    "WRONG PRODUCT RECEIVED": "WRONG_PRODUCT",
    "PRODUCT NOT AS DESCRIBED": "NOT_AS_DESCRIBED",
    "QUALITY ISSUE": "QUALITY_ISSUE",
    "MISSING ACCESSORIES": "MISSING_ACCESSORIES",
    "SIZE OR FIT ISSUE": "SIZE_OR_FIT",
    "OTHER": "OTHER",
}
RETURN_TYPES = {"SELF_SHIPPING", "MANUAL_PICKUP", "REPLACEMENT"}
RETURN_STATUSES = {
    "REQUESTED",
    "UNDER_REVIEW",
    "APPROVED",
    "REJECTED",
    "PICKUP_SCHEDULED",
    "PICKUP_COMPLETED",
    "RETURN_SHIPPED",
    "RECEIVED",
    "INSPECTED",
    "REFUND_PROCESSING",
    "REFUNDED",
    "REPLACEMENT_CREATED",
    "COMPLETED",
}
OPEN_RETURN_STATUSES = RETURN_STATUSES - {"REJECTED", "COMPLETED"}
REFUND_METHODS = {"ORIGINAL", "BANK_TRANSFER", "UPI", "STORE_WALLET"}
REFUND_STATUSES = {"PENDING", "PROCESSING", "SUCCESS", "FAILED"}
PAID_STATUSES = {"PAID", "COD"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {".jpg", ".jpeg", ".png", ".webp"}


class FulfillmentService:
    @staticmethod
    def ensure_tables(db: Session) -> None:
        if db.info.get("fulfillment_ready"):
            return
        bind = db.get_bind()
        existing = set(inspect(bind).get_table_names())
        for model in (
            PlatformSetting,
            Shipment,
            ShipmentHistory,
            OrderReturn,
            ReturnItem,
            ReturnHistory,
            RefundTransaction,
            ReplacementOrder,
        ):
            if model.__tablename__ not in existing:
                model.__table__.create(bind=bind, checkfirst=True)
        FulfillmentService._ensure_shiprocket_columns(db)
        db.info["fulfillment_ready"] = True

    @staticmethod
    def _ensure_shiprocket_columns(db: Session) -> None:
        bind = db.connection()
        additions = {
            "shipments": [
                ("courier_id", "VARCHAR(32)"),
                ("awb_number", "VARCHAR(64)"),
                ("label_url", "VARCHAR(500)"),
                ("shiprocket_order_id", "VARCHAR(64)"),
                ("shiprocket_shipment_id", "VARCHAR(64)"),
            ],
            "shipment_history": [
                ("event_time", "TIMESTAMP"),
                ("event_key", "VARCHAR(180)"),
            ],
            "order_returns": [
                ("shiprocket_order_id", "VARCHAR(64)"),
                ("shiprocket_shipment_id", "VARCHAR(64)"),
                ("tracking_url", "VARCHAR(500)"),
                ("inspection_status", "VARCHAR(40)"),
                ("refund_amount", "NUMERIC(12, 2)"),
                ("refund_status", "VARCHAR(20)"),
            ],
        }
        inspector = inspect(bind)
        tables = set(inspector.get_table_names())
        for table, columns in additions.items():
            if table not in tables:
                continue
            present = {column["name"] for column in inspector.get_columns(table)}
            for name, ddl in columns:
                if name in present:
                    continue
                bind.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
        if "shipment_history" in tables:
            try:
                bind.exec_driver_sql(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_shipment_history_event_key ON shipment_history (event_key)"
                )
            except Exception:
                pass

    @staticmethod
    def _is_admin(user: User) -> bool:
        return user.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN)

    @staticmethod
    def _money(value) -> Decimal:
        return Decimal(str(value or 0)).quantize(Decimal("0.01"))

    @staticmethod
    def _parse_status(value: str, allowed: set, label: str) -> str:
        clean = (value or "").strip().upper().replace(" ", "_").replace("-", "_")
        if clean not in allowed:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown {label}: {value}")
        return clean

    @staticmethod
    def _reason(value: str) -> str:
        raw = (value or "").strip()
        key = raw.upper().replace("-", "_")
        if key in RETURN_REASONS:
            return key
        alias = RETURN_REASON_ALIASES.get(raw.upper())
        if alias:
            return alias
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown return reason.")

    @staticmethod
    def return_window_days(db: Session) -> int:
        FulfillmentService.ensure_tables(db)
        row = db.query(PlatformSetting).filter(PlatformSetting.key == "return_window_days").first()
        if not row:
            return 7
        try:
            return max(0, int(row.value))
        except ValueError:
            return 7

    @staticmethod
    def set_return_window(db: Session, days: int) -> int:
        FulfillmentService.ensure_tables(db)
        row = db.query(PlatformSetting).filter(PlatformSetting.key == "return_window_days").first()
        if not row:
            row = PlatformSetting(key="return_window_days", value=str(days))
            db.add(row)
        else:
            row.value = str(days)
        db.commit()
        return days

    @staticmethod
    def _order(db: Session, order_id: int) -> ProductOrder:
        ProductService.ensure_order_schema(db)
        order = db.query(ProductOrder).filter(ProductOrder.id == order_id).first()
        if not order:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found.")
        return order

    @staticmethod
    def _can_manage_shipment(user: User, order: ProductOrder) -> bool:
        return FulfillmentService._is_admin(user) or order.seller_id == user.id

    @staticmethod
    def _can_view_order(user: User, order: ProductOrder) -> bool:
        return (
            FulfillmentService._can_manage_shipment(user, order)
            or order.buyer_user_id == user.id
        )

    @staticmethod
    def _notify(db: Session, user_id: Optional[int], title: str, message: str, data: dict) -> None:
        if not user_id:
            return
        try:
            from app.services.notification_service import NotificationService

            NotificationService.create_notification(db, user_id, title, message, type="ORDER", data=data)
        except Exception:
            db.rollback()

    @staticmethod
    def _audit(db: Session, user: User, action: str, entity_id: int, details: dict) -> None:
        try:
            from app.services.activity_log_service import ActivityLogService

            ActivityLogService.log_activity(
                db=db,
                action=action,
                entity_type="ORDER",
                entity_id=entity_id,
                user_id=user.id,
                details=details,
            )
        except Exception:
            db.rollback()

    @staticmethod
    def _advance_order(order: ProductOrder, shipment_status: str, note: Optional[str]) -> None:
        if shipment_status == "CANCELLED":
            current = normalize_order_status(order.status or "PLACED")
            if current in {"PLACED", "CONFIRMED"}:
                ProductService._record_status(order, "CANCELLED", note)
            return
        target = SHIPMENT_TO_ORDER.get(shipment_status)
        if not target:
            return
        rank = {key: index for index, (key, _label) in enumerate(DELIVERY_FLOW)}
        current = normalize_order_status(order.status or "PLACED")
        if current not in rank or target not in rank or rank[current] >= rank[target]:
            return
        while rank[normalize_order_status(order.status or "PLACED")] < rank[target]:
            nxt = DELIVERY_FLOW[rank[normalize_order_status(order.status)] + 1][0]
            ProductService._record_status(order, nxt, note if nxt == target else None)

    @staticmethod
    def _shipment_response(shipment: Shipment) -> dict:
        order = shipment.order
        product = order.product if order else None
        images = (product.images or []) if product else []
        if isinstance(images, str):
            images = []
        return {
            "id": shipment.id,
            "order_id": shipment.order_id,
            "order_code": order.order_code if order else None,
            "product_name": product.name if product else None,
            "product_image": images[0] if images else None,
            "quantity": order.quantity if order else None,
            "order_date": order.created_at if order else None,
            "courier_name": shipment.courier_name,
            "tracking_number": shipment.tracking_number or shipment.awb_number,
            "awb_number": shipment.awb_number or shipment.tracking_number,
            "tracking_url": shipment.tracking_url,
            "label_url": shipment.label_url,
            "shiprocket_order_id": shipment.shiprocket_order_id,
            "shiprocket_shipment_id": shipment.shiprocket_shipment_id,
            "shipment_status": shipment.shipment_status,
            "remarks": shipment.remarks,
            "dispatched_at": shipment.dispatched_at,
            "estimated_delivery": shipment.estimated_delivery,
            "delivered_at": shipment.delivered_at,
            "history": shipment.history or [],
        }

    @staticmethod
    def _copy_tracking(order: ProductOrder, shipment: Shipment) -> None:
        order.courier_partner = shipment.courier_name
        order.tracking_number = shipment.tracking_number
        order.tracking_url = shipment.tracking_url
        order.estimated_delivery_at = shipment.estimated_delivery

    @staticmethod
    def create_shipment(db: Session, user: User, data) -> Shipment:
        FulfillmentService.ensure_tables(db)
        order = FulfillmentService._order(db, data.order_id)
        if not FulfillmentService._can_manage_shipment(user, order):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only an admin or the seller can dispatch this order.")
        existing = db.query(Shipment).filter(Shipment.order_id == order.id).first()
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This order already has a shipment. Update it instead.")
        shipment_status = FulfillmentService._parse_status(data.shipment_status, SHIPMENT_STATUSES, "shipment status")
        shipment = Shipment(
            order_id=order.id,
            courier_name=(data.courier_name or "").strip() or None,
            tracking_number=(data.tracking_number or "").strip() or None,
            awb_number=(data.tracking_number or "").strip() or None,
            tracking_url=(data.tracking_url or "").strip() or None,
            shipment_status=shipment_status,
            remarks=(data.remarks or "").strip() or None,
            dispatched_at=data.dispatched_at or (datetime.now(timezone.utc) if shipment_status == "DISPATCHED" else None),
            estimated_delivery=data.estimated_delivery,
            delivered_at=datetime.now(timezone.utc) if shipment_status == "DELIVERED" else None,
        )
        db.add(shipment)
        db.flush()
        db.add(
            ShipmentHistory(
                shipment_id=shipment.id,
                status=shipment_status,
                location=(data.location or "").strip() or None,
                description=shipment.remarks,
                updated_by=user.id,
            )
        )
        FulfillmentService._copy_tracking(order, shipment)
        FulfillmentService._advance_order(order, shipment_status, shipment.remarks)
        db.commit()
        db.refresh(shipment)
        FulfillmentService._notify(
            db,
            order.buyer_user_id,
            "Shipment update",
            f"Order {order.order_code} is {shipment_status.replace('_', ' ').lower()}.",
            {"order_id": order.id, "shipment_id": shipment.id},
        )
        FulfillmentService._audit(db, user, "SHIPMENT_CREATED", order.id, {"status": shipment_status})
        return db.query(Shipment).options(joinedload(Shipment.history), joinedload(Shipment.order)).filter(Shipment.id == shipment.id).first()

    @staticmethod
    def shipment_for_order(db: Session, user: User, order_id: int) -> Shipment:
        FulfillmentService.ensure_tables(db)
        order = FulfillmentService._order(db, order_id)
        if not FulfillmentService._can_view_order(user, order):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot view this shipment.")
        shipment = (
            db.query(Shipment)
            .options(joinedload(Shipment.history), joinedload(Shipment.order))
            .filter(Shipment.order_id == order.id)
            .first()
        )
        if not shipment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shipment not found.")
        return shipment

    @staticmethod
    def _owned_shipment(db: Session, user: User, shipment_id: int) -> Shipment:
        FulfillmentService.ensure_tables(db)
        shipment = (
            db.query(Shipment)
            .options(joinedload(Shipment.history), joinedload(Shipment.order))
            .filter(Shipment.id == shipment_id)
            .first()
        )
        if not shipment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shipment not found.")
        if not FulfillmentService._can_manage_shipment(user, shipment.order):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot change this shipment.")
        return shipment

    @staticmethod
    def update_shipment_status(db: Session, user: User, shipment_id: int, data) -> Shipment:
        shipment = FulfillmentService._owned_shipment(db, user, shipment_id)
        shipment_status = FulfillmentService._parse_status(data.shipment_status, SHIPMENT_STATUSES, "shipment status")
        shipment.shipment_status = shipment_status
        if shipment_status == "DISPATCHED" and not shipment.dispatched_at:
            shipment.dispatched_at = datetime.now(timezone.utc)
        if shipment_status == "DELIVERED":
            shipment.delivered_at = datetime.now(timezone.utc)
        description = (data.description or "").strip() or None
        db.add(
            ShipmentHistory(
                shipment_id=shipment.id,
                status=shipment_status,
                location=(data.location or "").strip() or None,
                description=description,
                updated_by=user.id,
            )
        )
        FulfillmentService._advance_order(shipment.order, shipment_status, description)
        db.commit()
        order = shipment.order
        FulfillmentService._notify(
            db,
            order.buyer_user_id,
            "Shipment update",
            f"Order {order.order_code} is now {shipment_status.replace('_', ' ').lower()}.",
            {"order_id": order.id, "shipment_id": shipment.id},
        )
        return FulfillmentService._owned_shipment(db, user, shipment.id)

    @staticmethod
    def update_shipment_details(db: Session, user: User, shipment_id: int, data) -> Shipment:
        shipment = FulfillmentService._owned_shipment(db, user, shipment_id)
        changes = data.model_dump(exclude_unset=True)
        for field in ("courier_name", "tracking_number", "tracking_url", "remarks"):
            if field in changes:
                value = changes[field]
                setattr(shipment, field, value.strip() if isinstance(value, str) and value.strip() else None)
        if "dispatched_at" in changes:
            shipment.dispatched_at = changes["dispatched_at"]
        if "estimated_delivery" in changes:
            shipment.estimated_delivery = changes["estimated_delivery"]
        FulfillmentService._copy_tracking(shipment.order, shipment)
        db.commit()
        return FulfillmentService._owned_shipment(db, user, shipment.id)

    @staticmethod
    def shipment_history(db: Session, user: User, shipment_id: int) -> List[ShipmentHistory]:
        shipment = (
            db.query(Shipment)
            .options(joinedload(Shipment.order))
            .filter(Shipment.id == shipment_id)
            .first()
        )
        if not shipment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shipment not found.")
        if not FulfillmentService._can_view_order(user, shipment.order):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot view this shipment.")
        return db.query(ShipmentHistory).filter(ShipmentHistory.shipment_id == shipment.id).order_by(ShipmentHistory.id).all()

    @staticmethod
    def _returned_quantity(db: Session, order_id: int) -> int:
        rows = (
            db.query(ReturnItem)
            .join(OrderReturn, OrderReturn.id == ReturnItem.return_id)
            .filter(OrderReturn.order_id == order_id, OrderReturn.return_status != "REJECTED")
            .all()
        )
        return sum(row.quantity for row in rows)

    @staticmethod
    def _delivered_at(order: ProductOrder) -> datetime:
        history = order.status_history or []
        if isinstance(history, str):
            history = []
        for row in reversed(history):
            if isinstance(row, dict) and normalize_order_status(str(row.get("status"))) == "DELIVERED" and row.get("at"):
                try:
                    return datetime.fromisoformat(str(row["at"]).replace("Z", "+00:00"))
                except ValueError:
                    break
        return order.updated_at or datetime.now(timezone.utc)

    @staticmethod
    def _assert_returnable(db: Session, order: ProductOrder, quantity: int) -> None:
        if normalize_order_status(order.status or "") != "DELIVERED":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only a delivered order can be returned.")
        window = FulfillmentService.return_window_days(db)
        delivered_at = FulfillmentService._delivered_at(order)
        if delivered_at.tzinfo is None:
            delivered_at = delivered_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > delivered_at + timedelta(days=window):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The return window for this order has closed.")
        already = FulfillmentService._returned_quantity(db, order.id)
        remaining = int(order.quantity or 0) - already
        if quantity > remaining:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Return quantity cannot exceed the remaining quantity ({remaining}).",
            )

    @staticmethod
    def _return_number() -> str:
        return f"RET-{secrets.randbelow(90000) + 10000}"

    @staticmethod
    def _record_return(db: Session, order_return: OrderReturn, status_value: str, user: Optional[User], remarks: Optional[str]) -> None:
        order_return.return_status = status_value
        db.add(
            ReturnHistory(
                return_id=order_return.id,
                status=status_value,
                remarks=(remarks or "").strip() or None,
                updated_by=user.id if user else None,
            )
        )

    @staticmethod
    def create_return(db: Session, user: User, data) -> OrderReturn:
        FulfillmentService.ensure_tables(db)
        order = FulfillmentService._order(db, data.order_id)
        if order.buyer_user_id != user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can return only your own order.")
        return_type = FulfillmentService._parse_status(data.return_type, RETURN_TYPES, "return method")
        reason = FulfillmentService._reason(data.return_reason)
        FulfillmentService._assert_returnable(db, order, data.quantity)
        order_return = OrderReturn(
            return_number=FulfillmentService._return_number(),
            order_id=order.id,
            user_id=user.id,
            return_reason=reason,
            description=(data.description or "").strip() or None,
            return_type=return_type,
            return_status="REQUESTED",
            courier_name=(data.courier_name or "").strip() or None,
            awb_number=(data.awb_number or "").strip() or None,
            shipping_date=(data.shipping_date or "").strip() or None,
            receipt_url=(data.receipt_url or "").strip() or None,
        )
        db.add(order_return)
        db.flush()
        db.add(
            ReturnItem(
                return_id=order_return.id,
                order_item_id=order.id,
                product_id=order.product_id,
                quantity=data.quantity,
                image_urls=list(data.image_urls or []),
            )
        )
        FulfillmentService._record_return(db, order_return, "REQUESTED", user, data.description)
        if return_type == "SELF_SHIPPING" and order_return.awb_number:
            FulfillmentService._record_return(db, order_return, "RETURN_SHIPPED", user, order_return.awb_number)
        db.commit()
        FulfillmentService._notify(
            db,
            user.id,
            "Return requested",
            f"Return {order_return.return_number} was submitted for order {order.order_code}.",
            {"return_id": order_return.id, "order_id": order.id},
        )
        return FulfillmentService.get_return(db, user, order_return.id)

    @staticmethod
    def _load_return(db: Session, return_id: int) -> OrderReturn:
        FulfillmentService.ensure_tables(db)
        row = (
            db.query(OrderReturn)
            .options(
                joinedload(OrderReturn.items),
                joinedload(OrderReturn.history),
                joinedload(OrderReturn.refunds),
            )
            .filter(OrderReturn.id == return_id)
            .first()
        )
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Return request not found.")
        return row

    @staticmethod
    def _visible_return(db: Session, user: User, return_id: int) -> OrderReturn:
        row = FulfillmentService._load_return(db, return_id)
        if not FulfillmentService._is_admin(user) and row.user_id != user.id:
            order = FulfillmentService._order(db, row.order_id)
            if order.seller_id != user.id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot view this return.")
        return row

    @staticmethod
    def return_payload(db: Session, row: OrderReturn) -> dict:
        order = db.query(ProductOrder).filter(ProductOrder.id == row.order_id).first()
        buyer = db.query(User).filter(User.id == row.user_id).first()
        replacement = db.query(ReplacementOrder).filter(ReplacementOrder.return_id == row.id).first()
        replacement_code = None
        if replacement:
            replacement_order = db.query(ProductOrder).filter(ProductOrder.id == replacement.replacement_order_id).first()
            replacement_code = replacement_order.order_code if replacement_order else None
        data = {
            "id": row.id,
            "return_number": row.return_number,
            "order_id": row.order_id,
            "order_code": order.order_code if order else None,
            "user_id": row.user_id,
            "customer_name": buyer.name if buyer else None,
            "return_reason": row.return_reason,
            "description": row.description,
            "return_type": row.return_type,
            "return_status": row.return_status,
            "courier_name": row.courier_name,
            "awb_number": row.awb_number,
            "shiprocket_order_id": row.shiprocket_order_id,
            "shiprocket_shipment_id": row.shiprocket_shipment_id,
            "tracking_url": row.tracking_url,
            "inspection_status": row.inspection_status,
            "refund_amount": row.refund_amount,
            "refund_status": row.refund_status,
            "shipping_date": row.shipping_date,
            "receipt_url": row.receipt_url,
            "pickup_date": row.pickup_date,
            "pickup_remarks": row.pickup_remarks,
            "admin_notes": row.admin_notes,
            "rejection_reason": row.rejection_reason,
            "items": row.items or [],
            "history": row.history or [],
            "refunds": row.refunds or [],
            "replacement": None,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
        if replacement:
            data["replacement"] = {
                "id": replacement.id,
                "original_order_id": replacement.original_order_id,
                "return_id": replacement.return_id,
                "replacement_order_id": replacement.replacement_order_id,
                "replacement_order_code": replacement_code,
                "status": replacement.status,
                "created_at": replacement.created_at,
            }
        return data

    @staticmethod
    def get_return(db: Session, user: User, return_id: int) -> dict:
        return FulfillmentService.return_payload(db, FulfillmentService._visible_return(db, user, return_id))

    @staticmethod
    def my_returns(db: Session, user: User) -> List[dict]:
        FulfillmentService.ensure_tables(db)
        rows = (
            db.query(OrderReturn)
            .options(joinedload(OrderReturn.items), joinedload(OrderReturn.history), joinedload(OrderReturn.refunds))
            .filter(OrderReturn.user_id == user.id)
            .order_by(OrderReturn.id.desc())
            .all()
        )
        return [FulfillmentService.return_payload(db, row) for row in rows]

    @staticmethod
    def list_returns(db: Session, status_filter: Optional[str], query: Optional[str], page: int, page_size: int) -> tuple:
        FulfillmentService.ensure_tables(db)
        q = db.query(OrderReturn).options(
            joinedload(OrderReturn.items),
            joinedload(OrderReturn.history),
            joinedload(OrderReturn.refunds),
        )
        if status_filter:
            q = q.filter(OrderReturn.return_status == FulfillmentService._parse_status(status_filter, RETURN_STATUSES, "return status"))
        if query:
            term = f"%{query.strip()}%"
            q = q.outerjoin(ProductOrder, ProductOrder.id == OrderReturn.order_id).outerjoin(User, User.id == OrderReturn.user_id).filter(
                or_(
                    OrderReturn.return_number.ilike(term),
                    ProductOrder.order_code.ilike(term),
                    User.name.ilike(term),
                    User.email.ilike(term),
                )
            )
        total = q.count()
        rows = q.order_by(OrderReturn.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
        return [FulfillmentService.return_payload(db, row) for row in rows], total

    @staticmethod
    def stats(db: Session) -> dict:
        FulfillmentService.ensure_tables(db)
        rows = db.query(OrderReturn.return_status).all()
        statuses = [row[0] for row in rows]
        refunds_pending = (
            db.query(RefundTransaction)
            .filter(RefundTransaction.refund_status.in_(["PENDING", "PROCESSING"]))
            .count()
        )
        return {
            "total": len(statuses),
            "pending": sum(1 for item in statuses if item in {"REQUESTED", "UNDER_REVIEW"}),
            "approved": sum(1 for item in statuses if item == "APPROVED"),
            "rejected": sum(1 for item in statuses if item == "REJECTED"),
            "awaiting_pickup": sum(1 for item in statuses if item == "PICKUP_SCHEDULED"),
            "awaiting_inspection": sum(1 for item in statuses if item == "RECEIVED"),
            "refunds_pending": refunds_pending,
            "completed": sum(1 for item in statuses if item in {"COMPLETED", "REFUNDED", "REPLACEMENT_CREATED"}),
        }

    @staticmethod
    def _admin_return(db: Session, user: User, return_id: int) -> OrderReturn:
        if not FulfillmentService._is_admin(user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only an admin can manage returns.")
        return FulfillmentService._load_return(db, return_id)

    @staticmethod
    def approve_return(db: Session, user: User, return_id: int, remarks: Optional[str]) -> dict:
        row = FulfillmentService._admin_return(db, user, return_id)
        if row.return_status not in {"REQUESTED", "UNDER_REVIEW"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This return cannot be approved from its current status.")
        FulfillmentService._record_return(db, row, "APPROVED", user, remarks)
        db.commit()
        FulfillmentService._notify(db, row.user_id, "Return approved", f"Return {row.return_number} was approved.", {"return_id": row.id})
        FulfillmentService._audit(db, user, "RETURN_APPROVED", row.order_id, {"return_id": row.id})
        return FulfillmentService.get_return(db, user, row.id)

    @staticmethod
    def reject_return(db: Session, user: User, return_id: int, reason: str) -> dict:
        row = FulfillmentService._admin_return(db, user, return_id)
        if row.return_status in {"REJECTED", "REFUNDED", "COMPLETED", "REPLACEMENT_CREATED"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This return can no longer be rejected.")
        if not (reason or "").strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A rejection reason is required.")
        row.rejection_reason = reason.strip()
        FulfillmentService._record_return(db, row, "REJECTED", user, reason)
        db.commit()
        FulfillmentService._notify(db, row.user_id, "Return rejected", f"Return {row.return_number} was rejected.", {"return_id": row.id})
        FulfillmentService._audit(db, user, "RETURN_REJECTED", row.order_id, {"return_id": row.id, "reason": reason.strip()})
        return FulfillmentService.get_return(db, user, row.id)

    @staticmethod
    def set_return_status(db: Session, user: User, return_id: int, new_status: str, remarks: Optional[str]) -> dict:
        row = FulfillmentService._admin_return(db, user, return_id)
        clean = FulfillmentService._parse_status(new_status, RETURN_STATUSES, "return status")
        FulfillmentService._record_return(db, row, clean, user, remarks)
        if remarks:
            row.admin_notes = remarks.strip()
        db.commit()
        FulfillmentService._notify(db, row.user_id, "Return update", f"Return {row.return_number} is {clean.replace('_', ' ').lower()}.", {"return_id": row.id})
        return FulfillmentService.get_return(db, user, row.id)

    @staticmethod
    def schedule_pickup(db: Session, user: User, return_id: int, pickup_date: str, remarks: Optional[str]) -> dict:
        row = FulfillmentService._admin_return(db, user, return_id)
        row.pickup_date = pickup_date.strip()
        row.pickup_remarks = (remarks or "").strip() or None
        FulfillmentService._record_return(db, row, "PICKUP_SCHEDULED", user, remarks or pickup_date)
        db.commit()
        FulfillmentService._notify(db, row.user_id, "Pickup scheduled", f"Pickup for return {row.return_number} is set for {row.pickup_date}.", {"return_id": row.id})
        return FulfillmentService.get_return(db, user, row.id)

    @staticmethod
    def customer_shipping(db: Session, user: User, return_id: int, data) -> dict:
        row = FulfillmentService._visible_return(db, user, return_id)
        if row.user_id != user.id and not FulfillmentService._is_admin(user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot update this return shipment.")
        row.return_type = "SELF_SHIPPING"
        row.courier_name = data.courier_name.strip()
        row.awb_number = data.awb_number.strip()
        row.shipping_date = data.shipping_date.strip()
        row.receipt_url = (data.receipt_url or "").strip() or None
        FulfillmentService._record_return(db, row, "RETURN_SHIPPED", user, row.awb_number)
        db.commit()
        return FulfillmentService.get_return(db, user, row.id)

    @staticmethod
    def receive_return(db: Session, user: User, return_id: int, remarks: Optional[str]) -> dict:
        row = FulfillmentService._admin_return(db, user, return_id)
        FulfillmentService._record_return(db, row, "RECEIVED", user, remarks)
        db.commit()
        FulfillmentService._notify(db, row.user_id, "Return received", f"We received the items for return {row.return_number}.", {"return_id": row.id})
        return FulfillmentService.get_return(db, user, row.id)

    @staticmethod
    def inspect_return(db: Session, user: User, return_id: int, condition: str, remarks: Optional[str]) -> dict:
        row = FulfillmentService._admin_return(db, user, return_id)
        for item in row.items:
            item.product_condition = condition.strip()
        row.inspection_status = condition.strip()
        FulfillmentService._record_return(db, row, "INSPECTED", user, remarks or condition)
        db.commit()
        return FulfillmentService.get_return(db, user, row.id)

    @staticmethod
    def _eligible_refund(db: Session, order: ProductOrder, row: OrderReturn) -> Decimal:
        if (order.payment_status or "").upper() not in PAID_STATUSES:
            return Decimal("0.00")
        item_qty = sum(item.quantity for item in row.items) or 0
        share = FulfillmentService._money(order.total_price) * Decimal(item_qty) / Decimal(order.quantity or 1)
        previous = (
            db.query(RefundTransaction)
            .join(OrderReturn, OrderReturn.id == RefundTransaction.return_id)
            .filter(OrderReturn.order_id == order.id, RefundTransaction.refund_status == "SUCCESS")
            .all()
        )
        used = sum((FulfillmentService._money(item.refund_amount) for item in previous), Decimal("0.00"))
        remaining = FulfillmentService._money(share) - used
        return remaining if remaining > 0 else Decimal("0.00")

    @staticmethod
    def create_refund(db: Session, user: User, return_id: int, data) -> RefundTransaction:
        row = FulfillmentService._admin_return(db, user, return_id)
        method = FulfillmentService._parse_status(data.refund_method, REFUND_METHODS, "refund method")
        open_refund = (
            db.query(RefundTransaction)
            .filter(
                RefundTransaction.return_id == row.id,
                RefundTransaction.refund_status.in_(["PENDING", "PROCESSING", "SUCCESS"]),
            )
            .first()
        )
        if open_refund:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A refund is already recorded for this return.")
        order = FulfillmentService._order(db, row.order_id)
        eligible = FulfillmentService._eligible_refund(db, order, row)
        amount = FulfillmentService._money(data.refund_amount)
        if amount > eligible:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Refund cannot exceed the eligible amount of {eligible}.",
            )
        refund = RefundTransaction(
            return_id=row.id,
            refund_amount=amount,
            refund_method=method,
            transaction_reference=(data.transaction_reference or "").strip() or None,
            refund_status="PENDING",
            admin_remarks=(data.admin_remarks or "").strip() or None,
            refund_date=(data.refund_date or "").strip() or None,
            processed_by=user.id,
            wallet_credited=False,
        )
        db.add(refund)
        row.refund_amount = amount
        row.refund_status = "PENDING"
        FulfillmentService._record_return(db, row, "REFUND_PROCESSING", user, data.admin_remarks)
        db.commit()
        db.refresh(refund)
        FulfillmentService._audit(db, user, "REFUND_RECORDED", row.order_id, {"return_id": row.id, "amount": str(amount), "status": "PENDING"})
        return refund

    @staticmethod
    def list_refunds(db: Session, user: User, return_id: int) -> List[RefundTransaction]:
        row = FulfillmentService._visible_return(db, user, return_id)
        return db.query(RefundTransaction).filter(RefundTransaction.return_id == row.id).order_by(RefundTransaction.id).all()

    @staticmethod
    def _credit_wallet(db: Session, user_id: int, amount: Decimal, admin_id: int, reference: str) -> None:
        wallet = WalletService.ensure_wallet_for_user(db, user_id)
        txn = WalletTransaction(
            transaction_type=WalletTransactionType.ADMIN_CREDIT,
            amount=amount,
            description=f"Order refund {reference}",
            initiated_by_user_id=admin_id,
            reference_id=reference,
        )
        db.add(txn)
        db.flush()
        WalletService._apply_ledger_line(
            db,
            txn,
            wallet,
            WalletLedgerDirection.CREDIT,
            amount,
            note=f"Order refund {reference}",
        )

    @staticmethod
    def update_refund_status(db: Session, user: User, refund_id: int, data) -> RefundTransaction:
        if not FulfillmentService._is_admin(user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only an admin can update a refund.")
        FulfillmentService.ensure_tables(db)
        refund = db.query(RefundTransaction).filter(RefundTransaction.id == refund_id).first()
        if not refund:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Refund not found.")
        new_status = FulfillmentService._parse_status(data.refund_status, REFUND_STATUSES, "refund status")
        if refund.refund_status == "SUCCESS":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This refund is already successful.")
        if data.transaction_reference:
            refund.transaction_reference = data.transaction_reference.strip()
        if data.admin_remarks:
            refund.admin_remarks = data.admin_remarks.strip()
        if data.refund_date:
            refund.refund_date = data.refund_date.strip()
        refund.refund_status = new_status
        refund.processed_by = user.id
        refund.processed_at = datetime.now(timezone.utc)
        row = FulfillmentService._load_return(db, refund.return_id)
        row.refund_amount = refund.refund_amount
        row.refund_status = new_status
        if new_status == "SUCCESS":
            if refund.refund_method == "STORE_WALLET" and not refund.wallet_credited:
                FulfillmentService._credit_wallet(db, row.user_id, FulfillmentService._money(refund.refund_amount), user.id, row.return_number)
                refund.wallet_credited = True
            FulfillmentService._record_return(db, row, "REFUNDED", user, data.admin_remarks)
            order = FulfillmentService._order(db, row.order_id)
            order.payment_status = "REFUNDED"
        elif new_status == "FAILED":
            FulfillmentService._record_return(db, row, "INSPECTED", user, "Refund failed")
        db.commit()
        db.refresh(refund)
        if new_status == "SUCCESS":
            FulfillmentService._notify(db, row.user_id, "Refund processed", f"Refund for {row.return_number} is successful.", {"return_id": row.id})
        FulfillmentService._audit(db, user, "REFUND_STATUS", row.order_id, {"refund_id": refund.id, "status": new_status})
        return refund

    @staticmethod
    def create_replacement(db: Session, user: User, return_id: int, data) -> ReplacementOrder:
        row = FulfillmentService._admin_return(db, user, return_id)
        if db.query(ReplacementOrder).filter(ReplacementOrder.return_id == row.id).first():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A replacement order already exists for this return.")
        original = FulfillmentService._order(db, row.order_id)
        product_id = data.product_id or original.product_id
        product = db.query(CustomerProduct).filter(CustomerProduct.id == product_id).first()
        if not product:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Replacement product not found.")
        difference = FulfillmentService._money(data.price_difference)
        if difference < 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Price difference cannot be negative.")
        if product.stock_quantity is not None and product.stock_quantity < data.quantity:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Not enough stock for the replacement.")
        replacement_order = ProductOrder(
            order_code=generate_order_code(),
            product_id=product.id,
            seller_id=product.seller_id,
            buyer_user_id=original.buyer_user_id,
            buyer_name=original.buyer_name,
            buyer_phone=original.buyer_phone,
            buyer_address=original.buyer_address,
            buyer_location=original.buyer_location,
            buyer_city=original.buyer_city,
            buyer_district=original.buyer_district,
            buyer_pincode=original.buyer_pincode,
            selected_size=original.selected_size,
            quantity=data.quantity,
            unit_price=Decimal("0.00") if difference == 0 else difference,
            total_price=difference,
            status="PLACED",
            notes=f"Replacement for {original.order_code}. {(data.remarks or '').strip()}".strip(),
            payment_status="PAID" if difference == 0 else "UNPAID",
            payment_method="REPLACEMENT",
            status_history=[{"status": "PLACED", "note": "Replacement order", "at": datetime.now(timezone.utc).isoformat()}],
        )
        db.add(replacement_order)
        db.flush()
        if product.stock_quantity is not None:
            product.stock_quantity = product.stock_quantity - data.quantity
        link = ReplacementOrder(
            original_order_id=original.id,
            return_id=row.id,
            replacement_order_id=replacement_order.id,
            status="CREATED",
        )
        db.add(link)
        FulfillmentService._record_return(db, row, "REPLACEMENT_CREATED", user, data.remarks)
        db.commit()
        db.refresh(link)
        FulfillmentService._notify(
            db,
            original.buyer_user_id,
            "Replacement created",
            f"Replacement order {replacement_order.order_code} was created for return {row.return_number}.",
            {"return_id": row.id, "order_id": replacement_order.id},
        )
        FulfillmentService._audit(db, user, "REPLACEMENT_CREATED", original.id, {"replacement_order_id": replacement_order.id})
        return link

    @staticmethod
    def replacement_for_return(db: Session, user: User, return_id: int) -> dict:
        row = FulfillmentService._visible_return(db, user, return_id)
        link = db.query(ReplacementOrder).filter(ReplacementOrder.return_id == row.id).first()
        if not link:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No replacement order for this return.")
        return FulfillmentService.return_payload(db, row)["replacement"]

    @staticmethod
    def save_return_image(upload: UploadFile) -> str:
        ext = os.path.splitext(upload.filename or "")[1].lower()
        if ext not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Upload a JPG, PNG, or WEBP image.")
        content = upload.file.read()
        if len(content) > MAX_IMAGE_BYTES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Image must be 5 MB or smaller.")
        folder = os.path.join("uploads", "returns")
        os.makedirs(folder, exist_ok=True)
        name = f"{uuid.uuid4().hex}{ext}"
        with open(os.path.join(folder, name), "wb") as handle:
            handle.write(content)
        return f"/static/returns/{name}"
