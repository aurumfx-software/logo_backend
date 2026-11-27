import os
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, optional_security_scheme, resolve_access_token
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
from app.services.otp_delivery import OTPDeliveryService
from app.services.otp_service import OTPService
from app.services.storage_service import SpacesStorageService

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
    summary="Login with email or login ID",
    description="Customers and merchants sign in with an email or a login ID such as ASH4906, plus their password.",
)
def login(
    login_data: UserLoginRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    user = AuthService.authenticate_user(db=db, login_data=login_data)
    return AuthService.generate_token_pair(user)


@router.post(
    "/switch-back",
    response_model=TokenResponse,
    summary="Return from an impersonated merchant or customer session",
    description="Send the impersonation access token. The response is a normal admin login token.",
)
def switch_back_to_admin(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_security_scheme),
    db: Session = Depends(get_db),
) -> TokenResponse:
    token = resolve_access_token(request, credentials)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return AuthService.switch_back_to_admin(db, token)


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
        "Sends a 6-digit OTP with Resend to the customer's email. "
        "A phone number is used only to find that email."
    ),
)
def customer_login_send_otp(
    req: CustomerLoginOTPSendRequest,
    db: Session = Depends(get_db),
) -> SendOTPResponse:
    plain_otp = AuthService.send_customer_login_otp(
        db=db, email=req.email, phone=req.phone
    )
    target = req.email or "your email"
    dev_otp = plain_otp if OTPDeliveryService.expose_local_code(req.email or req.phone or "") else None
    return SendOTPResponse(
        message=f"OTP sent to {target}. Please check your inbox.",
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


_AVATAR_FIELDS = ("file", "avatar", "image", "profile_picture", "photo")
_AVATAR_TYPES = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
_AVATAR_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def _public_base_url(request: Request) -> str:
    forwarded = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip()
    proto = forwarded or request.url.scheme or "https"
    host = (
        (request.headers.get("x-forwarded-host") or "").split(",")[0].strip()
        or request.headers.get("host")
        or request.url.netloc
    )
    return f"{proto}://{host}".rstrip("/")


def _absolute_avatar_url(request: Request, stored_url: str) -> str:
    if stored_url.startswith("http://") or stored_url.startswith("https://"):
        if stored_url.startswith("http://") and _public_base_url(request).startswith("https://"):
            path = stored_url.split("://", 1)[-1]
            path = path[path.find("/") :] if "/" in path else ""
            if path.startswith("/static/"):
                return f"{_public_base_url(request)}{path}"
        return stored_url
    if stored_url.startswith("/"):
        return f"{_public_base_url(request)}{stored_url}"
    return stored_url


@router.post(
    "/upload-avatar",
    response_model=AvatarUploadResponse,
    summary="Upload user avatar image",
    description=(
        "Uploads a profile picture (JPEG, PNG, WEBP) from the admin site. "
        "Accepts multipart field file, avatar, image, profile_picture, or photo, "
        "or a JSON body with a data-URL image. Returns an absolute image URL."
    ),
)
async def upload_avatar(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AvatarUploadResponse:
    content_type = (request.headers.get("content-type") or "").lower()
    storage = SpacesStorageService()
    avatar_url = None

    if "application/json" in content_type:
        body = await request.json()
        if not isinstance(body, dict):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid avatar payload.")
        raw = next((body.get(name) for name in _AVATAR_FIELDS if body.get(name)), None)
        if not isinstance(raw, str) or not raw.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Send the image as file, avatar, image, or profile_picture.",
            )
        avatar_url = storage.upload_base64_media(raw.strip(), folder="avatars")
    else:
        form = await request.form()
        upload = next((form.get(name) for name in _AVATAR_FIELDS if form.get(name)), None)
        if not hasattr(upload, "read") or not hasattr(upload, "filename"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Send the image as multipart field file, avatar, image, profile_picture, or photo.",
            )
        file_ext = os.path.splitext(upload.filename or "")[1].lower()
        media_type = (upload.content_type or "").split(";")[0].strip().lower()
        if file_ext not in _AVATAR_EXTENSIONS:
            file_ext = _AVATAR_TYPES.get(media_type, "")
        if file_ext not in _AVATAR_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid image format. Allowed formats: JPG, JPEG, PNG, WEBP.",
            )
        upload.filename = f"avatar{file_ext}"
        avatar_url = storage.upload_file(upload, folder="avatars")

    if not avatar_url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Avatar image is empty.")

    avatar_url = _absolute_avatar_url(request, avatar_url)
    current_user.profile_picture = avatar_url

    # If this user is a merchant or has linked merchant profiles, sync photo_1
    try:
        from app.db.models.merchant import MerchantProfile
        merchants = db.query(MerchantProfile).filter(MerchantProfile.user_id == current_user.id).all()
        for m in merchants:
            m.photo_1 = avatar_url
            if hasattr(m, 'profile_picture'):
                m.profile_picture = avatar_url
    except Exception:
        pass

    db.commit()
    db.refresh(current_user)

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
    dev_otp = plain_otp if OTPDeliveryService.expose_local_code(otp_req.email) else None
    return SendOTPResponse(
        message=f"OTP sent to {otp_req.email}. Please check your inbox.",
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
        "Sends a password-reset OTP with Resend to the account email. "
        "A phone number is used only to find that email. "
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
    login_id = AuthService.reset_password(db=db, reset_data=reset_req)
    return GenericMessageResponse(
        message="Password has been reset successfully. You can now log in using your Login ID.",
        login_id=login_id,
    )
