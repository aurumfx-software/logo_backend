import enum
from datetime import datetime, timezone
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.db.database import Base


class LogoStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class LogoCategory(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(100), unique=True, index=True, nullable=False)
    slug = Column(String(120), unique=True, index=True, nullable=False)
    description = Column(String(500), nullable=True)
    icon_url = Column(String(500), nullable=True)
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

    logos = relationship("Logo", back_populates="category", cascade="all, delete-orphan")


class Logo(Base):
    __tablename__ = "logos"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    title = Column(String(255), index=True, nullable=False)
    description = Column(Text, nullable=True)
    image_url = Column(String(500), nullable=False)
    tags = Column(JSON, default=list, nullable=False)

    category_id = Column(
        Integer, ForeignKey("categories.id", ondelete="SET NULL"), nullable=True, index=True
    )
    submitted_by_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    status = Column(
        Enum(LogoStatus, name="logo_status", native_enum=False),
        default=LogoStatus.PENDING,
        nullable=False,
        index=True,
    )
    rejection_reason = Column(String(500), nullable=True)

    reviewed_by_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at = Column(DateTime(timezone=True), nullable=True)

    views_count = Column(Integer, default=0, nullable=False)
    favorites_count = Column(Integer, default=0, nullable=False)

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

    category = relationship("LogoCategory", back_populates="logos")
    submitted_by = relationship("User", foreign_keys=[submitted_by_id], backref="submitted_logos")
    reviewed_by = relationship("User", foreign_keys=[reviewed_by_id])
    favorites = relationship("LogoFavorite", back_populates="logo", cascade="all, delete-orphan")


class LogoFavorite(Base):
    __tablename__ = "logo_favorites"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    logo_id = Column(
        Integer, ForeignKey("logos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("user_id", "logo_id", name="uq_user_logo_favorite"),
    )

    user = relationship("User", backref="favorite_logos")
    logo = relationship("Logo", back_populates="favorites")
