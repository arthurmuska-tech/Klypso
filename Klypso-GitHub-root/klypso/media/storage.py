from pathlib import Path
from uuid import uuid4
from werkzeug.utils import secure_filename

ALLOWED_EXTENSIONS = {"mp4", "mov", "mkv", "webm", "m4v"}
ALLOWED_MIMES = {"video/mp4", "video/quicktime", "video/x-matroska", "video/webm", "video/x-m4v"}


def safe_media_name(original_name):
    cleaned = secure_filename(original_name or "video")
    suffix = Path(cleaned).suffix.lower().lstrip(".")
    if suffix not in ALLOWED_EXTENSIONS:
        raise ValueError("Format vidéo non autorisé.")
    return f"{uuid4().hex}.{suffix}"


def is_allowed_mime(mime):
    return mime in ALLOWED_MIMES
