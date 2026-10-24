import math
import random
import urllib.parse
from datetime import datetime, timezone
from typing import List, Optional, Tuple, Dict, Any
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import or_, desc

from app.db.models.user import User, UserRole
from app.db.models.product import CustomerProduct, ProductOrder
from app.schemas.product import (
    ProductCreateRequest,
    ProductUpdateRequest,
    ProductAdminStatusUpdate,
    ProductResponse,
    OrderCreateRequest,
    OrderResponse,
    SellerPermissionToggleRequest,
)


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
    def get_public_products(
        db: Session,
        category: Optional[str] = None,
        district: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[CustomerProduct]:
        """Fetch approved, active products for the Landing Page showcase."""
        q = db.query(CustomerProduct).filter(
            CustomerProduct.is_active == True,
            CustomerProduct.approval_status == "APPROVED",
        )

        if category and category.lower() != "all":
            q = q.filter(CustomerProduct.category.ilike(f"%{category.strip()}%"))

        if district and district.lower() != "all":
            q = q.filter(CustomerProduct.district.ilike(f"%{district.strip()}%"))

        if search and search.strip():
            kw = f"%{search.strip()}%"
            q = q.filter(
                or_(
                    CustomerProduct.name.ilike(kw),
                    CustomerProduct.description.ilike(kw),
                    CustomerProduct.seller_name.ilike(kw),
                    CustomerProduct.city.ilike(kw),
                )
            )

        return q.order_by(desc(CustomerProduct.created_at)).offset(offset).limit(limit).all()

    @staticmethod
    def get_product_by_id(db: Session, product_id: int) -> CustomerProduct:
        product = db.query(CustomerProduct).filter(CustomerProduct.id == product_id).first()
        if not product:
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
        # Check permissions: Admin, Super Admin, or user with can_sell_products = True
        is_admin = seller.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN)
        if not is_admin and not seller.can_sell_products and not seller.is_subscriber:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You need an active Seller Subscription (₹500 plan) allowed by Admin to list products.",
            )

        new_product = CustomerProduct(
            seller_id=seller.id,
            seller_name=data.seller_name or seller.name,
            seller_phone=data.seller_phone or seller.phone,
            seller_whatsapp=data.seller_whatsapp or data.seller_phone or seller.phone,
            name=data.name.strip(),
            description=data.description.strip() if data.description else None,
            category=data.category.strip() if data.category else "General",
            price=data.price,
            original_price=data.original_price,
            images=data.images or [],
            sizes=data.sizes or [],
            stock_status=data.stock_status or "IN_STOCK",
            district=data.district or seller.district,
            city=data.city or seller.city,
            is_active=True if is_admin else False,
            approval_status="APPROVED" if is_admin else "PENDING",  # Admin gets pending request to allow
        )
        db.add(new_product)
        db.commit()
        db.refresh(new_product)
        return new_product

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
            product.stock_status = data.stock_status
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
    def create_order(db: Session, data: OrderCreateRequest) -> Tuple[ProductOrder, str]:
        """Creates order and prepares WhatsApp link directly to seller."""
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

        unit_p = float(product.price)
        total_p = round(unit_p * data.quantity, 2)
        code = generate_order_code()

        # Ensure unique order code
        while db.query(ProductOrder).filter(ProductOrder.order_code == code).first():
            code = generate_order_code()

        order = ProductOrder(
            order_code=code,
            product_id=product.id,
            seller_id=product.seller_id,
            buyer_name=data.buyer_name.strip(),
            buyer_phone=data.buyer_phone.strip(),
            buyer_address=data.buyer_address.strip(),
            buyer_location=data.buyer_location.strip() if data.buyer_location else None,
            buyer_city=data.buyer_city.strip() if data.buyer_city else None,
            buyer_district=data.buyer_district.strip() if data.buyer_district else None,
            buyer_pincode=data.buyer_pincode.strip(),
            selected_size=data.selected_size.strip() if data.selected_size else None,
            quantity=data.quantity,
            unit_price=unit_p,
            total_price=total_p,
            status="NEW",
            notes=data.notes.strip() if data.notes else None,
        )
        db.add(order)
        product.orders_count += 1
        db.commit()
        db.refresh(order)

        # Generate WhatsApp link directly to seller
        seller_phone = product.seller_whatsapp or product.seller_phone or "919847123456"
        whatsapp_url = build_whatsapp_order_link(seller_phone, order, product.name)

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
    def get_seller_orders(db: Session, seller_id: int) -> List[ProductOrder]:
        return (
            db.query(ProductOrder)
            .filter(ProductOrder.seller_id == seller_id)
            .order_by(desc(ProductOrder.created_at))
            .all()
        )

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
