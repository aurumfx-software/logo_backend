from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import get_db
from app.db.models.otp import OTPPurpose
from app.db.models.user import User
from app.schemas.auth import (
    OTPChannelRequest,
    OTPVerifyChannelRequest,
    SendOTPResponse,
    VerifyOTPResponse,
)
from app.services.otp_delivery import OTPDeliveryService
from app.services.otp_service import OTPService

router = APIRouter(prefix="/otp", tags=["OTP"])


def _mark_account_verified(db: Session, payload: OTPChannelRequest) -> None:
    if payload.purpose != OTPPurpose.ACCOUNT_VERIFICATION:
        return
    query = db.query(User)
    if payload.email:
        user = query.filter(User.email == payload.email).first()
    else:
        user = query.filter(User.phone == payload.phone).first()
    if not user:
        return
    user.is_verified = True
    db.commit()


@router.post(
    "/send",
    response_model=SendOTPResponse,
    summary="Send a 6-digit OTP by email",
    description=(
        "Creates a single-use OTP and sends it with Resend. "
        "A phone number is accepted only to find the account email. "
        "dev_otp is returned only when Resend is not configured and ENVIRONMENT is development."
    ),
)
def send_otp(
    payload: OTPChannelRequest,
    db: Session = Depends(get_db),
) -> SendOTPResponse:
    plain_otp, _ = OTPService.create_otp(
        db=db,
        identifier=payload.identifier,
        purpose=payload.purpose,
    )
    dev_otp = plain_otp if OTPDeliveryService.expose_local_code(payload.identifier) else None
    destination = payload.email or "your email"
    return SendOTPResponse(
        message=f"OTP sent to {destination}. Please check your inbox.",
        expires_in_minutes=settings.OTP_EXPIRE_MINUTES,
        dev_otp=dev_otp,
    )


@router.post(
    "/verify",
    response_model=VerifyOTPResponse,
    summary="Validate an OTP",
    description=(
        "Checks the code for the same email or phone and purpose used when it was sent. "
        "Rejects expired codes and codes that exceed the attempt limit. "
        "ACCOUNT_VERIFICATION also sets is_verified on a matching user."
    ),
)
def verify_otp(
    payload: OTPVerifyChannelRequest,
    db: Session = Depends(get_db),
) -> VerifyOTPResponse:
    OTPService.verify_otp(
        db=db,
        identifier=payload.identifier,
        otp=payload.otp,
        purpose=payload.purpose,
    )
    _mark_account_verified(db, payload)
    return VerifyOTPResponse(
        message="OTP verified successfully.",
        is_verified=True,
    )
