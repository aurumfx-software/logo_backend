from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, DateTime
from app.db.database import Base


class Complaint(Base):
    __tablename__ = "complaints"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    complaint_code = Column(String(50), unique=True, index=True, nullable=True)  # e.g., CMP-001
    user = Column(String(255), nullable=False)  # User display name
    user_email = Column(String(255), nullable=True)
    user_phone = Column(String(50), nullable=True)
    merchant = Column(String(255), nullable=False)  # Merchant display name
    subject = Column(String(255), nullable=False)
    category = Column(String(100), nullable=False, default="General")  # Service Quality, Order Issue, Payment, Listing Accuracy, Product Quality
    priority = Column(String(50), nullable=False, default="medium")  # high, medium, low
    status = Column(String(50), nullable=False, default="open", index=True)  # open, in-progress, resolved
    date = Column(String(50), nullable=True)  # e.g. "2024-09-14"
    description = Column(Text, nullable=True)
    admin_response = Column(Text, nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)

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
