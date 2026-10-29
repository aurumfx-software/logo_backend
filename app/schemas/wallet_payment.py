from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.models.wallet import WalletTopupStatus


class RazorpayWalletConfigResponse(BaseModel):
    success: bool = True
    message: str = "Razorpay checkout configuration"
    razorpay_key_id: str = ""
    currency: str = "INR"
    min_amount: Decimal
    max_amount: Decimal
    razorpay_configured: bool = False


class WalletTopupCreateRequest(BaseModel):
    amount: Decimal = Field(..., gt=0, description="Amount in INR to add to wallet")
    merchant_profile_id: Optional[int] = Field(
        None,
        description="Merchant shop; defaults to your primary merchant profile",
    )

    @field_validator("amount")
    @classmethod
    def round_amount(cls, v: Decimal) -> Decimal:
        return v.quantize(Decimal("0.01"))


class RazorpayTopupOrderResponse(BaseModel):
    success: bool = True
    message: str
    topup_id: int
    razorpay_key_id: str
    razorpay_order_id: str
    amount: Decimal
    amount_paise: int
    currency: str
    receipt: str
    merchant_profile_id: int
    merchant_business_name: str


class RazorpayTopupVerifyRequest(BaseModel):
    razorpay_order_id: str = Field(..., min_length=4, max_length=64)
    razorpay_payment_id: str = Field(..., min_length=4, max_length=64)
    razorpay_signature: str = Field(..., min_length=8, max_length=128)


class RazorpayTopupVerifyResponse(BaseModel):
    success: bool = True
    message: str
    topup_id: int
    transaction_group_id: str
    wallet_balance: Decimal
    amount: Decimal
    razorpay_payment_id: str


class WalletTopupOrderStatusResponse(BaseModel):
    success: bool = True
    topup_id: int
    status: WalletTopupStatus
    amount: Decimal
    currency: str
    razorpay_order_id: str
    razorpay_payment_id: Optional[str] = None
    wallet_transaction_group_id: Optional[str] = None
    wallet_balance: Optional[Decimal] = None
    paid_at: Optional[datetime] = None


class WalletTopupListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    amount: Decimal
    currency: str
    status: WalletTopupStatus
    razorpay_order_id: str
    razorpay_payment_id: Optional[str] = None
    merchant_profile_id: Optional[int] = None
    wallet_transaction_group_id: Optional[str] = None
    paid_at: Optional[datetime] = None
    created_at: datetime


class WalletTopupListResponse(BaseModel):
    success: bool = True
    message: str = "Top-up orders retrieved"
    data: List[WalletTopupListItem] = []
