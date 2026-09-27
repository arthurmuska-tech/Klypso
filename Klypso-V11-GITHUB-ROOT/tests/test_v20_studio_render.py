from pathlib import Path

from klypso import create_app
from klypso.database import get_db


def make_app(tmp_path):
    return create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret",
        "DATABASE_PATH": str(tmp_path / "klypso.sqlite3"),
        "STORAGE_PATH": str(tmp_path / "storage"),
        "SESSION_COOKIE_SECURE": False,
        "PUBLIC_BASE_URL": "http://localhost",
    })


def test_v20_studio_timeline_renders_to_mp4(tmp_path, monkeypatch):
    app = make_app(tmp_path)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    with app.app_context():
        with get_db(app.config["DATABASE_PATH"]) as db:
            user = db.execute(
                "INSERT INTO users(email,password_hash,display_name) VALUES(?,?,?)",
                ("studio-render@example.com", "hash", "Studio"),
            ).lastrowid
            db.execute("UPDATE users SET plan='ultra',subscription_status='active' WHERE id=?", (user,))
            media = db.execute(
                "INSERT INTO media_files(user_id,original_name,stored_path,mime_type,size_bytes) VALUES(?,?,?,?,?)",
                (user, "source.mp4", str(source), "video/mp4", source.stat().st_size),
            ).lastrowid
            project = db.execute(
                "INSERT INTO projects(user_id,name,timeline_json) VALUES(?,?,?)",
                (user, "Render test", '{"clips":[{"media_id":%d,"start":0,"source_start":0,"duration":2}],"audio_tracks":[],"markers":[],"settings":{"ratio":"9:16"}}' % media),
            ).lastrowid
            db.commit()

    def fake_render(input_path, output_path, candidate, **kwargs):
        Path(output_path).write_bytes(b"mp4-output")
        return None

    monkeypatch.setattr("klypso.studio.render_candidate", fake_render)

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = user
        sess["csrf_token"] = "studio-test-csrf"

    response = client.post(
        f"/api/studio/projects/{project}/render",
        headers={"X-CSRF-Token": "studio-test-csrf"},
        json={"timeline": {"clips": [{"media_id": media, "start": 0, "source_start": 0, "duration": 2}], "audio_tracks": [], "markers": [], "settings": {"ratio": "9:16"}}},
    )
    assert response.status_code == 200, response.get_json()
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["clip_count"] == 1

    with app.app_context():
        with get_db(app.config["DATABASE_PATH"]) as db:
            row = db.execute(
                "SELECT stored_path,status FROM media_files WHERE id=? AND user_id=?",
                (payload["media_id"], user),
            ).fetchone()
    assert row["status"] == "rendered"
    assert Path(row["stored_path"]).is_file()
