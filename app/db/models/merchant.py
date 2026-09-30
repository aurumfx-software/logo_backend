from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, event, text
from sqlalchemy.orm import Session, relationship
from app.db.database import Base


class MerchantProfile(Base):
    __tablename__ = "merchant_profiles"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=False, nullable=False, index=True)
    user_code = Column(String(50), nullable=True, index=True)  # MRH 1, MRH 2, ...

    business_name = Column(String(255), nullable=False, index=True)
    owner = Column(String(255), nullable=True)
    owner_name = Column(String(255), nullable=True)

    category = Column(String(150), nullable=True, index=True)
    categories = Column(JSON, default=list, nullable=True)

    address = Column(Text, nullable=True)
    city = Column(String(100), nullable=True, index=True)
    district = Column(String(100), nullable=True, index=True)
    state = Column(String(100), nullable=True, index=True)
    location = Column(String(255), nullable=True, index=True)

    latitude = Column(Numeric(10, 8), nullable=True)
    longitude = Column(Numeric(11, 8), nullable=True)

    phone = Column(String(20), nullable=True, index=True)
    contact_number = Column(String(50), nullable=True, index=True)
    whatsapp = Column(String(20), nullable=True)
    landline = Column(String(20), nullable=True)
    email = Column(String(255), nullable=True)

    website = Column(String(255), nullable=True)
    facebook = Column(String(255), nullable=True)
    instagram = Column(String(255), nullable=True)
    twitter = Column(String(255), nullable=True)
    youtube = Column(String(255), nullable=True)

    photo_1 = Column(Text, nullable=True)
    photo_2 = Column(Text, nullable=True)
    photo_3 = Column(Text, nullable=True)
    photo_4 = Column(Text, nullable=True)
    photo_5 = Column(Text, nullable=True)
    photo_6 = Column(Text, nullable=True)
    merchant_photos = Column(JSON, default=list, nullable=True)

    about = Column(Text, nullable=True)
    rating = Column(Numeric(3, 2), default=0.0, nullable=True)
    reviews_count = Column(Integer, default=0, nullable=True)
    key_highlights = Column(JSON, default=list, nullable=True)

    video_url = Column(Text, nullable=True)
    merchant_videos = Column(JSON, default=list, nullable=True)

    verification_documents = Column(JSON, default=list, nullable=True)
    services = Column(JSON, default=list, nullable=True)
    service_timing = Column(String(255), default="General Store Hours", nullable=True)

    status = Column(String(50), default="PENDING", nullable=False, index=True)
    approval_status = Column(String(50), default="PENDING", nullable=False, index=True)

    landmark = Column(String(255), nullable=True)
    is_verified = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    rejection_reason = Column(String(500), nullable=True)

    approved_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    onboarded_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

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

    user = relationship("User", foreign_keys=[user_id], backref="merchant_profiles")
    approved_by = relationship("User", foreign_keys=[approved_by_id])
    onboarded_by = relationship("User", foreign_keys=[onboarded_by_id])


@event.listens_for(Session, "before_flush")
def sync_merchant_fields_and_user_codes(session, flush_context, instances):
    new_merchants = [obj for obj in session.new if isinstance(obj, MerchantProfile)]
    for m in new_merchants:
        # 1. Sync aliases
        if not m.owner and m.owner_name:
            m.owner = m.owner_name
        elif not m.owner_name and m.owner:
            m.owner_name = m.owner

        if not m.phone and m.contact_number:
            m.phone = m.contact_number
        elif not m.contact_number and m.phone:
            m.contact_number = m.phone

        if not m.status and m.approval_status:
            m.status = m.approval_status
        elif not m.approval_status and m.status:
            m.approval_status = m.status

        if not m.location:
            m.location = m.city or m.district or m.address or ""

        if not m.category and m.categories and len(m.categories) > 0:
            m.category = str(m.categories[0])
        elif m.category and (not m.categories or len(m.categories) == 0):
            m.categories = [m.category]

        photos = [p for p in [m.photo_1, m.photo_2, m.photo_3, m.photo_4, m.photo_5, m.photo_6] if p]
        if photos and (not m.merchant_photos or len(m.merchant_photos) == 0):
            m.merchant_photos = photos
        elif m.merchant_photos and len(m.merchant_photos) > 0 and not m.photo_1:
            m.photo_1 = m.merchant_photos[0]
            if len(m.merchant_photos) > 1:
                m.photo_2 = m.merchant_photos[1]
            if len(m.merchant_photos) > 2:
                m.photo_3 = m.merchant_photos[2]
            if len(m.merchant_photos) > 3:
                m.photo_4 = m.merchant_photos[3]
            if len(m.merchant_photos) > 4:
                m.photo_5 = m.merchant_photos[4]
            if len(m.merchant_photos) > 5:
                m.photo_6 = m.merchant_photos[5]

        if m.video_url and (not m.merchant_videos or len(m.merchant_videos) == 0):
            m.merchant_videos = [m.video_url]
        elif m.merchant_videos and len(m.merchant_videos) > 0 and not m.video_url:
            m.video_url = m.merchant_videos[0]

        # 2. Assign MRH 1, MRH 2... user_code if not already starting with MRH
        if not m.user_code or not m.user_code.startswith("MRH"):
            try:
                res = session.execute(
                    text("SELECT user_code FROM merchant_profiles WHERE user_code LIKE 'MRH %' OR user_code LIKE 'MRH_%'")
                ).fetchall()
                max_num = 0
                for row in res:
                    code = row[0]
                    if code:
                        digits = "".join(filter(str.isdigit, str(code)))
                        if digits:
                            max_num = max(max_num, int(digits))
                for other in new_merchants:
                    if other is not m and other.user_code:
                        digits = "".join(filter(str.isdigit, str(other.user_code)))
                        if digits:
                            max_num = max(max_num, int(digits))
                m.user_code = f"MRH {max_num + 1}"
            except Exception:
                m.user_code = "MRH 1"
