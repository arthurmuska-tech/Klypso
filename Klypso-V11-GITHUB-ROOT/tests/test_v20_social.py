import base64
import json

from klypso import create_app
from klypso.database import get_db
from klypso.social_connections import connection_status, tiktok_authorize_url, upsert_connection


def make_app(tmp_path):
    return create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret",
        "DATABASE_PATH": str(tmp_path / "klypso.sqlite3"),
        "STORAGE_PATH": str(tmp_path / "storage"),
        "SESSION_COOKIE_SECURE": False,
        "PUBLIC_BASE_URL": "http://localhost",
        "GOOGLE_CLIENT_ID": "",
        "GOOGLE_CLIENT_SECRET": "",
        "APPLE_CLIENT_ID": "",
        "APPLE_TEAM_ID": "",
        "APPLE_KEY_ID": "",
        "APPLE_PRIVATE_KEY": "",
    })


def test_v20_social_connection_tokens_are_stored_encrypted(tmp_path, monkeypatch):
    monkeypatch.setenv("TIKTOK_CLIENT_KEY", "client-key")
    app = make_app(tmp_path)
    with app.app_context():
        with get_db(app.config["DATABASE_PATH"]) as db:
            cur = db.execute(
                "INSERT INTO users(email,password_hash,display_name) VALUES(?,?,?)",
                ("social-v20@example.com", "hash", "Social"),
            )
            user_id = cur.lastrowid
            upsert_connection(
                db,
                user_id,
                "tiktok",
                "access-secret",
                "refresh-secret",
                account_id="open-123",
                account_name="Creator",
                scopes="user.info.basic,video.publish",
            )
            row = db.execute(
                "SELECT access_token_enc,refresh_token_enc FROM social_connections WHERE user_id=? AND platform='tiktok'",
                (user_id,),
            ).fetchone()
    assert row["access_token_enc"]
    assert row["refresh_token_enc"]
    assert "access-secret" not in row["access_token_enc"]
    assert "refresh-secret" not in row["refresh_token_enc"]

    with app.app_context():
        with get_db(app.config["DATABASE_PATH"]) as db:
            status = connection_status(db, user_id)
    assert status["tiktok"]["connected"] is True
    assert status["tiktok"]["adapter"] == "oauth"
    assert status["tiktok"]["account_name"] == "Creator"


def test_v20_tiktok_oauth_url_uses_v2_endpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("TIKTOK_CLIENT_KEY", "client-key")
    app = make_app(tmp_path)
    with app.test_request_context("/publisher/connect/tiktok"):
        url = tiktok_authorize_url("https://example.com/callback", "abc123")
    assert url.startswith("https://www.tiktok.com/v2/auth/authorize/?")
    assert "client_key=client-key" in url
    assert "response_type=code" in url
    assert "video.publish" in url
    assert "state=abc123" in url


def test_v20_social_schema_created(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        with get_db(app.config["DATABASE_PATH"]) as db:
            row = db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='social_connections'"
            ).fetchone()
    assert row is not None
