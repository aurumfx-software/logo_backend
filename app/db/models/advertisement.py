from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, Text

from app.db.database import Base


class MerchantAdvertisement(Base):
    __tablename__ = "merchant_advertisements"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    merchant_id = Column(Integer, nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    image_url = Column(String(500), nullable=True)
    video_url = Column(String(500), nullable=True)
    link_url = Column(String(500), nullable=True)
    start_date = Column(String(50), nullable=True)
    end_date = Column(String(50), nullable=True)
    status = Column(String(20), nullable=False, default="active", index=True)
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
