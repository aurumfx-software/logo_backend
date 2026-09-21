from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship
from app.db.database import Base


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    type = Column(String(50), default="INFO", nullable=False, index=True)  # e.g., MERCHANT_APPROVAL, MERCHANT_REJECTION, SYSTEM, INFO
    is_read = Column(Boolean, default=False, nullable=False, index=True)
    data = Column(JSON, nullable=True)  # Context data: e.g. {"merchant_id": 1, "link": "/merchants/1"}

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = relationship("User", backref="notifications")
