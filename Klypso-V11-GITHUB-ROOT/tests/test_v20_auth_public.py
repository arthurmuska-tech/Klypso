from klypso import create_app
from klypso import auth as auth_module


def make_app(tmp_path):
    return create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret",
        "DATABASE_PATH": str(tmp_path / "klypso.sqlite3"),
        "STORAGE_PATH": str(tmp_path / "storage"),
        "SESSION_COOKIE_SECURE": False,
        "PUBLIC_BASE_URL": "https://klypso-test.example",
        "GOOGLE_CLIENT_ID": "google-client",
        "GOOGLE_CLIENT_SECRET": "google-secret",
    })


def test_v20_google_oauth_uses_public_base_url(tmp_path, monkeypatch):
    app = make_app(tmp_path)
    captured = {}

    class FakeClient:
        def authorize_redirect(self, redirect_uri):
            captured["redirect_uri"] = redirect_uri
            return "REDIRECT"

    monkeypatch.setattr(auth_module.oauth, "create_client", lambda name: FakeClient())
    with app.test_request_context("/oauth/google"):
        response = auth_module.google_login()
    assert captured["redirect_uri"] == "https://klypso-test.example/oauth/google/callback"
    assert response == "REDIRECT"


def test_v20_email_password_registration_and_login(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    payload = {
        "email": "creator@example.com",
        "password": "secure-pass-123",
        "cgu": "on",
        "privacy": "on",
    }
    response = client.post("/register", data=payload)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/dashboard")

    client.post("/logout")
    response = client.post("/login", data={
        "email": "creator@example.com",
        "password": "secure-pass-123",
    })
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/dashboard")

    wrong = client.post("/login", data={
        "email": "creator@example.com",
        "password": "bad-password",
    })
    assert wrong.status_code == 401


def test_v20_public_home_has_product_sections(tmp_path):
    app = make_app(tmp_path)
    response = app.test_client().get("/")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    for marker in ["STUDIO", "CLIPS IA", "BRAND KIT", "PUBLICATION", "QUESTIONS FRÉQUENTES"]:
        assert marker in html
