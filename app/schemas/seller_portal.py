import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator


IFSC_PATTERN = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")


class SellerBankDetailsRequest(BaseModel):
    account_holder_name: str = Field(..., min_length=3, max_length=255)
    bank_name: str = Field(..., min_length=1, max_length=255)
    account_number: str = Field(..., min_length=9, max_length=18)
    ifsc_code: str = Field(..., min_length=11, max_length=11)
    upi_id: Optional[str] = Field(None, max_length=100)

    @field_validator("account_holder_name", "bank_name")
    @classmethod
    def strip_required(cls, value: str, info) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("This field is required")
        if info.field_name == "account_holder_name" and len(cleaned) < 3:
            raise ValueError("Account holder name must be at least 3 characters")
        return cleaned

    @field_validator("account_number")
    @classmethod
    def digits_only(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned.isdigit() or not 9 <= len(cleaned) <= 18:
            raise ValueError("Account number must be 9 to 18 digits")
        return cleaned

    @field_validator("ifsc_code")
    @classmethod
    def valid_ifsc(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if not IFSC_PATTERN.match(cleaned):
            raise ValueError("Invalid IFSC code format")
        return cleaned

    @field_validator("upi_id")
    @classmethod
    def empty_upi_is_none(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class SellerBankDetails(BaseModel):
    account_holder_name: str
    bank_name: str
    account_number: str
    ifsc_code: str
    upi_id: Optional[str] = None


class SellerBankDetailsResponse(BaseModel):
    success: bool = True
    data: Optional[SellerBankDetails] = None
    message: Optional[str] = None


class SellerBankSaveResponse(BaseModel):
    success: bool = True
    message: str = "Seller bank details saved successfully"
    data: SellerBankDetails


class SellerOrderPipeline(BaseModel):
    new_orders: int = 0
    contacted_orders: int = 0
    shipped_orders: int = 0
    delivered_orders: int = 0
    cancelled_orders: int = 0


class SellerAnalyticsData(BaseModel):
    currency: str = "INR"
    total_sales: float = 0
    online_paid: float = 0
    cod_to_collect: float = 0
    total_orders: int = 0
    pipeline: SellerOrderPipeline


class SellerAnalyticsResponse(BaseModel):
    success: bool = True
    data: SellerAnalyticsData


class CheckoutRulesData(BaseModel):
    min_order_value: float
    free_delivery_above: float
    delivery_fee: float
    cod_available: bool
    cod_fee: float
    free_cod_above: float
    online_discount_percentage: float
    online_discount_max_amount: float


class CheckoutRulesResponse(BaseModel):
    success: bool = True
    data: CheckoutRulesData
