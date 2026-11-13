from fastapi import APIRouter

from app.db.models.otp import OTPPurpose
from app.schemas.auth import OTPPurposeListResponse, OTPPurposeOption

router = APIRouter(prefix="/otp", tags=["OTP"])

_OTP_PURPOSE_LABELS = {
    OTPPurpose.ACCOUNT_VERIFICATION: "Account verification",
    OTPPurpose.PASSWORD_RESET: "Password reset",
    OTPPurpose.MERCHANT_LOGIN: "Merchant login",
    OTPPurpose.CUSTOMER_LOGIN: "Customer login",
}


def _otp_purpose_options() -> OTPPurposeListResponse:
    options = [
        OTPPurposeOption(value=p.value, label=_OTP_PURPOSE_LABELS.get(p, p.value.replace("_", " ").title()))
        for p in OTPPurpose
    ]
    return OTPPurposeListResponse(purposes=options, types=options)


@router.get(
    "/option-types",
    response_model=OTPPurposeListResponse,
    summary="List OTP purpose / type options (alias)",
    include_in_schema=False,
)
def list_otp_types() -> OTPPurposeListResponse:
    return _otp_purpose_options()
