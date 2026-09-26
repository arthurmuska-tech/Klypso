import secrets
from functools import wraps
from flask import request, session
from werkzeug.exceptions import BadRequest


def csrf_token():
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def validate_csrf():
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return
    expected = session.get("csrf_token")
    received = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
    if not expected or not received or not secrets.compare_digest(expected, received):
        raise BadRequest("CSRF token invalide")


def register_security(app):
    @app.before_request
    def csrf_protection():
        validate_csrf()

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; "
            "img-src 'self' data:; media-src 'self' blob:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
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
