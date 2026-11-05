from typing import Optional
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "LOGO Backend"
    ENVIRONMENT: str = "development"
    API_V1_STR: str = "/api/v1"

    # CORS — comma-separated origins, or "*" to use CORS_ORIGIN_REGEX (recommended for sslip + dev ports).
    CORS_ORIGINS: str = (
        "https://168.144.18.149.sslip.io:8443,"
        "https://168.144.18.149.sslip.io,"
        "http://168.144.18.149:5173,"
        "http://168.144.18.149:8000,"
        "http://168.144.18.149:8443,"
        "http://localhost:5173,"
        "http://127.0.0.1:5173"
    )
    CORS_ALLOW_CREDENTIALS: bool = True
    # Optional: comma ports or full origins appended to CORS allow list (production .env).
    CORS_EXTRA_ORIGINS: str = ""
    # If set (e.g. 168.144.18.149), adds http://IP:5173|:8000|:8443 to allowed origins.
    SERVER_PUBLIC_IP: str = ""
    # localhost/LAN/public IPv4/sslip.io — any port (Vite :5173, API :8000, nginx :8443).
    CORS_ORIGIN_REGEX: str = (
        r"^https?://("
        r"(localhost|127\.0\.0\.1|\[::1\]|192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3})"
        r"|(?:\d{1,3}\.){3}\d{1,3}"
        r"|([\w.-]*\d+(?:\.\d+){3}\.sslip\.io)"
        r")(:\d+)?$"
    )

    # Database parameters loaded strictly from .env
    DB_USER: str = "postgres"
    DB_PASSWORD: str = "postgres"
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "logo_trial_db"
    DATABASE_URL: Optional[str] = None

    @model_validator(mode="after")
    def assemble_db_connection(self) -> "Settings":
        if not self.DATABASE_URL:
            pwd_part = f":{self.DB_PASSWORD}" if self.DB_PASSWORD else ""
            ssl_part = "?sslmode=require" if ("ondigitalocean.com" in self.DB_HOST or "render.com" in self.DB_HOST) else ""
            self.DATABASE_URL = (
                f"postgresql+psycopg://{self.DB_USER}{pwd_part}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}{ssl_part}"
            )
        else:
            url = self.DATABASE_URL.strip()
            if url.startswith("postgres://"):
                url = url.replace("postgres://", "postgresql+psycopg://", 1)
            elif url.startswith("postgresql://") and not url.startswith("postgresql+psycopg://"):
                url = url.replace("postgresql://", "postgresql+psycopg://", 1)
            if ("ondigitalocean.com" in url or "render.com" in url) and "sslmode" not in url:
                sep = "&" if "?" in url else "?"
                url = f"{url}{sep}sslmode=require"
            self.DATABASE_URL = url
        return self

    # JWT
    JWT_SECRET_KEY: str = "super_secret_jwt_key_change_in_production_min_32_characters"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # OTP
    OTP_EXPIRE_MINUTES: int = 5
    OTP_MAX_ATTEMPTS: int = 3
    # SMS: MSG91 (India) is used when both values are set. Otherwise Twilio is used.
    MSG91_AUTH_KEY: str = ""
    MSG91_TEMPLATE_ID: str = ""
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_FROM_NUMBER: str = ""
    TWILIO_VERIFY_SERVICE_SID: str = ""
    # Email OTP via Resend (https://resend.com).
    RESEND_API_KEY: str = ""
    RESEND_FROM_EMAIL: str = ""
    # Legacy SMTP settings. OTP email uses Resend when RESEND_API_KEY is set.
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""
    SMTP_USE_TLS: bool = True

    # Google OAuth 2.0
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/google/callback"

    # DigitalOcean Spaces / S3
    SPACES_BUCKET: str = ""
    SPACES_REGION: str = "sgp1"
    SPACES_ENDPOINT: str = ""
    SPACES_ACCESS_KEY: str = ""
    SPACES_SECRET_KEY: str = ""

    # Wallet / cashback (percent of sale amount)
    WALLET_CURRENCY: str = "INR"
    CASHBACK_TOTAL_PERCENT: float = 5.0
    CASHBACK_USER_PERCENT: float = 3.0
    CASHBACK_COMPANY_PERCENT: float = 2.0
    SALE_QR_DEFAULT_EXPIRE_MINUTES: int = 30

    # Razorpay (wallet top-up)
    RAZORPAY_KEY_ID: str = ""
    RAZORPAY_KEY_SECRET: str = ""
    RAZORPAY_WEBHOOK_SECRET: str = ""
    WALLET_TOPUP_MIN_AMOUNT: float = 100.0
    WALLET_TOPUP_MAX_AMOUNT: float = 100000.0
    RAZORPAYX_KEY_ID: str = ""
    RAZORPAYX_KEY_SECRET: str = ""
    RAZORPAYX_ACCOUNT_NUMBER: str = ""
    RAZORPAYX_WEBHOOK_SECRET: str = ""

    # Phone / SMS Providers (MSG91 preferred, Twilio fallback)
    MSG91_AUTH_KEY: str = ""
    MSG91_TEMPLATE_ID: str = ""
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_FROM_NUMBER: str = ""

    # Email / SMTP Provider (SendGrid, AWS SES, or custom mail host)
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
