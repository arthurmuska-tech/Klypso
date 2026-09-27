from klypso.auth import _create_email_user
from klypso.database import get_db
from klypso import create_app
from klypso import worker


def app_factory(tmp_path):
    return create_app({
        "TESTING": True,
        "SECRET_KEY": "v23-ops-secret",
        "DATABASE_PATH": str(tmp_path / "klypso.sqlite3"),
        "STORAGE_PATH": str(tmp_path / "storage"),
        "SESSION_COOKIE_SECURE": False,
        "REQUIRE_POSTGRES": False,
        "REQUIRE_OBJECT_STORAGE": False,
        "ADMIN_EMAILS": "admin@example.com",
    })


def test_v23_admin_metrics_are_protected(tmp_path):
    app = app_factory(tmp_path)
    with app.app_context():
        user = _create_email_user("admin@example.com")
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = user["id"]
        sess["user_email"] = user["email"]
        sess["csrf_token"] = "csrf"
    response = client.get("/api/admin/metrics")
    assert response.status_code == 200
    assert response.get_json()["metrics"]["users_total"] == 1


def test_v23_non_admin_cannot_read_metrics(tmp_path):
    app = app_factory(tmp_path)
    with app.app_context():
        user = _create_email_user("user@example.com")
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = user["id"]
        sess["user_email"] = user["email"]
        sess["csrf_token"] = "csrf"
    response = client.get("/api/admin/metrics")
    assert response.status_code == 404


def test_v23_worker_claim_increments_attempts(tmp_path):
    app = app_factory(tmp_path)
    with app.app_context():
        user = _create_email_user("worker@example.com")
        with get_db(app.config["DATABASE_PATH"]) as db:
            db.execute(
                "INSERT INTO jobs(user_id,job_type,status,payload_json) VALUES(?,?,?,?)",
                (user["id"], "ai_clip_analysis", "queued", "{}"),
            )
            db.commit()
        job = worker.claim_next_job(app)
        assert job and job["attempts"] == 1
        with get_db(app.config["DATABASE_PATH"]) as db:
            row = db.execute("SELECT attempts,status,heartbeat_at FROM jobs WHERE id=?", (job["id"],)).fetchone()
        assert row["attempts"] == 1
        assert row["status"] == "processing"
        assert row["heartbeat_at"]
