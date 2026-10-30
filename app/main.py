import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_router
from app.core.config import settings
from app.db.database import Base, engine
import app.db.models  # Ensure all SQLAlchemy models are registered


def _cors_settings() -> dict:
    raw = (settings.CORS_ORIGINS or "*").strip()
    origin_regex = (settings.CORS_ORIGIN_REGEX or "").strip() or None
    # Always allow any localhost / 127.0.0.1 port, even when CORS_ORIGINS is a fixed list.
    local_dev = r"https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?"
    if origin_regex:
        inner = origin_regex[1:] if origin_regex.startswith("^") else origin_regex
        inner = inner[:-1] if inner.endswith("$") else inner
        origin_regex = rf"^(?:{inner}|{local_dev})$"
    else:
        origin_regex = rf"^{local_dev}$"

    if raw == "*":
        return {
            "allow_origins": [],
            "allow_origin_regex": origin_regex,
            "allow_credentials": settings.CORS_ALLOW_CREDENTIALS,
        }
    origins = [o.strip() for o in raw.split(",") if o.strip() and o.strip() != "*"]
    return {
        "allow_origins": origins,
        "allow_origin_regex": origin_regex,
        "allow_credentials": settings.CORS_ALLOW_CREDENTIALS,
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio

    from app.services.wallet_ws_manager import wallet_ws_manager

    wallet_ws_manager.bind_event_loop(asyncio.get_running_loop())
    # Ensure all tables exist in PostgreSQL (pgAdmin) on application start
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description="Trial Backend & Authentication API for LOGO — Local Service & Merchant Discovery Platform.",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# CORS must not combine allow_origins=["*"] with allow_credentials=True (browser blocks preflight).
_cors = _cors_settings()


class _PrivateNetworkHeaderMiddleware:
    """Lets Chrome preflights from localhost succeed against this public API."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        request_headers = {
            k.decode("latin1").lower(): v.decode("latin1")
            for k, v in scope.get("headers") or []
        }
        allow_private = request_headers.get("access-control-request-private-network", "").lower() == "true"

        async def send_wrapper(message):
            if allow_private and message.get("type") == "http.response.start":
                headers = list(message.get("headers") or [])
                headers.append((b"access-control-allow-private-network", b"true"))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_wrapper)


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors["allow_origins"],
    allow_origin_regex=_cors["allow_origin_regex"],
    allow_credentials=_cors["allow_credentials"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)
app.add_middleware(_PrivateNetworkHeaderMiddleware)

# Standardized Error Exception Handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    msg = exc.detail if isinstance(exc.detail, str) else "HTTP Exception"
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "message": msg,
            "detail": exc.detail,
            "data": None,
            "errors": [exc.detail] if isinstance(exc.detail, str) else exc.detail,
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Return JSON (so CORSMiddleware can attach headers) instead of plain-text 500."""
    if isinstance(exc, HTTPException):
        raise exc
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "message": "Internal server error",
            "detail": str(exc),
            "data": None,
            "errors": [str(exc)],
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    error_messages = [f"{'.'.join(str(loc) for loc in err['loc'])}: {err['msg']}" for err in errors]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "success": False,
            "message": "Request validation failed",
            "detail": error_messages,
            "data": None,
            "errors": error_messages,
        },
    )


# Ensure upload directories exist and mount static files
os.makedirs(os.path.join("uploads", "avatars"), exist_ok=True)
os.makedirs(os.path.join("uploads", "logos"), exist_ok=True)
os.makedirs(os.path.join("uploads", "merchants", "photos"), exist_ok=True)
os.makedirs(os.path.join("uploads", "merchants", "videos"), exist_ok=True)
os.makedirs(os.path.join("uploads", "merchants", "documents"), exist_ok=True)
os.makedirs(os.path.join("uploads", "categories", "icons"), exist_ok=True)
app.mount("/static", StaticFiles(directory="uploads"), name="static")

# Include v1 API router
app.include_router(api_router, prefix=settings.API_V1_STR)


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=settings.APP_NAME,
        version="1.0.0",
        description="Trial Backend & Authentication API for LOGO — Local Service & Merchant Discovery Platform.",
        routes=app.routes,
    )

    # Ensure Bearer JWT Authentication is visible in Swagger UI
    openapi_schema["components"] = openapi_schema.get("components", {})
    openapi_schema["components"]["securitySchemes"] = {
        "HTTPBearer": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "Enter your Bearer access token received from /api/v1/auth/login",
        }
    }

    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi


@app.get("/", tags=["Root"], include_in_schema=False)
def root():
    return {
        "service": settings.APP_NAME,
        "docs": "/docs",
        "health": f"{settings.API_V1_STR}/health",
    }
