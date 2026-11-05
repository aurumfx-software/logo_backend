from fastapi.testclient import TestClient


def test_health_check(client: TestClient):
    """Test GET /api/v1/health returns ok status and service name."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "LOGO Backend"


def test_cors_preflight_allows_browser_origin(client: TestClient):
    response = client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") in (
        "http://localhost:5173",
        "*",
    )


def test_cors_preflight_public_ip_frontend(client: TestClient):
    """Frontend on http://168.144.18.149:5173 calling API on :8000 must pass OPTIONS."""
    origin = "http://168.144.18.149:5173"
    response = client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,authorization",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == origin
    assert "POST" in (response.headers.get("access-control-allow-methods") or "")


def test_cors_preflight_sslip_frontend_port(client: TestClient):
    origin = "https://168.144.18.149.sslip.io:8443"
    response = client.options(
        "/api/v1/health",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization, content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == origin
    allow_headers = (response.headers.get("access-control-allow-headers") or "").lower()
    assert "authorization" in allow_headers
