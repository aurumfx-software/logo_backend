import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import bcrypt
import jwt
from app.core.config import settings


# --- Password Hashing ---
def hash_password(password: str) -> str:
    """Securely hash a plain text password using bcrypt."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against its bcrypt hash."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"), hashed_password.encode("utf-8")
        )
    except Exception:
        return False


# --- JWT Helpers ---
def create_token(
    data: Dict[str, Any],
    expires_delta: timedelta,
    token_type: str = "access",
) -> str:
    """Create a signed JWT token with minimal required claims."""
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + expires_delta
    to_encode.update({
        "exp": expire,
        "iat": now,
        "type": token_type,
    })
    encoded_jwt = jwt.encode(
        to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )
    return encoded_jwt


def create_access_token(user_id: int, role: str) -> str:
    """Generate an access token valid for ACCESS_TOKEN_EXPIRE_MINUTES."""
    expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return create_token(
        data={"sub": str(user_id), "role": role},
        expires_delta=expires_delta,
        token_type="access",
    )


def create_refresh_token(user_id: int, role: str) -> str:
    """Generate a refresh token valid for REFRESH_TOKEN_EXPIRE_DAYS."""
    expires_delta = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    return create_token(
        data={"sub": str(user_id), "role": role},
        expires_delta=expires_delta,
        token_type="refresh",
    )


def decode_token(token: str) -> Dict[str, Any]:
    """Decode and validate a JWT token signature and expiry."""
    return jwt.decode(
        token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
    )


# --- OTP Security ---
def generate_numeric_otp(length: int = 6) -> str:
    """Generate a cryptographically secure numeric OTP."""
    range_start = 10 ** (length - 1)
    range_end = (10 ** length) - 1
    return str(secrets.randbelow(range_end - range_start + 1) + range_start)


def hash_otp(otp: str) -> str:
    """Hash an OTP with HMAC-SHA256 using JWT_SECRET_KEY as salt."""
    return hmac.new(
        settings.JWT_SECRET_KEY.encode("utf-8"),
        otp.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_otp_hash(otp: str, hashed_otp: str) -> bool:
    """Securely compare an OTP against its stored hash."""
    expected_hash = hash_otp(otp)
    return hmac.compare_digest(expected_hash, hashed_otp)
