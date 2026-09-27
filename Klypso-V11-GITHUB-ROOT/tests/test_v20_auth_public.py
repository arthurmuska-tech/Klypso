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


def test_v20_auth_pages_expose_google_and_no_apple(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    for path in ["/login", "/register"]:
        html = client.get(path).get_data(as_text=True)
        assert "Google" in html
        assert "Apple" not in html
        assert "mot de passe" in html.lower()


def test_v20_email_password_registration_and_login(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["csrf_token"] = "auth-csrf"
    payload = {
        "email": "creator@example.com",
        "password": "secure-pass-123",
        "cgu": "on",
        "privacy": "on",
        "csrf_token": "auth-csrf",
    }
    response = client.post("/register", data=payload)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/dashboard")

    client.post("/logout", data={"csrf_token": "auth-csrf"})
    with client.session_transaction() as sess:
        sess["csrf_token"] = "auth-csrf-2"
    response = client.post("/login", data={
        "email": "creator@example.com",
        "password": "secure-pass-123",
        "csrf_token": "auth-csrf-2",
    })
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/dashboard")

    with client.session_transaction() as sess:
        fresh_csrf = sess["csrf_token"]
    wrong = client.post("/login", data={
        "email": "creator@example.com",
        "password": "bad-password",
        "csrf_token": fresh_csrf,
    })
    assert wrong.status_code == 401


def test_v20_public_home_has_product_sections(tmp_path):
    app = make_app(tmp_path)
    response = app.test_client().get("/")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    for marker in ["STUDIO", "CLIPS IA", "BRAND KIT", "PUBLICATION", "QUESTIONS FRÉQUENTES"]:
        assert marker in html


def test_v22_google_csp_allows_identity_services(tmp_path):
    app = make_app(tmp_path)
    response = app.test_client().get("/login")
    csp = response.headers["Content-Security-Policy"]
    assert "https://accounts.google.com" in csp
    assert "https://oauth2.googleapis.com" in csp
    assert "frame-src https://accounts.google.com" in csp


def test_v22_studio_is_server_gated_to_ultra(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        user = __import__("klypso.auth", fromlist=["_create_email_user"])._create_email_user("studio-free@example.com")
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = user["id"]
        sess["user_email"] = user["email"]
        sess["csrf_token"] = "studio-free-csrf"
    response = client.get("/studio")
    assert response.status_code == 302
    assert "pricing" in response.headers["Location"]


def test_v22_ai_analysis_is_queued(tmp_path, monkeypatch):
    from klypso.auth import _create_email_user
    from klypso.database import get_db
    import klypso.ai_api as ai_api

    app = make_app(tmp_path)
    with app.app_context():
        user = _create_email_user("queue@example.com")
        with get_db(app.config["DATABASE_PATH"]) as db:
            db.execute("UPDATE users SET plan='pro',subscription_status='active' WHERE id=?", (user["id"],))
            cur = db.execute(
                "INSERT INTO jobs(user_id,job_type,status,payload_json) VALUES(?,?,?,?)",
                (user["id"], "ai_clip_analysis", "queued", '{"path":"/tmp/nope.mp4","mode":"ai_clips"}'),
            )
            db.commit()
            job_id = cur.lastrowid

    submitted = {}
    monkeypatch.setattr(ai_api._ANALYSIS_EXECUTOR, "submit", lambda fn, app, user_id, jid: submitted.update(job_id=jid))
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = user["id"]
        sess["user_email"] = user["email"]
        sess["csrf_token"] = "queue-csrf"

    response = client.post(f"/api/ai/analyze/{job_id}", headers={"X-CSRF-Token":"queue-csrf"})
    assert response.status_code == 202
    assert submitted["job_id"] == job_id
    assert response.get_json()["status"] == "processing"
    status = client.get(f"/api/ai/analyze/status/{job_id}")
    assert status.status_code == 202
    assert status.get_json()["status"] == "processing"


def test_v22_postgres_placeholder_adapter():
    import klypso.database as database
    assert database._pg_sql("SELECT * FROM users WHERE id=? AND email=?") == "SELECT * FROM users WHERE id=%s AND email=%s"
    assert database._pg_sql("SELECT 'literal ?' AS value WHERE id=?") == "SELECT 'literal ?' AS value WHERE id=%s"
