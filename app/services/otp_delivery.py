"""Deliver OTP codes through MSG91 or Twilio (SMS) and SMTP (email)."""

import logging
import smtplib
from email.message import EmailMessage

import httpx
from fastapi import HTTPException, status

from app.core.config import settings
from app.db.models.otp import OTPPurpose

logger = logging.getLogger("logo.otp")


def _purpose_label(purpose: OTPPurpose) -> str:
    labels = {
        OTPPurpose.ACCOUNT_VERIFICATION: "account verification",
        OTPPurpose.PASSWORD_RESET: "password reset",
        OTPPurpose.MERCHANT_LOGIN: "merchant login",
        OTPPurpose.CUSTOMER_LOGIN: "login",
    }
    return labels.get(purpose, "verification")


def _to_indian_mobile(identifier: str) -> str:
    digits = "".join(ch for ch in identifier if ch.isdigit())
    if digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]
    if len(digits) == 10:
        digits = f"91{digits}"
    return digits


class OTPDeliveryService:
    @staticmethod
    def twilio_verify_configured() -> bool:
        return bool(
            settings.TWILIO_ACCOUNT_SID
            and settings.TWILIO_AUTH_TOKEN
            and settings.TWILIO_VERIFY_SERVICE_SID
        )

    @staticmethod
    def twilio_owns_sms(identifier: str) -> bool:
        return "@" not in identifier and OTPDeliveryService.twilio_verify_configured()

    @staticmethod
    def expose_local_code(identifier: str) -> bool:
        """Development may echo the local code only when Twilio did not generate the SMS."""
        return settings.ENVIRONMENT == "development" and not OTPDeliveryService.twilio_owns_sms(identifier)

    @staticmethod
    def sms_configured() -> bool:
        msg91 = bool(settings.MSG91_AUTH_KEY and settings.MSG91_TEMPLATE_ID)
        twilio_message = bool(
            settings.TWILIO_ACCOUNT_SID
            and settings.TWILIO_AUTH_TOKEN
            and settings.TWILIO_FROM_NUMBER
        )
        return OTPDeliveryService.twilio_verify_configured() or msg91 or twilio_message

    @staticmethod
    def email_configured() -> bool:
        return bool(settings.SMTP_HOST and settings.SMTP_FROM)

    @classmethod
    def deliver(cls, identifier: str, otp: str, purpose: OTPPurpose) -> None:
        if "@" in identifier:
            cls._send_email(identifier, otp, purpose)
        else:
            cls._send_sms(identifier, otp, purpose)

    @classmethod
    def _send_sms(cls, identifier: str, otp: str, purpose: OTPPurpose) -> None:
        mobile = _to_indian_mobile(identifier)
        if cls.twilio_verify_configured():
            cls._start_twilio_verification(mobile)
            return
        if settings.MSG91_AUTH_KEY and settings.MSG91_TEMPLATE_ID:
            cls._send_msg91(mobile, otp)
            return
        if settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN and settings.TWILIO_FROM_NUMBER:
            cls._send_twilio(mobile, otp, purpose)
            return
        if settings.ENVIRONMENT == "development":
            logger.info("OTP SMS skipped (no MSG91 or Twilio credentials). Destination=%s", mobile)
            return
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "SMS OTP is not configured. Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, "
                "and TWILIO_VERIFY_SERVICE_SID."
            ),
        )

    @staticmethod
    def _send_msg91(mobile: str, otp: str) -> None:
        try:
            with httpx.Client(timeout=20.0) as client:
                response = client.post(
                    "https://control.msg91.com/api/v5/otp",
                    params={
                        "template_id": settings.MSG91_TEMPLATE_ID,
                        "mobile": mobile,
                        "otp": otp,
                        "otp_expiry": str(settings.OTP_EXPIRE_MINUTES),
                    },
                    headers={
                        "authkey": settings.MSG91_AUTH_KEY,
                        "accept": "application/json",
                    },
                )
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="MSG91 could not send the OTP.",
            ) from exc
        body = {}
        try:
            body = response.json()
        except ValueError:
            body = {}
        failed = response.status_code >= 400 or str(body.get("type", "")).lower() == "error"
        if failed:
            message = body.get("message") or response.text or "MSG91 rejected the OTP request."
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"MSG91 OTP failed: {message}",
            )

    @staticmethod
    def _e164(mobile: str) -> str:
        return mobile if mobile.startswith("+") else f"+{mobile}"

    @staticmethod
    def _twilio_auth() -> tuple[str, str]:
        return settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN

    @classmethod
    def _start_twilio_verification(cls, mobile: str) -> None:
        url = (
            "https://verify.twilio.com/v2/Services/"
            f"{settings.TWILIO_VERIFY_SERVICE_SID}/Verifications"
        )
        try:
            with httpx.Client(timeout=20.0) as client:
                response = client.post(
                    url,
                    data={"To": cls._e164(mobile), "Channel": "sms"},
                    auth=cls._twilio_auth(),
                )
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Twilio could not send the OTP.",
            ) from exc
        if response.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Twilio rejected the OTP request.",
            )

    @classmethod
    def check_twilio_verification(cls, identifier: str, code: str) -> bool:
        mobile = _to_indian_mobile(identifier)
        url = (
            "https://verify.twilio.com/v2/Services/"
            f"{settings.TWILIO_VERIFY_SERVICE_SID}/VerificationCheck"
        )
        try:
            with httpx.Client(timeout=20.0) as client:
                response = client.post(
                    url,
                    data={"To": cls._e164(mobile), "Code": code.strip()},
                    auth=cls._twilio_auth(),
                )
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Twilio could not check the OTP.",
            ) from exc
        if response.status_code == 404:
            return False
        if response.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Twilio rejected the OTP check.",
            )
        try:
            body = response.json()
        except ValueError:
            return False
        return str(body.get("status", "")).lower() == "approved"

    @staticmethod
    def _send_twilio(mobile: str, otp: str, purpose: OTPPurpose) -> None:
        to_number = mobile if mobile.startswith("+") else f"+{mobile}"
        text = (
            f"Your LOGO {_purpose_label(purpose)} code is {otp}. "
            f"It expires in {settings.OTP_EXPIRE_MINUTES} minutes."
        )
        url = (
            "https://api.twilio.com/2010-04-01/Accounts/"
            f"{settings.TWILIO_ACCOUNT_SID}/Messages.json"
        )
        try:
            with httpx.Client(timeout=20.0) as client:
                response = client.post(
                    url,
                    data={
                        "To": to_number,
                        "From": settings.TWILIO_FROM_NUMBER,
                        "Body": text,
                    },
                    auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN),
                )
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Twilio could not send the OTP.",
            ) from exc
        if response.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Twilio rejected the OTP message.",
            )

    @classmethod
    def _send_email(cls, email: str, otp: str, purpose: OTPPurpose) -> None:
        if not cls.email_configured():
            if settings.ENVIRONMENT == "development":
                logger.info("OTP email skipped (SMTP is not configured). Destination=%s", email)
                return
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Email OTP is not configured. Set SMTP_HOST and SMTP_FROM.",
            )
        label = _purpose_label(purpose)
        message = EmailMessage()
        message["Subject"] = f"Your LOGO {label} code"
        message["From"] = settings.SMTP_FROM
        message["To"] = email
        message.set_content(
            f"Your LOGO {label} code is {otp}.\n"
            f"It expires in {settings.OTP_EXPIRE_MINUTES} minutes.\n"
            "If you did not request this, you can ignore this email."
        )
        try:
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as smtp:
                if settings.SMTP_USE_TLS:
                    smtp.starttls()
                if settings.SMTP_USER:
                    smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                smtp.send_message(message)
        except (smtplib.SMTPException, OSError) as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="The email provider could not send the OTP.",
            ) from exc
