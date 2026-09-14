from fastapi.testclient import TestClient


def test_health_check(client: TestClient):
    """Test GET /api/v1/health returns ok status and service name."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "LOGO Backend"
