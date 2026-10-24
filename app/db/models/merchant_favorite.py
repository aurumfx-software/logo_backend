from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import relationship

from app.db.database import Base


class CustomerMerchantFavorite(Base):
    __tablename__ = "customer_merchant_favorites"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    merchant_id = Column(Integer, ForeignKey("merchant_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("user_id", "merchant_id", name="uq_user_merchant_favorite"),
    )

    user = relationship("User", backref="merchant_favorites")
    merchant = relationship("MerchantProfile", backref="favorite_customers")
