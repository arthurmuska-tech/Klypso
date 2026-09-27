import os
import secrets
import time
from functools import wraps
from flask import current_app, request, session
from werkzeug.exceptions import BadRequest


def csrf_token():
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def validate_csrf():
    # The scheduled publishing cron authenticates with its dedicated secret,
    # because it has no browser session/CSRF token.
    if request.path == "/api/publisher/run-due" and request.method == "POST":
        expected_cron = os.getenv("KLYPSO_CRON_SECRET", "").strip()
        received_cron = request.headers.get("X-KLYPSO-CRON-KEY", "").strip()
        if expected_cron and received_cron and secrets.compare_digest(expected_cron, received_cron):
            return
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return
    expected = session.get("csrf_token")
    received = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
    if not expected or not received or not secrets.compare_digest(expected, received):
        raise BadRequest("CSRF token invalide")




def enforce_rate_limit():
    """Apply small endpoint-specific limits to protect auth and expensive AI work."""
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return
    path = request.path
    rules = [
        ("/login", 10, 60),
        ("/register", 5, 60),
        ("/oauth/google/credential", 10, 60),
        ("/resend-code", 4, 300),
        ("/verify-email", 8, 300),
        ("/api/ai/analyze/", 5, 60),
        ("/api/ai/render-clips/", 10, 60),
        ("/api/ai/render-social/", 10, 60),
        ("/api/ai/render-montage/", 10, 60),
        ("/studio/ai-edit", 5, 60),
        ("/api/ai/broll/", 5, 60),
        ("/api/ai/voiceover/", 5, 60),
        ("/api/ai/compose-assets/", 5, 60),
    ]
    rule = next(((limit, window) for prefix, limit, window in rules if path == prefix or path.startswith(prefix)), None)
    if not rule:
        return
    limit, window = rule
    actor = session.get("user_id") or (request.remote_addr or "unknown")
    key = f"{path}:{actor}"
    now = int(time.time())
    from .database import get_db
    with get_db(current_app.config["DATABASE_PATH"]) as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT window_start,hit_count FROM rate_limit_buckets WHERE rate_key=?", (key,)).fetchone()
        if not row or now - int(row["window_start"]) >= window:
            db.execute(
                "INSERT INTO rate_limit_buckets(rate_key,window_start,hit_count) VALUES(?,?,1) ON CONFLICT(rate_key) DO UPDATE SET window_start=excluded.window_start,hit_count=1",
                (key, now),
            )
            db.commit()
            return
        if int(row["hit_count"]) >= limit:
            db.commit()
            from werkzeug.exceptions import TooManyRequests
            raise TooManyRequests("Trop de requêtes. Réessaie dans un instant.")
        db.execute("UPDATE rate_limit_buckets SET hit_count=hit_count+1 WHERE rate_key=?", (key,))
        db.commit()


def register_security(app):
    @app.before_request
    def security_protection():
        enforce_rate_limit()
        validate_csrf()

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' https://accounts.google.com; "
            "img-src 'self' data: https://*.googleusercontent.com; media-src 'self' blob:; frame-src https://accounts.google.com; connect-src 'self' https://accounts.google.com https://oauth2.googleapis.com; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        )
        if not app.debug:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            from flask import redirect, url_for
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)
    return wrapped
