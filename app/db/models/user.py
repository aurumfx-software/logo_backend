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

    user_code = Column(String(50), unique=True, index=True, nullable=True)


def get_role_prefix(role) -> str:
    if not role:
        return "FLS_"
    r_str = str(role.value if isinstance(role, UserRole) else role).upper()
    if "SUPER" in r_str or r_str == "SUPER_ADMIN":
        return "SAD_"
    elif "ADMIN" in r_str:
        return "ADM_"
    else:
        return "FLS_"


from sqlalchemy import event, inspect, text
from sqlalchemy.orm import Session


@event.listens_for(Session, "before_flush")
def assign_user_codes_before_flush(session, flush_context, instances):
    new_users = [obj for obj in session.new if isinstance(obj, User)]
    for user in new_users:
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
