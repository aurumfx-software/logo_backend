from typing import Dict, Optional, Tuple
from fastapi import HTTPException, status
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
    RefreshTokenRequest,
    ResetPasswordRequest,
    SafeUserResponse,
    TokenResponse,
    UserLoginRequest,
    UserProfileUpdateRequest,
    UserRegisterRequest,
)
from app.services.otp_service import OTPService


class AuthService:
    """Service handling registration, authentication, token rotation, and password reset."""

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
        new_user = User(
            name=user_data.name.strip(),
            email=clean_email,
            phone=user_data.phone,
            password_hash=hashed_pwd,
            role=assigned_role,
            address=user_data.address,
            profile_picture=user_data.profile_picture,
            is_active=True,
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
