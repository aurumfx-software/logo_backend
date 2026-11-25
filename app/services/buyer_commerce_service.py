from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.db.models.product import CartItem, CustomerProduct, DeliveryAddress, ProductOrder, ProductReview, ProductWishlist
from app.db.models.user import User
from app.schemas.commerce import (
    AddressRequest,
    AddressUpdateRequest,
    CartItemInput,
    CartLineResponse,
    CartResponse,
    CourierEventResponse,
    DispatchUpdateRequest,
    OrderPaymentResponse,
    OrderTrackingResponse,
    ReviewCreateRequest,
    ReviewListResponse,
    ReviewResponse,
    WishlistItemResponse,
    WishlistResponse,
)
from app.schemas.product import OrderCreateRequest
from app.services.product_service import ProductService, normalize_order_status
from app.services.razorpay_service import RazorpayService

COURIER_EVENTS = {"PICKED_UP", "IN_TRANSIT", "OUT_FOR_DELIVERY", "DELIVERED", "EXCEPTION"}
EVENT_TO_STATUS = {
    "PICKED_UP": "SHIPPED",
    "IN_TRANSIT": "SHIPPED",
    "OUT_FOR_DELIVERY": "OUT_FOR_DELIVERY",
    "DELIVERED": "DELIVERED",
}
STATUS_LABELS = {
    "PLACED": "Order placed",
    "CONFIRMED": "Seller confirmed",
    "SHIPPED": "Shipped",
    "OUT_FOR_DELIVERY": "Out for delivery",
    "DELIVERED": "Delivered",
    "CANCELLED": "Cancelled",
}


def _money(value) -> float:
    return float(Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _parse_events(raw) -> list:
    if isinstance(raw, str):
        import json
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return []
    return list(raw or [])


class BuyerCommerceService:
    @staticmethod
    def _address_or_404(db: Session, user: User, address_id: int) -> DeliveryAddress:
        row = (
            db.query(DeliveryAddress)
            .filter(DeliveryAddress.id == address_id, DeliveryAddress.user_id == user.id)
            .first()
        )
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Address not found.")
        return row

    @staticmethod
    def _clear_default(db: Session, user_id: int) -> None:
        db.query(DeliveryAddress).filter(
            DeliveryAddress.user_id == user_id, DeliveryAddress.is_default.is_(True)
        ).update({DeliveryAddress.is_default: False})

    @staticmethod
    def list_addresses(db: Session, user: User) -> List[DeliveryAddress]:
        ProductService.ensure_order_schema(db)
        return (
            db.query(DeliveryAddress)
            .filter(DeliveryAddress.user_id == user.id)
            .order_by(DeliveryAddress.is_default.desc(), DeliveryAddress.id.desc())
            .all()
        )

    @staticmethod
    def create_address(db: Session, user: User, data: AddressRequest) -> DeliveryAddress:
        ProductService.ensure_order_schema(db)
        make_default = data.is_default or db.query(DeliveryAddress).filter(DeliveryAddress.user_id == user.id).count() == 0
        if make_default:
            BuyerCommerceService._clear_default(db, user.id)
        row = DeliveryAddress(
            user_id=user.id,
            label=(data.label or "Home").strip(),
            recipient_name=data.recipient_name.strip(),
            phone=data.phone.strip(),
            address_line=data.address_line.strip(),
            location=data.location.strip() if data.location else None,
            city=data.city.strip() if data.city else None,
            district=data.district.strip() if data.district else None,
            pincode=data.pincode.strip(),
            is_default=make_default,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def update_address(db: Session, user: User, address_id: int, data: AddressUpdateRequest) -> DeliveryAddress:
        row = BuyerCommerceService._address_or_404(db, user, address_id)
        payload = data.model_dump(exclude_unset=True)
        if payload.get("is_default"):
            BuyerCommerceService._clear_default(db, user.id)
        for key, value in payload.items():
            if isinstance(value, str):
                value = value.strip()
            setattr(row, key, value)
        row.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def delete_address(db: Session, user: User, address_id: int) -> None:
        row = BuyerCommerceService._address_or_404(db, user, address_id)
        was_default = row.is_default
        db.delete(row)
        db.commit()
        if was_default:
            nxt = (
                db.query(DeliveryAddress)
                .filter(DeliveryAddress.user_id == user.id)
                .order_by(DeliveryAddress.id.desc())
                .first()
            )
            if nxt:
                nxt.is_default = True
                db.commit()

    @staticmethod
    def _product_in_stock(product: CustomerProduct) -> bool:
        quantity = product.stock_quantity
        return bool(
            product.is_active
            and (product.approval_status or "").upper() == "APPROVED"
            and (product.stock_status or "").upper() != "OUT_OF_STOCK"
            and (quantity is None or quantity > 0)
        )

    @staticmethod
    def list_wishlist(db: Session, user: User) -> WishlistResponse:
        ProductService.ensure_order_schema(db)
        rows = (
            db.query(ProductWishlist)
            .filter(ProductWishlist.user_id == user.id)
            .order_by(ProductWishlist.created_at.desc())
            .all()
        )
        items = []
        for row in rows:
            product = row.product
            if not product:
                continue
            items.append(
                WishlistItemResponse(
                    product_id=product.id,
                    name=product.name,
                    price=_money(product.price),
                    image=product.images[0] if product.images else None,
                    in_stock=BuyerCommerceService._product_in_stock(product),
                    saved_at=row.created_at,
                )
            )
        return WishlistResponse(items=items, total=len(items))

    @staticmethod
    def add_wishlist(db: Session, user: User, product_id: int) -> WishlistResponse:
        ProductService.ensure_order_schema(db)
        product = db.query(CustomerProduct).filter(CustomerProduct.id == product_id).first()
        if not product or not product.is_active or (product.approval_status or "").upper() != "APPROVED":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.")
        existing = (
            db.query(ProductWishlist)
            .filter(ProductWishlist.user_id == user.id, ProductWishlist.product_id == product_id)
            .first()
        )
        if not existing:
            db.add(ProductWishlist(user_id=user.id, product_id=product_id))
            db.commit()
        return BuyerCommerceService.list_wishlist(db, user)

    @staticmethod
    def remove_wishlist(db: Session, user: User, product_id: int) -> WishlistResponse:
        ProductService.ensure_order_schema(db)
        db.query(ProductWishlist).filter(
            ProductWishlist.user_id == user.id, ProductWishlist.product_id == product_id
        ).delete()
        db.commit()
        return BuyerCommerceService.list_wishlist(db, user)

    @staticmethod
    def _cart_line(item: CartItem) -> Optional[CartLineResponse]:
        product = item.product
        if not product:
            return None
        unit = _money(product.price)
        return CartLineResponse(
            id=item.id,
            product_id=product.id,
            product_name=product.name,
            product_image=product.images[0] if product.images else None,
            unit_price=unit,
            quantity=item.quantity,
            selected_size=item.selected_size or None,
            line_total=_money(Decimal(str(unit)) * item.quantity),
            in_stock=BuyerCommerceService._product_in_stock(product),
        )

    @staticmethod
    def get_cart(db: Session, user: User) -> CartResponse:
        ProductService.ensure_order_schema(db)
        rows = db.query(CartItem).filter(CartItem.user_id == user.id).order_by(CartItem.id.asc()).all()
        items = [line for row in rows if (line := BuyerCommerceService._cart_line(row))]
        return CartResponse(
            items=items,
            item_count=sum(item.quantity for item in items),
            subtotal=_money(sum(item.line_total for item in items)),
        )

    @staticmethod
    def _validated_size(product: CustomerProduct, selected_size: Optional[str]) -> str:
        sizes = [str(size).strip() for size in (product.sizes or []) if str(size).strip()]
        chosen = (selected_size or "").strip()
        if sizes and chosen not in sizes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Choose one of the listed options: {', '.join(sizes)}.",
            )
        return chosen

    @staticmethod
    def sync_cart(db: Session, user: User, items: List[CartItemInput]) -> CartResponse:
        ProductService.ensure_order_schema(db)
        unavailable: List[str] = []
        accepted: dict = {}
        db.query(CartItem).filter(CartItem.user_id == user.id).delete()
        buyer_tail = "".join(ch for ch in (getattr(user, "phone", None) or "") if ch.isdigit())[-10:]
        for item in items:
            product = db.query(CustomerProduct).filter(CustomerProduct.id == item.product_id).first()
            if not product or not BuyerCommerceService._product_in_stock(product):
                unavailable.append(str(item.product_id))
                continue
            seller_tail = "".join(ch for ch in (product.seller_phone or product.seller_whatsapp or "") if ch.isdigit())[-10:]
            if product.seller_id == user.id or (len(buyer_tail) == 10 and buyer_tail == seller_tail):
                unavailable.append(product.name)
                continue
            try:
                size = BuyerCommerceService._validated_size(product, item.selected_size)
            except HTTPException:
                unavailable.append(product.name)
                continue
            key = (product.id, size)
            if key in accepted:
                accepted[key].quantity = min(100, accepted[key].quantity + item.quantity)
                continue
            row = CartItem(
                user_id=user.id,
                product_id=product.id,
                selected_size=size,
                quantity=item.quantity,
            )
            accepted[key] = row
            db.add(row)
        db.commit()
        cart = BuyerCommerceService.get_cart(db, user)
        cart.unavailable = unavailable
        return cart

    @staticmethod
    def add_cart_item(db: Session, user: User, item: CartItemInput) -> CartResponse:
        ProductService.ensure_order_schema(db)
        product = db.query(CustomerProduct).filter(CustomerProduct.id == item.product_id).first()
        if not product or not BuyerCommerceService._product_in_stock(product):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This item is not available.")
        buyer_tail = "".join(ch for ch in (getattr(user, "phone", None) or "") if ch.isdigit())[-10:]
        seller_tail = "".join(ch for ch in (product.seller_phone or product.seller_whatsapp or "") if ch.isdigit())[-10:]
        if product.seller_id == user.id or (len(buyer_tail) == 10 and buyer_tail == seller_tail):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot buy your own listing.")
        size = BuyerCommerceService._validated_size(product, item.selected_size)
        existing = (
            db.query(CartItem)
            .filter(
                CartItem.user_id == user.id,
                CartItem.product_id == product.id,
                CartItem.selected_size == size,
            )
            .first()
        )
        if existing:
            existing.quantity = min(100, existing.quantity + item.quantity)
            existing.updated_at = datetime.now(timezone.utc)
        else:
            db.add(CartItem(user_id=user.id, product_id=product.id, selected_size=size, quantity=item.quantity))
        db.commit()
        return BuyerCommerceService.get_cart(db, user)

    @staticmethod
    def update_cart_item(db: Session, user: User, item_id: int, quantity: int) -> CartResponse:
        row = db.query(CartItem).filter(CartItem.id == item_id, CartItem.user_id == user.id).first()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cart item not found.")
        row.quantity = quantity
        row.updated_at = datetime.now(timezone.utc)
        db.commit()
        return BuyerCommerceService.get_cart(db, user)

    @staticmethod
    def remove_cart_item(db: Session, user: User, item_id: int) -> CartResponse:
        row = db.query(CartItem).filter(CartItem.id == item_id, CartItem.user_id == user.id).first()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cart item not found.")
        db.delete(row)
        db.commit()
        return BuyerCommerceService.get_cart(db, user)

    @staticmethod
    def clear_cart(db: Session, user: User) -> CartResponse:
        db.query(CartItem).filter(CartItem.user_id == user.id).delete()
        db.commit()
        return CartResponse()

    @staticmethod
    def checkout_cart(db: Session, user: User, address_id: int, notes: Optional[str]):
        address = BuyerCommerceService._address_or_404(db, user, address_id)
        rows = db.query(CartItem).filter(CartItem.user_id == user.id).all()
        if not rows:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Your cart is empty.")
        orders = []
        failed = []
        for row in rows:
            product = row.product
            if not product:
                db.delete(row)
                continue
            try:
                order, _link = ProductService.create_order(
                    db,
                    OrderCreateRequest(
                        product_id=product.id,
                        buyer_name=address.recipient_name,
                        buyer_phone=address.phone,
                        buyer_address=address.address_line,
                        buyer_location=address.location,
                        buyer_city=address.city,
                        buyer_district=address.district,
                        buyer_pincode=address.pincode,
                        selected_size=row.selected_size or None,
                        quantity=row.quantity,
                        notes=notes,
                    ),
                    buyer=user,
                )
            except HTTPException as exc:
                failed.append(f"{product.name}: {exc.detail}")
                continue
            orders.append(order)
            db.delete(row)
            db.commit()
        return orders, failed

    @staticmethod
    def create_review(db: Session, user: User, order_id: int, data: ReviewCreateRequest) -> ProductReview:
        order = ProductService.get_buyer_order(db, user, order_id)
        if normalize_order_status(order.status) != "DELIVERED":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You can review this item after it is delivered.",
            )
        existing = db.query(ProductReview).filter(ProductReview.order_id == order.id).first()
        if existing:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This order already has a review.")
        review = ProductReview(
            product_id=order.product_id,
            order_id=order.id,
            buyer_user_id=user.id,
            rating=data.rating,
            title=data.title.strip() if data.title else None,
            comment=data.comment.strip() if data.comment else None,
        )
        product = order.product
        if product:
            product.rating_sum = int(product.rating_sum or 0) + data.rating
            product.rating_count = int(product.rating_count or 0) + 1
        db.add(review)
        db.commit()
        db.refresh(review)
        return review

    @staticmethod
    def list_product_reviews(db: Session, product_id: int) -> ReviewListResponse:
        ProductService.ensure_order_schema(db)
        product = db.query(CustomerProduct).filter(CustomerProduct.id == product_id).first()
        if not product:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.")
        rows = (
            db.query(ProductReview)
            .filter(ProductReview.product_id == product_id)
            .order_by(ProductReview.created_at.desc())
            .all()
        )
        count = int(product.rating_count or 0)
        average = round((product.rating_sum or 0) / count, 2) if count else 0
        reviews = []
        for row in rows:
            item = ReviewResponse.model_validate(row)
            item.buyer_name = row.buyer.name if row.buyer else None
            reviews.append(item)
        return ReviewListResponse(reviews=reviews, total=len(reviews), rating_average=average, rating_count=count)

    @staticmethod
    def start_payment(db: Session, user: User, order_id: int, method: str) -> OrderPaymentResponse:
        order = ProductService.get_buyer_order(db, user, order_id)
        if normalize_order_status(order.status) == "CANCELLED":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This order is cancelled.")
        chosen = (method or "").strip().upper()
        if chosen not in {"RAZORPAY", "UPI", "COD"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Method must be RAZORPAY, UPI, or COD.")
        amount = Decimal(str(order.total_price or 0)).quantize(Decimal("0.01"))
        paise = RazorpayService.inr_to_paise(amount)
        if (order.payment_status or "").upper() == "PAID":
            return OrderPaymentResponse(
                order_id=order.id,
                order_code=order.order_code,
                payment_status="PAID",
                payment_method=order.payment_method,
                amount=_money(amount),
                amount_paise=paise,
                razorpay_order_id=order.razorpay_order_id,
                razorpay_payment_id=order.razorpay_payment_id,
                razorpay_key_id=RazorpayService.get_public_key() or None,
            )
        if chosen == "COD":
            order.payment_method = "COD"
            order.payment_status = "COD"
            db.commit()
            db.refresh(order)
            return OrderPaymentResponse(
                order_id=order.id,
                order_code=order.order_code,
                payment_status="COD",
                payment_method="COD",
                amount=_money(amount),
                amount_paise=paise,
            )
        created = RazorpayService.create_order(
            amount_paise=paise,
            receipt=order.order_code[:40],
            notes={"order_code": order.order_code, "purpose": "marketplace"},
        )
        order.payment_method = chosen
        order.payment_status = "PENDING"
        order.razorpay_order_id = created.get("id")
        db.commit()
        db.refresh(order)
        return OrderPaymentResponse(
            order_id=order.id,
            order_code=order.order_code,
            payment_status="PENDING",
            payment_method=chosen,
            amount=_money(amount),
            amount_paise=int(created.get("amount") or paise),
            razorpay_key_id=RazorpayService.get_public_key() or None,
            razorpay_order_id=order.razorpay_order_id,
        )

    @staticmethod
    def verify_payment(
        db: Session,
        user: User,
        order_id: int,
        razorpay_order_id: str,
        razorpay_payment_id: str,
        razorpay_signature: str,
    ) -> OrderPaymentResponse:
        order = ProductService.get_buyer_order(db, user, order_id)
        if order.razorpay_order_id and order.razorpay_order_id != razorpay_order_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This payment does not match the order.")
        if (order.payment_status or "").upper() == "PAID":
            amount = Decimal(str(order.total_price or 0))
            return OrderPaymentResponse(
                order_id=order.id,
                order_code=order.order_code,
                payment_status="PAID",
                payment_method=order.payment_method,
                amount=_money(amount),
                amount_paise=RazorpayService.inr_to_paise(amount),
                razorpay_order_id=order.razorpay_order_id,
                razorpay_payment_id=order.razorpay_payment_id,
            )
        RazorpayService.verify_payment_signature(razorpay_order_id, razorpay_payment_id, razorpay_signature)
        order.razorpay_order_id = razorpay_order_id
        order.razorpay_payment_id = razorpay_payment_id
        order.payment_status = "PAID"
        order.payment_method = order.payment_method or "RAZORPAY"
        db.commit()
        db.refresh(order)
        amount = Decimal(str(order.total_price or 0))
        return OrderPaymentResponse(
            order_id=order.id,
            order_code=order.order_code,
            payment_status="PAID",
            payment_method=order.payment_method,
            amount=_money(amount),
            amount_paise=RazorpayService.inr_to_paise(amount),
            razorpay_key_id=RazorpayService.get_public_key() or None,
            razorpay_order_id=order.razorpay_order_id,
            razorpay_payment_id=order.razorpay_payment_id,
        )

    @staticmethod
    def tracking(db: Session, user: Optional[User], order_id: int) -> OrderTrackingResponse:
        if user is None:
            order = ProductService.get_order_by_id(db, order_id)
        else:
            order = ProductService.get_buyer_order(db, user, order_id)
        current = normalize_order_status(order.status)
        events = []
        for row in _parse_events(order.courier_events):
            if not isinstance(row, dict):
                continue
            at = row.get("at")
            parsed = None
            if isinstance(at, str):
                try:
                    parsed = datetime.fromisoformat(at.replace("Z", "+00:00"))
                except ValueError:
                    parsed = None
            events.append(CourierEventResponse(event=str(row.get("event") or ""), note=row.get("note"), at=parsed))
        latest = events[-1] if events else None
        headline = latest.note if latest and latest.note else STATUS_LABELS.get(current, current)
        detail = None
        if order.courier_partner and order.tracking_number:
            detail = f"{order.courier_partner} · {order.tracking_number}"
        return OrderTrackingResponse(
            order_id=order.id,
            order_code=order.order_code,
            status=current,
            status_label=STATUS_LABELS.get(current, current),
            payment_status=(order.payment_status or "UNPAID").upper(),
            payment_method=order.payment_method,
            headline=headline,
            detail=detail,
            updated_at=order.updated_at,
            courier_partner=order.courier_partner,
            tracking_number=order.tracking_number,
            tracking_url=order.tracking_url,
            estimated_delivery_at=order.estimated_delivery_at,
            events=events,
            delivery_steps=ProductService.delivery_steps(order),
        )

    @staticmethod
    def dispatch(db: Session, seller: User, order_id: int, data: DispatchUpdateRequest) -> ProductOrder:
        ProductService.ensure_order_schema(db)
        order = ProductService.get_seller_order_by_id(db, seller.id, order_id)
        if not order:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found.")
        event = (data.event or "IN_TRANSIT").strip().upper()
        if event not in COURIER_EVENTS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Event must be PICKED_UP, IN_TRANSIT, OUT_FOR_DELIVERY, DELIVERED, or EXCEPTION.",
            )
        order.courier_partner = data.courier_partner.strip()
        order.tracking_number = data.tracking_number.strip()
        order.tracking_url = data.tracking_url.strip() if data.tracking_url else order.tracking_url
        if data.estimated_delivery_at:
            order.estimated_delivery_at = data.estimated_delivery_at
        events = _parse_events(order.courier_events)
        events.append(
            {
                "event": event,
                "note": (data.note or event.replace("_", " ").title()).strip(),
                "at": datetime.now(timezone.utc).isoformat(),
            }
        )
        order.courier_events = events
        target = EVENT_TO_STATUS.get(event)
        current = normalize_order_status(order.status)
        if target and target != current:
            try:
                ProductService._assert_status_transition(current, target)
                ProductService._record_status(order, target, data.note)
            except HTTPException:
                pass
        order.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(order)
        return order
