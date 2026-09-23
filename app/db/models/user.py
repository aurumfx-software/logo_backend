import enum
from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, DateTime, Enum, Integer, String
from app.db.database import Base


class UserRole(str, enum.Enum):
    SUPER_ADMIN = "SUPER_ADMIN"
    ADMIN = "ADMIN"
    FIELD_STAFF = "FIELD_STAFF"

    @classmethod
    def _missing_(cls, value):
        if isinstance(value, str):
            norm = value.strip().upper().replace(" ", "_").replace("-", "_")
            if norm in ("PUBLIC_USER", "PUBLICUSER", "USER", "FIELDSTAFF"):
                return cls.FIELD_STAFF
            if norm in ("SUPERADMIN", "SUPER_ADMIN"):
                return cls.SUPER_ADMIN
            if norm in ("ADMIN", "ADMINISTRATOR"):
                return cls.ADMIN
        return None


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    phone = Column(String(50), unique=True, index=True, nullable=True)
    password_hash = Column(String(255), nullable=True)  # nullable for OAuth users
    role = Column(
        Enum(UserRole, name="user_role", native_enum=False),
        default=UserRole.FIELD_STAFF,
        nullable=False,
    )
    address = Column(String(500), nullable=True)
    profile_picture = Column(String(500), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
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

    @property
    def user_code(self) -> str:
        """Returns standard formatted user code, e.g. USR000001."""
        return f"USR{self.id:06d}" if self.id is not None else ""
