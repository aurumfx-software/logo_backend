from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import List, Optional, Tuple
import uuid
import hashlib
import hmac
import json

from fastapi import HTTPException, status
import httpx
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models.merchant import MerchantProfile
from app.db.models.user import User, UserRole
from app.db.models.wallet import (
    MerchantSaleQR,
    RewardClaimStatus,
    SaleQRStatus,
    Wallet,
    WalletLedgerDirection,
    WalletLedgerEntry,
    WalletRewardClaim,
    WalletTransaction,
    WalletTransactionType,
    WalletType,
    WalletTopupOrder,
    WalletWithdrawal,
)
from app.schemas.wallet import (
    PlatformWalletResponse,
    PlatformWalletTransaction,
    SaleQRCreateRequest,
    SaleQRCreateResponse,
    SaleQRMerchantStatusResponse,
    SaleQRPreviewResponse,
    SaleRedeemResponse,
    WalletLedgerEntryResponse,
    WalletResponse,
    WalletTopUpRequest,
    WalletTopUpResponse,
    WalletTransferRequest,
    WalletTransferResponse,
    WalletWithdrawalRequest,
    WalletWithdrawalResponse,
    AdminWalletLedgerLineResponse,
    AdminWalletTransactionResponse,
)


MONEY_QUANT = Decimal("0.01")


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _percent_label(percent: float) -> str:
    return f"{percent:.2f}".rstrip("0").rstrip(".") or "0"


class WalletService:
    @staticmethod
    def _money(value: Decimal) -> Decimal:
        return Decimal(value).quantize(MONEY_QUANT)

    @staticmethod
    def _percent_of(amount: Decimal, percent: float) -> Decimal:
        return WalletService._money(amount * Decimal(str(percent)) / Decimal("100"))

    @staticmethod
    def wallet_to_response(wallet: Wallet) -> WalletResponse:
        return WalletResponse(
            id=wallet.id,
            user_id=wallet.user_id,
            wallet_type=wallet.wallet_type.value if hasattr(wallet.wallet_type, "value") else str(wallet.wallet_type),
            currency=wallet.currency,
            balance=WalletService._money(wallet.balance),
            is_active=wallet.is_active,
        )

    @staticmethod
    def ensure_wallet_for_user(db: Session, user_id: int) -> Wallet:
        wallet = db.query(Wallet).filter(Wallet.user_id == user_id).first()
        if wallet:
            return wallet
        wallet = Wallet(
            user_id=user_id,
            wallet_type=WalletType.USER,
            currency=settings.WALLET_CURRENCY,
            balance=Decimal("0.00"),
        )
        db.add(wallet)
        db.flush()
        return wallet

    @staticmethod
    def get_company_wallet(db: Session) -> Wallet:
        wallet = (
            db.query(Wallet)
            .filter(Wallet.wallet_type == WalletType.COMPANY)
            .first()
        )
        if wallet:
            return wallet
        wallet = Wallet(
            user_id=None,
            wallet_type=WalletType.COMPANY,
            currency=settings.WALLET_CURRENCY,
            balance=Decimal("0.00"),
        )
        db.add(wallet)
        db.flush()
        return wallet

    @staticmethod
    def _lock_wallet(db: Session, wallet_id: int) -> Wallet:
        wallet = (
            db.query(Wallet)
            .filter(Wallet.id == wallet_id, Wallet.is_active.is_(True))
            .with_for_update()
            .first()
        )
        if not wallet:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Wallet not found or inactive.",
            )
        return wallet

    @staticmethod
    def _apply_ledger_line(
        db: Session,
        txn: WalletTransaction,
        wallet: Wallet,
        direction: WalletLedgerDirection,
        amount: Decimal,
        counterparty_wallet_id: Optional[int] = None,
        note: Optional[str] = None,
    ) -> WalletLedgerEntry:
        amount = WalletService._money(amount)
        if amount <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ledger amount must be positive.",
            )

        if direction == WalletLedgerDirection.DEBIT:
            if WalletService._money(wallet.balance) < amount:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Insufficient wallet balance.",
                )
            wallet.balance = WalletService._money(wallet.balance - amount)
        else:
            wallet.balance = WalletService._money(wallet.balance + amount)

        entry = WalletLedgerEntry(
            transaction_id=txn.id,
            wallet_id=wallet.id,
            direction=direction,
            amount=amount,
            balance_after=wallet.balance,
            counterparty_wallet_id=counterparty_wallet_id,
            note=note,
        )
        db.add(entry)
        return entry

    @staticmethod
    def create_wallet_withdrawal(db: Session, user: User, payload: WalletWithdrawalRequest) -> WalletWithdrawalResponse:
        if not settings.RAZORPAYX_KEY_ID or not settings.RAZORPAYX_KEY_SECRET or not settings.RAZORPAYX_ACCOUNT_NUMBER:
            raise HTTPException(status_code=503, detail="Bank withdrawals are not configured.")
        amount = WalletService._money(payload.amount)
        phone = "".join(ch for ch in (user.phone or "") if ch.isdigit())
        if len(phone) < 10:
            raise HTTPException(status_code=400, detail="Add a valid phone number to your profile before withdrawing.")
        user_wallet = WalletService._lock_wallet(db, WalletService.ensure_wallet_for_user(db, user.id).id)
        company_wallet = WalletService._lock_wallet(db, WalletService.get_company_wallet(db).id)
        if WalletService._money(user_wallet.balance) < amount:
            raise HTTPException(status_code=400, detail="Insufficient wallet balance.")
        if WalletService._money(company_wallet.balance) < amount:
            raise HTTPException(status_code=400, detail="Insufficient admin wallet funds for payout.")
        group_id = str(uuid.uuid4())
        txn = WalletTransaction(
            group_id=group_id, transaction_type=WalletTransactionType.WALLET_WITHDRAWAL,
            amount=amount, currency=settings.WALLET_CURRENCY,
            description="Wallet withdrawal to bank account", initiated_by_user_id=user.id,
            reference_id=group_id,
        )
        db.add(txn)
        db.flush()
        WalletService._apply_ledger_line(db, txn, user_wallet, WalletLedgerDirection.DEBIT, amount,
                                         counterparty_wallet_id=company_wallet.id, note="Bank withdrawal requested")
        WalletService._apply_ledger_line(db, txn, company_wallet, WalletLedgerDirection.DEBIT, amount,
                                         counterparty_wallet_id=user_wallet.id, note="Cash payout submitted")
        withdrawal = WalletWithdrawal(
            user_id=user.id, amount=amount, currency=settings.WALLET_CURRENCY, status="PROCESSING",
            wallet_transaction_group_id=group_id, bank_account_holder_name=payload.account_holder_name,
            bank_account_last4=payload.account_number.strip()[-4:], bank_ifsc=payload.ifsc.upper(),
        )
        db.add(withdrawal)
        db.commit()
        payout_payload = {
            "account_number": settings.RAZORPAYX_ACCOUNT_NUMBER, "amount": int(amount * 100),
            "currency": settings.WALLET_CURRENCY, "mode": payload.mode, "purpose": "cashback",
            "queue_if_low_balance": False, "reference_id": group_id[:40], "narration": "Wallet cashback",
            "fund_account": {
                "account_type": "bank_account",
                "bank_account": {"name": payload.account_holder_name, "ifsc": payload.ifsc.upper(), "account_number": payload.account_number.strip()},
                "contact": {"name": user.name, "email": user.email, "contact": phone[-10:], "type": "customer"},
            },
        }
        try:
            response = httpx.post("https://api.razorpay.com/v1/payouts",
                                  auth=(settings.RAZORPAYX_KEY_ID, settings.RAZORPAYX_KEY_SECRET),
                                  headers={"X-Payout-Idempotency": group_id}, json=payout_payload, timeout=25)
            response.raise_for_status()
            payout = response.json()
        except httpx.HTTPStatusError as exc:
            db.refresh(withdrawal)
            WalletService._refund_failed_withdrawal(db, withdrawal, "RazorpayX rejected payout")
            raise HTTPException(status_code=502, detail="RazorpayX could not create the bank payout.") from exc
        except httpx.HTTPError as exc:
            try:
                response = httpx.post("https://api.razorpay.com/v1/payouts",
                                      auth=(settings.RAZORPAYX_KEY_ID, settings.RAZORPAYX_KEY_SECRET),
                                      headers={"X-Payout-Idempotency": group_id}, json=payout_payload, timeout=25)
                response.raise_for_status()
                payout = response.json()
            except httpx.HTTPStatusError as retry_exc:
                db.refresh(withdrawal)
                WalletService._refund_failed_withdrawal(db, withdrawal, "RazorpayX rejected payout")
                raise HTTPException(status_code=502, detail="RazorpayX could not create the bank payout.") from retry_exc
            except httpx.HTTPError:
                raise HTTPException(status_code=503, detail="Payout status is pending provider confirmation.") from exc
        db.refresh(withdrawal)
        if not withdrawal.payout_id:
            withdrawal.payout_id = payout.get("id")
        if withdrawal.status not in {"PROCESSED", "FAILED", "REVERSED", "REJECTED", "CANCELLED"}:
            provider_status = str(payout.get("status", "processing")).upper()
            withdrawal.status = provider_status
            if provider_status in {"FAILED", "REVERSED", "REJECTED", "CANCELLED"}:
                withdrawal.status = "PROCESSING"
                WalletService._refund_failed_withdrawal(db, withdrawal, f"RazorpayX payout {provider_status.lower()}", provider_status)
            else:
                db.commit()
        db.refresh(user_wallet)
        return WalletWithdrawalResponse(message="Withdrawal submitted", status=withdrawal.status,
                                        payout_id=withdrawal.payout_id, failure_reason=withdrawal.failure_reason,
                                        transaction_group_id=group_id, wallet_balance=WalletService._money(user_wallet.balance))

    @staticmethod
    def _refund_failed_withdrawal(db: Session, withdrawal: WalletWithdrawal, reason: str, final_status: str = "FAILED") -> None:
        if withdrawal.status in {"FAILED", "REVERSED", "REJECTED", "CANCELLED", "PROCESSED"}:
            return
        user_wallet = WalletService._lock_wallet(db, WalletService.ensure_wallet_for_user(db, withdrawal.user_id).id)
        company_wallet = WalletService._lock_wallet(db, WalletService.get_company_wallet(db).id)
        group_id = str(uuid.uuid4())
        txn = WalletTransaction(group_id=group_id, transaction_type=WalletTransactionType.ADMIN_CREDIT,
                                amount=withdrawal.amount, currency=withdrawal.currency,
                                description=f"Withdrawal reversal: {reason}", reference_id=withdrawal.payout_id or str(withdrawal.id))
        db.add(txn)
        db.flush()
        WalletService._apply_ledger_line(db, txn, user_wallet, WalletLedgerDirection.CREDIT, withdrawal.amount,
                                         counterparty_wallet_id=company_wallet.id, note=reason)
        WalletService._apply_ledger_line(db, txn, company_wallet, WalletLedgerDirection.CREDIT, withdrawal.amount,
                                         counterparty_wallet_id=user_wallet.id, note=f"Payout reversal: {reason}")
        withdrawal.status = final_status
        withdrawal.failure_reason = reason[:1000]
        db.commit()

    @staticmethod
    def process_razorpayx_webhook(db: Session, raw_body: bytes, signature: str) -> None:
        secret = settings.RAZORPAYX_WEBHOOK_SECRET
        if not secret:
            raise HTTPException(status_code=503, detail="RazorpayX webhooks are not configured.")
        expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise HTTPException(status_code=400, detail="Invalid RazorpayX webhook signature.")
        try:
            event = json.loads(raw_body)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid webhook payload.") from exc
        event_name = event.get("event")
        payout = (event.get("payload") or {}).get("payout", {}).get("entity", {})
        payout_id = payout.get("id")
        if not payout_id:
            return
        reference_id = payout.get("reference_id")
        withdrawal = db.query(WalletWithdrawal).filter(
            (WalletWithdrawal.payout_id == payout_id) | (WalletWithdrawal.wallet_transaction_group_id == reference_id)
        ).with_for_update().first()
        if not withdrawal or withdrawal.status in {"FAILED", "REVERSED", "REJECTED", "CANCELLED", "PROCESSED"}:
            return
        withdrawal.payout_id = payout_id
        if event_name == "payout.processed":
            withdrawal.status = "PROCESSED"
            db.commit()
        elif event_name in {"payout.failed", "payout.reversed", "payout.rejected", "payout.cancelled"}:
            final_status = {"payout.reversed": "REVERSED", "payout.rejected": "REJECTED", "payout.cancelled": "CANCELLED"}.get(event_name, "FAILED")
            withdrawal.status = "PROCESSING"
            WalletService._refund_failed_withdrawal(db, withdrawal, f"RazorpayX {event_name}", final_status)

    @staticmethod
    def get_withdrawal_status(db: Session, user: User, group_id: str) -> WalletWithdrawalResponse:
        withdrawal = db.query(WalletWithdrawal).filter_by(wallet_transaction_group_id=group_id, user_id=user.id).first()
        if not withdrawal:
            raise HTTPException(status_code=404, detail="Withdrawal not found.")
        wallet = WalletService.ensure_wallet_for_user(db, user.id)
        return WalletWithdrawalResponse(message="Withdrawal status retrieved", status=withdrawal.status,
                                        payout_id=withdrawal.payout_id, failure_reason=withdrawal.failure_reason,
                                        transaction_group_id=group_id, wallet_balance=WalletService._money(wallet.balance))

    @staticmethod
    def admin_list_transactions(db: Session, page: int, page_size: int):
        query = db.query(WalletTransaction)
        total = query.count()
        txns = query.order_by(WalletTransaction.created_at.desc(), WalletTransaction.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
        data = []
        for txn in txns:
            initiator = txn.initiated_by
            initiator_profile = db.query(MerchantProfile).filter_by(user_id=initiator.id).first() if initiator else None
            provider_status = provider_id = failure_reason = bank_name = bank_last4 = bank_ifsc = None
            if txn.transaction_type == WalletTransactionType.WALLET_TOPUP:
                topup = db.query(WalletTopupOrder).filter_by(wallet_transaction_group_id=txn.group_id).first()
                if topup:
                    provider_status, provider_id = topup.status.value, topup.razorpay_payment_id or topup.razorpay_order_id
            elif txn.transaction_type == WalletTransactionType.WALLET_WITHDRAWAL:
                withdrawal = db.query(WalletWithdrawal).filter_by(wallet_transaction_group_id=txn.group_id).first()
                if withdrawal:
                    provider_status, provider_id = withdrawal.status, withdrawal.payout_id
                    failure_reason, bank_name, bank_last4, bank_ifsc = withdrawal.failure_reason, withdrawal.bank_account_holder_name, withdrawal.bank_account_last4, withdrawal.bank_ifsc
            lines = []
            for row in sorted(txn.ledger_entries, key=lambda item: item.id):
                wallet = row.wallet
                user = wallet.user
                cp_wallet = row.counterparty_wallet
                cp_user = cp_wallet.user if cp_wallet else None
                profile = db.query(MerchantProfile).filter_by(user_id=user.id).first() if user else None
                cp_profile = db.query(MerchantProfile).filter_by(user_id=cp_user.id).first() if cp_user else None
                lines.append(AdminWalletLedgerLineResponse(
                    id=row.id, direction=row.direction.value, amount=WalletService._money(row.amount),
                    balance_after=WalletService._money(row.balance_after), wallet_id=wallet.id,
                    wallet_type=wallet.wallet_type.value, user_id=user.id if user else None,
                    user_name=(profile.business_name if profile else user.name) if user else None,
                    user_email=user.email if user else None, counterparty_wallet_id=cp_wallet.id if cp_wallet else None,
                    counterparty_user_id=cp_user.id if cp_user else None,
                    counterparty_name=(cp_profile.business_name if cp_profile else cp_user.name) if cp_user else ("Admin wallet" if cp_wallet and cp_wallet.wallet_type == WalletType.COMPANY else None),
                    counterparty_email=cp_user.email if cp_user else None, note=row.note, created_at=row.created_at,
                ))
            data.append(AdminWalletTransactionResponse(
                id=txn.id, transaction_group_id=txn.group_id, transaction_type=txn.transaction_type.value,
                amount=WalletService._money(txn.amount), currency=txn.currency, description=txn.description,
                initiated_by_user_id=initiator.id if initiator else None,
                initiated_by_name=(initiator_profile.business_name if initiator_profile else initiator.name) if initiator else None,
                initiated_by_email=initiator.email if initiator else None, reference_id=txn.reference_id,
                provider_status=provider_status, provider_id=provider_id, failure_reason=failure_reason,
                bank_account_holder_name=bank_name, bank_account_last4=bank_last4, bank_ifsc=bank_ifsc,
                created_at=txn.created_at, ledger_entries=lines,
            ))
        return data, total

    @staticmethod
    def _sum_money(value) -> Decimal:
        return WalletService._money(Decimal(str(value or 0)))

    @staticmethod
    def get_platform_wallet(db: Session, page: int = 1, page_size: int = 20) -> PlatformWalletResponse:
        """Company wallet balance, QR fee totals, and platform ledger credits."""
        company = WalletService.get_company_wallet(db)
        db.commit()
        db.refresh(company)

        revenue = WalletService._sum_money(
            db.query(func.coalesce(func.sum(WalletLedgerEntry.amount), 0))
            .join(WalletTransaction, WalletTransaction.id == WalletLedgerEntry.transaction_id)
            .filter(
                WalletLedgerEntry.wallet_id == company.id,
                WalletLedgerEntry.direction == WalletLedgerDirection.CREDIT,
                WalletTransaction.transaction_type == WalletTransactionType.CASHBACK_REDEMPTION,
            )
            .scalar()
        )
        cashback = WalletService._sum_money(
            db.query(func.coalesce(func.sum(WalletLedgerEntry.amount), 0))
            .join(WalletTransaction, WalletTransaction.id == WalletLedgerEntry.transaction_id)
            .filter(
                WalletLedgerEntry.wallet_id != company.id,
                WalletLedgerEntry.direction == WalletLedgerDirection.CREDIT,
                WalletTransaction.transaction_type == WalletTransactionType.CASHBACK_REDEMPTION,
            )
            .scalar()
        )
        gross_sales = WalletService._sum_money(
            db.query(func.coalesce(func.sum(MerchantSaleQR.sale_amount), 0))
            .filter(MerchantSaleQR.status == SaleQRStatus.REDEEMED)
            .scalar()
        )
        redemptions = (
            db.query(func.count(MerchantSaleQR.id))
            .filter(MerchantSaleQR.status == SaleQRStatus.REDEEMED)
            .scalar()
            or 0
        )

        ledger = (
            db.query(WalletLedgerEntry)
            .filter(WalletLedgerEntry.wallet_id == company.id)
            .order_by(WalletLedgerEntry.created_at.desc())
        )
        total = ledger.count()
        rows = ledger.offset((page - 1) * page_size).limit(page_size).all()
        transactions = []
        for row in rows:
            txn = row.transaction
            # Try to find merchant name from the transaction group's sale QR
            merchant_name = None
            merchant_city = None
            if txn and txn.group_id:
                sale_qr = db.query(MerchantSaleQR).filter(
                    MerchantSaleQR.wallet_transaction_group_id == txn.group_id
                ).first()
                if sale_qr and sale_qr.merchant_profile_id:
                    mp = db.query(MerchantProfile).filter(
                        MerchantProfile.id == sale_qr.merchant_profile_id
                    ).first()
                    if mp:
                        merchant_name = mp.business_name
                        merchant_city = mp.city
            transactions.append(
                PlatformWalletTransaction(
                    id=row.id,
                    direction=row.direction.value if hasattr(row.direction, "value") else str(row.direction),
                    amount=WalletService._money(row.amount),
                    balance_after=WalletService._money(row.balance_after),
                    note=row.note,
                    created_at=row.created_at,
                    transaction_type=(
                        txn.transaction_type.value
                        if txn and hasattr(txn.transaction_type, "value")
                        else (str(txn.transaction_type) if txn else None)
                    ),
                    transaction_group_id=txn.group_id if txn else None,
                    merchant_name=merchant_name,
                    merchant_city=merchant_city,
                )
            )

        user_pct = float(settings.CASHBACK_USER_PERCENT)
        company_pct = float(settings.CASHBACK_COMPANY_PERCENT)
        return PlatformWalletResponse(
            currency=company.currency or settings.WALLET_CURRENCY,
            balance=WalletService._money(company.balance),
            customer_cashback_percent=user_pct,
            platform_fee_percent=company_pct,
            total_shop_deduction_percent=user_pct + company_pct,
            total_platform_revenue=revenue,
            cashback_distributed=cashback,
            gross_sales_volume=gross_sales,
            qr_redemptions=int(redemptions),
            transactions=transactions,
            total=total,
            page=page,
            page_size=page_size,
        )

    @staticmethod
    def get_my_wallet(db: Session, user: User) -> WalletResponse:
        wallet = WalletService.ensure_wallet_for_user(db, user.id)
        db.commit()
        db.refresh(wallet)
        return WalletService.wallet_to_response(wallet)

    @staticmethod
    def list_transactions(
        db: Session,
        user: User,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[WalletLedgerEntryResponse], int]:
        wallet = WalletService.ensure_wallet_for_user(db, user.id)
        db.flush()

        q = (
            db.query(WalletLedgerEntry)
            .filter(WalletLedgerEntry.wallet_id == wallet.id)
            .order_by(WalletLedgerEntry.created_at.desc())
        )
        total = q.count()
        offset = (page - 1) * page_size
        rows = q.offset(offset).limit(page_size).all()

        items: List[WalletLedgerEntryResponse] = []
        for row in rows:
            txn = row.transaction
            items.append(
                WalletLedgerEntryResponse(
                    id=row.id,
                    direction=row.direction.value if hasattr(row.direction, "value") else str(row.direction),
                    amount=WalletService._money(row.amount),
                    balance_after=WalletService._money(row.balance_after),
                    note=row.note,
                    counterparty_wallet_id=row.counterparty_wallet_id,
                    created_at=row.created_at,
                    transaction_type=(
                        txn.transaction_type.value
                        if txn and hasattr(txn.transaction_type, "value")
                        else (str(txn.transaction_type) if txn else None)
                    ),
                    transaction_group_id=txn.group_id if txn else None,
                )
            )
        return items, total

    @staticmethod
    def _resolve_recipient(db: Session, payload: WalletTransferRequest) -> User:
        user = None

        # 1. Direct transfer to Platform Admin
        if payload.to_admin:
            user = (
                db.query(User)
                .filter(
                    User.role.in_(['admin', 'superadmin', 'ADMIN', 'SUPER_ADMIN', UserRole.ADMIN, UserRole.SUPER_ADMIN]),
                    User.is_active == True,
                )
                .order_by(User.id.asc())
                .first()
            )
            if not user:
                user = db.query(User).filter(User.id == 15).first()
            if user:
                return user

        if not payload.to_user_id and not payload.to_user_code and not payload.to_email and not payload.to_phone and not payload.to_merchant_id and not payload.to_admin:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Provide to_user_id, to_user_code, to_email, to_phone, to_merchant_id, or set to_admin=True.",
            )

        if payload.to_merchant_id:
            merchant = db.query(MerchantProfile).filter(MerchantProfile.id == payload.to_merchant_id).first()
            if merchant and merchant.user_id:
                user = db.query(User).filter(User.id == merchant.user_id).first()
            if not user:
                user = db.query(User).filter(User.id == payload.to_merchant_id).first()
        elif payload.to_user_id:
            user = db.query(User).filter(User.id == payload.to_user_id).first()
        elif payload.to_phone:
            phone_clean = payload.to_phone.strip()
            user = db.query(User).filter(User.phone == phone_clean).first()
            if not user:
                merchant = db.query(MerchantProfile).filter(
                    or_(
                        MerchantProfile.phone == phone_clean,
                        MerchantProfile.whatsapp == phone_clean,
                    )
                ).first()
                if merchant and merchant.user_id:
                    user = db.query(User).filter(User.id == merchant.user_id).first()
        elif payload.to_user_code:
            code_clean = payload.to_user_code.strip()
            user = db.query(User).filter(User.user_code == code_clean).first()
            if not user and code_clean.isdigit():
                merchant = db.query(MerchantProfile).filter(MerchantProfile.id == int(code_clean)).first()
                if merchant and merchant.user_id:
                    user = db.query(User).filter(User.id == merchant.user_id).first()
        elif payload.to_email:
            target_email = payload.to_email.strip().lower()
            user = db.query(User).filter(User.email == target_email).first()
            if not user:
                merchant = db.query(MerchantProfile).filter(MerchantProfile.email == target_email).first()
                if merchant and merchant.user_id:
                    user = db.query(User).filter(User.id == merchant.user_id).first()
            # If aurumfxsoftware or admin email alias was passed, map to platform admin user
            if not user and (target_email in ['aurumfxsoftware@gmail.com', 'admin@aurumfx.com'] or 'admin' in target_email or 'aurum' in target_email):
                user = (
                    db.query(User)
                    .filter(
                        User.role.in_(['admin', 'superadmin', 'ADMIN', 'SUPER_ADMIN', UserRole.ADMIN, UserRole.SUPER_ADMIN]),
                        User.is_active == True,
                    )
                    .order_by(User.id.asc())
                    .first()
                ) or db.query(User).filter(User.id == 15).first()

        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Recipient user not found or inactive.",
            )
        return user

    @staticmethod
    def transfer_wallet_to_wallet(
        db: Session,
        sender: User,
        payload: WalletTransferRequest,
    ) -> WalletTransferResponse:
        recipient = WalletService._resolve_recipient(db, payload)
        if recipient.id == sender.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot transfer to your own wallet.",
            )

        amount = WalletService._money(payload.amount)
        sender_wallet = WalletService.ensure_wallet_for_user(db, sender.id)
        recipient_wallet = WalletService.ensure_wallet_for_user(db, recipient.id)
        db.flush()

        group_id = str(uuid.uuid4())
        txn = WalletTransaction(
            group_id=group_id,
            transaction_type=WalletTransactionType.P2P_TRANSFER,
            amount=amount,
            currency=settings.WALLET_CURRENCY,
            description=payload.note or f"P2P transfer to user {recipient.id}",
            initiated_by_user_id=sender.id,
            reference_id=str(recipient.id),
        )
        db.add(txn)
        db.flush()

        locked_sender = WalletService._lock_wallet(db, sender_wallet.id)
        locked_recipient = WalletService._lock_wallet(db, recipient_wallet.id)

        WalletService._apply_ledger_line(
            db,
            txn,
            locked_sender,
            WalletLedgerDirection.DEBIT,
            amount,
            counterparty_wallet_id=locked_recipient.id,
            note=payload.note or "Wallet transfer sent",
        )
        WalletService._apply_ledger_line(
            db,
            txn,
            locked_recipient,
            WalletLedgerDirection.CREDIT,
            amount,
            counterparty_wallet_id=locked_sender.id,
            note=payload.note or f"Wallet transfer from {sender.name}",
        )

        db.commit()
        db.refresh(locked_sender)
        db.refresh(locked_recipient)

        return WalletTransferResponse(
            message="Transfer completed successfully",
            transaction_group_id=group_id,
            sender_balance=WalletService._money(locked_sender.balance),
            recipient_balance=WalletService._money(locked_recipient.balance),
        )

    @staticmethod
    def top_up_wallet(
        db: Session,
        user: User,
        payload: WalletTopUpRequest,
    ) -> WalletTopUpResponse:
        amount = WalletService._money(payload.amount)
        if amount <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Amount must be greater than zero.",
            )

        target_wallet = WalletService.ensure_wallet_for_user(db, user.id)
        db.flush()

        group_id = str(uuid.uuid4())
        ref_id = payload.reference_id or f"TOPUP_{group_id[:8].upper()}"
        pay_method = (payload.payment_method or "UPI").strip().upper()
        note = payload.note or f"Wallet top-up via {pay_method}"

        txn = WalletTransaction(
            group_id=group_id,
            transaction_type=WalletTransactionType.WALLET_TOPUP,
            amount=amount,
            currency=settings.WALLET_CURRENCY,
            description=note,
            initiated_by_user_id=user.id,
            reference_id=ref_id,
        )
        db.add(txn)
        db.flush()

        locked = WalletService._lock_wallet(db, target_wallet.id)
        WalletService._apply_ledger_line(
            db,
            txn,
            locked,
            WalletLedgerDirection.CREDIT,
            amount,
            note=note,
        )

        db.commit()
        db.refresh(locked)

        try:
            from app.services.notification_service import NotificationService

            NotificationService.create_notification(
                db=db,
                user_id=user.id,
                title="Wallet Top-Up Successful",
                message=f"₹{amount} credited to your wallet via {pay_method}. New balance: ₹{locked.balance}.",
                type="WALLET_TOPUP",
                data={
                    "amount": str(amount),
                    "new_balance": str(locked.balance),
                    "payment_method": pay_method,
                    "reference_id": ref_id,
                    "group_id": group_id,
                },
            )
        except Exception:
            pass

        return WalletTopUpResponse(
            success=True,
            message=f"Successfully added ₹{amount:.2f} to wallet via {pay_method}.",
            wallet=WalletService.wallet_to_response(locked),
            transaction_group_id=group_id,
            amount_credited=amount,
            new_balance=WalletService._money(locked.balance),
            payment_method=pay_method,
        )

    @staticmethod
    def _merchant_access_clause(user: User):
        clauses = [
            MerchantProfile.user_id == user.id,
            MerchantProfile.onboarded_by_id == user.id,
        ]
        if user.phone:
            clauses.append(MerchantProfile.phone == user.phone)
            clauses.append(MerchantProfile.contact_number == user.phone)
        if user.email:
            clean = user.email.strip().lower()
            clauses.append(func.lower(MerchantProfile.email) == clean)
        return or_(*clauses)

    @staticmethod
    def _merchant_for_user(
        db: Session,
        user: User,
        merchant_profile_id: Optional[int],
        *,
        allow_unapproved: bool = False,
    ) -> MerchantProfile:
        access = WalletService._merchant_access_clause(user)
        merchant: Optional[MerchantProfile] = None
        if merchant_profile_id:
            merchant = (
                db.query(MerchantProfile)
                .filter(MerchantProfile.id == merchant_profile_id, access)
                .first()
            )
        if not merchant:
            merchant = (
                db.query(MerchantProfile)
                .filter(access)
                .order_by(MerchantProfile.id.desc())
                .first()
            )
        if not merchant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No merchant profile found. Please register a shop first.",
            )
        approved = {"APPROVED", "ACTIVE"}
        status_ok = (
            (merchant.approval_status or "").upper() in approved
            or (merchant.status or "").upper() in approved
        )
        if not status_ok and settings.ENVIRONMENT == "development" and merchant.is_active:
            status_ok = True
        if not status_ok and allow_unapproved:
            merchant.status = "APPROVED"
            merchant.approval_status = "APPROVED"
            db.commit()
            db.refresh(merchant)
            status_ok = True
        if not status_ok:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Merchant profile must be approved to use this wallet feature.",
            )
        return merchant

    @staticmethod
    def _merchant_row(db: Session, merchant_profile_id: Optional[int]) -> Optional[MerchantProfile]:
        if not merchant_profile_id:
            return None
        return (
            db.query(MerchantProfile)
            .filter(MerchantProfile.id == merchant_profile_id)
            .first()
        )

    @staticmethod
    def _cashback_rates(merchant: Optional[MerchantProfile]) -> Tuple[float, float]:
        """Customer cashback and company fee percents from merchant_profiles."""
        if merchant is None:
            return float(settings.CASHBACK_USER_PERCENT), float(settings.CASHBACK_COMPANY_PERCENT)
        user_pct = merchant.cashback_percent
        company_pct = merchant.company_fee_percent
        return (
            float(user_pct if user_pct is not None else settings.CASHBACK_USER_PERCENT),
            float(company_pct if company_pct is not None else settings.CASHBACK_COMPANY_PERCENT),
        )

    @staticmethod
    def _split_cashback(
        sale_amount: Decimal, merchant: Optional[MerchantProfile]
    ) -> Tuple[Decimal, Decimal, Decimal]:
        user_pct, company_pct = WalletService._cashback_rates(merchant)
        user_cb = WalletService._percent_of(sale_amount, user_pct)
        company_fee = WalletService._percent_of(sale_amount, company_pct)
        total = WalletService._money(user_cb + company_fee)
        return total, user_cb, company_fee

    @staticmethod
    def _sale_qr_payload(token: str, sale_amount: Decimal, business_name: str) -> str:
        return (
            f"logo://wallet/redeem?token={token}"
            f"&amount={sale_amount}&merchant={business_name}"
        )

    @staticmethod
    def _expire_if_pending(db: Session, sale_qr: MerchantSaleQR) -> bool:
        if sale_qr.status != SaleQRStatus.PENDING:
            return False
        if _as_utc(sale_qr.expires_at) >= datetime.now(timezone.utc):
            return False
        sale_qr.status = SaleQRStatus.EXPIRED
        db.commit()
        db.refresh(sale_qr)
        return True

    @staticmethod
    def create_sale_qr(
        db: Session,
        merchant_user: User,
        payload: SaleQRCreateRequest,
    ) -> SaleQRCreateResponse:
        if payload.merchant_profile_id:
            merchant = WalletService._merchant_for_user(
                db, merchant_user, payload.merchant_profile_id, allow_unapproved=True
            )
        else:
            from app.services.merchant_service import MerchantService

            try:
                merchant = MerchantService.get_merchant_by_user_id(db, merchant_user.id)
            except HTTPException:
                merchant = WalletService._merchant_for_user(
                    db, merchant_user, None, allow_unapproved=True
                )
        db.refresh(merchant)
        sale_amount = WalletService._money(payload.sale_amount)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=payload.expires_in_minutes)

        user_pct, company_pct = WalletService._cashback_rates(merchant)
        total_cb, user_cb, company_fee = WalletService._split_cashback(sale_amount, merchant)
        user_pct, company_pct = WalletService._cashback_rates(merchant)

        sale_qr = MerchantSaleQR(
            merchant_profile_id=merchant.id,
            merchant_user_id=merchant_user.id,
            sale_amount=sale_amount,
            currency=settings.WALLET_CURRENCY,
            status=SaleQRStatus.PENDING,
            expires_at=expires_at,
        )
        db.add(sale_qr)
        db.commit()
        db.refresh(sale_qr)

        qr_payload = WalletService._sale_qr_payload(
            sale_qr.token, sale_amount, merchant.business_name
        )
        return SaleQRCreateResponse(
            message="Sale QR created",
            token=sale_qr.token,
            qr_payload=qr_payload,
            sale_amount=sale_amount,
            estimated_cashback_total=total_cb,
            estimated_user_cashback=user_cb,
            estimated_company_fee=company_fee,
            cashback_percent=user_pct,
            company_fee_percent=company_pct,
            total_deduction_percent=user_pct + company_pct,
            expires_at=sale_qr.expires_at,
            status=sale_qr.status,
        )

    @staticmethod
    def preview_sale_qr(db: Session, token: str) -> SaleQRPreviewResponse:
        sale_qr = db.query(MerchantSaleQR).filter(MerchantSaleQR.token == token).first()
        if not sale_qr:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sale QR not found.")

        WalletService._expire_if_pending(db, sale_qr)

        merchant = WalletService._merchant_row(db, sale_qr.merchant_profile_id) or sale_qr.merchant_profile
        user_pct, company_pct = WalletService._cashback_rates(merchant)
        user_cb = WalletService._split_cashback(sale_qr.sale_amount, merchant)[1]
        return SaleQRPreviewResponse(
            message="Sale QR details",
            token=sale_qr.token,
            sale_amount=WalletService._money(sale_qr.sale_amount),
            merchant_business_name=merchant.business_name if merchant else "Merchant",
            status=sale_qr.status,
            expires_at=sale_qr.expires_at,
            estimated_user_cashback=user_cb,
            cashback_percent=user_pct,
            company_fee_percent=company_pct,
            total_deduction_percent=user_pct + company_pct,
        )

    @staticmethod
    def _assert_merchant_owns_sale_qr(sale_qr: MerchantSaleQR, merchant_user: User) -> None:
        if sale_qr.merchant_user_id == merchant_user.id:
            return
        profile = sale_qr.merchant_profile
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this sale QR.",
            )
        if profile.user_id == merchant_user.id or profile.onboarded_by_id == merchant_user.id:
            return
        if merchant_user.phone and (
            profile.phone == merchant_user.phone or profile.contact_number == merchant_user.phone
        ):
            return
        if merchant_user.email and profile.email:
            if profile.email.strip().lower() == merchant_user.email.strip().lower():
                return
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this sale QR.",
        )

    @staticmethod
    def get_merchant_sale_qr_status(
        db: Session, merchant_user: User, token: str
    ) -> SaleQRMerchantStatusResponse:
        sale_qr = db.query(MerchantSaleQR).filter(MerchantSaleQR.token == token).first()
        if not sale_qr:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sale QR not found.")

        WalletService._assert_merchant_owns_sale_qr(sale_qr, merchant_user)

        WalletService._expire_if_pending(db, sale_qr)
        now = datetime.now(timezone.utc)

        sale_amount = WalletService._money(sale_qr.sale_amount)
        merchant = WalletService._merchant_row(db, sale_qr.merchant_profile_id)
        user_pct, company_pct = WalletService._cashback_rates(merchant)
        total_cb, user_cb, company_fee = WalletService._split_cashback(sale_amount, merchant)
        business_name = merchant.business_name if merchant else "Merchant"

        expires_at = _as_utc(sale_qr.expires_at)
        seconds_left: Optional[int] = None
        if sale_qr.status == SaleQRStatus.PENDING and expires_at > now:
            seconds_left = max(0, int((expires_at - now).total_seconds()))

        is_redeemed = sale_qr.status == SaleQRStatus.REDEEMED
        is_expired = sale_qr.status == SaleQRStatus.EXPIRED
        is_pending = sale_qr.status == SaleQRStatus.PENDING

        merchant_wallet = WalletService.ensure_wallet_for_user(db, sale_qr.merchant_user_id)
        db.refresh(merchant_wallet)

        merchant_debit = total_cb if is_redeemed else None
        txn_group = sale_qr.wallet_transaction_group_id if is_redeemed else None

        if is_redeemed:
            message = "Cashback redeemed — transaction complete."
        elif is_expired:
            message = "Sale QR has expired. Generate a new QR."
        else:
            message = "Waiting for customer to scan and redeem."

        qr_payload = (
            WalletService._sale_qr_payload(sale_qr.token, sale_amount, business_name)
            if is_pending
            else None
        )

        return SaleQRMerchantStatusResponse(
            message=message,
            token=sale_qr.token,
            status=sale_qr.status,
            sale_amount=sale_amount,
            currency=sale_qr.currency or settings.WALLET_CURRENCY,
            merchant_business_name=business_name,
            expires_at=sale_qr.expires_at,
            redeemed_at=sale_qr.redeemed_at,
            is_redeemed=is_redeemed,
            is_expired=is_expired,
            is_pending=is_pending,
            seconds_until_expiry=seconds_left,
            estimated_cashback_total=total_cb,
            estimated_user_cashback=user_cb,
            estimated_company_fee=company_fee,
            cashback_percent=user_pct,
            company_fee_percent=company_pct,
            total_deduction_percent=user_pct + company_pct,
            merchant_debit=merchant_debit,
            transaction_group_id=txn_group,
            merchant_wallet_balance=WalletService._money(merchant_wallet.balance),
            qr_payload=qr_payload,
        )

    @staticmethod
    def redeem_sale_cashback(db: Session, customer: User, token: str) -> SaleRedeemResponse:
        sale_qr = (
            db.query(MerchantSaleQR)
            .filter(MerchantSaleQR.token == token)
            .with_for_update()
            .first()
        )
        if not sale_qr:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sale QR not found.")

        if WalletService._expire_if_pending(db, sale_qr):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Sale QR has expired.")
        now = datetime.now(timezone.utc)

        if sale_qr.status != SaleQRStatus.PENDING:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Sale QR is not redeemable (status={sale_qr.status.value}).",
            )

        if sale_qr.merchant_user_id == customer.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Merchant cannot redeem their own sale QR.",
            )

        sale_amount = WalletService._money(sale_qr.sale_amount)
        merchant = WalletService._merchant_row(db, sale_qr.merchant_profile_id)
        user_pct, company_pct = WalletService._cashback_rates(merchant)
        merchant_debit, user_cb, company_fee = WalletService._split_cashback(sale_amount, merchant)

        merchant_wallet = WalletService.ensure_wallet_for_user(db, sale_qr.merchant_user_id)
        user_wallet = WalletService.ensure_wallet_for_user(db, customer.id)
        company_wallet = WalletService.get_company_wallet(db)
        db.flush()

        group_id = str(uuid.uuid4())
        txn = WalletTransaction(
            group_id=group_id,
            transaction_type=WalletTransactionType.CASHBACK_REDEMPTION,
            amount=merchant_debit,
            currency=settings.WALLET_CURRENCY,
            description=f"Cashback redemption for sale QR {sale_qr.token}",
            initiated_by_user_id=customer.id,
            reference_id=sale_qr.token,
        )
        db.add(txn)
        db.flush()

        locked_merchant = WalletService._lock_wallet(db, merchant_wallet.id)
        locked_user = WalletService._lock_wallet(db, user_wallet.id)
        locked_company = WalletService._lock_wallet(db, company_wallet.id)

        WalletService._apply_ledger_line(
            db,
            txn,
            locked_merchant,
            WalletLedgerDirection.DEBIT,
            merchant_debit,
            counterparty_wallet_id=locked_user.id,
            note=f"{_percent_label(user_pct + company_pct)}% cashback on sale {sale_amount}",
        )
        WalletService._apply_ledger_line(
            db,
            txn,
            locked_user,
            WalletLedgerDirection.CREDIT,
            user_cb,
            counterparty_wallet_id=locked_merchant.id,
            note=f"{_percent_label(user_pct)}% user cashback on sale {sale_amount}",
        )
        WalletService._apply_ledger_line(
            db,
            txn,
            locked_company,
            WalletLedgerDirection.CREDIT,
            company_fee,
            counterparty_wallet_id=locked_merchant.id,
            note=f"{_percent_label(company_pct)}% platform fee on sale {sale_amount}",
        )

        sale_qr.status = SaleQRStatus.REDEEMED
        sale_qr.redeemed_by_user_id = customer.id
        sale_qr.redeemed_at = now
        sale_qr.wallet_transaction_group_id = group_id

        db.commit()
        db.refresh(locked_user)
        db.refresh(locked_merchant)

        from app.services.wallet_ws_manager import wallet_ws_manager

        wallet_ws_manager.publish_sale_qr_redeemed(
            merchant_user_id=sale_qr.merchant_user_id,
            payload={
                "token": sale_qr.token,
                "status": SaleQRStatus.REDEEMED.value,
                "transaction_group_id": group_id,
                "sale_amount": str(sale_amount),
                "merchant_debit": str(merchant_debit),
                "user_cashback": str(user_cb),
                "company_fee": str(company_fee),
                "cashback_percent": user_pct,
                "company_fee_percent": company_pct,
                "total_deduction_percent": user_pct + company_pct,
                "merchant_wallet_balance": str(WalletService._money(locked_merchant.balance)),
                "currency": settings.WALLET_CURRENCY,
                "redeemed_at": now.isoformat(),
                "merchant_profile_id": sale_qr.merchant_profile_id,
            },
        )

        return SaleRedeemResponse(
            message="Cashback redeemed to your wallet",
            transaction_group_id=group_id,
            sale_amount=sale_amount,
            user_cashback=user_cb,
            company_fee=company_fee,
            cashback_percent=user_pct,
            company_fee_percent=company_pct,
            merchant_debit=merchant_debit,
            user_wallet_balance=WalletService._money(locked_user.balance),
        )

    @staticmethod
    def admin_adjust_wallet(
        db: Session,
        admin_user: User,
        target_user_id: Optional[int],
        amount: Decimal,
        operation: str,
        note: Optional[str] = None,
        merchant_id: Optional[int] = None,
        claim_mode: bool = True,
    ) -> Tuple[Optional[WalletResponse], Optional[str], Optional[WalletTransactionType], Optional[int], Optional[str]]:
        amount = WalletService._money(amount)

        # Resolve target user if only merchant_id was provided
        if target_user_id is None and merchant_id is not None:
            merchant = db.query(MerchantProfile).filter(MerchantProfile.id == merchant_id).first()
            if not merchant:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Merchant with ID {merchant_id} not found.")
            if merchant.user_id:
                target_user_id = merchant.user_id
            else:
                m_phone = merchant.phone or merchant.contact_number
                if m_phone:
                    clean_p = m_phone.strip().replace(" ", "").replace("-", "")[-10:]
                    u = db.query(User).filter(User.phone.endswith(clean_p)).first()
                    if u:
                        target_user_id = u.id
                        merchant.user_id = u.id
                        db.commit()
            if not target_user_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Merchant '{merchant.business_name}' has no linked user account.")

        if not target_user_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Target user ID or Merchant ID is required.")

        target_wallet = WalletService.ensure_wallet_for_user(db, target_user_id)
        db.flush()

        # If credit and claim_mode is True, put in Redeem section
        if operation == "credit" and claim_mode:
            claim = WalletRewardClaim(
                recipient_user_id=target_user_id,
                merchant_profile_id=merchant_id,
                amount=amount,
                currency=settings.WALLET_CURRENCY,
                title="Admin Cash Grant",
                note=note or "Promotional credit from Platform Admin (Redeem to Wallet)",
                status=RewardClaimStatus.PENDING,
                created_by_admin_id=admin_user.id,
            )
            db.add(claim)
            db.commit()
            db.refresh(claim)
            return WalletService.wallet_to_response(target_wallet), None, None, claim.id, "PENDING"

        # Otherwise direct credit or debit
        group_id = str(uuid.uuid4())
        txn_type = (
            WalletTransactionType.ADMIN_CREDIT
            if operation == "credit"
            else WalletTransactionType.ADMIN_DEBIT
        )
        txn = WalletTransaction(
            group_id=group_id,
            transaction_type=txn_type,
            amount=amount,
            currency=settings.WALLET_CURRENCY,
            description=note or f"Admin {operation} by user {admin_user.id}",
            initiated_by_user_id=admin_user.id,
            reference_id=str(target_user_id),
        )
        db.add(txn)
        db.flush()

        locked = WalletService._lock_wallet(db, target_wallet.id)
        direction = (
            WalletLedgerDirection.CREDIT
            if operation == "credit"
            else WalletLedgerDirection.DEBIT
        )
        WalletService._apply_ledger_line(
            db,
            txn,
            locked,
            direction,
            amount,
            note=note or f"Admin {operation}",
        )

        db.commit()
        db.refresh(locked)
        return WalletService.wallet_to_response(locked), group_id, txn_type, None, None

    @staticmethod
    def list_pending_rewards(db: Session, user: User) -> List[WalletRewardClaim]:
        from app.db.models.merchant import MerchantProfile
        from sqlalchemy import or_

        filters = [WalletRewardClaim.recipient_user_id == user.id]
        clean_p = (user.phone or "").strip()[-10:] if user.phone else None
        
        # Also include any claims targeting merchant profiles owned by or linked to this user/phone
        merchant_q = db.query(MerchantProfile.id)
        if clean_p:
            merchant_q = merchant_q.filter(
                or_(
                    MerchantProfile.user_id == user.id,
                    MerchantProfile.phone.like(f"%{clean_p}%")
                )
            )
        else:
            merchant_q = merchant_q.filter(MerchantProfile.user_id == user.id)

        merchant_ids = [m[0] for m in merchant_q.all()]
        if merchant_ids:
            filters.append(WalletRewardClaim.merchant_profile_id.in_(merchant_ids))

        q = db.query(WalletRewardClaim).filter(
            or_(*filters),
            WalletRewardClaim.status == RewardClaimStatus.PENDING,
        ).order_by(WalletRewardClaim.created_at.desc())
        return q.all()

    @staticmethod
    def redeem_reward_claim(
        db: Session,
        user: User,
        claim_id: int,
    ) -> Tuple[WalletResponse, WalletRewardClaim, str]:
        from app.db.models.merchant import MerchantProfile
        from sqlalchemy import or_

        claim = db.query(WalletRewardClaim).filter(WalletRewardClaim.id == claim_id).first()
        if not claim:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reward claim not found.")

        is_owner = (claim.recipient_user_id == user.id)
        if not is_owner and claim.merchant_profile_id:
            clean_p = (user.phone or "").strip()[-10:] if user.phone else None
            mp_filter = [MerchantProfile.user_id == user.id]
            if clean_p:
                mp_filter.append(MerchantProfile.phone.like(f"%{clean_p}%"))
            mp = db.query(MerchantProfile).filter(
                MerchantProfile.id == claim.merchant_profile_id,
                or_(*mp_filter)
            ).first()
            if mp:
                is_owner = True

        if not is_owner:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This reward does not belong to you.")
        if claim.status != RewardClaimStatus.PENDING:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"This reward has already been {claim.status.lower()}.")

        wallet = WalletService.ensure_wallet_for_user(db, user.id)
        db.flush()

        group_id = str(uuid.uuid4())
        txn = WalletTransaction(
            group_id=group_id,
            transaction_type=WalletTransactionType.ADMIN_CREDIT,
            amount=claim.amount,
            currency=claim.currency,
            description=f"Redeemed: {claim.title} ({claim.note or ''})".strip(),
            initiated_by_user_id=user.id,
            reference_id=str(claim.id),
        )
        db.add(txn)
        db.flush()

        locked = WalletService._lock_wallet(db, wallet.id)
        WalletService._apply_ledger_line(
            db,
            txn,
            locked,
            WalletLedgerDirection.CREDIT,
            WalletService._money(claim.amount),
            note=f"Redeemed reward claim #{claim.id}",
        )

        claim.status = RewardClaimStatus.REDEEMED
        claim.redeemed_at = datetime.now(timezone.utc)
        claim.wallet_transaction_group_id = group_id

        db.commit()
        db.refresh(locked)
        db.refresh(claim)
        return WalletService.wallet_to_response(locked), claim, group_id

