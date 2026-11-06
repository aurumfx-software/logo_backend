from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import List, Optional, Tuple
import uuid

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_
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
    WithdrawalStatus,
)
from app.schemas.wallet import (
    AdminSendFundsRequest,
    AdminSendFundsResponse,
    AdminWalletSummaryResponse,
    AdminWalletTransactionItem,
    AdminWalletTransactionsResponse,
    MerchantTopupOrderRequest,
    MerchantTopupOrderResponse,
    MerchantTopupVerifyRequest,
    MerchantTopupVerifyResponse,
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
    WalletWithdrawalStatusResponse,
    AdminPlatformCashItem,
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
    def _serialize_admin_transaction(db: Session, txn: WalletTransaction) -> AdminWalletTransactionResponse:
        initiator = txn.initiated_by
        initiator_profile = (
            db.query(MerchantProfile).filter_by(user_id=initiator.id).first() if initiator else None
        )
        provider_status = provider_id = failure_reason = bank_name = bank_last4 = bank_ifsc = None
        if txn.transaction_type == WalletTransactionType.WALLET_TOPUP:
            topup = db.query(WalletTopupOrder).filter_by(wallet_transaction_group_id=txn.group_id).first()
            if topup:
                provider_status = topup.status.value
                provider_id = topup.razorpay_payment_id or topup.razorpay_order_id
        elif txn.transaction_type in (
            WalletTransactionType.WALLET_WITHDRAWAL,
            WalletTransactionType.WITHDRAWAL,
        ):
            withdrawal = (
                db.query(WalletWithdrawal)
                .filter(WalletWithdrawal.transaction_group_id == txn.group_id)
                .first()
            )
            if withdrawal:
                provider_status = (
                    withdrawal.status.value if hasattr(withdrawal.status, "value") else str(withdrawal.status)
                )
                provider_id = withdrawal.payout_mode
                failure_reason = withdrawal.admin_note
                bank_name = withdrawal.account_holder_name
                bank_last4 = (withdrawal.account_number or "")[-4:] or None
                bank_ifsc = withdrawal.ifsc
        lines = []
        for row in sorted(txn.ledger_entries, key=lambda item: item.id):
            wallet = row.wallet
            user = wallet.user
            cp_wallet = row.counterparty_wallet
            cp_user = cp_wallet.user if cp_wallet else None
            profile = db.query(MerchantProfile).filter_by(user_id=user.id).first() if user else None
            cp_profile = db.query(MerchantProfile).filter_by(user_id=cp_user.id).first() if cp_user else None
            lines.append(
                AdminWalletLedgerLineResponse(
                    id=row.id,
                    direction=row.direction.value,
                    amount=WalletService._money(row.amount),
                    balance_after=WalletService._money(row.balance_after),
                    wallet_id=wallet.id,
                    wallet_type=wallet.wallet_type.value,
                    user_id=user.id if user else None,
                    user_name=(profile.business_name if profile else user.name) if user else None,
                    user_email=user.email if user else None,
                    counterparty_wallet_id=cp_wallet.id if cp_wallet else None,
                    counterparty_user_id=cp_user.id if cp_user else None,
                    counterparty_name=(
                        (cp_profile.business_name if cp_profile else cp_user.name)
                        if cp_user
                        else ("Admin wallet" if cp_wallet and cp_wallet.wallet_type == WalletType.COMPANY else None)
                    ),
                    counterparty_email=cp_user.email if cp_user else None,
                    note=row.note,
                    created_at=row.created_at,
                )
            )
        return AdminWalletTransactionResponse(
            id=txn.id,
            transaction_group_id=txn.group_id,
            transaction_type=txn.transaction_type.value,
            amount=WalletService._money(txn.amount),
            currency=txn.currency,
            description=txn.description,
            initiated_by_user_id=initiator.id if initiator else None,
            initiated_by_name=(
                (initiator_profile.business_name if initiator_profile else initiator.name) if initiator else None
            ),
            initiated_by_email=initiator.email if initiator else None,
            reference_id=txn.reference_id,
            provider_status=provider_status,
            provider_id=provider_id,
            failure_reason=failure_reason,
            bank_account_holder_name=bank_name,
            bank_account_last4=bank_last4,
            bank_ifsc=bank_ifsc,
            created_at=txn.created_at,
            ledger_entries=lines,
        )

    @staticmethod
    def admin_list_transactions(
        db: Session,
        page: int,
        page_size: int,
        transaction_type: Optional[str] = None,
    ):
        query = db.query(WalletTransaction)
        if transaction_type and transaction_type.strip().lower() not in ("all", ""):
            type_norm = transaction_type.strip().upper().replace("-", "_").replace(" ", "_")
            try:
                txn_type = WalletTransactionType(type_norm)
                query = query.filter(WalletTransaction.transaction_type == txn_type)
            except ValueError:
                from sqlalchemy import false

                query = query.filter(false())
        total = query.count()
        txns = (
            query.order_by(WalletTransaction.created_at.desc(), WalletTransaction.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        data = [WalletService._serialize_admin_transaction(db, txn) for txn in txns]
        return data, total

    @staticmethod
    def platform_cash_totals(db: Session):
        """Merchant top-ups received, user withdrawals deducted, and the net balance."""
        merchant_user_ids = db.query(MerchantProfile.user_id)
        received_filter = and_(
            WalletTransaction.transaction_type == WalletTransactionType.WALLET_TOPUP,
            WalletTransaction.initiated_by_user_id.in_(merchant_user_ids),
        )
        deducted_filter = WalletTransaction.transaction_type.in_(
            [WalletTransactionType.WITHDRAWAL, WalletTransactionType.WALLET_WITHDRAWAL]
        )
        total_received = WalletService._sum_money(
            db.query(func.coalesce(func.sum(WalletTransaction.amount), 0))
            .filter(received_filter)
            .scalar()
        )
        total_deducted = WalletService._sum_money(
            db.query(func.coalesce(func.sum(WalletTransaction.amount), 0))
            .filter(deducted_filter)
            .scalar()
        )
        real_balance = WalletService._money(total_received - total_deducted)
        return received_filter, deducted_filter, total_received, total_deducted, real_balance

    @staticmethod
    def list_admin_platform_cash(db: Session, page: int, page_size: int):
        """Merchant wallet top-ups (money in) and user withdrawals (money out)."""
        received_filter, deducted_filter, total_received, total_deducted, real_balance = (
            WalletService.platform_cash_totals(db)
        )
        query = db.query(WalletTransaction).filter(or_(received_filter, deducted_filter))
        total = query.count()
        rows = (
            query.order_by(WalletTransaction.created_at.desc(), WalletTransaction.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        items = []
        for txn in rows:
            user = txn.initiated_by
            profile = db.query(MerchantProfile).filter_by(user_id=user.id).first() if user else None
            is_topup = txn.transaction_type == WalletTransactionType.WALLET_TOPUP
            items.append(
                AdminPlatformCashItem(
                    id=txn.id,
                    transaction_group_id=txn.group_id,
                    movement="RECEIVED" if is_topup else "DEDUCTED",
                    transaction_type=txn.transaction_type.value,
                    amount=WalletService._money(txn.amount),
                    party_name=(profile.business_name if profile else user.name) if user else None,
                    party_email=user.email if user else None,
                    party_phone=user.phone if user else None,
                    party_role="merchant" if profile else "user",
                    description=txn.description,
                    created_at=txn.created_at,
                )
            )
        return items, total, total_received, total_deducted, real_balance

    @staticmethod
    def get_admin_transaction(db: Session, transaction_id: int) -> AdminWalletTransactionResponse:
        txn = db.query(WalletTransaction).filter(WalletTransaction.id == transaction_id).first()
        if not txn:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Transaction not found.",
            )
        return WalletService._serialize_admin_transaction(db, txn)

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
        _, _, total_received, total_deducted, real_balance = WalletService.platform_cash_totals(db)
        return PlatformWalletResponse(
            currency=company.currency or settings.WALLET_CURRENCY,
            balance=WalletService._money(company.balance),
            total_received=total_received,
            total_deducted=total_deducted,
            real_balance=real_balance,
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
        claim_mode: bool = False,
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

    @staticmethod
    def get_admin_wallet_summary(db: Session) -> AdminWalletSummaryResponse:
        company_wallet = WalletService.get_company_wallet(db)
        company_balance = WalletService._money(company_wallet.balance)

        total_user_balance = (
            db.query(func.coalesce(func.sum(Wallet.balance), 0))
            .filter(Wallet.wallet_type == WalletType.USER, Wallet.is_active == True)
            .scalar()
        )
        total_wallet_count = (
            db.query(func.count(Wallet.id))
            .filter(Wallet.wallet_type == WalletType.USER, Wallet.is_active == True)
            .scalar()
        )

        wallets_balance = WalletService._money(Decimal(str(total_user_balance or 0)))
        wallet_count = int(total_wallet_count or 0)
        _, _, total_received, total_deducted, real_balance = WalletService.platform_cash_totals(db)

        return AdminWalletSummaryResponse(
            success=True,
            company_balance=company_balance,
            total_received=total_received,
            total_deducted=total_deducted,
            real_balance=real_balance,
            total_active_wallets_balance=wallets_balance,
            total_balance_across_active_wallets=wallets_balance,
            total_wallet_count=wallet_count,
            total_wallets_count=wallet_count,
            currency="INR",
        )

    @staticmethod
    def list_admin_wallet_transactions(
        db: Session, page: int = 1, page_size: int = 20
    ) -> AdminWalletTransactionsResponse:
        page = max(1, page)
        page_size = max(1, min(page_size, 100))

        company = WalletService.get_company_wallet(db)

        # Admin only needs company wallet commission credits & transactions
        query = (
            db.query(WalletLedgerEntry, WalletTransaction)
            .join(WalletTransaction, WalletLedgerEntry.transaction_id == WalletTransaction.id)
            .filter(WalletLedgerEntry.wallet_id == company.id)
            .order_by(WalletLedgerEntry.id.desc())
        )

        total = query.count()
        total_pages = max(1, (total + page_size - 1) // page_size)
        rows = query.offset((page - 1) * page_size).limit(page_size).all()

        items = []
        for entry, txn in rows:
            customer_name = None
            customer_phone = None
            customer_email = None
            customer_details = None

            merchant_name = None
            merchant_city = None
            merchant_details = None

            # 1. Resolve customer & merchant from Sale QR transaction group
            qr = None
            if txn and txn.group_id:
                qr = db.query(MerchantSaleQR).filter(
                    MerchantSaleQR.wallet_transaction_group_id == txn.group_id
                ).first()

            if qr:
                if qr.redeemed_by_user_id:
                    cust = db.query(User).filter(User.id == qr.redeemed_by_user_id).first()
                    if cust:
                        customer_name = cust.name or cust.email or f"User #{cust.id}"
                        customer_phone = cust.phone
                        customer_email = cust.email
                        contact = customer_phone or customer_email
                        customer_details = f"{customer_name} ({contact})" if contact else customer_name

                if qr.merchant_profile_id:
                    merch = db.query(MerchantProfile).filter(
                        MerchantProfile.id == qr.merchant_profile_id
                    ).first()
                    if merch:
                        merchant_name = merch.business_name or f"Merchant #{merch.id}"
                        merchant_city = merch.city
                        merchant_details = f"{merchant_name} ({merch.city})" if merch.city else merchant_name

            # 2. If not found via QR, resolve from counterparty wallet or reference
            if not customer_name and not merchant_name:
                cp_id = entry.counterparty_wallet_id
                if cp_id:
                    cp_wallet = db.query(Wallet).filter(Wallet.id == cp_id).first()
                    if cp_wallet and cp_wallet.user_id:
                        m = db.query(MerchantProfile).filter(
                            MerchantProfile.user_id == cp_wallet.user_id
                        ).first()
                        if m:
                            merchant_name = m.business_name or f"Merchant #{m.id}"
                            merchant_city = m.city
                            merchant_details = f"{merchant_name} ({m.city})" if m.city else merchant_name
                        else:
                            u = db.query(User).filter(User.id == cp_wallet.user_id).first()
                            if u:
                                customer_name = u.name or u.email or f"User #{u.id}"
                                customer_phone = u.phone
                                customer_email = u.email
                                contact = customer_phone or customer_email
                                customer_details = f"{customer_name} ({contact})" if contact else customer_name

            if not customer_name and not merchant_name and txn and txn.reference_id:
                try:
                    ref_id = int(str(txn.reference_id).strip())
                    m = db.query(MerchantProfile).filter(
                        or_(MerchantProfile.id == ref_id, MerchantProfile.user_id == ref_id)
                    ).first()
                    if m:
                        merchant_name = m.business_name
                        merchant_city = m.city
                        merchant_details = f"{m.business_name} ({m.city})" if m.city else m.business_name
                    else:
                        u = db.query(User).filter(User.id == ref_id).first()
                        if u:
                            customer_name = u.name or u.email
                            customer_phone = u.phone
                            customer_email = u.email
                            contact = customer_phone or customer_email
                            customer_details = f"{customer_name} ({contact})" if contact else customer_name
                except ValueError:
                    pass

            txn_type_str = (
                txn.transaction_type.value
                if txn and hasattr(txn.transaction_type, "value")
                else (str(txn.transaction_type) if txn else "PLATFORM_FEE")
            )
            dir_str = (
                entry.direction.value
                if hasattr(entry.direction, "value")
                else str(entry.direction)
            )

            # Determine primary recipient label for backwards compatibility
            recipient_label = merchant_name or customer_name or "Platform Company"
            recipient_type = "merchant" if merchant_name else ("user" if customer_name else "company")

            items.append(
                AdminWalletTransactionItem(
                    id=entry.id,
                    recipient=recipient_label,
                    recipient_type=recipient_type,
                    customer_name=customer_name,
                    customer_phone=customer_phone,
                    customer_email=customer_email,
                    customer_details=customer_details,
                    merchant_name=merchant_name,
                    merchant_city=merchant_city,
                    merchant_details=merchant_details,
                    transaction_type=txn_type_str,
                    direction=dir_str,
                    amount=WalletService._money(entry.amount),
                    balance_after=WalletService._money(entry.balance_after),
                    note=entry.note or (txn.description if txn else ""),
                    date=entry.created_at,
                )
            )

        return AdminWalletTransactionsResponse(
            success=True,
            data=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

    @staticmethod
    def admin_send_funds(
        db: Session, admin_user: User, payload: AdminSendFundsRequest
    ) -> AdminSendFundsResponse:
        amount = WalletService._money(payload.amount)
        if amount <= Decimal("0.00"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Amount must be greater than zero.",
            )

        recip_type = (payload.recipient_type or "").strip().lower()
        if recip_type not in ("user", "merchant"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="recipient_type must be either 'user' or 'merchant'.",
            )

        target_user = None
        merchant_name = None

        if recip_type == "merchant":
            m = None
            if payload.user_id is not None and str(payload.user_id).strip():
                raw_id_str = str(payload.user_id).strip()
                try:
                    num_id = int(raw_id_str)
                    m = db.query(MerchantProfile).filter(MerchantProfile.id == num_id).first()
                    if not m:
                        m = db.query(MerchantProfile).filter(MerchantProfile.user_id == num_id).first()
                except ValueError:
                    pass

            if not m and payload.email:
                clean_email = payload.email.strip().lower()
                m = db.query(MerchantProfile).filter(func.lower(MerchantProfile.email) == clean_email).first()

            if m:
                merchant_name = m.business_name
                if m.user_id:
                    target_user = db.query(User).filter(User.id == m.user_id).first()
                if not target_user:
                    m_phone = m.phone or m.contact_number
                    if m_phone:
                        clean_p = m_phone.strip()[-10:]
                        target_user = db.query(User).filter(User.phone.like(f"%{clean_p}%")).first()
                        if target_user:
                            m.user_id = target_user.id
                            db.flush()

            if not target_user:
                if payload.email:
                    target_user = db.query(User).filter(func.lower(User.email) == payload.email.strip().lower()).first()
                elif payload.user_id is not None:
                    try:
                        target_user = db.query(User).filter(User.id == int(str(payload.user_id).strip())).first()
                    except ValueError:
                        pass

            if not target_user and not m:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Merchant '{payload.email or payload.user_id}' not found.",
                )
        else:
            if payload.email:
                clean_email = payload.email.strip().lower()
                target_user = db.query(User).filter(func.lower(User.email) == clean_email).first()
            elif payload.user_id is not None:
                try:
                    target_user = db.query(User).filter(User.id == int(str(payload.user_id).strip())).first()
                except ValueError:
                    pass

            if not target_user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"User '{payload.email or payload.user_id}' not found.",
                )

        target_wallet = WalletService.ensure_wallet_for_user(db, target_user.id)
        db.flush()

        group_id = str(uuid.uuid4())
        txn = WalletTransaction(
            group_id=group_id,
            transaction_type=WalletTransactionType.ADMIN_CREDIT,
            amount=amount,
            currency=settings.WALLET_CURRENCY,
            description=payload.note or f"Admin funds transfer to {merchant_name or target_user.name or target_user.email}",
            initiated_by_user_id=admin_user.id,
            reference_id=str(target_user.id),
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
            note=payload.note or f"Admin transfer from platform",
        )

        db.commit()
        db.refresh(locked)

        recipient_display = merchant_name or target_user.name or target_user.email or f"ID #{target_user.id}"
        return AdminSendFundsResponse(
            success=True,
            message=f"Successfully sent ₹{amount} to {recipient_display}.",
            recipient=recipient_display,
            recipient_type=recip_type,
            amount=amount,
            wallet_balance=WalletService._money(locked.balance),
            transaction_group_id=group_id,
        )

    @staticmethod
    def create_merchant_topup_order(
        db: Session, user: User, payload: MerchantTopupOrderRequest
    ) -> MerchantTopupOrderResponse:
        from app.services.wallet_topup_service import WalletTopupService
        from app.schemas.wallet_payment import WalletTopupCreateRequest

        topup_req = WalletTopupCreateRequest(
            amount=payload.amount,
            merchant_profile_id=payload.merchant_profile_id,
        )
        res = WalletTopupService.create_razorpay_topup_order(db=db, user=user, payload=topup_req)
        return MerchantTopupOrderResponse(
            success=True,
            order_id=res.razorpay_order_id,
            razorpay_order_id=res.razorpay_order_id,
            amount=res.amount,
            amount_paise=res.amount_paise,
            currency=res.currency,
            key_id=res.razorpay_key_id,
            topup_id=res.topup_id,
            merchant_profile_id=res.merchant_profile_id,
        )

    @staticmethod
    def verify_merchant_topup(
        db: Session, user: User, payload: MerchantTopupVerifyRequest
    ) -> MerchantTopupVerifyResponse:
        from app.services.wallet_topup_service import WalletTopupService
        from app.schemas.wallet_payment import RazorpayTopupVerifyRequest

        order_id = payload.order_id or payload.razorpay_order_id
        payment_id = payload.payment_id or payload.razorpay_payment_id
        sig = payload.signature or payload.razorpay_signature

        if not order_id or not payment_id or not sig:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="order_id, payment_id, and signature are required.",
            )

        verify_req = RazorpayTopupVerifyRequest(
            razorpay_order_id=order_id.strip(),
            razorpay_payment_id=payment_id.strip(),
            razorpay_signature=sig.strip(),
        )
        res = WalletTopupService.verify_and_credit(db=db, user=user, payload=verify_req)
        return MerchantTopupVerifyResponse(
            success=True,
            message="Payment verified and wallet credited successfully.",
            wallet_balance=res.wallet_balance,
            transaction_group_id=res.transaction_group_id,
        )

    @staticmethod
    def create_wallet_withdrawal(
        db: Session, user: User, payload: WalletWithdrawalRequest
    ) -> WalletWithdrawalResponse:
        WalletWithdrawal.__table__.create(bind=db.get_bind(), checkfirst=True)

        amount = WalletService._money(payload.amount)
        if amount <= Decimal("0.00"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Withdrawal amount must be greater than zero.",
            )

        wallet = WalletService.ensure_wallet_for_user(db, user.id)
        locked = WalletService._lock_wallet(db, wallet.id)

        if locked.balance < amount:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Insufficient wallet balance. Available: ₹{locked.balance:.2f}, Requested: ₹{amount:.2f}",
            )

        group_id = str(uuid.uuid4())
        txn = WalletTransaction(
            group_id=group_id,
            transaction_type=WalletTransactionType.WITHDRAWAL,
            amount=amount,
            currency=settings.WALLET_CURRENCY,
            description=f"Withdrawal to bank account {payload.account_number[-4:]} ({payload.ifsc}) via {payload.payout_mode or 'IMPS'}",
            initiated_by_user_id=user.id,
            reference_id=payload.account_number[-4:],
        )
        db.add(txn)
        db.flush()

        WalletService._apply_ledger_line(
            db,
            txn,
            locked,
            WalletLedgerDirection.DEBIT,
            amount,
            note=f"Bank withdrawal to {payload.account_holder_name} A/C ending {payload.account_number[-4:]}",
        )

        masked_acc = ("X" * max(0, len(payload.account_number) - 4)) + payload.account_number[-4:]
        withdrawal = WalletWithdrawal(
            transaction_group_id=group_id,
            user_id=user.id,
            wallet_id=locked.id,
            amount=amount,
            currency=settings.WALLET_CURRENCY,
            account_holder_name=payload.account_holder_name.strip(),
            account_number=masked_acc,
            ifsc=payload.ifsc.strip().upper(),
            payout_mode=(payload.payout_mode or "IMPS").strip().upper(),
            status=WithdrawalStatus.PENDING,
        )
        db.add(withdrawal)
        db.commit()
        db.refresh(locked)
        db.refresh(withdrawal)

        return WalletWithdrawalResponse(
            success=True,
            message="Withdrawal request submitted successfully. Funds will be transferred to your bank account.",
            transaction_group_id=group_id,
            amount=amount,
            account_holder_name=withdrawal.account_holder_name,
            account_number_masked=withdrawal.account_number,
            ifsc=withdrawal.ifsc,
            payout_mode=withdrawal.payout_mode,
            status=withdrawal.status.value if hasattr(withdrawal.status, "value") else str(withdrawal.status),
            wallet_balance=WalletService._money(locked.balance),
            created_at=withdrawal.created_at,
        )

    @staticmethod
    def get_wallet_withdrawal_status(
        db: Session, user: User, transaction_group_id: str
    ) -> WalletWithdrawalStatusResponse:
        WalletWithdrawal.__table__.create(bind=db.get_bind(), checkfirst=True)
        w = db.query(WalletWithdrawal).filter(
            WalletWithdrawal.transaction_group_id == transaction_group_id.strip()
        ).first()

        if not w:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Withdrawal '{transaction_group_id}' not found.",
            )

        user_role_str = getattr(user.role, "value", str(user.role)).upper()
        if w.user_id != user.id and user_role_str not in ("ADMIN", "SUPER_ADMIN"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to view this withdrawal.",
            )

        return WalletWithdrawalStatusResponse(
            success=True,
            transaction_group_id=w.transaction_group_id,
            status=w.status.value if hasattr(w.status, "value") else str(w.status),
            amount=WalletService._money(w.amount),
            account_holder_name=w.account_holder_name,
            account_number_masked=w.account_number,
            ifsc=w.ifsc,
            payout_mode=w.payout_mode,
            created_at=w.created_at,
        )



