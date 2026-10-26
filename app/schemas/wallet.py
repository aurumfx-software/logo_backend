from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.models.wallet import SaleQRStatus, WalletTransactionType


class WalletResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: Optional[int] = None
    wallet_type: str
    currency: str
    balance: Decimal
    is_active: bool


class WalletLedgerEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    direction: str
    amount: Decimal
    balance_after: Decimal
    note: Optional[str] = None
    counterparty_wallet_id: Optional[int] = None
    created_at: datetime
    transaction_type: Optional[str] = None
    transaction_group_id: Optional[str] = None


class WalletTransactionListResponse(BaseModel):
    success: bool = True
    message: str = "Transactions retrieved"
    data: List[WalletLedgerEntryResponse] = []
    total: int = 0
    page: int = 1
    page_size: int = 20


class WalletMeResponse(BaseModel):
    success: bool = True
    message: str = "Wallet retrieved"
    wallet: WalletResponse


class WalletTransferRequest(BaseModel):
    amount: Decimal = Field(..., gt=0, description="Amount to send in INR")
    to_user_id: Optional[int] = Field(None, description="Recipient user id")
    to_user_code: Optional[str] = Field(None, description="Recipient user code (e.g. FLS_1)")
    to_email: Optional[str] = Field(None, description="Recipient email")
    note: Optional[str] = Field(None, max_length=500)

    @field_validator("amount")
    @classmethod
    def round_amount(cls, v: Decimal) -> Decimal:
        return v.quantize(Decimal("0.01"))


class WalletTransferResponse(BaseModel):
    success: bool = True
    message: str
    transaction_group_id: str
    sender_balance: Decimal
    recipient_balance: Decimal


class SaleQRCreateRequest(BaseModel):
    sale_amount: Decimal = Field(..., gt=0)
    merchant_profile_id: Optional[int] = Field(
        None,
        description="Merchant profile id; defaults to the caller's primary merchant profile",
    )
    expires_in_minutes: int = Field(5, ge=1, le=1440)

    @field_validator("sale_amount")
    @classmethod
    def round_sale_amount(cls, v: Decimal) -> Decimal:
        return v.quantize(Decimal("0.01"))


class SaleQRCreateResponse(BaseModel):
    success: bool = True
    message: str
    token: str
    qr_payload: str
    sale_amount: Decimal
    estimated_cashback_total: Decimal
    estimated_user_cashback: Decimal
    estimated_company_fee: Decimal
    cashback_percent: Optional[Decimal] = None
    company_fee_percent: Optional[Decimal] = None
    total_deduction_percent: Optional[Decimal] = None
    merchant_wallet_balance: Optional[Decimal] = None
    expires_at: datetime
    status: SaleQRStatus


class SaleQRPreviewResponse(BaseModel):
    success: bool = True
    message: str
    token: str
    sale_amount: Decimal
    merchant_business_name: str
    category: Optional[str] = None
    status: SaleQRStatus
    expires_at: datetime
    estimated_user_cashback: Decimal
    cashback_percent: Optional[Decimal] = None
    company_fee_percent: Optional[Decimal] = None
    total_deduction_percent: Optional[Decimal] = None


class SaleQRMerchantStatusResponse(BaseModel):
    """Poll this from the merchant QR screen to detect customer redemption."""

    success: bool = True
    message: str
    token: str
    status: SaleQRStatus
    sale_amount: Decimal
    currency: str = "INR"
    merchant_business_name: str
    expires_at: datetime
    redeemed_at: Optional[datetime] = None
    is_redeemed: bool = False
    is_expired: bool = False
    is_pending: bool = False
    seconds_until_expiry: Optional[int] = None
    estimated_cashback_total: Decimal
    estimated_user_cashback: Decimal
    estimated_company_fee: Decimal
    merchant_debit: Optional[Decimal] = None
    transaction_group_id: Optional[str] = None
    merchant_wallet_balance: Decimal
    qr_payload: Optional[str] = None


class SaleRedeemRequest(BaseModel):
    token: str = Field(..., min_length=8, max_length=64)


class SaleRedeemResponse(BaseModel):
    success: bool = True
    message: str
    transaction_group_id: str
    merchant_business_name: Optional[str] = None
    sale_amount: Decimal
    user_cashback: Decimal
    company_fee: Decimal
    merchant_debit: Decimal
    cashback_percent: Optional[Decimal] = None
    user_wallet_balance: Decimal


class AdminWalletAdjustRequest(BaseModel):
    user_id: int
    amount: Decimal = Field(..., gt=0)
    note: Optional[str] = Field(None, max_length=500)
    operation: str = Field("credit", pattern="^(credit|debit)$")

    @field_validator("amount")
    @classmethod
    def round_amount(cls, v: Decimal) -> Decimal:
        return v.quantize(Decimal("0.01"))


class AdminWalletAdjustResponse(BaseModel):
    success: bool = True
    message: str
    wallet: WalletResponse
    transaction_group_id: str
    transaction_type: WalletTransactionType


class WalletTopUpRequest(BaseModel):
    amount: Decimal = Field(..., gt=0, le=100000, description="Amount to add to wallet in INR")
    payment_method: str = Field(default="UPI", description="Payment method: UPI, CARD, NETBANKING, CASH")
    reference_id: Optional[str] = Field(None, max_length=128, description="External transaction ID or payment reference")
    note: Optional[str] = Field(None, max_length=500, description="Optional note")

    @field_validator("amount")
    @classmethod
    def round_amount(cls, v: Decimal) -> Decimal:
        return v.quantize(Decimal("0.01"))


class WalletTopUpResponse(BaseModel):
    success: bool = True
    message: str
    wallet: WalletResponse
    transaction_group_id: str
    amount_credited: Decimal
    new_balance: Decimal
    payment_method: str

