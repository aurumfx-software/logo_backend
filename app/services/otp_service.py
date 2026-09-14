import logging
from datetime import datetime, timedelta, timezone
from typing import Tuple, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import generate_numeric_otp, hash_otp, verify_otp_hash
from app.db.models.otp import OTPVerification, OTPPurpose

logger = logging.getLogger("logo.otp")


class OTPService:
    """Service handling OTP creation, delivery abstraction, and verification."""

    @staticmethod
    def send_notification_stub(identifier: str, otp: str, purpose: OTPPurpose) -> None:
        """
        Provider abstraction for OTP delivery.
        In production, this delegates to Twilio / AWS SNS / SendGrid / Postmark.
        In trial/development mode, it logs safely to the dev server console.
        """
        logger.info(
            f"[DEV/TRIAL OTP] Destination: {identifier} | Purpose: {purpose.value} | Generated OTP: {otp}"
        )
        print(
            f"\n>>> [DEV/TRIAL OTP NOTIFICATION] To: {identifier} | Purpose: {purpose.value} | CODE: {otp} <<<\n"
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

        # Trigger notification delivery stub
        cls.send_notification_stub(clean_identifier, plain_otp, purpose)

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
