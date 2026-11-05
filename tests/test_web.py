def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json == {"status": "ok"}


def test_index(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json["health"] == "/health"


def test_unknown_route_returns_404(client):
    assert client.get("/does-not-exist").status_code == 404

def test_register_missing_fields(client):
    response = client.post("/api/register", json={"username": "tester"})
    assert response.status_code == 400


def test_login_unknown_user(client):
    response = client.post(
        "/api/login", json={"username": "nobody", "password": "wrong"}
    )
    assert response.status_code == 401


def test_audits_requires_login(client):
    assert client.get("/api/audits").status_code == 401