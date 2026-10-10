from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, DateTime
from app.db.database import Base


class Promotion(Base):
    __tablename__ = "promotions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    promo_code = Column(String(50), unique=True, index=True, nullable=True)
    title = Column(String(255), nullable=False)
    category = Column(String(100), nullable=True)
    type = Column(String(50), nullable=False, default="Featured")  # Featured, Sponsored, Banner, Promotion
    placement = Column(String(255), nullable=True)  # Home Top, Food Category, etc.
    location = Column(String(255), nullable=True)
    start_date = Column(String(50), nullable=True)
    end_date = Column(String(50), nullable=True)
    status = Column(String(50), nullable=False, default="active", index=True)  # active, pending, inactive
    impressions = Column(Integer, default=0, nullable=False)
    clicks = Column(Integer, default=0, nullable=False)
    image_url = Column(String(500), nullable=True)
    video_url = Column(String(500), nullable=True)
    media_type = Column(String(20), nullable=False, default="image")  # image, video
    thumbnail_url = Column(String(500), nullable=True)
    target_url = Column(String(500), nullable=True)
    description = Column(Text, nullable=True)

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
