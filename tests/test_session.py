from app import create_app

USER = {"username": "tester", "password": "Test1234!"}


def make_app(tmp_path):
    return create_app({"TESTING": True, "DATA_DIR": str(tmp_path), "SECRET_KEY": "same"})


def test_session_does_not_survive_restart(tmp_path):
    first = make_app(tmp_path).test_client()
    first.post("/register", data=USER)
    first.post("/login", data=USER)
    assert first.get("/history").status_code == 200

    cookie = first.get_cookie("session")             # same cookie, "restarted" server
    second = make_app(tmp_path).test_client()
    second.set_cookie("session", cookie.value)
    response = second.get("/history")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_login_page_redirects_when_logged_in(client):
    client.post("/register", data=USER)
    client.post("/login", data=USER)
    assert client.get("/login").status_code == 302
    assert client.get("/register").status_code == 302
    assert client.post("/login", data=USER).status_code == 302


def test_cannot_switch_account_without_logout(client):
    client.post("/register", data=USER)
    client.post("/login", data=USER)
    other = {"username": "other", "password": "Test1234!"}
    client.post("/register", data=other)
    client.post("/login", data=other)
    page = client.get("/history")                    # still the first user
    assert page.status_code == 200 and b"tester" in page.data


def test_login_available_again_after_logout(client):
    client.post("/register", data=USER)
    client.post("/login", data=USER)
    client.post("/logout", data={"force": "1"})
    assert client.get("/login").status_code == 200


def test_api_login_and_register_blocked_when_logged_in(client):
    client.post("/api/register", json=USER)
    client.post("/api/login", json=USER)
    assert client.post("/api/login", json=USER).status_code == 409
    assert client.post("/api/register", json=USER).status_code == 409


def test_pages_are_not_cached(client):
    assert "no-store" in client.get("/login").headers["Cache-Control"]