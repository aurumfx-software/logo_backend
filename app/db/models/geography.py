from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime
from app.db.database import Base


class GeographyRegion(Base):
    __tablename__ = "geography_regions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    geo_code = Column(String(50), unique=True, index=True, nullable=True)  # e.g., GEO-001
    city = Column(String(100), nullable=False, index=True)
    state = Column(String(100), nullable=False, index=True)
    zones = Column(Integer, default=1, nullable=False)
    merchants = Column(Integer, default=0, nullable=False)
    users = Column(Integer, default=0, nullable=False)
    status = Column(String(50), default="active", nullable=False, index=True)  # active, pending, inactive

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
