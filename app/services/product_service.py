import math
import random
import urllib.parse
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional, Tuple, Dict, Any
from fastapi import HTTPException, status
from sqlalchemy import and_, inspect, or_, desc, text
from sqlalchemy.orm import Session

from app.db.models.user import User, UserRole
from app.db.models.product import (
    CartItem,
    CustomerProduct,
    DeliveryAddress,
    ProductOrder,
    ProductReview,
    ProductWishlist,
)
from app.schemas.product import (
    ProductCreateRequest,
    ProductUpdateRequest,
    ProductAdminStatusUpdate,
    ProductResponse,
    OrderCreateRequest,
    OrderResponse,
    SellerPermissionToggleRequest,
)


DELIVERY_FLOW = [
    ("PLACED", "Order placed"),
    ("CONFIRMED", "Seller confirmed"),
    ("SHIPPED", "Shipped"),
    ("OUT_FOR_DELIVERY", "Out for delivery"),
    ("DELIVERED", "Delivered"),
]
STATUS_ALIASES = {
    "NEW": "PLACED",
    "PENDING": "PLACED",
    "CONTACTED": "CONFIRMED",
    "PACKED": "CONFIRMED",
}
ALLOWED_ORDER_STATUSES = {
    "PLACED",
    "CONFIRMED",
    "SHIPPED",
    "OUT_FOR_DELIVERY",
    "DELIVERED",
    "CANCELLED",
    "NEW",
    "PENDING",
    "CONTACTED",
    "PACKED",
}


def normalize_order_status(value: str) -> str:
    clean = (value or "").strip().upper().replace(" ", "_")
    return STATUS_ALIASES.get(clean, clean)


def generate_order_code() -> str:
    """Generates a unique, friendly order code e.g. ORD-89241"""
    num = random.randint(10000, 99999)
    return f"ORD-{num}"


def build_whatsapp_order_link(phone: str, order: ProductOrder, product_name: str) -> str:
    """Constructs a direct WhatsApp link pre-filled with complete buyer and order details."""
    clean_phone = "".join(filter(str.isdigit, phone or ""))
    if len(clean_phone) == 10:
        clean_phone = f"91{clean_phone}"

    msg_lines = [
        "🛍️ *NEW ORDER from Logo Kerala!*",
        f"*Order Code:* {order.order_code}",
        f"*Product:* {product_name}",
        f"*Size:* {order.selected_size or 'Standard'}",
        f"*Quantity:* {order.quantity}",
        f"*Total Price:* ₹{order.total_price:,.2f}",
        "--------------------------------",
        "👤 *Customer Delivery Details:*",
        f"*Name:* {order.buyer_name}",
        f"*Phone:* {order.buyer_phone}",
        f"*Address:* {order.buyer_address}",
    ]
    if order.buyer_location:
        msg_lines.append(f"*Location:* {order.buyer_location}")
    if order.buyer_city or order.buyer_district:
        msg_lines.append(f"*City/District:* {order.buyer_city or ''}, {order.buyer_district or ''}")
    msg_lines.append(f"*Pincode:* {order.buyer_pincode}")

    if order.notes:
        msg_lines.append(f"*Customer Note:* {order.notes}")

    msg_lines.append("--------------------------------")
    msg_lines.append("Please confirm this order directly with the customer. Thank you!")

    encoded_msg = urllib.parse.quote("\n".join(msg_lines))
    return f"https://api.whatsapp.com/send?phone={clean_phone}&text={encoded_msg}"


class ProductService:
    @staticmethod
    def ensure_order_schema(db: Session) -> None:
        if db.info.get("product_order_schema_ready"):
            return
        conn = db.connection()
        inspector = inspect(conn)
        if "product_orders" not in inspector.get_table_names():
            ProductOrder.__table__.create(bind=conn, checkfirst=True)
            for table in (
                DeliveryAddress.__table__,
                ProductWishlist.__table__,
                CartItem.__table__,
                ProductReview.__table__,
            ):
                table.create(bind=conn, checkfirst=True)
            db.commit()
            db.info["product_order_schema_ready"] = True
            return
        existing = {column["name"] for column in inspector.get_columns("product_orders")}
        json_type = "JSON" if conn.dialect.name == "postgresql" else "TEXT"
        additions = [
            ("unit_price", "NUMERIC(10, 2)"),
            ("buyer_user_id", "INTEGER"),
            ("status_history", json_type),
            ("payment_status", "VARCHAR(32)"),
            ("payment_method", "VARCHAR(32)"),
            ("razorpay_order_id", "VARCHAR(64)"),
            ("razorpay_payment_id", "VARCHAR(64)"),
            ("cancellation_reason", "VARCHAR(500)"),
            ("cancelled_at", "TIMESTAMP"),
            ("courier_partner", "VARCHAR(100)"),
            ("tracking_number", "VARCHAR(64)"),
            ("tracking_url", "VARCHAR(500)"),
            ("estimated_delivery_at", "TIMESTAMP"),
            ("courier_events", json_type),
        ]
        missing = [(name, ddl) for name, ddl in additions if name not in existing]
        product_columns = set()
        if "customer_products" in inspector.get_table_names():
            product_columns = {column["name"] for column in inspector.get_columns("customer_products")}
            if "stock_quantity" not in product_columns:
                missing.append(("stock_quantity", "INTEGER"))
            if "rating_sum" not in product_columns:
                missing.append(("rating_sum", "INTEGER"))
            if "rating_count" not in product_columns:
                missing.append(("rating_count", "INTEGER"))
        for name, ddl in missing:
            table = "customer_products" if name in {"stock_quantity", "rating_sum", "rating_count"} else "product_orders"
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
        for table in (
            DeliveryAddress.__table__,
            ProductWishlist.__table__,
            CartItem.__table__,
            ProductReview.__table__,
        ):
            if table.name not in inspector.get_table_names():
                table.create(bind=conn, checkfirst=True)
                missing.append((table.name, "TABLE"))
        if missing:
            db.commit()
        db.info["product_order_schema_ready"] = True

    @staticmethod
    def delivery_steps(order: ProductOrder) -> list:
        from datetime import datetime as dt

        current = normalize_order_status(order.status or "PLACED")
        history = order.status_history or []
        seen_at = {}
        if isinstance(history, str):
            import json
            try:
                history = json.loads(history)
            except json.JSONDecodeError:
                history = []
        for row in history:
            if isinstance(row, dict) and row.get("status"):
                seen_at[normalize_order_status(str(row["status"]))] = row.get("at")
        keys = [key for key, _label in DELIVERY_FLOW]
        current_index = keys.index(current) if current in keys else -1
        steps = []
        for index, (key, label) in enumerate(DELIVERY_FLOW):
            raw_at = seen_at.get(key)
            parsed = None
            if isinstance(raw_at, str):
                try:
                    parsed = dt.fromisoformat(raw_at.replace("Z", "+00:00"))
                except ValueError:
                    parsed = None
            steps.append(
                {
                    "key": key,
                    "label": label,
                    "done": current != "CANCELLED" and current_index >= index,
                    "current": current == key,
                    "at": parsed,
                }
            )
        if current == "CANCELLED":
            steps.append(
                {
                    "key": "CANCELLED",
                    "label": "Cancelled",
                    "done": True,
                    "current": True,
                    "at": None,
                }
            )
        return steps

    @staticmethod
    def _record_status(order: ProductOrder, status_value: str, note: Optional[str] = None) -> None:
        normalized = normalize_order_status(status_value)
        if normalized not in ALLOWED_ORDER_STATUSES and normalized not in {item[0] for item in DELIVERY_FLOW}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Status must be PLACED, CONFIRMED, SHIPPED, OUT_FOR_DELIVERY, DELIVERED, or CANCELLED.",
            )
        order.status = normalized
        history = list(order.status_history or [])
        history.append(
            {
                "status": normalized,
                "note": note,
                "at": datetime.now(timezone.utc).isoformat(),
            }
        )
        order.status_history = history

    @staticmethod
    def _assert_status_transition(current_status: str, new_status: str) -> None:
        current = normalize_order_status(current_status or "PLACED")
        new = normalize_order_status(new_status)
        flow = [key for key, _label in DELIVERY_FLOW]
        if new == "CANCELLED":
            if current not in {"PLACED", "CONFIRMED"}:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="An order can be cancelled only before it is shipped.",
                )
            return
        if current in {"CANCELLED", "DELIVERED"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"This order is already {current.lower().replace('_', ' ')}.",
            )
        if current not in flow or new not in flow:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Status must be the next delivery step: CONFIRMED, SHIPPED, OUT_FOR_DELIVERY, or DELIVERED.",
            )
        if flow.index(new) != flow.index(current) + 1:
            nxt = flow[flow.index(current) + 1]
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Next status is {nxt}.",
            )

    @staticmethod
    def _restore_stock(order: ProductOrder) -> None:
        product = order.product
        if product is None or product.stock_quantity is None:
            return
        product.stock_quantity += order.quantity
        if product.stock_quantity > 0:
            product.stock_status = "IN_STOCK"

    @staticmethod
    def _public_query(
        db: Session,
        category: Optional[str] = None,
        district: Optional[str] = None,
        search: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
    ):
        q = db.query(CustomerProduct).filter(
            CustomerProduct.is_active == True,
            CustomerProduct.approval_status == "APPROVED",
        )

        if category and category.lower() != "all":
            q = q.filter(CustomerProduct.category.ilike(f"%{category.strip()}%"))

        if district and district.lower() != "all" and "all kerala" not in district.lower():
            q = q.filter(CustomerProduct.district.ilike(f"%{district.strip()}%"))

        if min_price is not None:
            q = q.filter(CustomerProduct.price >= min_price)

        if max_price is not None:
            q = q.filter(CustomerProduct.price <= max_price)

        if search and search.strip():
            kw = f"%{search.strip()}%"
            q = q.filter(
                or_(
                    CustomerProduct.name.ilike(kw),
                    CustomerProduct.description.ilike(kw),
                    CustomerProduct.seller_name.ilike(kw),
                    CustomerProduct.city.ilike(kw),
                    CustomerProduct.category.ilike(kw),
                )
            )

        return q

    @staticmethod
    def get_public_products(
        db: Session,
        category: Optional[str] = None,
        district: Optional[str] = None,
        search: Optional[str] = None,
        sort_by: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[CustomerProduct]:
        """Fetch approved, active products for the shop page."""
        q = ProductService._public_query(
            db, category, district, search, min_price, max_price
        )
        if sort_by == "price_asc":
            q = q.order_by(CustomerProduct.price.asc())
        elif sort_by == "price_desc":
            q = q.order_by(CustomerProduct.price.desc())
        elif sort_by == "popular":
            q = q.order_by(desc(CustomerProduct.views_count))
        else:
            q = q.order_by(desc(CustomerProduct.created_at))

        return q.offset(offset).limit(limit).all()

    @staticmethod
    def count_public_products(
        db: Session,
        category: Optional[str] = None,
        district: Optional[str] = None,
        search: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
    ) -> int:
        return ProductService._public_query(
            db, category, district, search, min_price, max_price
        ).count()

    @staticmethod
    def get_product_categories(db: Session) -> List[str]:
        """Categories that currently have an approved, active listing."""
        rows = (
            db.query(CustomerProduct.category)
            .filter(
                CustomerProduct.is_active == True,
                CustomerProduct.approval_status == "APPROVED",
                CustomerProduct.category.isnot(None),
            )
            .distinct()
            .all()
        )
        cats = sorted({r[0].strip() for r in rows if r[0] and r[0].strip()}, key=str.lower)
        return cats

    @staticmethod
    def get_product_by_id(db: Session, product_id: int) -> CustomerProduct:
        product = db.query(CustomerProduct).filter(CustomerProduct.id == product_id).first()
        if not product or not product.is_active or product.approval_status != "APPROVED":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product with ID {product_id} not found",
            )
        product.views_count += 1
        db.commit()
        db.refresh(product)
        return product

    @staticmethod
    def create_product(db: Session, seller: User, data: ProductCreateRequest) -> CustomerProduct:
        category = (data.category or "General").strip() or "General"
        new_product = CustomerProduct(
            seller_id=seller.id,
            seller_name=data.seller_name or seller.name,
            seller_phone=data.seller_phone or seller.phone,
            seller_whatsapp=data.seller_whatsapp or data.seller_phone or seller.phone,
            name=data.name.strip(),
            description=data.description.strip() if data.description else None,
            category=category,
            price=data.price,
            original_price=data.original_price,
            images=data.images or [],
            sizes=data.sizes or [],
            stock_status="OUT_OF_STOCK" if data.stock_quantity == 0 else "IN_STOCK",
            stock_quantity=data.stock_quantity,
            district=data.district or seller.district,
            city=data.city or seller.city,
            location=data.location,
            is_active=True,
            approval_status="APPROVED",
        )
        db.add(new_product)
        db.commit()
        db.refresh(new_product)
        return new_product

    @staticmethod
    def add_stock(db: Session, product_id: int, user: User, quantity: int) -> CustomerProduct:
        product = db.query(CustomerProduct).filter(CustomerProduct.id == product_id).first()
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product {product_id} not found",
            )
        is_admin = user.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN)
        if not is_admin and product.seller_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to edit this product.",
            )
        current = product.stock_quantity or 0
        product.stock_quantity = current + quantity
        product.stock_status = "IN_STOCK"
        db.commit()
        db.refresh(product)
        return product

    @staticmethod
    def update_product(
        db: Session, product_id: int, user: User, data: ProductUpdateRequest
    ) -> CustomerProduct:
        product = db.query(CustomerProduct).filter(CustomerProduct.id == product_id).first()
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product {product_id} not found",
            )

        is_admin = user.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN)
        if not is_admin and product.seller_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to edit this product.",
            )

        if data.name is not None:
            product.name = data.name.strip()
        if data.description is not None:
            product.description = data.description.strip()
        if data.category is not None:
            product.category = data.category.strip()
        if data.price is not None:
            product.price = data.price
        if data.original_price is not None:
            product.original_price = data.original_price
        if data.images is not None:
            product.images = data.images
        if data.sizes is not None:
            product.sizes = data.sizes
        if data.stock_status is not None:
            product.stock_status = data.stock_status.strip().upper()
        if data.stock_quantity is not None:
            product.stock_quantity = data.stock_quantity
            if data.stock_quantity == 0:
                product.stock_status = "OUT_OF_STOCK"
            elif (product.stock_status or "").upper() == "OUT_OF_STOCK":
                product.stock_status = "IN_STOCK"
        if data.district is not None:
            product.district = data.district
        if data.city is not None:
            product.city = data.city
        if data.location is not None:
            product.location = data.location
        if data.seller_name is not None:
            product.seller_name = data.seller_name
        if data.seller_phone is not None:
            product.seller_phone = data.seller_phone
        if data.seller_whatsapp is not None:
            product.seller_whatsapp = data.seller_whatsapp
        if data.is_active is not None:
            product.is_active = data.is_active

        product.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(product)
        return product

    @staticmethod
    def toggle_product_status(
        db: Session, product_id: int, data: ProductAdminStatusUpdate
    ) -> CustomerProduct:
        """Admin toggle for On/Off (is_active) and Allow/Deny (approval_status)."""
        product = db.query(CustomerProduct).filter(CustomerProduct.id == product_id).first()
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product {product_id} not found",
            )

        if data.is_active is not None:
            product.is_active = data.is_active
        if data.approval_status is not None:
            norm = data.approval_status.upper().strip()
            if norm in ("ALLOW", "ALLOWED", "APPROVED", "APPROVE"):
                product.approval_status = "APPROVED"
                product.is_active = True
            elif norm in ("DENY", "DENIED", "REJECT", "REJECTED"):
                product.approval_status = "DENIED"
                product.is_active = False
            else:
                product.approval_status = norm

        if data.rejection_reason is not None:
            product.rejection_reason = data.rejection_reason

        product.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(product)
        return product

    @staticmethod
    def delete_product(db: Session, product_id: int, user: User) -> bool:
        product = db.query(CustomerProduct).filter(CustomerProduct.id == product_id).first()
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product {product_id} not found",
            )

        is_admin = user.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN)
        if not is_admin and product.seller_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to delete this product",
            )

        db.delete(product)
        db.commit()
        return True

    @staticmethod
    def create_order(
        db: Session, data: OrderCreateRequest, buyer: Optional[User] = None
    ) -> Tuple[ProductOrder, str]:
        """Creates an in-app purchase and prepares a WhatsApp note for the seller."""
        ProductService.ensure_order_schema(db)
        product = db.query(CustomerProduct).filter(CustomerProduct.id == data.product_id).first()
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product {data.product_id} not found",
            )
        if not product.is_active or product.approval_status != "APPROVED":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This product is currently unavailable for ordering.",
            )
        if (product.stock_status or "").upper() == "OUT_OF_STOCK":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This item is out of stock.",
            )
        if buyer and product.seller_id == buyer.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You cannot buy your own listing.",
            )
        sizes = [str(size).strip() for size in (product.sizes or []) if str(size).strip()]
        chosen_size = data.selected_size.strip() if data.selected_size else None
        if sizes and chosen_size not in sizes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Choose one of the listed options: {', '.join(sizes)}.",
            )
        if product.stock_quantity is not None and data.quantity > product.stock_quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Only {product.stock_quantity} available.",
            )

        unit_p = Decimal(str(product.price)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        total_p = (unit_p * data.quantity).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # Enforce Minimum Order Amount: ₹150 (Both Online & COD)
        MIN_ORDER_AMOUNT = Decimal("150.00")
        if total_p < MIN_ORDER_AMOUNT:
            req_qty = int(math.ceil(float(MIN_ORDER_AMOUNT) / float(unit_p))) if unit_p > 0 else 1
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Minimum order amount is ₹150. Please increase quantity to at least {req_qty} (Total: ₹{unit_p * req_qty}) to place this order.",
            )

        code = generate_order_code()

        # Ensure unique order code
        while db.query(ProductOrder).filter(ProductOrder.order_code == code).first():
            code = generate_order_code()

        order = ProductOrder(
            order_code=code,
            product_id=product.id,
            seller_id=product.seller_id,
            buyer_user_id=buyer.id if buyer else None,
            buyer_name=data.buyer_name.strip(),
            buyer_phone=data.buyer_phone.strip(),
            buyer_address=data.buyer_address.strip(),
            buyer_location=data.buyer_location.strip() if data.buyer_location else None,
            buyer_city=data.buyer_city.strip() if data.buyer_city else None,
            buyer_district=data.buyer_district.strip() if data.buyer_district else None,
            buyer_pincode=data.buyer_pincode.strip(),
            selected_size=chosen_size,
            quantity=data.quantity,
            unit_price=unit_p,
            total_price=total_p,
            status="PLACED",
            notes=data.notes.strip() if data.notes else None,
            status_history=[],
            payment_status="UNPAID",
            courier_events=[],
        )
        ProductService._record_status(order, "PLACED", data.notes)
        db.add(order)
        product.orders_count += 1
        if product.stock_quantity is not None:
            product.stock_quantity -= data.quantity
            if product.stock_quantity <= 0:
                product.stock_quantity = 0
                product.stock_status = "OUT_OF_STOCK"
        db.commit()
        db.refresh(order)

        # Generate WhatsApp link directly to seller
        seller_phone = product.seller_whatsapp or product.seller_phone
        whatsapp_url = (
            build_whatsapp_order_link(seller_phone, order, product.name) if seller_phone else None
        )

        return order, whatsapp_url

    @staticmethod
    def get_seller_products(db: Session, seller_id: int) -> List[CustomerProduct]:
        return (
            db.query(CustomerProduct)
            .filter(CustomerProduct.seller_id == seller_id)
            .order_by(desc(CustomerProduct.created_at))
            .all()
        )

    @staticmethod
    def get_buyer_orders(
        db: Session,
        buyer: User,
        status_filter: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[ProductOrder], int]:
        ProductService.ensure_order_schema(db)
        filters = [ProductOrder.buyer_user_id == buyer.id]
        tail = "".join(ch for ch in (buyer.phone or "") if ch.isdigit())[-10:]
        if len(tail) == 10:
            filters.append(
                and_(
                    ProductOrder.buyer_user_id.is_(None),
                    ProductOrder.buyer_phone.like(f"%{tail}"),
                )
            )
        query = db.query(ProductOrder).filter(or_(*filters))
        if status_filter and status_filter.strip().lower() not in {"", "all"}:
            query = query.filter(ProductOrder.status == normalize_order_status(status_filter))
        total = query.count()
        orders = query.order_by(desc(ProductOrder.created_at)).offset(offset).limit(limit).all()
        return orders, total

    @staticmethod
    def get_order_by_id(db: Session, order_id: int) -> ProductOrder:
        ProductService.ensure_order_schema(db)
        order = db.query(ProductOrder).filter(ProductOrder.id == order_id).first()
        if not order:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found.")
        return order

    @staticmethod
    def get_buyer_order(db: Session, buyer: User, order_id: int) -> ProductOrder:
        ProductService.ensure_order_schema(db)
        order = db.query(ProductOrder).filter(ProductOrder.id == order_id).first()
        if not order or not ProductService._buyer_owns(order, buyer):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found.")
        return order

    @staticmethod
    def _buyer_owns(order: ProductOrder, buyer: User) -> bool:
        if order.buyer_user_id == buyer.id:
            return True
        if order.buyer_user_id is not None:
            return False
        tail = "".join(ch for ch in (buyer.phone or "") if ch.isdigit())[-10:]
        order_tail = "".join(ch for ch in (order.buyer_phone or "") if ch.isdigit())[-10:]
        return len(tail) == 10 and tail == order_tail

    @staticmethod
    def cancel_buyer_order(
        db: Session, buyer: Optional[User], order_id: int, reason: Optional[str] = None
    ) -> ProductOrder:
        if buyer is None:
            order = ProductService.get_order_by_id(db, order_id)
        else:
            order = ProductService.get_buyer_order(db, buyer, order_id)
        current = normalize_order_status(order.status)
        if current not in {"PLACED", "CONFIRMED", "NEW", "PENDING"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This order can only be cancelled before it is shipped.",
            )
        note = (reason or "Cancelled by buyer").strip()
        ProductService._record_status(order, "CANCELLED", note)
        ProductService._restore_stock(order)
        order.cancellation_reason = note[:500]
        order.cancelled_at = datetime.now(timezone.utc)
        if (order.payment_status or "").upper() == "PAID":
            order.payment_status = "REFUND_PENDING"
        order.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(order)
        return order

    @staticmethod
    def get_seller_orders(db: Session, seller_id: int) -> List[ProductOrder]:
        ProductService.ensure_order_schema(db)
        return (
            db.query(ProductOrder)
            .filter(ProductOrder.seller_id == seller_id)
            .order_by(desc(ProductOrder.created_at))
            .all()
        )

    @staticmethod
    def get_seller_order_by_id(db: Session, seller_id: int, order_id: int) -> Optional[ProductOrder]:
        return (
            db.query(ProductOrder)
            .filter(ProductOrder.id == order_id, ProductOrder.seller_id == seller_id)
            .first()
        )

    @staticmethod
    def update_seller_order_status(
        db: Session, seller_id: int, order_id: int, new_status: str, notes: Optional[str] = None
    ) -> ProductOrder:
        ProductService.ensure_order_schema(db)
        order = (
            db.query(ProductOrder)
            .filter(ProductOrder.id == order_id, ProductOrder.seller_id == seller_id)
            .first()
        )
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Order #{order_id} not found.",
            )
        ProductService._assert_status_transition(order.status, new_status)
        if normalize_order_status(new_status) == "CANCELLED":
            ProductService._restore_stock(order)
        ProductService._record_status(order, new_status, notes)
        if notes is not None:
            order.notes = notes
        order.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(order)
        return order

    @staticmethod
    def get_all_products_admin(
        db: Session,
        status_filter: Optional[str] = None,
        is_active: Optional[bool] = None,
        search: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[CustomerProduct]:
        q = db.query(CustomerProduct)
        if status_filter and status_filter.lower() != "all":
            q = q.filter(CustomerProduct.approval_status.ilike(status_filter.strip()))
        if is_active is not None:
            q = q.filter(CustomerProduct.is_active == is_active)
        if search and search.strip():
            kw = f"%{search.strip()}%"
            q = q.filter(
                or_(
                    CustomerProduct.name.ilike(kw),
                    CustomerProduct.seller_name.ilike(kw),
                    CustomerProduct.seller_phone.ilike(kw),
                    CustomerProduct.category.ilike(kw),
                    CustomerProduct.district.ilike(kw),
                )
            )
        return q.order_by(desc(CustomerProduct.created_at)).offset(offset).limit(limit).all()

    @staticmethod
    def get_all_orders_admin(
        db: Session,
        status_filter: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[ProductOrder]:
        ProductService.ensure_order_schema(db)
        q = db.query(ProductOrder)
        if status_filter and status_filter.lower() != "all":
            q = q.filter(ProductOrder.status.ilike(status_filter.strip()))
        if search and search.strip():
            kw = f"%{search.strip()}%"
            q = q.filter(
                or_(
                    ProductOrder.order_code.ilike(kw),
                    ProductOrder.buyer_name.ilike(kw),
                    ProductOrder.buyer_phone.ilike(kw),
                    ProductOrder.buyer_pincode.ilike(kw),
                )
            )
        return q.order_by(desc(ProductOrder.created_at)).offset(offset).limit(limit).all()

    @staticmethod
    def toggle_seller_permission(
        db: Session, user_id: int, data: SellerPermissionToggleRequest
    ) -> User:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {user_id} not found",
            )
        user.can_sell_products = data.can_sell_products
        if data.is_subscriber is not None:
            user.is_subscriber = data.is_subscriber
        else:
            user.is_subscriber = data.can_sell_products
        if data.subscription_plan:
            user.subscription_plan = data.subscription_plan

        db.commit()
        db.refresh(user)
        return user
