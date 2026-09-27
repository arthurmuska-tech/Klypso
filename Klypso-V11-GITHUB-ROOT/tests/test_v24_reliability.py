from klypso import create_app
from klypso.auth import _create_email_user
from klypso.database import get_db
import klypso.auth as auth_module


def make_app(tmp_path):
    return create_app({
        "TESTING": True,
        "SECRET_KEY": "v24-test-secret",
        "DATABASE_PATH": str(tmp_path / "klypso.sqlite3"),
        "STORAGE_PATH": str(tmp_path / "storage"),
        "SESSION_COOKIE_SECURE": False,
        "PUBLIC_BASE_URL": "https://klypso-test.example",
        "GOOGLE_CLIENT_ID": "google-client",
        "GOOGLE_CLIENT_SECRET": "google-secret",
        "EMAIL_FROM": "noreply@example.com",
    })


def test_v24_otp_send_failure_does_not_destroy_previous_code(tmp_path, monkeypatch):
    app = make_app(tmp_path)
    with app.app_context():
        _create_email_user("otp@example.com")
        monkeypatch.setattr(auth_module, "_send_code", lambda email, code: None)
        auth_module._issue_code("otp@example.com", "login")

        with get_db(app.config["DATABASE_PATH"]) as db:
            first = db.execute(
                "SELECT id,used_at FROM email_codes WHERE email=? ORDER BY id DESC LIMIT 1",
                ("otp@example.com",),
            ).fetchone()

        def fail_send(email, code):
            raise RuntimeError("mail provider unavailable")

        monkeypatch.setattr(auth_module, "_send_code", fail_send)
        try:
            auth_module._issue_code("otp@example.com", "login")
        except RuntimeError:
            pass
        else:
            raise AssertionError("Expected mail failure")

        with get_db(app.config["DATABASE_PATH"]) as db:
            rows = db.execute(
                "SELECT id,used_at FROM email_codes WHERE email=? ORDER BY id DESC",
                ("otp@example.com",),
            ).fetchall()

        assert len(rows) == 1
        assert rows[0]["id"] == first["id"]
        assert rows[0]["used_at"] is None


def test_v24_google_credential_validates_issuer_and_expiry(tmp_path, monkeypatch):
    app = make_app(tmp_path)

    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "aud": "google-client",
                "iss": "https://accounts.google.com",
                "exp": 4102444800,
                "email_verified": "true",
                "sub": "google-sub-1",
                "email": "google@example.com",
                "name": "Google User",
            }

    monkeypatch.setattr(auth_module, "urlopen", lambda *args, **kwargs: None)
    monkeypatch.setattr(auth_module.requests, "get", lambda *args, **kwargs: FakeResponse(), raising=False) if hasattr(auth_module, "requests") else None

    # The endpoint imports requests locally, so patch the module loader path.
    import requests
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: FakeResponse())

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["csrf_token"] = "google-csrf"

    response = client.post(
        "/oauth/google/credential",
        json={"credential": "fake-token"},
        headers={"X-CSRF-Token": "google-csrf"},
    )
    assert response.status_code == 200
    assert response.get_json()["ok"] is True

    with client.session_transaction() as sess:
        assert sess["user_email"] == "google@example.com"


def test_v24_public_discovery_routes(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()

    robots = client.get("/robots.txt")
    assert robots.status_code == 200
    assert "Sitemap:" in robots.get_data(as_text=True)

    sitemap = client.get("/sitemap.xml")
    assert sitemap.status_code == 200
    assert "<urlset" in sitemap.get_data(as_text=True)
    assert "https://klypso-test.example/" in sitemap.get_data(as_text=True)

    verification = client.get("/google5ac38975c108f180.html")
    assert verification.status_code == 200
    assert "google-site-verification:" in verification.get_data(as_text=True)

def test_v24_healthz_exposes_safe_dependency_status(tmp_path):
    app = make_app(tmp_path)
    payload = app.test_client().get("/healthz").get_json()
    assert "google_configured" in payload
    assert "email_configured" in payload
    assert set(payload["media_tools"]) == {"ffmpeg", "ffprobe"}
