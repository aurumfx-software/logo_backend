from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, Integer, String, Text, DateTime
from app.db.database import Base


class AppPolicy(Base):
    __tablename__ = "app_policies"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    key = Column(String(100), unique=True, index=True, nullable=False)  # e.g. terms, privacy
    label = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    last_updated = Column(String(50), nullable=True)

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


class PushNotification(Base):
    __tablename__ = "push_notifications"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    status = Column(String(50), nullable=False, default="active")  # active, scheduled, sent
    sent = Column(String(50), nullable=False, default="0")  # e.g. "24,850" or count
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class Announcement(Base):
    __tablename__ = "announcements"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    date = Column(String(50), nullable=True)
    pinned = Column(Boolean, default=False, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
