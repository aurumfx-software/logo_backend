import enum
from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, DateTime, Enum, Integer, String
from app.db.database import Base


class OTPPurpose(str, enum.Enum):
    ACCOUNT_VERIFICATION = "ACCOUNT_VERIFICATION"
    PASSWORD_RESET = "PASSWORD_RESET"


class OTPVerification(Base):
    __tablename__ = "otp_verifications"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    identifier = Column(String(255), index=True, nullable=False)  # email or phone
    otp_hash = Column(String(255), nullable=False)
    purpose = Column(
        Enum(OTPPurpose, name="otp_purpose", native_enum=False),
        default=OTPPurpose.ACCOUNT_VERIFICATION,
        nullable=False,
    )
    attempts = Column(Integer, default=0, nullable=False)
    max_attempts = Column(Integer, default=3, nullable=False)
    is_used = Column(Boolean, default=False, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
