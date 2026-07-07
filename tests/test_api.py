def test_health_check(client):
    """Verify that the health check endpoint returns success status."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["api"] == "ok"
    assert data["database"] == "connected"

def test_root_endpoint(client):
    """Verify that the root endpoint responds with a welcome message."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert "platform api" in data["message"].lower()
