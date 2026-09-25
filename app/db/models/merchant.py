from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship
from app.db.database import Base


class MerchantProfile(Base):
    __tablename__ = "merchant_profiles"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=False, nullable=False, index=True)
    user_code = Column(String(50), nullable=True, index=True)

    business_name = Column(String(255), nullable=False, index=True)
    owner_name = Column(String(255), nullable=True)
    categories = Column(JSON, default=list, nullable=False)  # e.g. ["Food & Dining"]
    district = Column(String(100), nullable=True, index=True)  # e.g. "Bangalore Urban", "Ernakulam"
    city = Column(String(100), nullable=True, index=True)  # e.g. "Bangalore", "Kochi"
    location = Column(String(255), nullable=False, index=True)  # e.g. "Indiranagar", "MG Road"
    address = Column(String(500), nullable=False)
    landmark = Column(String(255), nullable=True)
    contact_number = Column(String(50), nullable=False, index=True)

    services = Column(JSON, default=list, nullable=True)  # e.g. ["Takeaway", "Dine-in"]
    service_timing = Column(String(255), default="General Store Hours", nullable=True)
    merchant_photos = Column(JSON, default=list, nullable=False)  # list of photo URLs
    merchant_videos = Column(JSON, default=list, nullable=False)  # list of video URLs
    verification_documents = Column(JSON, default=list, nullable=False)  # list of document URLs

    is_verified = Column(Boolean, default=False, nullable=False)
    approval_status = Column(String(50), default="PENDING", nullable=False, index=True)  # PENDING, APPROVED, REJECTED
    rejection_reason = Column(String(500), nullable=True)
    approved_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    onboarded_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = relationship("User", foreign_keys=[user_id], backref="merchant_profiles")
    approved_by = relationship("User", foreign_keys=[approved_by_id])
    onboarded_by = relationship("User", foreign_keys=[onboarded_by_id])
