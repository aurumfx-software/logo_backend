from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, JSON, String, UniqueConstraint

from app.db.database import Base


class ServiceArea(Base):
    """A Kerala town or commercial hub shown on the Geography screen."""

    __tablename__ = "service_areas"
    __table_args__ = (
        UniqueConstraint("district", "town", name="uq_service_areas_district_town"),
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    district = Column(String(100), nullable=False, index=True)
    town = Column(String(150), nullable=False, index=True)
    zones = Column(JSON, default=list, nullable=False)
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
