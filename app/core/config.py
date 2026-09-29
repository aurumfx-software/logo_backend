from typing import Optional
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "LOGO Backend"
    ENVIRONMENT: str = "development"
    API_V1_STR: str = "/api/v1"

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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
