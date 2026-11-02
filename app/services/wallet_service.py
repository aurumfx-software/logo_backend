from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import List, Optional, Tuple
import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models.merchant import MerchantProfile
from app.db.models.user import User
from app.db.models.wallet import (
    MerchantSaleQR,
    SaleQRStatus,
    Wallet,
    WalletLedgerDirection,
    WalletLedgerEntry,
    WalletTransaction,
    WalletTransactionType,
    WalletType,
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
            .filter(
                WalletLedgerEntry.wallet_id == company.id,
                WalletLedgerEntry.direction == WalletLedgerDirection.CREDIT,
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
        if not payload.to_user_id and not payload.to_user_code and not payload.to_email:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Provide to_user_id, to_user_code, or to_email.",
            )

        user = None
        if payload.to_user_id:
            user = db.query(User).filter(User.id == payload.to_user_id).first()
        elif payload.to_user_code:
            user = db.query(User).filter(User.user_code == payload.to_user_code.strip()).first()
        elif payload.to_email:
            user = db.query(User).filter(User.email == payload.to_email.strip().lower()).first()

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
            expires_at=sale_qr.expires_at,
            status=sale_qr.status,
        )

    @staticmethod
    def preview_sale_qr(db: Session, token: str) -> SaleQRPreviewResponse:
        sale_qr = db.query(MerchantSaleQR).filter(MerchantSaleQR.token == token).first()
        if not sale_qr:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sale QR not found.")

        WalletService._expire_if_pending(db, sale_qr)

        merchant = WalletService._merchant_row(db, sale_qr.merchant_profile_id)
        user_pct, _company_pct = WalletService._cashback_rates(merchant)
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
        target_user_id: int,
        amount: Decimal,
        operation: str,
        note: Optional[str] = None,
    ) -> Tuple[WalletResponse, str, WalletTransactionType]:
        amount = WalletService._money(amount)
        target_wallet = WalletService.ensure_wallet_for_user(db, target_user_id)
        db.flush()

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
        return WalletService.wallet_to_response(locked), group_id, txn_type
