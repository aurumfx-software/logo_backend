import enum
from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, DateTime, Enum, Float, Integer, String, Text, JSON
from app.db.database import Base


class UserRole(str, enum.Enum):
    SUPER_ADMIN = "SUPER_ADMIN"
    ADMIN = "ADMIN"
    FIELD_STAFF = "FIELD_STAFF"
    CUSTOMER = "CUSTOMER"

    @classmethod
    def _missing_(cls, value):
        if isinstance(value, str):
            norm = value.strip().upper().replace(" ", "_").replace("-", "_")
            if norm in ("CUSTOMER", "CLIENT", "CONSUMER", "PUBLIC_USER", "PUBLICUSER", "USER"):
                return cls.CUSTOMER
            if norm in ("SUPERADMIN", "SUPER_ADMIN"):
                return cls.SUPER_ADMIN
            if norm in ("ADMIN", "ADMINISTRATOR"):
                return cls.ADMIN
            if norm in ("FIELDSTAFF", "FIELD_STAFF", "STAFF"):
                return cls.FIELD_STAFF
        return None


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_code = Column(String(50), unique=True, index=True, nullable=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    phone = Column(String(50), unique=True, index=True, nullable=True)
    password = Column(String(255), nullable=True)
    password_hash = Column(String(255), nullable=True)  # stores hashed password
    role = Column(
        Enum(UserRole, name="user_role", native_enum=False),
        default=UserRole.FIELD_STAFF,
        nullable=False,
    )
    district = Column(String(100), nullable=True)
    regions = Column(JSON, default=list, nullable=True)
    city = Column(String(100), nullable=True)
    module_access = Column(JSON, default=list, nullable=True)
    send_email = Column(Boolean, default=False, nullable=False)
    status = Column(String(50), default="ACTIVE", nullable=False)
    last_active = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(String(50), nullable=True)
    address = Column(Text, nullable=True)
    location = Column(String(255), nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    profile_picture = Column(Text, nullable=True)
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


def get_role_prefix(role) -> str:
    if not role:
        return "FLS_"
    r_str = str(role.value if isinstance(role, UserRole) else role).upper()
    if "SUPER" in r_str or r_str == "SUPER_ADMIN":
        return "SAD_"
    elif "ADMIN" in r_str:
        return "ADM_"
    elif "CUSTOMER" in r_str or "CLIENT" in r_str or "USER" in r_str:
        return "CST_"
    else:
        return "FLS_"


from sqlalchemy import event, inspect, text
from sqlalchemy.orm import Session


@event.listens_for(Session, "before_flush")
def assign_user_codes_before_flush(session, flush_context, instances):
    new_users = [obj for obj in session.new if isinstance(obj, User)]
    for user in new_users:
        # Sync password and password_hash
        if user.password_hash and not user.password:
            user.password = user.password_hash
        elif user.password and not user.password_hash:
            user.password_hash = user.password

        # Sync status and is_active
        if user.status and user.status.upper() == "INACTIVE":
            user.is_active = False
        elif user.is_active is False and (not user.status or user.status == "ACTIVE"):
            user.status = "INACTIVE"
        elif not user.status:
            user.status = "ACTIVE" if user.is_active else "INACTIVE"

        if user.regions is None:
            user.regions = []
        if user.module_access is None:
            user.module_access = []
        if user.send_email is None:
            user.send_email = False

        if not user.user_code:
            prefix = get_role_prefix(user.role)
            try:
                res = session.execute(
                    text(f"SELECT user_code FROM users WHERE user_code LIKE '{prefix}%'")
                ).fetchall()
                max_num = 0
                for row in res:
                    code = row[0]
                    if code and code.startswith(prefix):
                        num_str = code[len(prefix):]
                        if num_str.isdigit():
                            max_num = max(max_num, int(num_str))
                for other in new_users:
                    if other is not user and other.user_code and other.user_code.startswith(prefix):
                        num_str = other.user_code[len(prefix):]
                        if num_str.isdigit():
                            max_num = max(max_num, int(num_str))
                user.user_code = f"{prefix}{max_num + 1}"
            except Exception:
                user.user_code = f"{prefix}1"

    for obj in session.dirty:
        if isinstance(obj, User):
            # Sync password and password_hash if modified
            if obj.password_hash and not obj.password:
                obj.password = obj.password_hash
            elif obj.password and not obj.password_hash:
                obj.password_hash = obj.password

            # Sync status and is_active if modified
            if obj.status and obj.status.upper() == "INACTIVE":
                obj.is_active = False
            elif obj.is_active is False and (not obj.status or obj.status == "ACTIVE"):
                obj.status = "INACTIVE"
            elif obj.is_active is True and obj.status == "INACTIVE":
                obj.status = "ACTIVE"

            try:
                state = inspect(obj)
                history = state.get_history("role", True)
                if history.has_changes():
                    prefix = get_role_prefix(obj.role)
                    uid = obj.id or 0
                    res = session.execute(
                        text(f"SELECT user_code FROM users WHERE user_code LIKE '{prefix}%' AND id != {uid}")
                    ).fetchall()
                    max_num = 0
                    for row in res:
                        code = row[0]
                        if code and code.startswith(prefix):
                            num_str = code[len(prefix):]
                            if num_str.isdigit():
                                max_num = max(max_num, int(num_str))
                    obj.user_code = f"{prefix}{max_num + 1}"
            except Exception:
                pass
