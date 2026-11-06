from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Union
import re

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


class PlatformWalletTransaction(BaseModel):
    id: int
    direction: str
    amount: Decimal
    balance_after: Decimal
    note: Optional[str] = None
    created_at: datetime
    transaction_type: Optional[str] = None
    transaction_group_id: Optional[str] = None
    merchant_name: Optional[str] = None
    merchant_city: Optional[str] = None


class PlatformWalletResponse(BaseModel):
    """Admin platform wallet screen: company balance, fee totals, and ledger."""

    success: bool = True
    message: str = "Platform wallet retrieved"
    currency: str = "INR"
    balance: Decimal
    customer_cashback_percent: float
    platform_fee_percent: float
    total_shop_deduction_percent: float
    total_platform_revenue: Decimal
    cashback_distributed: Decimal
    gross_sales_volume: Decimal
    qr_redemptions: int
    total_received: Decimal = Decimal("0.00")
    total_deducted: Decimal = Decimal("0.00")
    real_balance: Decimal = Decimal("0.00")
    transactions: List[PlatformWalletTransaction] = []
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
    to_phone: Optional[str] = Field(None, description="Recipient phone number")
    to_merchant_id: Optional[int] = Field(None, description="Recipient merchant profile ID")
    to_admin: Optional[bool] = Field(False, description="Transfer directly to platform admin")
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
    expires_in_minutes: int = Field(30, ge=5, le=1440)

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
    cashback_percent: float = 3.0
    company_fee_percent: float = 2.0
    total_deduction_percent: float = 5.0
    expires_at: datetime
    status: SaleQRStatus


class SaleQRPreviewResponse(BaseModel):
    success: bool = True
    message: str
    token: str
    sale_amount: Decimal
    merchant_business_name: str
    status: SaleQRStatus
    expires_at: datetime
    estimated_user_cashback: Decimal
    cashback_percent: float = 3.0
    company_fee_percent: float = 2.0
    total_deduction_percent: float = 5.0


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
    cashback_percent: float = 3.0
    company_fee_percent: float = 2.0
    total_deduction_percent: float = 5.0
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
    sale_amount: Decimal
    user_cashback: Decimal
    company_fee: Decimal
    cashback_percent: float = 0
    company_fee_percent: float = 0
    merchant_debit: Decimal
    user_wallet_balance: Decimal


class WalletTopUpRequest(BaseModel):
    amount: Decimal = Field(..., gt=0, le=100000, description="Amount to add to wallet in INR")
    payment_method: str = Field(default="UPI", description="Payment method: UPI, CARD, NETBANKING, CASH")
    reference_id: Optional[str] = Field(None, max_length=128, description="External transaction ID or payment reference")
    note: Optional[str] = Field(None, max_length=500, description="Optional note")

    @field_validator("amount")
    @classmethod
    def round_topup_amount(cls, v: Decimal) -> Decimal:
        return v.quantize(Decimal("0.01"))


class WalletTopUpResponse(BaseModel):
    success: bool = True
    message: str
    wallet: WalletResponse
    transaction_group_id: str
    amount_credited: Decimal
    new_balance: Decimal
    payment_method: str


class AdminWalletAdjustRequest(BaseModel):
    user_id: Optional[Union[int, str]] = Field(None, description="Target user id")
    merchant_id: Optional[Union[int, str]] = Field(None, description="Target merchant profile id")
    amount: Decimal = Field(..., gt=0)
    note: Optional[str] = Field(None, max_length=500)
    operation: str = Field("credit", pattern="^(credit|debit)$")
    claim_mode: bool = Field(
        False,
        description="When true for credits, sends to Redeem section until claimed instead of direct wallet credit",
    )

    @field_validator("user_id", mode="before")
    @classmethod
    def parse_user_id(cls, v):
        if v is None or v == "":
            return None
        if isinstance(v, int):
            return v
        m = re.search(r"\d+", str(v))
        if m:
            return int(m.group(0))
        return None

    @field_validator("merchant_id", mode="before")
    @classmethod
    def parse_merchant_id(cls, v):
        if v is None or v == "":
            return None
        if isinstance(v, int):
            return v
        m = re.search(r"\d+", str(v))
        if m:
            return int(m.group(0))
        return None

    @field_validator("amount")
    @classmethod
    def round_amount(cls, v: Decimal) -> Decimal:
        return v.quantize(Decimal("0.01"))


class AdminWalletAdjustResponse(BaseModel):
    success: bool = True
    message: str
    wallet: Optional[WalletResponse] = None
    transaction_group_id: Optional[str] = None
    transaction_type: Optional[WalletTransactionType] = None
    claim_id: Optional[int] = None
    claim_status: Optional[str] = None


class WalletRewardClaimResponse(BaseModel):
    id: int
    claim_token: str
    amount: Decimal
    currency: str = "INR"
    title: str
    note: Optional[str] = None
    status: str
    recipient_user_id: int
    merchant_profile_id: Optional[int] = None
    created_at: datetime
    redeemed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class WalletWithdrawalRequest(BaseModel):
    amount: Decimal = Field(..., gt=0)
    account_holder_name: str = Field(..., min_length=2, max_length=100, description="Bank account holder name")
    account_number: str = Field(..., min_length=6, max_length=34, description="Bank account number")
    ifsc: str = Field(..., min_length=4, max_length=11, description="Bank IFSC code")
    payout_mode: Optional[str] = Field("IMPS", description="IMPS, NEFT, or RTGS")
    mode: Optional[str] = None

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, value: Decimal) -> Decimal:
        value = value.quantize(Decimal("0.01"))
        if value < Decimal("1.00"):
            raise ValueError("Minimum withdrawal amount is 1.00")
        return value


class AdminWalletSummaryResponse(BaseModel):
    success: bool = True
    company_balance: Decimal
    total_commission: Decimal = Decimal("0.00")
    total_active_wallets_balance: Decimal
    total_balance_across_active_wallets: Decimal
    total_wallet_count: int
    total_wallets_count: int
    total_received: Decimal = Decimal("0.00")
    total_deducted: Decimal = Decimal("0.00")
    real_balance: Decimal = Decimal("0.00")
    currency: str = "INR"


class AdminWalletTransactionItem(BaseModel):
    id: int
    recipient: Optional[str] = None
    recipient_type: Optional[str] = "user"
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    customer_email: Optional[str] = None
    customer_details: Optional[str] = None
    merchant_name: Optional[str] = None
    merchant_city: Optional[str] = None
    merchant_details: Optional[str] = None
    transaction_type: str
    direction: str
    amount: Decimal
    balance_after: Decimal
    note: Optional[str] = None
    date: datetime


class AdminWalletTransactionsResponse(BaseModel):
    success: bool = True
    data: List[AdminWalletTransactionItem] = []
    total: int = 0
    page: int = 1
    page_size: int = 20
    total_pages: int = 1


class AdminSendFundsRequest(BaseModel):
    recipient_type: str = Field(..., description="'user' or 'merchant'")
    user_id: Optional[Union[int, str]] = None
    email: Optional[str] = None
    amount: Decimal = Field(..., gt=0, description="Amount to send in INR")
    note: Optional[str] = Field(None, max_length=500)

    @field_validator("amount")
    @classmethod
    def round_amount(cls, v: Decimal) -> Decimal:
        return v.quantize(Decimal("0.01"))


class AdminSendFundsResponse(BaseModel):
    success: bool = True
    message: str
    recipient: str
    recipient_type: str
    amount: Decimal
    wallet_balance: Decimal
    transaction_group_id: Optional[str] = None


class MerchantTopupOrderRequest(BaseModel):
    amount: Decimal = Field(..., gt=0, description="Top-up amount in INR")
    merchant_profile_id: Optional[int] = None

    @field_validator("amount")
    @classmethod
    def round_amount(cls, v: Decimal) -> Decimal:
        return v.quantize(Decimal("0.01"))


class MerchantTopupOrderResponse(BaseModel):
    success: bool = True
    order_id: str
    razorpay_order_id: str
    amount: Decimal
    amount_paise: int
    currency: str = "INR"
    key_id: str
    topup_id: int
    merchant_profile_id: Optional[int] = None


class MerchantTopupVerifyRequest(BaseModel):
    order_id: Optional[str] = None
    razorpay_order_id: Optional[str] = None
    payment_id: Optional[str] = None
    razorpay_payment_id: Optional[str] = None
    signature: Optional[str] = None
    razorpay_signature: Optional[str] = None


class MerchantTopupVerifyResponse(BaseModel):
    success: bool = True
    message: str
    wallet_balance: Decimal
    transaction_group_id: Optional[str] = None


class WalletWithdrawalResponse(BaseModel):
    success: bool = True
    message: str
    transaction_group_id: str
    amount: Optional[Decimal] = None
    account_holder_name: Optional[str] = None
    account_number_masked: Optional[str] = None
    ifsc: Optional[str] = None
    payout_mode: Optional[str] = "IMPS"
    status: str = "PENDING"
    payout_id: Optional[str] = None
    failure_reason: Optional[str] = None
    wallet_balance: Decimal
    created_at: Optional[datetime] = None


class WalletWithdrawalStatusResponse(BaseModel):
    success: bool = True
    transaction_group_id: str
    status: str
    amount: Decimal
    account_holder_name: str
    account_number_masked: str
    ifsc: str
    payout_mode: str
    created_at: datetime


class AdminWalletLedgerLineResponse(BaseModel):
    id: int
    direction: str
    amount: Decimal
    balance_after: Decimal
    wallet_id: int
    wallet_type: str
    user_id: Optional[int] = None
    user_name: Optional[str] = None
    user_email: Optional[str] = None
    counterparty_wallet_id: Optional[int] = None
    counterparty_user_id: Optional[int] = None
    counterparty_name: Optional[str] = None
    counterparty_email: Optional[str] = None
    note: Optional[str] = None
    created_at: datetime


class AdminWalletTransactionResponse(BaseModel):
    id: int
    transaction_group_id: str
    transaction_type: str
    amount: Decimal
    currency: str
    description: Optional[str] = None
    initiated_by_user_id: Optional[int] = None
    initiated_by_name: Optional[str] = None
    initiated_by_email: Optional[str] = None
    reference_id: Optional[str] = None
    provider_status: Optional[str] = None
    provider_id: Optional[str] = None
    failure_reason: Optional[str] = None
    bank_account_holder_name: Optional[str] = None
    bank_account_last4: Optional[str] = None
    bank_ifsc: Optional[str] = None
    created_at: datetime
    ledger_entries: List[AdminWalletLedgerLineResponse] = []


class AdminPlatformCashItem(BaseModel):
    """One row in the admin cash table: merchant top-up received or user withdrawal deducted."""

    id: int
    transaction_group_id: str
    movement: str
    transaction_type: str
    amount: Decimal
    party_name: Optional[str] = None
    party_email: Optional[str] = None
    party_phone: Optional[str] = None
    party_role: str
    description: Optional[str] = None
    created_at: datetime


class AdminWalletTransactionListResponse(BaseModel):
    success: bool = True
    data: List[AdminWalletTransactionResponse] = []
    total: int = 0
    page: int = 1
    page_size: int = 20
    platform_cash: List[AdminPlatformCashItem] = []
    platform_cash_total: int = 0
    platform_cash_page: int = 1
    platform_cash_page_size: int = 20
    total_received: Decimal = Decimal("0.00")
    total_deducted: Decimal = Decimal("0.00")
    real_balance: Decimal = Decimal("0.00")

