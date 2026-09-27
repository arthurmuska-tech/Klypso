from pathlib import Path

from klypso import create_app
from klypso.database import get_db
from klypso.media import object_storage


def make_app(tmp_path):
    return create_app({
        "TESTING": True,
        "SECRET_KEY": "v22-test-secret",
        "DATABASE_PATH": str(tmp_path / "klypso.sqlite3"),
        "STORAGE_PATH": str(tmp_path / "storage"),
        "SESSION_COOKIE_SECURE": False,
        "S3_BUCKET": "",
        "S3_ACCESS_KEY_ID": "",
        "S3_SECRET_ACCESS_KEY": "",
    })


def test_v22_postgres_sql_placeholder_adapter():
    from klypso.database import _pg_sql
    assert _pg_sql("SELECT * FROM users WHERE id=? AND email=?") == "SELECT * FROM users WHERE id=%s AND email=%s"
    assert _pg_sql("SELECT 'literal ?' WHERE id=?") == "SELECT 'literal ?' WHERE id=%s"


def test_v22_local_storage_is_backward_compatible(tmp_path):
    app = make_app(tmp_path)
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"clip")
    with app.app_context():
        result = object_storage.persist_file(source, 1, "clip.mp4", "video/mp4")
    assert result == str(source)
    assert source.exists()


def test_v22_s3_storage_roundtrip_uses_local_cache(tmp_path, monkeypatch):
    app = make_app(tmp_path)
    app.config.update({
        "S3_BUCKET": "klypso-test",
        "S3_ACCESS_KEY_ID": "key",
        "S3_SECRET_ACCESS_KEY": "secret",
        "S3_REGION": "auto",
        "S3_ENDPOINT_URL": "https://object.example",
    })

    store = {}

    class FakeS3:
        def upload_file(self, filename, bucket, key, ExtraArgs=None):
            store[(bucket, key)] = Path(filename).read_bytes()

        def download_file(self, bucket, key, filename):
            Path(filename).write_bytes(store[(bucket, key)])

        def delete_object(self, Bucket, Key):
            store.pop((Bucket, Key), None)

    monkeypatch.setattr(object_storage, "_client", lambda: FakeS3())

    source = tmp_path / "clip.mp4"
    source.write_bytes(b"shared-clip")
    with app.app_context():
        uri = object_storage.persist_file(source, 42, "clip.mp4", "video/mp4")
        assert uri.startswith("s3://klypso-test/users/42/media/")
        assert not source.exists()

        cached = Path(object_storage.materialize_media_path(uri))
        assert cached.read_bytes() == b"shared-clip"

        object_storage.delete_stored_path(uri)
        assert not store


def test_v22_rate_limit_schema_exists(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        with get_db(app.config["DATABASE_PATH"]) as db:
            row = db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='rate_limit_buckets'"
            ).fetchone()
    assert row is not None
