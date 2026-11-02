from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String

from app.db.database import Base


class SearchEvent(Base):
    """One row each time a customer runs a merchant search."""

    __tablename__ = "search_events"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    source = Column(String(40), nullable=False, index=True)
    query = Column(String(255), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
