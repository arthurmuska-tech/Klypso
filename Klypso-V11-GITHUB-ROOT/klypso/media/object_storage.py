"""Optional S3-compatible object storage for KLYPSO media.

When S3_BUCKET + credentials are configured, media is stored outside the web
instance so web services and background workers can share the same objects.
Without those variables, KLYPSO keeps using its local filesystem for development.
"""
from contextlib import contextmanager
import hashlib
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import uuid4

from flask import after_this_request, current_app, send_file


def enabled():
    cfg = current_app.config
    return bool(
        cfg.get("S3_BUCKET")
        and cfg.get("S3_ACCESS_KEY_ID")
        and cfg.get("S3_SECRET_ACCESS_KEY")
    )


def _client():
    import boto3
    cfg = current_app.config
    kwargs = {
        "service_name": "s3",
        "region_name": cfg.get("S3_REGION") or "auto",
        "aws_access_key_id": cfg.get("S3_ACCESS_KEY_ID"),
        "aws_secret_access_key": cfg.get("S3_SECRET_ACCESS_KEY"),
    }
    endpoint = str(cfg.get("S3_ENDPOINT_URL") or "").strip()
    if endpoint:
        kwargs["endpoint_url"] = endpoint
    return boto3.client(**kwargs)


def _bucket():
    return str(current_app.config["S3_BUCKET"]).strip()


def _parse_uri(value):
    raw = str(value or "")
    if not raw.startswith("s3://"):
        return None, None
    rest = raw[5:]
    bucket, _, key = rest.partition("/")
    if not bucket or not key:
        return None, None
    return bucket, key


def _safe_leaf(name):
    leaf = Path(str(name or "media.bin")).name
    return leaf.replace("\\", "_").replace("/", "_")[:140] or "media.bin"


def persist_file(local_path, user_id, original_name, content_type="application/octet-stream"):
    """Upload a local file when object storage is configured and return its stored URI."""
    path = Path(local_path)
    if not path.is_file():
        raise FileNotFoundError(str(path))
    if not enabled():
        return str(path)

    key = f"users/{int(user_id)}/media/{uuid4().hex}-{_safe_leaf(original_name)}"
    _client().upload_file(
        str(path),
        _bucket(),
        key,
        ExtraArgs={"ContentType": str(content_type or "application/octet-stream")},
    )
    path.unlink(missing_ok=True)
    return f"s3://{_bucket()}/{key}"


def materialize_media_path(stored_path):
    """Return a local cache path for a local file or an S3 object."""
    bucket, key = _parse_uri(stored_path)
    if not bucket or not key:
        return str(stored_path)
    if not enabled():
        raise RuntimeError("Le stockage objet est configuré avec un URI S3 mais ses identifiants sont absents.")
    suffix = Path(key).suffix or ".bin"
    cache_root = Path(current_app.config["STORAGE_PATH"]) / "object-cache"
    cache_root.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(str(stored_path).encode("utf-8")).hexdigest()
    target = cache_root / f"{digest}{suffix}"
    if not target.is_file():
        temp = target.with_suffix(target.suffix + ".part")
        try:
            _client().download_file(bucket, key, str(temp))
            temp.replace(target)
        finally:
            temp.unlink(missing_ok=True)
    return str(target)


def delete_stored_path(stored_path):
    bucket, key = _parse_uri(stored_path)
    if bucket and key:
        if enabled():
            _client().delete_object(Bucket=bucket, Key=key)
        return
    path = Path(str(stored_path or ""))
    if path.is_file():
        path.unlink(missing_ok=True)


@contextmanager
def materialize_media(stored_path):
    """Yield a local path for local files or temporarily downloaded S3 objects."""
    bucket, key = _parse_uri(stored_path)
    if not bucket or not key:
        yield str(stored_path)
        return

    suffix = Path(key).suffix or ".bin"
    handle = NamedTemporaryFile(prefix="klypso-media-", suffix=suffix, delete=False)
    temp_path = Path(handle.name)
    handle.close()
    try:
        _client().download_file(bucket, key, str(temp_path))
        yield str(temp_path)
    finally:
        temp_path.unlink(missing_ok=True)


def send_stored_file(stored_path, download_name, mimetype=None):
    bucket, key = _parse_uri(stored_path)
    if not bucket or not key:
        return send_file(stored_path, as_attachment=True, download_name=download_name, mimetype=mimetype)

    handle = NamedTemporaryFile(prefix="klypso-download-", suffix=Path(key).suffix or ".bin", delete=False)
    temp_path = Path(handle.name)
    handle.close()
    _client().download_file(bucket, key, str(temp_path))
    response = send_file(
        str(temp_path),
        as_attachment=True,
        download_name=download_name,
        mimetype=mimetype,
    )

    @after_this_request
    def cleanup(resp):
        temp_path.unlink(missing_ok=True)
        return resp

    return response
