import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models.merchant import MerchantProfile
from app.db.models.user import User
from app.db.models.wallet import (
    WalletLedgerDirection,
    WalletTopupOrder,
    WalletTopupStatus,
    WalletTransaction,
    WalletTransactionType,
)
from app.schemas.wallet_payment import (
    RazorpayTopupOrderResponse,
    RazorpayTopupVerifyRequest,
    RazorpayTopupVerifyResponse,
    RazorpayWalletConfigResponse,
    WalletTopupCreateRequest,
    WalletTopupOrderStatusResponse,
)
from app.services.razorpay_service import RazorpayService
from app.services.wallet_service import WalletService


class WalletTopupService:
    @staticmethod
    def get_checkout_config() -> RazorpayWalletConfigResponse:
        return RazorpayWalletConfigResponse(
            razorpay_key_id=RazorpayService.get_public_key(),
            currency=settings.WALLET_CURRENCY,
            min_amount=Decimal(str(settings.WALLET_TOPUP_MIN_AMOUNT)).quantize(Decimal("0.01")),
            max_amount=Decimal(str(settings.WALLET_TOPUP_MAX_AMOUNT)).quantize(Decimal("0.01")),
            razorpay_configured=RazorpayService.is_configured(),
        )

    @staticmethod
    def _validate_amount(amount: Decimal) -> Decimal:
        amount = WalletService._money(amount)
        min_amt = Decimal(str(settings.WALLET_TOPUP_MIN_AMOUNT)).quantize(Decimal("0.01"))
        max_amt = Decimal(str(settings.WALLET_TOPUP_MAX_AMOUNT)).quantize(Decimal("0.01"))
        if amount < min_amt or amount > max_amt:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Top-up amount must be between {min_amt} and {max_amt} INR.",
            )
        return amount

    @staticmethod
    def _resolve_merchant(
        db: Session, user: User, merchant_profile_id: Optional[int]
    ) -> MerchantProfile:
        return WalletService._merchant_for_user(db, user, merchant_profile_id)

    @staticmethod
    def create_razorpay_topup_order(
        db: Session,
        user: User,
        payload: WalletTopupCreateRequest,
    ) -> RazorpayTopupOrderResponse:
        amount = WalletTopupService._validate_amount(payload.amount)
        merchant: Optional[MerchantProfile] = None
        try:
            merchant = WalletTopupService._resolve_merchant(
                db, user, payload.merchant_profile_id
            )
        except Exception:
            merchant = None

        amount_paise = RazorpayService.inr_to_paise(amount)
        receipt = f"WTU-{uuid.uuid4().hex[:12].upper()}"

        notes = {
            "user_id": str(user.id),
            "purpose": "wallet_topup",
        }
        if merchant:
            notes["merchant_profile_id"] = str(merchant.id)

        rp_order = RazorpayService.create_order(
            amount_paise=amount_paise,
            receipt=receipt,
            notes=notes,
        )

        topup = WalletTopupOrder(
            user_id=user.id,
            merchant_profile_id=merchant.id if merchant else None,
            amount=amount,
            amount_paise=amount_paise,
            currency=settings.WALLET_CURRENCY,
            receipt=receipt,
            razorpay_order_id=str(rp_order["id"]),
            status=WalletTopupStatus.CREATED,
        )
        db.add(topup)
        db.commit()
        db.refresh(topup)

        return RazorpayTopupOrderResponse(
            message="Razorpay order created. Complete payment in checkout, then call verify.",
            topup_id=topup.id,
            razorpay_key_id=RazorpayService.get_public_key(),
            razorpay_order_id=topup.razorpay_order_id,
            amount=amount,
            amount_paise=amount_paise,
            currency=topup.currency,
            receipt=receipt,
            merchant_profile_id=merchant.id if merchant else None,
            merchant_business_name=merchant.business_name if merchant else None,
        )

    @staticmethod
    def _credit_topup_order(
        db: Session,
        topup: WalletTopupOrder,
        razorpay_payment_id: str,
    ) -> Tuple[WalletTopupOrder, str]:
        if topup.status == WalletTopupStatus.PAID:
            return topup, topup.wallet_transaction_group_id or ""

        existing = (
            db.query(WalletTopupOrder)
            .filter(
                WalletTopupOrder.razorpay_payment_id == razorpay_payment_id,
                WalletTopupOrder.id != topup.id,
            )
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This Razorpay payment was already used for another top-up.",
            )

        wallet = WalletService.ensure_wallet_for_user(db, topup.user_id)
        company_wallet = WalletService.get_company_wallet(db)
        db.flush()

        group_id = str(uuid.uuid4())
        txn = WalletTransaction(
            group_id=group_id,
            transaction_type=WalletTransactionType.WALLET_TOPUP,
            amount=topup.amount,
            currency=topup.currency,
            description=f"Wallet top-up via Razorpay order {topup.razorpay_order_id}",
            initiated_by_user_id=topup.user_id,
            reference_id=razorpay_payment_id,
        )
        db.add(txn)
        db.flush()

        locked = WalletService._lock_wallet(db, wallet.id)
        locked_company = WalletService._lock_wallet(db, company_wallet.id)
        WalletService._apply_ledger_line(
            db,
            txn,
            locked,
            WalletLedgerDirection.CREDIT,
            WalletService._money(topup.amount),
            counterparty_wallet_id=locked_company.id,
            note=f"Razorpay merchant wallet funding {razorpay_payment_id}",
        )
        WalletService._apply_ledger_line(
            db,
            txn,
            locked_company,
            WalletLedgerDirection.CREDIT,
            WalletService._money(topup.amount),
            counterparty_wallet_id=locked.id,
            note=f"Razorpay merchant payment received {razorpay_payment_id}",
        )

        now = datetime.now(timezone.utc)
        topup.status = WalletTopupStatus.PAID
        topup.razorpay_payment_id = razorpay_payment_id
        topup.wallet_transaction_group_id = group_id
        topup.paid_at = now

        db.commit()
        db.refresh(topup)
        db.refresh(locked)
        return topup, group_id

    @staticmethod
    def verify_and_credit(
        db: Session,
        user: User,
        payload: RazorpayTopupVerifyRequest,
    ) -> RazorpayTopupVerifyResponse:
        order_id = payload.razorpay_order_id.strip()
        payment_id = payload.razorpay_payment_id.strip()

        topup = (
            db.query(WalletTopupOrder)
            .filter(
                WalletTopupOrder.razorpay_order_id == order_id,
                WalletTopupOrder.user_id == user.id,
            )
            .with_for_update()
            .first()
        )
        if not topup:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Wallet top-up order not found for this user.",
            )

        if topup.status == WalletTopupStatus.PAID:
            wallet = WalletService.ensure_wallet_for_user(db, user.id)
            db.refresh(wallet)
            return RazorpayTopupVerifyResponse(
                message="Wallet already credited for this order.",
                topup_id=topup.id,
                transaction_group_id=topup.wallet_transaction_group_id or "",
                wallet_balance=WalletService._money(wallet.balance),
                amount=WalletService._money(topup.amount),
                razorpay_payment_id=topup.razorpay_payment_id or payment_id,
            )

        RazorpayService.verify_payment_signature(
            order_id,
            payment_id,
            payload.razorpay_signature.strip(),
        )

        topup, group_id = WalletTopupService._credit_topup_order(db, topup, payment_id)
        wallet = WalletService.ensure_wallet_for_user(db, user.id)
        db.refresh(wallet)

        return RazorpayTopupVerifyResponse(
            message="Wallet topped up successfully.",
            topup_id=topup.id,
            transaction_group_id=group_id,
            wallet_balance=WalletService._money(wallet.balance),
            amount=WalletService._money(topup.amount),
            razorpay_payment_id=payment_id,
        )

    @staticmethod
    def process_webhook_payment(
        db: Session,
        razorpay_order_id: str,
        razorpay_payment_id: str,
    ) -> Optional[RazorpayTopupVerifyResponse]:
        topup = (
            db.query(WalletTopupOrder)
            .filter(WalletTopupOrder.razorpay_order_id == razorpay_order_id)
            .with_for_update()
            .first()
        )
        if not topup:
            return None
        if topup.status == WalletTopupStatus.PAID:
            wallet = WalletService.ensure_wallet_for_user(db, topup.user_id)
            db.refresh(wallet)
            return RazorpayTopupVerifyResponse(
                message="Wallet already credited (webhook).",
                topup_id=topup.id,
                transaction_group_id=topup.wallet_transaction_group_id or "",
                wallet_balance=WalletService._money(wallet.balance),
                amount=WalletService._money(topup.amount),
                razorpay_payment_id=topup.razorpay_payment_id or razorpay_payment_id,
            )

        topup, group_id = WalletTopupService._credit_topup_order(
            db, topup, razorpay_payment_id
        )
        wallet = WalletService.ensure_wallet_for_user(db, topup.user_id)
        db.refresh(wallet)
        return RazorpayTopupVerifyResponse(
            message="Wallet topped up via webhook.",
            topup_id=topup.id,
            transaction_group_id=group_id,
            wallet_balance=WalletService._money(wallet.balance),
            amount=WalletService._money(topup.amount),
            razorpay_payment_id=razorpay_payment_id,
        )

    @staticmethod
    def list_my_topups(db: Session, user: User, limit: int = 20) -> List[WalletTopupOrder]:
        return (
            db.query(WalletTopupOrder)
            .filter(WalletTopupOrder.user_id == user.id)
            .order_by(WalletTopupOrder.created_at.desc())
            .limit(limit)
            .all()
        )

    @staticmethod
    def get_topup_status(
        db: Session, user: User, topup_id: int
    ) -> WalletTopupOrderStatusResponse:
        topup = (
            db.query(WalletTopupOrder)
            .filter(WalletTopupOrder.id == topup_id, WalletTopupOrder.user_id == user.id)
            .first()
        )
        if not topup:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Top-up order not found.")
        wallet_balance = None
        if topup.status == WalletTopupStatus.PAID:
            wallet = WalletService.ensure_wallet_for_user(db, user.id)
            wallet_balance = WalletService._money(wallet.balance)
        return WalletTopupOrderStatusResponse(
            topup_id=topup.id,
            status=topup.status,
            amount=WalletService._money(topup.amount),
            currency=topup.currency,
            razorpay_order_id=topup.razorpay_order_id,
            razorpay_payment_id=topup.razorpay_payment_id,
            wallet_transaction_group_id=topup.wallet_transaction_group_id,
            wallet_balance=wallet_balance,
            paid_at=topup.paid_at,
        )
