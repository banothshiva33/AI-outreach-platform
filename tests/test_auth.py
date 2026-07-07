def test_api_key_required_when_configured(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "API_KEY", "test-secret-key")
    response = client.get("/api/leads")
    assert response.status_code == 401

    authed = client.get("/api/leads", headers={"X-API-Key": "test-secret-key"})
    assert authed.status_code == 200
