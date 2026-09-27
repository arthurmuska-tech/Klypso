# KLYPSO V15.8 regression matrix
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from klypso import create_app
from klypso import auth as auth_module
from klypso.auth import _create_email_user, _login, _oauth_user
from klypso.database import get_db
from klypso.plans import get_plan, trial_active, trial_ends_at


@pytest.fixture()
def app(tmp_path, monkeypatch):
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret",
        "DATABASE_PATH": str(tmp_path / "klypso.sqlite3"),
        "STORAGE_PATH": str(tmp_path / "storage"),
        "SESSION_COOKIE_SECURE": False,
        "EMAIL_OTP_DEV_LOG_CODE": False,
        "EMAIL_OTP_COOLDOWN_SECONDS": 0,
        "EMAIL_OTP_MAX_PER_HOUR": 100,
        "GOOGLE_CLIENT_ID": "",
        "GOOGLE_CLIENT_SECRET": "",
        "APPLE_CLIENT_ID": "",
        "APPLE_TEAM_ID": "",
        "APPLE_KEY_ID": "",
        "APPLE_PRIVATE_KEY": "",
    })
    app.config["TESTING"] = True
    yield app


@pytest.fixture()
def client(app):
    return app.test_client()


PUBLIC_SCENARIOS = [
    ("homepage", "/", 200),
    ("pricing", "/pricing", 200),
    ("login", "/login", 200),
    ("register", "/register", 200),
    ("health", "/healthz", 200),
    ("dashboard_requires_auth", "/dashboard", 302),
    ("clips_requires_auth", "/clips", 302),
    ("studio_requires_auth", "/studio", 302),
    ("account_requires_auth", "/account", 302),
    ("brand_requires_auth", "/brand-kit", 302),
]


@pytest.mark.parametrize("name,path,expected", PUBLIC_SCENARIOS, ids=[x[0] for x in PUBLIC_SCENARIOS])
def test_surface_scenarios(client, name, path, expected):
    response = client.get(path)
    assert response.status_code == expected
    if expected == 302:
        assert "/login" in response.headers["Location"]
    if name == "homepage":
        assert b"KLYPSO" in response.data
    if name == "health":
        assert response.get_json()["status"] == "ok"


AUTH_SCENARIOS = [
    "invalid_email",
    "missing_cgu",
    "missing_privacy",
    "missing_csrf",
    "wrong_csrf",
    "valid_register_request",
    "pending_register_state",
    "wrong_otp",
    "correct_otp",
    "verified_user",
]


@pytest.mark.parametrize("scenario", AUTH_SCENARIOS, ids=AUTH_SCENARIOS)
def test_auth_scenarios(client, app, scenario, monkeypatch):
    email = "creator@example.com"

    with client.session_transaction() as sess:
        sess["csrf_token"] = "csrf-ok"

    if scenario == "invalid_email":
        r = client.post("/register", data={"email": "not-an-email", "cgu": "on", "privacy": "on", "csrf_token": "csrf-ok"})
        assert r.status_code == 400
    elif scenario == "missing_cgu":
        r = client.post("/register", data={"email": email, "privacy": "on", "csrf_token": "csrf-ok"})
        assert r.status_code == 400
    elif scenario == "missing_privacy":
        r = client.post("/register", data={"email": email, "cgu": "on", "csrf_token": "csrf-ok"})
        assert r.status_code == 400
    elif scenario == "missing_csrf":
        r = client.post("/register", data={"email": email, "cgu": "on", "privacy": "on"})
        assert r.status_code == 400
    elif scenario == "wrong_csrf":
        r = client.post("/register", data={"email": email, "cgu": "on", "privacy": "on", "csrf_token": "wrong"})
        assert r.status_code == 400
    else:
        captured = {}
        monkeypatch.setattr(auth_module, "_send_code", lambda address, code: captured.update(email=address, code=code))
        r = client.post("/register", data={"email": email, "cgu": "on", "privacy": "on", "csrf_token": "csrf-ok"})
        assert r.status_code == 302
        assert r.headers["Location"].endswith("/verify-email")
        if scenario == "valid_register_request":
            assert captured["email"] == email and len(captured["code"]) == 6
        elif scenario == "pending_register_state":
            with client.session_transaction() as sess:
                assert sess["pending_email"] == email
                assert sess["pending_purpose"] == "register"
        elif scenario == "wrong_otp":
            r = client.post("/verify-email", data={"code": "000000", "csrf_token": "csrf-ok"})
            assert r.status_code == 400
        elif scenario in {"correct_otp", "verified_user"}:
            r = client.post("/verify-email", data={"code": captured["code"], "csrf_token": "csrf-ok"})
            assert r.status_code == 302
            assert r.headers["Location"].endswith("/dashboard")
            with get_db(app.config["DATABASE_PATH"]) as db:
                user = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
            assert user is not None
            assert user["email_verified_at"]
            assert user["auth_provider"] == "email"
            if scenario == "verified_user":
                assert user["display_name"] == "creator"


OAUTH_SCENARIOS = [
    "google_create",
    "google_identity",
    "google_profile_name",
    "google_avatar",
    "google_idempotent",
    "same_email_cross_provider",
    "apple_identity",
    "account_displays_profile",
    "login_session_metadata",
    "google_callback",
]


@pytest.mark.parametrize("scenario", OAUTH_SCENARIOS, ids=OAUTH_SCENARIOS)
def test_oauth_and_account_scenarios(client, app, scenario, monkeypatch):
    profile = {"sub": "google-sub-001", "email": "google@example.com", "name": "Google Creator", "picture": "https://example.com/avatar.png"}

    if scenario == "google_create":
        with app.app_context():
            user = _oauth_user("google", profile["sub"], profile["email"], profile)
        assert user["email"] == profile["email"]
        assert user["auth_provider"] == "google"
    elif scenario == "google_identity":
        with app.app_context():
            user = _oauth_user("google", profile["sub"], profile["email"], profile)
            with get_db(app.config["DATABASE_PATH"]) as db:
                row = db.execute("SELECT * FROM oauth_identities WHERE user_id=? AND provider='google'", (user["id"],)).fetchone()
        assert row is not None
    elif scenario == "google_profile_name":
        with app.app_context():
            user = _oauth_user("google", profile["sub"], profile["email"], profile)
        assert user["display_name"] == "Google Creator"
    elif scenario == "google_avatar":
        with app.app_context():
            user = _oauth_user("google", profile["sub"], profile["email"], profile)
        assert user["avatar_url"] == profile["picture"]
    elif scenario == "google_idempotent":
        with app.app_context():
            first = _oauth_user("google", profile["sub"], profile["email"], profile)
            second = _oauth_user("google", profile["sub"], profile["email"], profile)
        assert first["id"] == second["id"]
    elif scenario == "same_email_cross_provider":
        with app.app_context():
            first = _oauth_user("google", profile["sub"], profile["email"], profile)
            second = _oauth_user("apple", "apple-sub-001", profile["email"], {"name": "Apple Creator"})
            with get_db(app.config["DATABASE_PATH"]) as db:
                count = db.execute("SELECT COUNT(*) AS n FROM oauth_identities WHERE user_id=?", (first["id"],)).fetchone()["n"]
        assert second["id"] == first["id"]
        assert count == 2
    elif scenario == "apple_identity":
        with app.app_context():
            user = _oauth_user("apple", "apple-sub-123", "apple@example.com", {"name": "Apple Creator"})
            row = get_db(app.config["DATABASE_PATH"]).__enter__()
            row.close()
        assert user["auth_provider"] == "apple"
    elif scenario == "account_displays_profile":
        with app.app_context():
            user = _oauth_user("google", profile["sub"], profile["email"], profile)
        with client.session_transaction() as sess:
            sess["user_id"] = user["id"]
            sess["user_email"] = user["email"]
            sess["csrf_token"] = "csrf-ok"
        r = client.get("/account")
        assert r.status_code == 200
        assert b"Google Creator" in r.data
    elif scenario == "login_session_metadata":
        with app.app_context():
            user = _oauth_user("google", profile["sub"], profile["email"], profile)
        with app.test_request_context("/"):
            _login(user)
            from flask import session
            assert session["auth_provider"] == "google"
            assert session["user_name"] == "Google Creator"
    elif scenario == "google_callback":
        class FakeGoogleClient:
            def authorize_access_token(self):
                return {"userinfo": profile}

            def userinfo(self):
                return profile

        monkeypatch.setattr(auth_module.oauth, "create_client", lambda name: FakeGoogleClient())
        r = client.get("/oauth/google/callback")
        assert r.status_code == 302
        assert r.headers["Location"].endswith("/dashboard")
        with client.session_transaction() as sess:
            assert sess["user_email"] == profile["email"]


DATA_SECURITY_SCENARIOS = [
    "authenticated_dashboard",
    "logout_requires_csrf",
    "logout_valid_csrf",
    "security_content_type",
    "security_frame",
    "security_referrer",
    "security_permissions",
    "security_csp",
    "security_hsts",
    "delete_cascade",
]


@pytest.mark.parametrize("scenario", DATA_SECURITY_SCENARIOS, ids=DATA_SECURITY_SCENARIOS)
def test_data_security_scenarios(client, app, scenario):
    if scenario == "security_hsts":
        prod = create_app({
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "DATABASE_PATH": str(Path(app.config["DATABASE_PATH"]).with_name("prod.sqlite3")),
            "STORAGE_PATH": str(Path(app.config["STORAGE_PATH"]).with_name("prod-storage")),
            "FLASK_ENV": "production",
            "SESSION_COOKIE_SECURE": True,
            "GOOGLE_CLIENT_ID": "",
            "GOOGLE_CLIENT_SECRET": "",
            "APPLE_CLIENT_ID": "",
            "APPLE_TEAM_ID": "",
            "APPLE_KEY_ID": "",
            "APPLE_PRIVATE_KEY": "",
        })
        r = prod.test_client().get("/healthz")
        assert r.headers["Strict-Transport-Security"].startswith("max-age=")
        return

    with app.app_context():
        user = _create_email_user("security@example.com")
        user_id = user["id"]
        with get_db(app.config["DATABASE_PATH"]) as db:
            db.execute("INSERT INTO projects(user_id,name) VALUES(?,?)", (user_id, "Project test"))
            db.execute("INSERT INTO jobs(user_id,job_type) VALUES(?,?)", (user_id, "clip"))
            db.execute("INSERT INTO media_files(user_id,original_name,stored_path,mime_type,size_bytes) VALUES(?,?,?,?,?)", (user_id, "test.mp4", "storage/test.mp4", "video/mp4", 123))
            db.execute("INSERT INTO clip_feedback(user_id,job_id,candidate_id,decision) VALUES(?,?,?,?)", (user_id, 1, "c1", "keep"))
            db.execute("INSERT INTO credit_transactions(user_id,amount,balance_after,transaction_type) VALUES(?,?,?,?)", (user_id, 3, 3, "test"))
            db.commit()

    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["user_email"] = "security@example.com"
        sess["csrf_token"] = "csrf-ok"

    if scenario == "authenticated_dashboard":
        r = client.get("/dashboard")
        assert r.status_code == 200
    elif scenario == "logout_requires_csrf":
        r = client.post("/logout")
        assert r.status_code == 400
    elif scenario == "logout_valid_csrf":
        r = client.post("/logout", data={"csrf_token": "csrf-ok"})
        assert r.status_code == 302
        assert r.headers["Location"].endswith("/")
    elif scenario == "security_content_type":
        assert client.get("/").headers["X-Content-Type-Options"] == "nosniff"
    elif scenario == "security_frame":
        assert client.get("/").headers["X-Frame-Options"] == "DENY"
    elif scenario == "security_referrer":
        assert client.get("/").headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    elif scenario == "security_permissions":
        assert "camera=()" in client.get("/").headers["Permissions-Policy"]
    elif scenario == "security_csp":
        assert "form-action 'self'" in client.get("/").headers["Content-Security-Policy"]
    elif scenario == "delete_cascade":
        storage_user = Path(app.config["STORAGE_PATH"]) / "users" / str(user_id)
        storage_user.mkdir(parents=True, exist_ok=True)
        (storage_user / "test.mp4").write_bytes(b"test")
        r = client.post("/delete-account", data={"csrf_token": "csrf-ok"})
        assert r.status_code == 302
        with get_db(app.config["DATABASE_PATH"]) as db:
            assert db.execute("SELECT 1 FROM users WHERE id=?", (user_id,)).fetchone() is None
            for table in ["oauth_identities", "user_consents", "projects", "jobs", "media_files", "clip_feedback", "credit_transactions"]:
                assert db.execute(f"SELECT 1 FROM {table} WHERE user_id=?", (user_id,)).fetchone() is None
        assert not storage_user.exists()


PLAN_SCENARIOS = [
    "free_limits",
    "pro_limits",
    "ultra_limits",
    "trial_missing",
    "trial_active",
    "trial_expiry",
    "promo_invalid_range",
    "health_version",
    "no_github_login",
    "theme_gallery",
]


@pytest.mark.parametrize("scenario", PLAN_SCENARIOS, ids=PLAN_SCENARIOS)
def test_plan_and_product_scenarios(client, app, scenario):
    if scenario == "free_limits":
        plan = get_plan("free")
        assert (plan.clips_per_month, plan.daily_credits, plan.max_projects, plan.max_upload_mb) == (15, 3, 2, 512)
    elif scenario == "pro_limits":
        plan = get_plan("pro")
        assert (plan.clips_per_month, plan.daily_credits, plan.max_projects, plan.max_upload_mb) == (100, 12, 20, 2048)
        assert plan.advanced_ai and plan.batch
    elif scenario == "ultra_limits":
        plan = get_plan("ultra")
        assert (plan.clips_per_month, plan.daily_credits, plan.max_projects, plan.max_upload_mb) == (500, 24, 100, 4096)
        assert plan.advanced_ai and plan.studio and plan.batch
    elif scenario == "trial_missing":
        assert not trial_active(None)
        assert trial_ends_at(None) is None
    elif scenario == "trial_active":
        started = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        assert trial_active(started)
    elif scenario == "trial_expiry":
        started = (datetime.now(timezone.utc) - timedelta(days=10, seconds=1)).isoformat()
        assert not trial_active(started)
        assert trial_ends_at(started) is not None
    elif scenario == "promo_invalid_range":
        from klypso.plans import promo_ends_at
        with pytest.raises(ValueError):
            promo_ends_at(datetime.now(timezone.utc).isoformat(), 0)
    elif scenario == "health_version":
        body = client.get("/healthz").get_json()
        assert body["version"] == "15.8.0"
    elif scenario == "no_github_login":
        text = Path(app.root_path).parent.joinpath("templates", "login.html").read_text(encoding="utf-8").lower()
        assert "github" not in text
    elif scenario == "theme_gallery":
        text = Path(app.root_path).parent.joinpath("templates", "account.html").read_text(encoding="utf-8")
        for palette in ["paper", "linen", "clay", "ocean", "forest", "plum", "graphite", "midnight"]:
            assert f'data-palette="{palette}"' in text


V16_SCENARIOS = [
    "profile_update_requires_csrf",
    "profile_update_success",
    "resend_without_pending",
    "verify_page_has_resend",
    "pricing_has_checkout",
    "command_center_exists",
    "clip_library_search_exists",
    "theme_gallery_has_12",
    "oauth_rejects_unverified",
    "oauth_profile_refresh",
]

@pytest.mark.parametrize("scenario", V16_SCENARIOS, ids=V16_SCENARIOS)
def test_v16_surface_scenarios(client, app, scenario):
    if scenario == "profile_update_requires_csrf":
        with get_db(app.config["DATABASE_PATH"]) as db:
            user = _create_email_user("profile@example.com")
        with client.session_transaction() as sess:
            sess["user_id"] = user["id"]; sess["user_email"] = user["email"]; sess["csrf_token"] = "csrf-ok"
        r = client.post("/account/profile", data={"display_name": "New Name"})
        assert r.status_code == 400
    elif scenario == "profile_update_success":
        with get_db(app.config["DATABASE_PATH"]) as db:
            user = _create_email_user("profile2@example.com")
        with client.session_transaction() as sess:
            sess["user_id"] = user["id"]; sess["user_email"] = user["email"]; sess["csrf_token"] = "csrf-ok"
        r = client.post("/account/profile", data={"display_name": "New Name", "csrf_token": "csrf-ok"})
        assert r.status_code == 302
        with get_db(app.config["DATABASE_PATH"]) as db:
            row = db.execute("SELECT display_name FROM users WHERE id=?", (user["id"],)).fetchone()
        assert row["display_name"] == "New Name"
    elif scenario == "resend_without_pending":
        with client.session_transaction() as sess:
            sess["csrf_token"] = "csrf-ok"
        r = client.post("/resend-code", data={"csrf_token": "csrf-ok"})
        assert r.status_code == 302 and "/login" in r.headers["Location"]
    elif scenario == "verify_page_has_resend":
        r = client.get("/verify-email")
        assert r.status_code == 302
        with client.session_transaction() as sess:
            sess["pending_email"] = "x@example.com"; sess["pending_purpose"] = "login"; sess["csrf_token"] = "csrf-ok"
        r = client.get("/verify-email")
        assert r.status_code == 200 and b"Renvoyer un code" in r.data
    elif scenario == "pricing_has_checkout":
        r = client.get("/pricing")
        assert r.status_code == 200
        assert b"Choisir Pro" in r.data and b"Choisir Ultra" in r.data
    elif scenario == "command_center_exists":
        with get_db(app.config["DATABASE_PATH"]) as db:
            user = _create_email_user("cmd@example.com")
        with client.session_transaction() as sess:
            sess["user_id"] = user["id"]; sess["user_email"] = user["email"]; sess["csrf_token"] = "csrf-ok"
        r = client.get("/dashboard")
        assert r.status_code == 200 and b"COMMAND CENTER" in r.data
    elif scenario == "clip_library_search_exists":
        with get_db(app.config["DATABASE_PATH"]) as db:
            user = _create_email_user("clips@example.com")
        with client.session_transaction() as sess:
            sess["user_id"] = user["id"]; sess["user_email"] = user["email"]; sess["csrf_token"] = "csrf-ok"
        r = client.get("/clips")
        assert r.status_code == 200 and b"data-clips-search-toggle" in r.data
    elif scenario == "theme_gallery_has_12":
        textv = Path(app.root_path).parent.joinpath("templates", "account.html").read_text(encoding="utf-8")
        for palette in ["paper","linen","clay","ocean","forest","plum","graphite","midnight","sage","sand","lavender","slate"]:
            assert f'data-palette="{palette}"' in textv
    elif scenario == "oauth_rejects_unverified":
        from klypso.auth import _oauth_user
        with app.app_context(), pytest.raises(ValueError):
            _oauth_user("google", "sub-unverified", "unverified@example.com", {"email_verified": False})
    elif scenario == "oauth_profile_refresh":
        from klypso.auth import _oauth_user
        with app.app_context():
            user = _oauth_user("google", "sub-refresh", "refresh@example.com", {"name": "Old Name", "picture": "https://example.com/old.png"})
            updated = _oauth_user("google", "sub-refresh", "refresh@example.com", {"name": "New Name", "picture": "https://example.com/new.png"})
        assert updated["id"] == user["id"]
        assert updated["display_name"] == "New Name"
        assert updated["avatar_url"] == "https://example.com/new.png"
