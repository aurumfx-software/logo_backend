"""Shared CORS allow-list used by CORSMiddleware and the ensure-cors HTTP middleware."""

from __future__ import annotations

import re
from typing import List, Pattern

from starlette.responses import Response

from app.core.config import settings

# Any http(s) localhost, LAN, public IPv4, or sslip.io host with optional port.
DEFAULT_ORIGIN_REGEX: Pattern[str] = re.compile(
    r"^https?://("
    r"(localhost|127\.0\.0\.1|\[::1\])"
    r"|(?:\d{1,3}\.){3}\d{1,3}"
    r"|192\.168\.\d{1,3}\.\d{1,3}"
    r"|10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
    r"|(?:[\w.-]*\d+(?:\.\d+){3}\.sslip\.io)"
    r")(:\d+)?$",
    re.IGNORECASE,
)


def _explicit_origins() -> List[str]:
    raw = (settings.CORS_ORIGINS or "").strip()
    origins: List[str] = []
    if raw and raw != "*":
        origins.extend(o.strip() for o in raw.split(",") if o.strip() and o.strip() != "*")

    extra = (settings.CORS_EXTRA_ORIGINS or "").strip()
    if extra:
        origins.extend(o.strip() for o in extra.split(",") if o.strip())

    public_ip = (settings.SERVER_PUBLIC_IP or "").strip()
    if public_ip:
        for port in ("5173", "8000", "8443", "3000", "4173", "443", "80"):
            origins.append(f"http://{public_ip}:{port}")
            origins.append(f"https://{public_ip}:{port}")
        origins.append(f"http://{public_ip}")
        origins.append(f"https://{public_ip}")

    seen: set[str] = set()
    unique: List[str] = []
    for o in origins:
        if o not in seen:
            seen.add(o)
            unique.append(o)
    return unique


def is_origin_allowed(origin: str | None) -> bool:
    if not origin or not str(origin).strip():
        return False
    normalized = str(origin).strip().rstrip("/")
    if normalized in _explicit_origins():
        return True
    if DEFAULT_ORIGIN_REGEX.fullmatch(normalized):
        return True
    env_pattern = (settings.CORS_ORIGIN_REGEX or "").strip()
    if env_pattern:
        try:
            if re.fullmatch(env_pattern, normalized, re.IGNORECASE):
                return True
        except re.error:
            pass
    return False


def apply_cors_headers(response: Response, origin: str) -> None:
    response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Vary"] = "Origin"
    if settings.CORS_ALLOW_CREDENTIALS:
        response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers.setdefault("Access-Control-Expose-Headers", "*")


def cors_middleware_settings() -> dict:
    return {
        "allow_origins": _explicit_origins(),
        "allow_origin_regex": DEFAULT_ORIGIN_REGEX.pattern,
        "allow_credentials": settings.CORS_ALLOW_CREDENTIALS,
    }
