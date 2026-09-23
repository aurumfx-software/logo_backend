import secrets
from typing import Dict, Any, Tuple
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models.user import User, UserRole
from app.schemas.auth import TokenResponse
from app.services.auth_service import AuthService


GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"


class GoogleOAuthService:
    """Service implementing the Google OAuth 2.0 authentication flow."""

    @staticmethod
    def is_configured() -> bool:
        """Check if Google OAuth credentials have been populated in environment."""
        return bool(
            settings.GOOGLE_CLIENT_ID
            and settings.GOOGLE_CLIENT_SECRET
            and settings.GOOGLE_CLIENT_ID.strip() != ""
            and settings.GOOGLE_CLIENT_SECRET.strip() != ""
        )

    @classmethod
    def get_authorization_url(cls) -> Dict[str, str]:
        """Generate Google OAuth 2.0 authorization URL."""
        if not cls.is_configured():
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail=(
                    "Google OAuth is not configured. Please set GOOGLE_CLIENT_ID "
                    "and GOOGLE_CLIENT_SECRET in your .env file."
                ),
            )

        state = secrets.token_urlsafe(32)
        params = {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "redirect_uri": settings.GOOGLE_REDIRECT_URI,
            "response_type": "code",
            "scope": "openid email profile",
            "access_type": "offline",
            "state": state,
            "prompt": "select_account",
        }
        auth_url = f"{GOOGLE_AUTH_URL}?{urlencode(params)}"
        return {"authorization_url": auth_url, "state": state}

    @classmethod
    async def exchange_code_and_authenticate(
        cls, db: Session, code: str
    ) -> Tuple[User, TokenResponse]:
        """Exchange Google auth code, fetch verified email, and issue LOGO JWT."""
        if not cls.is_configured():
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="Google OAuth is not configured in .env.",
            )

        # Exchange code for access token with Google
        async with httpx.AsyncClient(timeout=10.0) as client:
            token_response = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                    "grant_type": "authorization_code",
                },
            )

            if token_response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to authenticate with Google. Invalid authorization code.",
                )

            google_tokens = token_response.json()
            google_access_token = google_tokens.get("access_token")

            # Fetch user profile info from Google
            userinfo_response = await client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {google_access_token}"},
            )

            if userinfo_response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to retrieve profile from Google.",
                )

            user_info = userinfo_response.json()

        email = user_info.get("email")
        if not email or not user_info.get("verified_email", False):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google account does not have a verified email address.",
            )

        clean_email = email.strip().lower()
        name = user_info.get("name") or clean_email.split("@")[0]

        # Check if user already exists
        user = db.query(User).filter(User.email == clean_email).first()
        if not user:
            # Create new user with FIELD_STAFF role
            user = User(
                name=name,
                email=clean_email,
                phone=None,
                password_hash=None,  # OAuth users have no password hash
                role=UserRole.FIELD_STAFF,
                profile_picture=user_info.get("picture"),
                is_active=True,
                is_verified=True,  # Verified by Google
            )
            db.add(user)
            db.commit()
            db.refresh(user)

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is inactive.",
            )

        # Generate LOGO's own JWT token pair (NOT Google's token)
        token_pair = AuthService.generate_token_pair(user)
        return user, token_pair
