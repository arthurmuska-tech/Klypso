import json

from klypso import create_app
from klypso.database import get_db
from klypso.social_connections import connection_status, tiktok_authorize_url, upsert_connection
from klypso.clips.distribution_intelligence import build_distribution_strategy


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
            db.commit()
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


def test_v20_native_youtube_publish_path(tmp_path, monkeypatch):
    app = make_app(tmp_path)
    media_path = tmp_path / "clip.mp4"
    media_path.write_bytes(b"fake")
    with app.app_context():
        with get_db(app.config["DATABASE_PATH"]) as db:
            cur = db.execute(
                "INSERT INTO users(email,password_hash,display_name) VALUES(?,?,?)",
                ("youtube-v20@example.com", "hash", "YouTube"),
            )
            user_id = cur.lastrowid
            db.execute(
                "INSERT INTO media_files(user_id,original_name,stored_path,mime_type,size_bytes) VALUES(?,?,?,?,?)",
                (user_id, "clip.mp4", str(media_path), "video/mp4", media_path.stat().st_size),
            )
            media_id = db.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
            from klypso.social_connections import upsert_connection
            upsert_connection(db, user_id, "youtube", "access", "refresh", account_name="Test Channel")
            cur = db.execute(
                "INSERT INTO publish_queue(user_id,media_id,platform,scheduled_for,status,title,caption,hashtags) VALUES(?,?,?,'2099-01-01T00:00:00Z','scheduled',?,?,?)",
                (user_id, media_id, "youtube", "Title", "Caption", "#tag"),
            )
            queue_id = cur.lastrowid
            db.commit()
    monkeypatch.setattr("klypso.publisher.ensure_fresh_token", lambda db, connection: "access")
    monkeypatch.setattr(
        "klypso.publisher.youtube_upload",
        lambda *args, **kwargs: {"video_id": "abc123", "url": "https://youtube.com/watch?v=abc123", "status": "published"},
    )
    from klypso.publisher import publish_queue_item
    with app.app_context():
        result = publish_queue_item(queue_id)
        assert result["native"] is True
        assert result["status"] == "published"
        with get_db(app.config["DATABASE_PATH"]) as db:
            row = db.execute("SELECT status,remote_url FROM publish_queue WHERE id=?", (queue_id,)).fetchone()
    assert row["status"] == "published"
    assert row["remote_url"].endswith("abc123")


def test_v20_distribution_strategy_learns_time_and_platform(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        with get_db(app.config["DATABASE_PATH"]) as db:
            cur = db.execute(
                "INSERT INTO users(email,password_hash,display_name) VALUES(?,?,?)",
                ("strategy-v20@example.com", "hash", "Strategy"),
            )
            user_id = cur.lastrowid
            db.execute(
                "INSERT INTO media_files(user_id,original_name,stored_path,mime_type,size_bytes) VALUES(?,?,?,?,?)",
                (user_id, "strategy.mp4", "/tmp/strategy.mp4", "video/mp4", 1),
            )
            media_id = db.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
            for idx, scheduled, platform, views, completion in [
                (1, "2026-09-21T18:00:00Z", "youtube", 10000, 90),
                (2, "2026-09-22T18:00:00Z", "youtube", 9000, 85),
                (3, "2026-09-23T18:00:00Z", "tiktok", 1000, 50),
            ]:
                cur = db.execute(
                    "INSERT INTO publish_queue(user_id,media_id,platform,scheduled_for,status) VALUES(?,?,?,?,'published')",
                    (user_id, media_id, platform, scheduled),
                )
                queue_id = cur.lastrowid
                db.execute(
                    "INSERT INTO clip_metrics(user_id,queue_id,platform,views,likes,comments,shares,completion_rate) VALUES(?,?,?,?,?,?,?,?)",
                    (user_id, queue_id, platform, views, 100, 10, 5, completion),
                )
            db.commit()
            strategy = build_distribution_strategy(db, user_id)
    assert strategy["samples"] == 3
    assert strategy["best_hours"][0]["hour"] == 18
    assert strategy["platforms"][0]["platform"] == "youtube"
