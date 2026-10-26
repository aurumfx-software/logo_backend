import re
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple
from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session
import jwt

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.models.otp import OTPPurpose
from app.db.models.user import User, UserRole
from app.schemas.auth import (
    CustomerRegisterRequest,
    CustomerRegisterResponse,
    RefreshTokenRequest,
    ResetPasswordRequest,
    SafeUserResponse,
    TokenResponse,
    UserLoginRequest,
    UserProfileUpdateRequest,
    UserRegisterRequest,
)
from app.services.otp_service import OTPService
from app.services.wallet_service import WalletService


class AuthService:
    """Service handling registration, authentication, token rotation, and password reset."""

    @staticmethod
    def normalize_phone(phone: str) -> str:
        cleaned = re.sub(r"[\s\-()]", "", phone.strip())
        if cleaned.startswith("+91"):
            cleaned = cleaned[3:]
        elif cleaned.startswith("91") and len(cleaned) > 10:
            cleaned = cleaned[2:]
        return cleaned

    @staticmethod
    def find_user_by_phone(db: Session, phone: str) -> Optional[User]:
        """Look up a user by phone (exact, normalized, +91 prefix, or last 10 digits)."""
        normalized = AuthService.normalize_phone(phone)
        user = db.query(User).filter(
            or_(
                User.phone == normalized,
                User.phone == f"+91 {normalized}",
                User.phone == f"+91{normalized}",
                User.phone == phone.strip(),
            )
        ).first()
        if user:
            return user
        if len(normalized) >= 10:
            tail = normalized[-10:]
            user = (
                db.query(User)
                .filter(User.phone.isnot(None), User.phone.like(f"%{tail}"))
                .first()
            )
        return user

    @staticmethod
    def _stored_password_hash(user: User) -> Optional[str]:
        return user.password_hash or user.password

    @staticmethod
    def _find_user_for_customer_login(
        db: Session, email: Optional[str] = None, phone: Optional[str] = None
    ) -> User:
        user = None
        if email:
            user = db.query(User).filter(User.email == email.strip().lower()).first()
        elif phone:
            user = AuthService.find_user_by_phone(db, phone)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No customer account found with this email or phone.",
            )
        if user.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Please use the admin portal to sign in.",
            )
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is inactive. Please contact support.",
            )
        return user

    @staticmethod
    def customer_login_identifier(email: Optional[str], phone: Optional[str]) -> str:
        if email:
            return email.strip().lower()
        return AuthService.normalize_phone(phone or "")

    @staticmethod
    def send_customer_login_otp(
        db: Session, email: Optional[str] = None, phone: Optional[str] = None
    ) -> Optional[str]:
        user = AuthService._find_user_for_customer_login(db, email=email, phone=phone)
        identifier = AuthService.customer_login_identifier(email, phone or user.phone)
        plain_otp, _ = OTPService.create_otp(
            db=db,
            identifier=identifier,
            purpose=OTPPurpose.CUSTOMER_LOGIN,
        )
        return plain_otp

    @staticmethod
    def verify_customer_login_otp(
        db: Session,
        otp: str,
        email: Optional[str] = None,
        phone: Optional[str] = None,
    ) -> TokenResponse:
        identifier = AuthService.customer_login_identifier(email, phone)
        OTPService.verify_otp(
            db=db,
            identifier=identifier,
            otp=otp,
            purpose=OTPPurpose.CUSTOMER_LOGIN,
        )
        user = AuthService._find_user_for_customer_login(db, email=email, phone=phone)
        user.last_active = datetime.now(timezone.utc)
        user.is_verified = True
        db.commit()
        db.refresh(user)
        return AuthService.generate_token_pair(user)

    @staticmethod
    def authenticate_user_by_phone(db: Session, phone: str, password: str) -> User:
        user = AuthService.find_user_by_phone(db, phone)
        pwd_hash = AuthService._stored_password_hash(user) if user else None
        if not user or not pwd_hash:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid phone or password.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if user.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Please use the admin portal to sign in.",
            )
        if not verify_password(password, pwd_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid phone or password.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is inactive. Please contact support.",
            )
        user.last_active = datetime.now(timezone.utc)
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def register_customer(db: Session, data: CustomerRegisterRequest) -> TokenResponse:
        phone_norm = AuthService.normalize_phone(data.phone)
        existing_phone = db.query(User).filter(User.phone == phone_norm).first()
        if existing_phone:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this mobile number already exists. Please sign in.",
            )

        clean_email: str
        if data.email:
            clean_email = data.email.strip().lower()
            existing_email = db.query(User).filter(User.email == clean_email).first()
            if existing_email:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="An account with this email address already exists. Please sign in or use another email.",
                )
        else:
            clean_email = f"{phone_norm}@customer.logoapp.local"
            suffix = 1
            while db.query(User).filter(User.email == clean_email).first():
                clean_email = f"{phone_norm}_{suffix}@customer.logoapp.local"
                suffix += 1

        hashed_pwd = hash_password(data.password)
        new_user = User(
            name=data.name.strip(),
            email=clean_email,
            phone=phone_norm,
            password=hashed_pwd,
            password_hash=hashed_pwd,
            role=UserRole.CUSTOMER,
            district=data.district.strip() if data.district else None,
            city=data.city.strip() if data.city else None,
            address=f"{data.city.strip() if data.city else ''}, {data.district.strip() if data.district else ''}, Kerala",
            regions=[],
            module_access=[],
            send_email=False,
            status="ACTIVE",
            is_active=True,
            is_verified=False,
        )
        db.add(new_user)
        db.flush()
        try:
            WalletService.ensure_wallet_for_user(db, new_user.id)
        except Exception:
            pass
        db.commit()
        db.refresh(new_user)
        return AuthService.generate_token_pair(new_user)

    @staticmethod
    def register_user(db: Session, user_data: UserRegisterRequest) -> User:
        clean_email = user_data.email.strip().lower()

        # Check duplicate email
        existing_email = db.query(User).filter(User.email == clean_email).first()
        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A user with this email already exists.",
            )

        # Check duplicate phone if provided
        if user_data.phone:
            existing_phone = db.query(User).filter(User.phone == user_data.phone).first()
            if existing_phone:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="A user with this phone number already exists.",
                )

        # Hash password and assign requested role (or default to FIELD_STAFF)
        hashed_pwd = hash_password(user_data.password)
        assigned_role = user_data.role if user_data.role is not None else UserRole.FIELD_STAFF
        user_status = getattr(user_data, "status", "ACTIVE") or "ACTIVE"
        is_active = (user_status.upper() != "INACTIVE")

        new_user = User(
            name=user_data.name.strip(),
            email=clean_email,
            phone=user_data.phone,
            password=hashed_pwd,
            password_hash=hashed_pwd,
            role=assigned_role,
            district=getattr(user_data, "district", None),
            regions=getattr(user_data, "regions", None) or [],
            city=getattr(user_data, "city", None),
            module_access=getattr(user_data, "module_access", None) or [],
            send_email=bool(getattr(user_data, "send_email", False)),
            status=user_status,
            created_by=getattr(user_data, "created_by", None),
            address=user_data.address,
            profile_picture=user_data.profile_picture,
            is_active=is_active,
            is_verified=False,
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return new_user

    @staticmethod
    def update_user_profile(
        db: Session, user: User, update_data: UserProfileUpdateRequest
    ) -> User:
        if update_data.name is not None:
            user.name = update_data.name.strip()
        if update_data.phone is not None:
            if update_data.phone != user.phone:
                existing_phone = (
                    db.query(User).filter(User.phone == update_data.phone).first()
                )
                if existing_phone:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="A user with this phone number already exists.",
                    )
                user.phone = update_data.phone
        if update_data.address is not None:
            user.address = update_data.address
        if update_data.profile_picture is not None:
            user.profile_picture = update_data.profile_picture

        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def authenticate_user(db: Session, login_data: UserLoginRequest) -> User:
        clean_email = login_data.email.strip().lower()
        user = db.query(User).filter(User.email == clean_email).first()

        if not user or not user.password_hash:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not verify_password(login_data.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is inactive. Please contact support.",
            )

        user.last_active = datetime.now(timezone.utc)
        db.commit()
        db.refresh(user)

        return user

    @staticmethod
    def generate_token_pair(user: User) -> TokenResponse:
        role_val = user.role.value if hasattr(user.role, "value") else str(user.role)
        access_token = create_access_token(user_id=user.id, role=role_val)
        refresh_token = create_refresh_token(user_id=user.id, role=role_val)
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            user_code=user.user_code,
            role=role_val,
            user=SafeUserResponse.model_validate(user),
        )

    @staticmethod
    def refresh_access_token(db: Session, token_request: RefreshTokenRequest) -> TokenResponse:
        try:
            payload = decode_token(token_request.refresh_token)
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token has expired. Please login again.",
            )
        except jwt.InvalidTokenError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token.",
            )

        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token provided is not a refresh token.",
            )

        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token claims.",
            )

        user = db.query(User).filter(User.id == int(user_id)).first()
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User inactive or no longer exists.",
            )

        # Generate new token pair
        return AuthService.generate_token_pair(user)

    @staticmethod
    def request_password_reset(db: Session, email: str) -> Optional[str]:
        clean_email = email.strip().lower()
        user = db.query(User).filter(User.email == clean_email).first()
        dev_otp = None
        if user and user.is_active:
            plain_otp, _ = OTPService.create_otp(
                db=db,
                identifier=clean_email,
                purpose=OTPPurpose.PASSWORD_RESET,
            )
            dev_otp = plain_otp
        # Always return safe indication
        return dev_otp

    @staticmethod
    def reset_password(db: Session, reset_data: ResetPasswordRequest) -> None:
        clean_email = reset_data.email.strip().lower()
        # Verify OTP first
        OTPService.verify_otp(
            db=db,
            identifier=clean_email,
            otp=reset_data.otp,
            purpose=OTPPurpose.PASSWORD_RESET,
        )

        user = db.query(User).filter(User.email == clean_email).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found.",
            )

        user.password_hash = hash_password(reset_data.new_password)
        db.commit()
