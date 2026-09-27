from pathlib import Path

from klypso import create_app
from klypso.auth import _create_email_user
from klypso.clips.pipeline import create_analysis_job
from klypso.database import get_db
from klypso import worker


def make_app(tmp_path):
    return create_app({
        "TESTING": True,
        "SECRET_KEY": "v23-test-secret",
        "DATABASE_PATH": str(tmp_path / "klypso.sqlite3"),
        "STORAGE_PATH": str(tmp_path / "storage"),
        "SESSION_COOKIE_SECURE": False,
        "S3_BUCKET": "",
        "S3_ACCESS_KEY_ID": "",
        "S3_SECRET_ACCESS_KEY": "",
        "REQUIRE_POSTGRES": False,
        "REQUIRE_OBJECT_STORAGE": False,
    })


def test_v23_upload_job_keeps_persisted_uri(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        user = _create_email_user("uri@example.com")
        job_id = create_analysis_job(
            user["id"], 42, "s3://bucket/users/1/media/source.mp4",
            app.config["DATABASE_PATH"], {"mode": "ai_clips"},
        )
        with get_db(app.config["DATABASE_PATH"]) as db:
            row = db.execute("SELECT payload_json FROM jobs WHERE id=?", (job_id,)).fetchone()
        assert "s3://bucket/users/1/media/source.mp4" in row["payload_json"]


def test_v23_job_lease_columns_exist(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        with get_db(app.config["DATABASE_PATH"]) as db:
            columns = {row[1] for row in db.execute("PRAGMA table_info(jobs)").fetchall()}
    assert {"attempts", "locked_at", "heartbeat_at"} <= columns


def test_v23_stale_job_is_recovered(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        user = _create_email_user("stale@example.com")
        job_id = create_analysis_job(
            user["id"], 42, "/tmp/source.mp4",
            app.config["DATABASE_PATH"], {"mode": "ai_clips"},
        )
        with get_db(app.config["DATABASE_PATH"]) as db:
            db.execute(
                "UPDATE jobs SET status='processing',attempts=1,locked_at='2020-01-01T00:00:00+00:00',"
                "heartbeat_at='2020-01-01T00:00:00+00:00' WHERE id=?",
                (job_id,),
            )
            db.commit()
        recovered, failed = worker.recover_stale_jobs(app)
        assert recovered == 1
        assert failed == 0
        with get_db(app.config["DATABASE_PATH"]) as db:
            row = db.execute("SELECT status,locked_at,heartbeat_at FROM jobs WHERE id=?", (job_id,)).fetchone()
        assert row["status"] == "queued"
        assert row["locked_at"] is None
        assert row["heartbeat_at"] is None


def test_v23_readiness_can_require_shared_storage(tmp_path):
    app = make_app(tmp_path)
    app.config["REQUIRE_OBJECT_STORAGE"] = True
    response = app.test_client().get("/readyz")
    assert response.status_code == 503
    assert response.get_json()["status"] == "not_ready"


def test_v23_new_accounts_start_trial(tmp_path, monkeypatch):
    app = make_app(tmp_path)
    monkeypatch.setenv("TRIAL_DAYS", "14")
    with app.app_context():
        user = _create_email_user("trial@example.com")
    assert user["trial_started_at"]
