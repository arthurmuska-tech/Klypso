import hashlib
import re
import secrets
import smtplib
import shutil
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from functools import wraps
from pathlib import Path

from authlib.integrations.flask_client import OAuth
from authlib.jose import jwt
from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from werkzeug.security import generate_password_hash

from .database import get_db

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
auth_bp = Blueprint("auth", __name__)
oauth = OAuth()


def init_oauth(app):
    if app.config["GOOGLE_CLIENT_ID"] and app.config["GOOGLE_CLIENT_SECRET"]:
        oauth.register(
            name="google",
            client_id=app.config["GOOGLE_CLIENT_ID"],
            client_secret=app.config["GOOGLE_CLIENT_SECRET"],
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )
    if app.config["APPLE_CLIENT_ID"] and app.config["APPLE_TEAM_ID"] and app.config["APPLE_KEY_ID"] and app.config["APPLE_PRIVATE_KEY"]:
        now = int(_now().timestamp())
        header = {"alg":"ES256","kid":app.config["APPLE_KEY_ID"]}
        claims = {"iss":app.config["APPLE_TEAM_ID"],"iat":now,"exp":now+86400*180,"aud":"https://appleid.apple.com","sub":app.config["APPLE_CLIENT_ID"]}
        secret = jwt.encode(header, claims, app.config["APPLE_PRIVATE_KEY"]).decode()
        oauth.register(
            name="apple",
            client_id=app.config["APPLE_CLIENT_ID"],
            client_secret=secret,
            server_metadata_url="https://appleid.apple.com/.well-known/openid-configuration",
            client_kwargs={"scope":"openid email name"},
        )


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def _now():
    return datetime.now(timezone.utc)


def _public_callback(endpoint):
    base = (current_app.config.get("PUBLIC_BASE_URL") or "").rstrip("/")
    if base:
        return f"{base}{endpoint}"
    return url_for(endpoint.lstrip("/"), _external=True)


def _iso():
    return _now().isoformat()


def _login(user):
    now = _iso()
    with get_db(current_app.config["DATABASE_PATH"]) as db:
        db.execute("UPDATE users SET last_login_at=?, updated_at=? WHERE id=?", (now, now, user["id"]))
        db.commit()
    session.clear()
    session["user_id"] = user["id"]
    session["user_email"] = user["email"]
    session["user_name"] = user["display_name"] or user["email"].split("@", 1)[0]
    session["auth_provider"] = user["auth_provider"]
    session["csrf_token"] = secrets.token_urlsafe(32)


def _hash_code(code):
    return hashlib.sha256((code + current_app.config["SECRET_KEY"]).encode()).hexdigest()


def _send_code(email, code):
    host = current_app.config["EMAIL_SMTP_HOST"]
    sender = current_app.config["EMAIL_SMTP_FROM"] or current_app.config["EMAIL_SMTP_USER"]
    if not host or not sender:
        if current_app.config["EMAIL_OTP_DEV_LOG_CODE"]:
            current_app.logger.warning("KLYPSO OTP for %s: %s", email, code)
            return
        raise RuntimeError("EMAIL_SMTP_HOST et EMAIL_SMTP_FROM doivent être configurés.")
    msg = EmailMessage()
    msg["Subject"] = "Ton code KLYPSO"
    msg["From"] = sender
    msg["To"] = email
    msg.set_content(
        f"Ton code KLYPSO est : {code}\n\n"
        f"Il est valable {current_app.config['EMAIL_OTP_MINUTES']} minutes."
    )
    with smtplib.SMTP(host, current_app.config["EMAIL_SMTP_PORT"], timeout=20) as smtp:
        if current_app.config["EMAIL_SMTP_TLS"]:
            smtp.starttls()
        if current_app.config["EMAIL_SMTP_USER"]:
            smtp.login(current_app.config["EMAIL_SMTP_USER"], current_app.config["EMAIL_SMTP_PASSWORD"])
        smtp.send_message(msg)


def _issue_code(email, purpose):
    with get_db(current_app.config["DATABASE_PATH"]) as db:
        latest = db.execute(
            "SELECT created_at FROM email_codes WHERE email=? AND purpose=? ORDER BY id DESC LIMIT 1",
            (email, purpose),
        ).fetchone()
        if latest and latest["created_at"]:
            try:
                last = datetime.fromisoformat(latest["created_at"].replace("Z", "+00:00"))
                if (_now() - last).total_seconds() < current_app.config["EMAIL_OTP_COOLDOWN_SECONDS"]:
                    raise RuntimeError("Trop de demandes. Attends quelques secondes avant de redemander un code.")
            except ValueError:
                pass
        recent = db.execute(
            "SELECT COUNT(*) AS count FROM email_codes WHERE email=? AND purpose=? AND created_at >= ?",
            (email, purpose, (_now() - timedelta(hours=1)).isoformat()),
        ).fetchone()
        if recent["count"] >= current_app.config["EMAIL_OTP_MAX_PER_HOUR"]:
            raise RuntimeError("Trop de demandes de code. Réessaie plus tard.")
    code = f"{secrets.randbelow(1000000):06d}"
    expires = _now() + timedelta(minutes=current_app.config["EMAIL_OTP_MINUTES"])
    with get_db(current_app.config["DATABASE_PATH"]) as db:
        db.execute(
            "UPDATE email_codes SET used_at=? WHERE email=? AND purpose=? AND used_at IS NULL",
            (_iso(), email, purpose),
        )
        db.execute(
            "INSERT INTO email_codes(email,purpose,code_hash,expires_at) VALUES(?,?,?,?)",
            (email, purpose, _hash_code(code), expires.isoformat()),
        )
        db.commit()
    _send_code(email, code)


def _verify_code(email, purpose, code):
    if not re.fullmatch(r"\d{6}", code or ""):
        return False
    with get_db(current_app.config["DATABASE_PATH"]) as db:
        row = db.execute(
            "SELECT * FROM email_codes WHERE email=? AND purpose=? AND used_at IS NULL ORDER BY id DESC LIMIT 1",
            (email, purpose),
        ).fetchone()
        if not row or row["attempts"] >= 5:
            return False
        expires = datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00"))
        db.execute("UPDATE email_codes SET attempts=attempts+1 WHERE id=?", (row["id"],))
        if expires < _now() or not secrets.compare_digest(row["code_hash"], _hash_code(code)):
            db.commit()
            return False
        db.execute("UPDATE email_codes SET used_at=? WHERE id=?", (_iso(), row["id"]))
        db.commit()
        return True


def _create_email_user(email):
    now = _iso()
    display_name = email.split("@", 1)[0][:80]
    with get_db(current_app.config["DATABASE_PATH"]) as db:
        cur = db.execute(
            "INSERT INTO users(email,password_hash,auth_provider,email_verified_at,trial_started_at,display_name) VALUES(?,?,?,?,?,?)",
            (email, generate_password_hash(secrets.token_urlsafe(32)), "email", now, None, display_name),
        )
        uid = cur.lastrowid
        db.execute(
            "INSERT INTO user_consents(user_id,cgu_accepted_at,privacy_accepted_at,cgu_version,privacy_version) VALUES(?,?,?,?,?)",
            (uid, now, now, current_app.config["CGU_VERSION"], current_app.config["PRIVACY_VERSION"]),
        )
        db.commit()
        return db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()


def _oauth_user(provider, subject, email, profile=None):
    profile = profile or {}
    if "email_verified" in profile and profile.get("email_verified") is False:
        raise ValueError("L'adresse e-mail du fournisseur OAuth n'est pas vérifiée.")
    email = (email or "").lower().strip()
    display_name = str(profile.get("name") or profile.get("given_name") or email.split("@", 1)[0]).strip()[:80]
    avatar_url = str(profile.get("picture") or "").strip()[:1000] or None
    if not EMAIL_RE.match(email) or not subject:
        raise ValueError("Identité OAuth incomplète.")
    now = _iso()
    with get_db(current_app.config["DATABASE_PATH"]) as db:
        identity = db.execute(
            "SELECT user_id FROM oauth_identities WHERE provider=? AND subject=?",
            (provider, subject),
        ).fetchone()
        if identity:
            uid = identity["user_id"]
            db.execute(
                "UPDATE users SET auth_provider=?,email_verified_at=COALESCE(email_verified_at,?),display_name=COALESCE(NULLIF(?,''),display_name),avatar_url=COALESCE(NULLIF(?,''),avatar_url),updated_at=? WHERE id=?",
                (provider, now, display_name, avatar_url or "", now, uid),
            )
            db.commit()
            return db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        user = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if not user:
            cur = db.execute(
                "INSERT INTO users(email,password_hash,auth_provider,email_verified_at,trial_started_at,display_name,avatar_url) VALUES(?,?,?,?,?,?,?)",
                (email, generate_password_hash(secrets.token_urlsafe(32)), provider, now, None, display_name, avatar_url),
            )
            uid = cur.lastrowid
            db.execute(
                "INSERT INTO user_consents(user_id,cgu_accepted_at,privacy_accepted_at,cgu_version,privacy_version) VALUES(?,?,?,?,?)",
                (uid, now, now, current_app.config["CGU_VERSION"], current_app.config["PRIVACY_VERSION"]),
            )
        else:
            uid = user["id"]
            db.execute(
                "UPDATE users SET auth_provider=?,email_verified_at=COALESCE(email_verified_at,?),display_name=COALESCE(NULLIF(?,''),display_name),avatar_url=COALESCE(NULLIF(?,''),avatar_url),updated_at=? WHERE id=?",
                (provider, now, display_name, avatar_url or "", now, uid),
            )
        db.execute(
            "INSERT INTO oauth_identities(user_id,provider,subject) VALUES(?,?,?)",
            (uid, provider, subject),
        )
        db.commit()
        return db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")
    email = request.form.get("email", "").strip().lower()
    if not EMAIL_RE.match(email):
        flash("Adresse e-mail invalide.", "error")
        return render_template("register.html"), 400
    if request.form.get("cgu") != "on" or request.form.get("privacy") != "on":
        flash("Accepte les CGU et la politique de confidentialité.", "error")
        return render_template("register.html"), 400
    with get_db(current_app.config["DATABASE_PATH"]) as db:
        exists = db.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone()
    if exists:
        flash("Ce compte existe déjà. Utilise la connexion.", "error")
        return redirect(url_for("auth.login"))
    try:
        _issue_code(email, "register")
    except Exception:
        current_app.logger.exception("OTP send failed")
        flash("L'envoi du code n'est pas configuré sur le serveur.", "error")
        return render_template("register.html"), 503
    session["pending_email"] = email
    session["pending_purpose"] = "register"
    return redirect(url_for("auth.verify_email"))


@auth_bp.route("/verify-email", methods=["GET", "POST"])
def verify_email():
    email = session.get("pending_email")
    purpose = session.get("pending_purpose")
    if not email or purpose not in {"register", "login"}:
        return redirect(url_for("auth.login"))
    if request.method == "GET":
        return render_template("verify_email.html", email=email)
    if not _verify_code(email, purpose, request.form.get("code", "").strip()):
        flash("Code invalide ou expiré.", "error")
        return render_template("verify_email.html", email=email), 400
    if purpose == "register":
        user = _create_email_user(email)
    else:
        with get_db(current_app.config["DATABASE_PATH"]) as db:
            user = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
            if not user:
                flash("Compte introuvable.", "error")
                return redirect(url_for("auth.register"))
    session.pop("pending_email", None)
    session.pop("pending_purpose", None)
    _login(user)
    return redirect(url_for("dashboard"))


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")
    email = request.form.get("email", "").strip().lower()
    with get_db(current_app.config["DATABASE_PATH"]) as db:
        exists = db.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone()
    if not EMAIL_RE.match(email) or not exists:
        flash("Aucun compte trouvé avec cette adresse.", "error")
        return render_template("login.html"), 404
    try:
        _issue_code(email, "login")
    except Exception:
        current_app.logger.exception("OTP send failed")
        flash("L'envoi du code n'est pas configuré sur le serveur.", "error")
        return render_template("login.html"), 503
    session["pending_email"] = email
    session["pending_purpose"] = "login"
    return redirect(url_for("auth.verify_email"))


@auth_bp.post("/resend-code")
def resend_code():
    email = session.get("pending_email")
    purpose = session.get("pending_purpose")
    if not email or purpose not in {"register", "login"}:
        return redirect(url_for("auth.login"))
    try:
        _issue_code(email, purpose)
        flash("Un nouveau code a été envoyé.", "success")
    except RuntimeError as exc:
        flash(str(exc), "error")
    except Exception:
        current_app.logger.exception("OTP resend failed")
        flash("Impossible d'envoyer un nouveau code pour le moment.", "error")
    return redirect(url_for("auth.verify_email"))

@auth_bp.get("/oauth/google")
def google_login():
    client = oauth.create_client("google")
    if client is None:
        flash("Google OAuth n'est pas encore configuré sur KLYPSO.", "error")
        return redirect(url_for("auth.login"))
    redirect_uri = _public_callback("/oauth/google/callback")
    return client.authorize_redirect(redirect_uri)


@auth_bp.get("/oauth/apple")
def apple_login():
    client = oauth.create_client("apple")
    if client is None:
        flash("Apple OAuth n'est pas encore configuré sur KLYPSO.", "error")
        return redirect(url_for("auth.login"))
    return client.authorize_redirect(_public_callback("/oauth/apple/callback"))


@auth_bp.get("/oauth/apple/callback")
def apple_callback():
    client = oauth.create_client("apple")
    if client is None:
        return redirect(url_for("auth.login"))
    try:
        token = client.authorize_access_token()
        info = token.get("userinfo") or client.userinfo()
        user = _oauth_user("apple", str(info.get("sub") or ""), info.get("email"), info)
        _login(user)
        return redirect(url_for("dashboard"))
    except Exception:
        current_app.logger.exception("Apple OAuth failed")
        flash("Connexion Apple impossible.", "error")
        return redirect(url_for("auth.login"))


@auth_bp.get("/oauth/google/callback")
def google_callback():
    client = oauth.create_client("google")
    if client is None:
        return redirect(url_for("auth.login"))
    try:
        token = client.authorize_access_token()
        info = token.get("userinfo") or client.userinfo()
        user = _oauth_user("google", str(info.get("sub") or ""), info.get("email"), info)
        _login(user)
        return redirect(url_for("dashboard"))
    except Exception:
        current_app.logger.exception("Google OAuth failed")
        flash("Connexion Google impossible.", "error")
        return redirect(url_for("auth.login"))


@auth_bp.post("/logout")
@login_required
def logout():
    session.clear()
    return redirect(url_for("index"))


@auth_bp.post("/delete-account")
@login_required
def delete_account():
    user_id = session["user_id"]
    storage_root = Path(current_app.config["STORAGE_PATH"]).resolve()
    if current_app.config["STRIPE_SECRET_KEY"]:
        try:
            import stripe
            stripe.api_key = current_app.config["STRIPE_SECRET_KEY"]
            with get_db(current_app.config["DATABASE_PATH"]) as db:
                user = db.execute("SELECT stripe_customer_id FROM users WHERE id=?", (user_id,)).fetchone()
            if user and user["stripe_customer_id"]:
                for sub in stripe.Subscription.list(customer=user["stripe_customer_id"], status="all", limit=100).data:
                    if sub.status in {"active", "trialing", "past_due", "unpaid"}:
                        stripe.Subscription.cancel(sub.id)
        except Exception:
            current_app.logger.exception("Stripe cancellation failed")
    with get_db(current_app.config["DATABASE_PATH"]) as db:
        db.execute("DELETE FROM users WHERE id=?", (user_id,))
        db.commit()
    folder = (storage_root / "users" / str(user_id)).resolve()
    try:
        folder.relative_to(storage_root / "users")
        if folder.exists():
            shutil.rmtree(folder)
    except (ValueError, OSError):
        pass
    session.clear()
    flash("Compte supprimé.", "success")
    return redirect(url_for("index"))
