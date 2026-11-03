import logging
from datetime import datetime, timedelta, timezone
from typing import Tuple, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

import re
from app.core.config import settings
from app.core.security import generate_numeric_otp, hash_otp, verify_otp_hash
from app.db.models.otp import OTPVerification, OTPPurpose
from app.services.otp_delivery import OTPDeliveryService

logger = logging.getLogger("logo.otp")


class OTPService:
    """Service handling OTP creation, real provider delivery (MSG91 / Twilio / SMTP), and verification."""

    @classmethod
    def send_notification(cls, identifier: str, otp: str, purpose: OTPPurpose) -> None:
        """
        Dispatches OTP through real delivery providers:
        - Email: SMTP (SendGrid, SES, or custom host) using SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM
        - Phone:
          1. MSG91 Send OTP (https://control.msg91.com/api/v5/otp) using MSG91_AUTH_KEY, MSG91_TEMPLATE_ID
          2. Twilio Messages API using TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER
        If no provider is configured:
        - In development: logs code to console & allows dev_otp.
        - In production: raises 503 Service Unavailable.
        """
        clean_target = identifier.strip().lower()

        # ── 1. EMAIL CHANNEL ──
        if "@" in clean_target:
            if settings.SMTP_HOST and settings.SMTP_USER:
                cls._send_email_smtp(clean_target, otp, purpose)
            else:
                if settings.ENVIRONMENT != "development":
                    logger.error(f"Cannot dispatch OTP email to {clean_target}: SMTP is not configured.")
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="Email delivery provider is not configured on this server.",
                    )
                logger.info(f"[DEV OTP] Destination (Email): {clean_target} | Purpose: {purpose.value} | OTP: {otp}")
                print(f"\n>>> [DEV OTP NOTIFICATION] To: {clean_target} | Purpose: {purpose.value} | CODE: {otp} <<<\n")
            return

        # ── 2. PHONE / SMS CHANNEL ──
        raw_digits = re.sub(r"[^\d]", "", clean_target)
        if len(raw_digits) == 10:
            mobile = f"91{raw_digits}"
        elif len(raw_digits) == 12 and raw_digits.startswith("91"):
            mobile = raw_digits
        else:
            mobile = f"91{raw_digits[-10:]}" if len(raw_digits) >= 10 else raw_digits

        if settings.MSG91_AUTH_KEY and settings.MSG91_TEMPLATE_ID:
            cls._send_phone_msg91(mobile, otp)
        elif settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN and settings.TWILIO_FROM_NUMBER:
            cls._send_phone_twilio(mobile, otp)
        else:
            if settings.ENVIRONMENT != "development":
                logger.error(f"Cannot dispatch OTP SMS to {clean_target} ({mobile}): No SMS provider configured.")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="SMS delivery provider is not configured on this server.",
                )
            logger.info(f"[DEV OTP] Destination (Phone): {clean_target} ({mobile}) | Purpose: {purpose.value} | OTP: {otp}")
            print(f"\n>>> [DEV OTP NOTIFICATION] To: {clean_target} ({mobile}) | Purpose: {purpose.value} | CODE: {otp} <<<\n")

    @staticmethod
    def _send_email_smtp(recipient: str, otp: str, purpose: OTPPurpose) -> None:
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        sender = settings.SMTP_FROM or settings.SMTP_USER or "noreply@logo.app"
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"Your LOGO Verification Code: {otp}"
        msg["From"] = f"Logo <{sender}>" if "<" not in sender else sender
        msg["To"] = recipient

        body_text = (
            f"Your LOGO verification code is: {otp}\n\n"
            f"This code will expire in {settings.OTP_EXPIRE_MINUTES} minutes.\n"
            f"Do not share this code with anyone. If you did not request this, please ignore this email."
        )
        msg.attach(MIMEText(body_text, "plain"))

        try:
            port = int(settings.SMTP_PORT or 587)
            if port == 465:
                with smtplib.SMTP_SSL(settings.SMTP_HOST, port, timeout=20) as server:
                    if settings.SMTP_USER and settings.SMTP_PASSWORD:
                        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                    server.send_message(msg)
            else:
                with smtplib.SMTP(settings.SMTP_HOST, port, timeout=20) as server:
                    server.ehlo()
                    server.starttls()
                    server.ehlo()
                    if settings.SMTP_USER and settings.SMTP_PASSWORD:
                        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                    server.send_message(msg)
            logger.info(f"Successfully sent OTP email to {recipient} via SMTP ({settings.SMTP_HOST})")
        except HTTPException:
            raise
        except Exception as exc:
            logger.error(f"SMTP error sending to {recipient}: {exc}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="The email provider could not send the OTP.",
            ) from exc

    @staticmethod
    def _send_phone_msg91(mobile: str, otp: str) -> None:
        import httpx

        # MSG91 Send OTP v5 API:
        # POST https://control.msg91.com/api/v5/otp?template_id={TEMPLATE_ID}&mobile={MOBILE}&authkey={AUTH_KEY}&otp={OTP}
        url = "https://control.msg91.com/api/v5/otp"
        params = {
            "template_id": settings.MSG91_TEMPLATE_ID.strip(),
            "mobile": mobile.strip(),
            "authkey": settings.MSG91_AUTH_KEY.strip(),
            "otp": otp.strip(),
        }
        headers = {
            "Content-Type": "application/json",
            "authkey": settings.MSG91_AUTH_KEY.strip(),
        }
        try:
            resp = httpx.post(url, params=params, headers=headers, timeout=10.0)
            data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            if resp.status_code >= 400 or (isinstance(data, dict) and data.get("type") == "error"):
                logger.error(f"MSG91 API error for {mobile}: {resp.status_code} - {resp.text}")
                if settings.ENVIRONMENT != "development":
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="Failed to send SMS through provider (MSG91).",
                    )
            else:
                logger.info(f"MSG91 OTP sent successfully to {mobile}")
        except HTTPException:
            raise
        except Exception as exc:
            logger.error(f"MSG91 request exception for {mobile}: {exc}")
            if settings.ENVIRONMENT != "development":
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="SMS delivery provider connection failed.",
                )

    @staticmethod
    def _send_phone_twilio(mobile: str, otp: str) -> None:
        import httpx

        # Twilio Messages REST API
        sid = settings.TWILIO_ACCOUNT_SID.strip()
        auth_token = settings.TWILIO_AUTH_TOKEN.strip()
        from_number = settings.TWILIO_FROM_NUMBER.strip()
        to_number = f"+{mobile}" if not mobile.startswith("+") else mobile

        url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
        data = {
            "From": from_number,
            "To": to_number,
            "Body": f"Your LOGO verification code is {otp}. Valid for {settings.OTP_EXPIRE_MINUTES} minutes.",
        }
        try:
            resp = httpx.post(url, data=data, auth=(sid, auth_token), timeout=10.0)
            if resp.status_code >= 400:
                logger.error(f"Twilio API error for {to_number}: {resp.status_code} - {resp.text}")
                if settings.ENVIRONMENT != "development":
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="Failed to send SMS through provider (Twilio).",
                    )
            else:
                logger.info(f"Twilio OTP sent successfully to {to_number}")
        except HTTPException:
            raise
        except Exception as exc:
            logger.error(f"Twilio request exception for {to_number}: {exc}")
            if settings.ENVIRONMENT != "development":
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="SMS delivery provider connection failed.",
                )

    @staticmethod
    def send_notification_stub(identifier: str, otp: str, purpose: OTPPurpose) -> None:
        """Send the code by SMS (MSG91 or Twilio) or email (SMTP)."""
        try:
            OTPDeliveryService.deliver(identifier, otp, purpose)
        except HTTPException:
            raise
        if settings.ENVIRONMENT == "development" and not (
            ("@" in identifier and OTPDeliveryService.email_configured())
            or ("@" not in identifier and OTPDeliveryService.sms_configured())
        ):
            logger.info(
                "[DEV OTP] Destination: %s | Purpose: %s | Code: %s",
                identifier,
                purpose.value,
                otp,
            )

    @classmethod
    def create_otp(
        cls, db: Session, identifier: str, purpose: OTPPurpose = OTPPurpose.ACCOUNT_VERIFICATION
    ) -> Tuple[str, OTPVerification]:
        clean_identifier = identifier.strip().lower()

        # Invalidate any existing unused OTPs for this identifier and purpose
        db.query(OTPVerification).filter(
            OTPVerification.identifier == clean_identifier,
            OTPVerification.purpose == purpose,
            OTPVerification.is_used == False,
        ).update({"is_used": True})

        plain_otp = generate_numeric_otp(6)
        hashed_otp = hash_otp(plain_otp)
        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=settings.OTP_EXPIRE_MINUTES
        )

        otp_record = OTPVerification(
            identifier=clean_identifier,
            otp_hash=hashed_otp,
            purpose=purpose,
            attempts=0,
            max_attempts=settings.OTP_MAX_ATTEMPTS,
            is_used=False,
            expires_at=expires_at,
        )
        db.add(otp_record)
        db.commit()
        db.refresh(otp_record)

        try:
            cls.send_notification(clean_identifier, plain_otp, purpose)
        except HTTPException:
            otp_record.is_used = True
            db.commit()
            raise

        return plain_otp, otp_record

    @classmethod
    def verify_otp(
        cls, db: Session, identifier: str, otp: str, purpose: OTPPurpose
    ) -> bool:
        clean_identifier = identifier.strip().lower()
        now = datetime.now(timezone.utc)

        otp_record = (
            db.query(OTPVerification)
            .filter(
                OTPVerification.identifier == clean_identifier,
                OTPVerification.purpose == purpose,
                OTPVerification.is_used == False,
            )
            .order_by(OTPVerification.created_at.desc())
            .first()
        )

        if not otp_record:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No active OTP found. Please request a new OTP.",
            )

        # Ensure timezone-aware comparison
        expires_at = otp_record.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if expires_at < now:
            otp_record.is_used = True
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="OTP has expired. Please request a new one.",
            )

        if otp_record.attempts >= otp_record.max_attempts:
            otp_record.is_used = True
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Maximum verification attempts exceeded. Please request a new OTP.",
            )

        if OTPDeliveryService.twilio_owns_sms(clean_identifier):
            approved = OTPDeliveryService.check_twilio_verification(clean_identifier, otp)
            if not approved:
                otp_record.attempts += 1
                if otp_record.attempts >= otp_record.max_attempts:
                    otp_record.is_used = True
                db.commit()
                remaining = otp_record.max_attempts - otp_record.attempts
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid OTP. {remaining} attempt(s) remaining.",
                )
            otp_record.is_used = True
            db.commit()
            return True

        # Check OTP match
        otp_record.attempts += 1
        if not verify_otp_hash(otp.strip(), otp_record.otp_hash):
            db.commit()
            remaining = otp_record.max_attempts - otp_record.attempts
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid OTP. {remaining} attempt(s) remaining.",
            )

        # OTP is valid!
        otp_record.is_used = True
        db.commit()
        return True
