import enum
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.db.database import Base


class WalletType(str, enum.Enum):
    USER = "USER"
    COMPANY = "COMPANY"


class SaleQRStatus(str, enum.Enum):
    PENDING = "PENDING"
    REDEEMED = "REDEEMED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class WalletTransactionType(str, enum.Enum):
    P2P_TRANSFER = "P2P_TRANSFER"
    CASHBACK_REDEMPTION = "CASHBACK_REDEMPTION"
    ADMIN_CREDIT = "ADMIN_CREDIT"
    ADMIN_DEBIT = "ADMIN_DEBIT"


class WalletLedgerDirection(str, enum.Enum):
    CREDIT = "CREDIT"
    DEBIT = "DEBIT"


class Wallet(Base):
    __tablename__ = "wallets"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_wallets_user_id"),
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    wallet_type = Column(
        Enum(WalletType, name="wallet_type", native_enum=False),
        default=WalletType.USER,
        nullable=False,
        index=True,
    )
    currency = Column(String(3), default="INR", nullable=False)
    balance = Column(Numeric(18, 2), default=Decimal("0.00"), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = relationship("User", backref="wallet")
    ledger_entries = relationship(
        "WalletLedgerEntry",
        back_populates="wallet",
        foreign_keys="WalletLedgerEntry.wallet_id",
    )


class WalletTransaction(Base):
    """Logical wallet operation (may include multiple ledger lines)."""

    __tablename__ = "wallet_transactions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    group_id = Column(String(36), default=lambda: str(uuid.uuid4()), nullable=False, index=True)
    transaction_type = Column(
        Enum(WalletTransactionType, name="wallet_transaction_type", native_enum=False),
        nullable=False,
        index=True,
    )
    amount = Column(Numeric(18, 2), nullable=False)
    currency = Column(String(3), default="INR", nullable=False)
    description = Column(Text, nullable=True)
    initiated_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reference_id = Column(String(64), nullable=True, index=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    initiated_by = relationship("User", foreign_keys=[initiated_by_user_id])
    ledger_entries = relationship("WalletLedgerEntry", back_populates="transaction")


class WalletLedgerEntry(Base):
    __tablename__ = "wallet_ledger_entries"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    transaction_id = Column(
        Integer,
        ForeignKey("wallet_transactions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    wallet_id = Column(Integer, ForeignKey("wallets.id", ondelete="CASCADE"), nullable=False, index=True)
    direction = Column(
        Enum(WalletLedgerDirection, name="wallet_ledger_direction", native_enum=False),
        nullable=False,
    )
    amount = Column(Numeric(18, 2), nullable=False)
    balance_after = Column(Numeric(18, 2), nullable=False)
    counterparty_wallet_id = Column(Integer, ForeignKey("wallets.id", ondelete="SET NULL"), nullable=True)
    note = Column(String(500), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    transaction = relationship("WalletTransaction", back_populates="ledger_entries")
    wallet = relationship("Wallet", back_populates="ledger_entries", foreign_keys=[wallet_id])
    counterparty_wallet = relationship("Wallet", foreign_keys=[counterparty_wallet_id])


class MerchantSaleQR(Base):
    __tablename__ = "merchant_sale_qrs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    token = Column(String(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False, index=True)
    merchant_profile_id = Column(
        Integer,
        ForeignKey("merchant_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    merchant_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    sale_amount = Column(Numeric(18, 2), nullable=False)
    currency = Column(String(3), default="INR", nullable=False)
    status = Column(
        Enum(SaleQRStatus, name="sale_qr_status", native_enum=False),
        default=SaleQRStatus.PENDING,
        nullable=False,
        index=True,
    )
    redeemed_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    wallet_transaction_group_id = Column(String(36), nullable=True, index=True)

    cashback_percent = Column(Numeric(5, 2), default=3.0, nullable=True)
    company_fee_percent = Column(Numeric(5, 2), default=2.0, nullable=True)
    total_deduction_percent = Column(Numeric(5, 2), default=5.0, nullable=True)

    user_cashback_amount = Column(Numeric(18, 2), nullable=True)
    company_fee_amount = Column(Numeric(18, 2), nullable=True)
    merchant_debit_amount = Column(Numeric(18, 2), nullable=True)

    expires_at = Column(DateTime(timezone=True), nullable=False)
    redeemed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    merchant_profile = relationship("MerchantProfile", backref="sale_qrs")
    merchant_user = relationship("User", foreign_keys=[merchant_user_id])
    redeemed_by = relationship("User", foreign_keys=[redeemed_by_user_id])


class CompanyPlatformWalletLedger(Base):
    """Dedicated table for Company Platform Wallet commissions (2%) and audit tracking."""

    __tablename__ = "company_platform_wallet_ledger"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    transaction_type = Column(String(50), default="PLATFORM_FEE", nullable=False, index=True)
    direction = Column(String(10), default="CREDIT", nullable=False)

    # Financial amounts
    amount = Column(Numeric(18, 2), nullable=False)  # 2% platform fee
    currency = Column(String(3), default="INR", nullable=False)
    balance_after = Column(Numeric(18, 2), nullable=True)

    # Sale & QR Context
    sale_qr_id = Column(Integer, ForeignKey("merchant_sale_qrs.id", ondelete="SET NULL"), nullable=True, index=True)
    qr_token = Column(String(36), nullable=True, index=True)
    sale_amount = Column(Numeric(18, 2), nullable=True)  # Gross bill amount
    platform_fee_percent = Column(Numeric(5, 2), nullable=True)  # e.g. 2.00%
    customer_cashback_amount = Column(Numeric(18, 2), nullable=True)
    merchant_deducted_amount = Column(Numeric(18, 2), nullable=True)

    # Store / Counterparty Info
    merchant_id = Column(Integer, ForeignKey("merchant_profiles.id", ondelete="SET NULL"), nullable=True, index=True)
    merchant_name = Column(String(255), nullable=True)
    customer_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    customer_name = Column(String(255), nullable=True)
    customer_phone = Column(String(30), nullable=True)

    # Audit reference & Notes
    reference_id = Column(String(64), nullable=True, index=True)
    note = Column(String(500), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    sale_qr = relationship("MerchantSaleQR", foreign_keys=[sale_qr_id])
    merchant = relationship("MerchantProfile", foreign_keys=[merchant_id])
    customer = relationship("User", foreign_keys=[customer_user_id])

