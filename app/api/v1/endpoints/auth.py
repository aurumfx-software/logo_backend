import os
import shutil
import uuid
from typing import Optional

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, optional_security_scheme, require_role, require_admin
from app.core.config import settings
from app.db.database import get_db
from app.db.models.otp import OTPPurpose
from app.db.models.user import User, UserRole
from app.schemas.auth import (
    AvatarUploadResponse,
    CustomerLoginOTPSendRequest,
    CustomerLoginOTPVerifyRequest,
    ForgotPasswordRequest,
    GenericMessageResponse,
    LogoutRequest,
    LogoutResponse,
    RefreshTokenRequest,
    RegisterResponse,
    ResetPasswordRequest,
    SafeUserResponse,
    SendOTPRequest,
    SendOTPResponse,
    TokenResponse,
    UserLoginRequest,
    UserPhoneLoginRequest,
    UserProfileUpdateRequest,
    UserRegisterRequest,
    VerifyOTPRequest,
    VerifyOTPResponse,
)
from app.services.auth_service import AuthService
from app.services.oauth_service import GoogleOAuthService
from app.services.otp_delivery import OTPDeliveryService
from app.services.otp_service import OTPService

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register new user",
    description="Registers a new user account with the specified role (SUPER_ADMIN, ADMIN, or FIELD_STAFF). If role is omitted, defaults to FIELD_STAFF.",
)
def register(
    user_data: UserRegisterRequest,
    db: Session = Depends(get_db),
) -> RegisterResponse:
    new_user = AuthService.register_user(db=db, user_data=user_data)
    return RegisterResponse(
        message="User registered successfully",
        user=SafeUserResponse.model_validate(new_user),
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login user",
    description="Authenticates credentials and returns JWT access and refresh token pair.",
)
def login(
    login_data: UserLoginRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    user = AuthService.authenticate_user(db=db, login_data=login_data)
    return AuthService.generate_token_pair(user)


@router.post(
    "/login/phone",
    response_model=TokenResponse,
    summary="Customer quick login with phone + password",
    description="Mobile customer sign-in using registered phone number and password.",
)
def login_with_phone(
    login_data: UserPhoneLoginRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    user = AuthService.authenticate_user_by_phone(
        db=db, phone=login_data.phone, password=login_data.password
    )
    return AuthService.generate_token_pair(user)


@router.post(
    "/login/send-otp",
    response_model=SendOTPResponse,
    summary="Customer OTP login — send code",
    description=(
        "Sends a 6-digit OTP to the customer's registered email or phone. "
        "Phone codes are sent by Twilio Verify. Email codes go through SMTP."
    ),
)
def customer_login_send_otp(
    req: CustomerLoginOTPSendRequest,
    db: Session = Depends(get_db),
) -> SendOTPResponse:
    plain_otp = AuthService.send_customer_login_otp(
        db=db, email=req.email, phone=req.phone
    )
    target = req.email or req.phone or "your account"
    dev_otp = plain_otp if OTPDeliveryService.expose_local_code(req.email or req.phone or "") else None
    return SendOTPResponse(
        message=f"OTP sent to {target}. Please check your messages.",
        expires_in_minutes=settings.OTP_EXPIRE_MINUTES,
        dev_otp=dev_otp,
    )


@router.post(
    "/login/verify-otp",
    response_model=TokenResponse,
    summary="Customer OTP login — verify code and get JWT",
    description="Verifies OTP and returns access + refresh tokens for the customer app.",
)
def customer_login_verify_otp(
    req: CustomerLoginOTPVerifyRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    return AuthService.verify_customer_login_otp(
        db=db, otp=req.otp, email=req.email, phone=req.phone
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refresh access token",
    description="Exchanges a valid refresh token for a newly issued access token.",
)
def refresh_token(
    refresh_req: RefreshTokenRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    return AuthService.refresh_access_token(db=db, token_request=refresh_req)


@router.post(
    "/logout",
    response_model=LogoutResponse,
    summary="Logout user",
    description=(
        "Identifies the user from the Bearer access token when one is sent, revokes access "
        "(and optional refresh) tokens, and sets users.logged_out_at. "
        "Missing or expired tokens still return success so the client can clear its session."
    ),
)
def logout(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_security_scheme),
    body: Optional[LogoutRequest] = Body(None),
    db: Session = Depends(get_db),
) -> LogoutResponse:
    access = credentials.credentials if credentials else None
    refresh = body.refresh_token if body else None
    return AuthService.logout_request(db=db, access_token=access, refresh_token=refresh)


@router.get(
    "/me",
    response_model=SafeUserResponse,
    summary="Get current authenticated user profile",
    description="Returns current authenticated user details. Requires Bearer access token. Never exposes password hash.",
)
@router.get(
    "/profile",
    response_model=SafeUserResponse,
    summary="Get current authenticated user profile",
    description=(
        "Alias of GET /auth/me. Returns the authenticated user (name, email, phone, "
        "district, city, address, avatar). Requires Bearer access token."
    ),
)
def get_me(
    current_user: User = Depends(get_current_user),
) -> SafeUserResponse:
    return SafeUserResponse.model_validate(current_user)


@router.put(
    "/profile",
    response_model=SafeUserResponse,
    summary="Update current user profile",
    description="Updates name, email, phone, district, city, address, and profile picture for the authenticated user.",
)
def update_profile(
    update_data: UserProfileUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SafeUserResponse:
    updated_user = AuthService.update_user_profile(
        db=db, user=current_user, update_data=update_data
    )
    return SafeUserResponse.model_validate(updated_user)


@router.post(
    "/upload-avatar",
    response_model=AvatarUploadResponse,
    summary="Upload user avatar image",
    description="Uploads a profile picture (JPEG, PNG, WEBP), saves it securely, and updates the user profile.",
)
def upload_avatar(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AvatarUploadResponse:
    ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
    file_ext = os.path.splitext(file.filename)[1].lower() if file.filename else ""
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid image format. Allowed formats: JPG, JPEG, PNG, WEBP.",
        )

    upload_dir = os.path.join("uploads", "avatars")
    os.makedirs(upload_dir, exist_ok=True)

    unique_filename = f"{uuid.uuid4().hex}{file_ext}"
    file_path = os.path.join(upload_dir, unique_filename)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    avatar_url = f"/static/avatars/{unique_filename}"
    current_user.profile_picture = avatar_url
    db.commit()

    return AvatarUploadResponse(
        message="Profile picture uploaded successfully.",
        profile_picture_url=avatar_url,
    )


@router.post(
    "/send-otp",
    response_model=SendOTPResponse,
    summary="Generate and send OTP",
    description="Generates a secure 6-digit OTP with a 5-minute expiry. Hashed in database.",
)
def send_otp(
    otp_req: SendOTPRequest,
    db: Session = Depends(get_db),
) -> SendOTPResponse:
    plain_otp, _ = OTPService.create_otp(
        db=db,
        identifier=otp_req.email,
        purpose=otp_req.purpose,
    )
    dev_otp = plain_otp if settings.ENVIRONMENT == "development" else None
    return SendOTPResponse(
        message=f"OTP successfully generated for {otp_req.email}.",
        expires_in_minutes=settings.OTP_EXPIRE_MINUTES,
        dev_otp=dev_otp,
    )


@router.post(
    "/verify-otp",
    response_model=VerifyOTPResponse,
    summary="Verify OTP",
    description="Verifies the submitted OTP against stored hash, enforcing expiration and attempt limits.",
)
def verify_otp(
    verify_req: VerifyOTPRequest,
    db: Session = Depends(get_db),
) -> VerifyOTPResponse:
    OTPService.verify_otp(
        db=db,
        identifier=verify_req.email,
        otp=verify_req.otp,
        purpose=verify_req.purpose,
    )

    # If verification is for account verification, update user's is_verified flag
    if verify_req.purpose == OTPPurpose.ACCOUNT_VERIFICATION:
        user = db.query(User).filter(User.email == verify_req.email.strip().lower()).first()
        if user:
            user.is_verified = True
            db.commit()

    return VerifyOTPResponse(
        message="OTP verified successfully.",
        is_verified=True,
    )


@router.post(
    "/forgot-password",
    response_model=SendOTPResponse,
    summary="Request password reset OTP",
    description=(
        "Sends a password-reset OTP to a registered email (SMTP) or phone (Twilio Verify). "
        "The response does not reveal whether the account exists."
    ),
)
def forgot_password(
    forgot_req: ForgotPasswordRequest,
    db: Session = Depends(get_db),
) -> SendOTPResponse:
    dev_otp = AuthService.request_password_reset(
        db=db, email=forgot_req.email, phone=forgot_req.phone
    )
    channel = forgot_req.email or forgot_req.phone or ""
    dev_otp_val = dev_otp if dev_otp and OTPDeliveryService.expose_local_code(channel) else None
    return SendOTPResponse(
        message="If the account is registered, a password reset OTP has been sent.",
        expires_in_minutes=settings.OTP_EXPIRE_MINUTES,
        dev_otp=dev_otp_val,
    )


@router.post(
    "/reset-password",
    response_model=GenericMessageResponse,
    summary="Reset password with OTP",
    description="Resets the user's password after validating the OTP.",
)
def reset_password(
    reset_req: ResetPasswordRequest,
    db: Session = Depends(get_db),
) -> GenericMessageResponse:
    AuthService.reset_password(db=db, reset_data=reset_req)
    return GenericMessageResponse(message="Password has been reset successfully.")


@router.get(
    "/google",
    summary="Google OAuth 2.0 Login URL",
    description="Returns the Google OAuth 2.0 authorization URL for client redirection.",
)
def google_login() -> dict:
    return GoogleOAuthService.get_authorization_url()


@router.get(
    "/google/callback",
    response_model=TokenResponse,
    summary="Google OAuth 2.0 Callback",
    description="Handles OAuth callback from Google, authenticates user, and returns LOGO JWT tokens.",
)
async def google_callback(
    code: str = Query(..., description="Authorization code returned by Google"),
    state: str = Query(..., description="State parameter for CSRF mitigation"),
    db: Session = Depends(get_db),
) -> TokenResponse:
    _, token_pair = await GoogleOAuthService.exchange_code_and_authenticate(
        db=db, code=code
    )
    return token_pair


@router.get(
    "/admin-test",
    response_model=GenericMessageResponse,
    summary="Admin role test endpoint",
    description="Protected endpoint accessible only by users with the ADMIN role.",
)
def admin_only_test(
    admin_user: User = Depends(require_admin),
) -> GenericMessageResponse:
    return GenericMessageResponse(
        message=f"Welcome, Administrator {admin_user.name}. You have verified admin access."
    )
