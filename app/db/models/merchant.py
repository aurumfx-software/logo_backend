from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship
from app.db.database import Base


class MerchantProfile(Base):
    __tablename__ = "merchant_profiles"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)

    business_name = Column(String(255), nullable=False, index=True)
    categories = Column(JSON, default=list, nullable=False)  # e.g. ["Salon", "Spa"]
    location = Column(String(255), nullable=False, index=True)  # e.g. "MG Road, Kochi"
    services = Column(JSON, default=list, nullable=False)  # e.g. ["Hair Cut", "Facial"]
    service_timing = Column(String(255), nullable=False)  # e.g. "09:00 AM - 08:00 PM"
    merchant_photos = Column(JSON, default=list, nullable=False)  # list of photo URLs
    contact_number = Column(String(50), nullable=False, index=True)
    address = Column(String(500), nullable=False)

    is_verified = Column(Boolean, default=False, nullable=False)
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

    user = relationship("User", backref="merchant_profile")
