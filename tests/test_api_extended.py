def test_list_categories(client):
    response = client.get("/api/categories")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_create_lead_via_api(client):
    payload = {
        "name": "API Test Startup",
        "website": "https://apitest.example.com",
        "description": "Created via API test",
        "city": "Mumbai",
        "state": "Maharashtra",
        "country": "India",
        "lead_score": 60,
        "confidence_score": 0.6,
        "categories": ["Startup"],
        "contacts": [{"type": "EMAIL", "value": "contact@apitest.example.com"}],
        "social_links": [],
        "profiles": [],
        "sources": [],
    }
    response = client.post("/api/leads", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "API Test Startup"
    assert data["lead_score"] == 60


def test_search_leads_api(client):
    payload = {
        "name": "Searchable Co",
        "website": "https://searchable.example.com",
        "city": "Pune",
        "categories": ["SaaS"],
        "contacts": [],
        "social_links": [],
        "profiles": [],
        "sources": [],
    }
    client.post("/api/leads", json=payload)

    response = client.get("/api/leads", params={"query": "Searchable", "city": "Pune"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1


def test_discovery_status(client):
    response = client.get("/api/discovery/status")
    assert response.status_code == 200
    data = response.json()
    assert "is_running" in data
    assert data["is_running"] is False
