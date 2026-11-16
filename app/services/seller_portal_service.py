from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models.product import ProductOrder, SellerBankDetail
from app.db.models.user import User
from app.schemas.seller_portal import (
    CheckoutRulesData,
    SellerAnalyticsData,
    SellerBankDetails,
    SellerBankDetailsRequest,
    SellerOrderPipeline,
)
from app.services.product_service import ProductService, normalize_order_status


NEW_STATUSES = {"PLACED", "NEW", "PENDING"}
CONTACTED_STATUSES = {"CONFIRMED", "CONTACTED", "PACKED"}
SHIPPED_STATUSES = {"SHIPPED", "OUT_FOR_DELIVERY"}
ONLINE_METHODS = {"ONLINE", "RAZORPAY", "UPI"}


class SellerPortalService:
    @staticmethod
    def ensure_bank_schema(db: Session) -> None:
        if db.info.get("seller_bank_schema_ready"):
            return
        conn = db.connection()
        inspector = inspect(conn)
        if "seller_bank_details" not in inspector.get_table_names():
            SellerBankDetail.__table__.create(bind=conn, checkfirst=True)
            db.commit()
        db.info["seller_bank_schema_ready"] = True

    @staticmethod
    def get_bank_details(db: Session, seller: User) -> Optional[SellerBankDetail]:
        SellerPortalService.ensure_bank_schema(db)
        return db.query(SellerBankDetail).filter(SellerBankDetail.user_id == seller.id).first()

    @staticmethod
    def save_bank_details(db: Session, seller: User, data: SellerBankDetailsRequest) -> SellerBankDetail:
        SellerPortalService.ensure_bank_schema(db)
        row = db.query(SellerBankDetail).filter(SellerBankDetail.user_id == seller.id).first()
        if row is None:
            row = SellerBankDetail(user_id=seller.id)
            db.add(row)
        row.account_holder_name = data.account_holder_name
        row.bank_name = data.bank_name.strip()
        row.account_number = data.account_number
        row.ifsc_code = data.ifsc_code
        row.upi_id = data.upi_id
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def to_bank_details(row: SellerBankDetail) -> SellerBankDetails:
        return SellerBankDetails(
            account_holder_name=row.account_holder_name,
            bank_name=row.bank_name,
            account_number=row.account_number,
            ifsc_code=row.ifsc_code,
            upi_id=row.upi_id,
        )

    @staticmethod
    def seller_analytics(db: Session, seller: User, period: str) -> SellerAnalyticsData:
        chosen = (period or "all").strip().lower()
        if chosen not in {"all", "this_month", "this_year"}:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="period must be all, this_month, or this_year",
            )
        ProductService.ensure_order_schema(db)
        query = db.query(ProductOrder).filter(ProductOrder.seller_id == seller.id)
        now = datetime.now(timezone.utc)
        if chosen == "this_month":
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            query = query.filter(ProductOrder.created_at >= start)
        elif chosen == "this_year":
            start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            query = query.filter(ProductOrder.created_at >= start)

        pipeline = SellerOrderPipeline()
        total_sales = Decimal("0")
        online_paid = Decimal("0")
        cod_to_collect = Decimal("0")
        total_orders = 0
        for order in query.all():
            total_orders += 1
            current = normalize_order_status(order.status or "PLACED")
            amount = Decimal(str(order.total_price or 0))
            method = (order.payment_method or "").strip().upper()
            paid = (order.payment_status or "").strip().upper() == "PAID"
            if current == "CANCELLED":
                pipeline.cancelled_orders += 1
            elif current == "DELIVERED":
                pipeline.delivered_orders += 1
            elif current in SHIPPED_STATUSES:
                pipeline.shipped_orders += 1
            elif current in CONTACTED_STATUSES:
                pipeline.contacted_orders += 1
            else:
                pipeline.new_orders += 1
            if current == "CANCELLED":
                continue
            total_sales += amount
            if method in ONLINE_METHODS or paid:
                online_paid += amount
            if method == "COD" and current != "DELIVERED":
                cod_to_collect += amount

        def money(value: Decimal) -> float:
            return float(value.quantize(Decimal("0.01")))

        return SellerAnalyticsData(
            currency=settings.WALLET_CURRENCY or "INR",
            total_sales=money(total_sales),
            online_paid=money(online_paid),
            cod_to_collect=money(cod_to_collect),
            total_orders=total_orders,
            pipeline=pipeline,
        )

    @staticmethod
    def checkout_rules() -> CheckoutRulesData:
        return CheckoutRulesData(
            min_order_value=float(settings.CHECKOUT_MIN_ORDER_VALUE),
            free_delivery_above=float(settings.CHECKOUT_FREE_DELIVERY_ABOVE),
            delivery_fee=float(settings.CHECKOUT_DELIVERY_FEE),
            cod_available=bool(settings.CHECKOUT_COD_AVAILABLE),
            cod_fee=float(settings.CHECKOUT_COD_FEE),
            free_cod_above=float(settings.CHECKOUT_FREE_COD_ABOVE),
            online_discount_percentage=float(settings.CHECKOUT_ONLINE_DISCOUNT_PERCENTAGE),
            online_discount_max_amount=float(settings.CHECKOUT_ONLINE_DISCOUNT_MAX_AMOUNT),
        )
