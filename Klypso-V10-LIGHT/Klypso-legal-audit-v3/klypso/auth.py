import re
import shutil
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from .database import get_db

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
auth_bp = Blueprint("auth", __name__)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    cgu = request.form.get("cgu") == "on"
    privacy = request.form.get("privacy") == "on"
    errors = []
    if not EMAIL_RE.match(email):
        errors.append("Adresse e-mail invalide.")
    if len(password) < 8:
        errors.append("Le mot de passe doit contenir au moins 8 caractères.")
    if not cgu or not privacy:
        errors.append("Il faut accepter les CGU et confirmer avoir pris connaissance de la politique de confidentialité.")
    if errors:
        for error in errors:
            flash(error, "error")
        return render_template("register.html"), 400

    now = _utc_now()
    try:
        with get_db(current_app.config["DATABASE_PATH"]) as db:
            cur = db.execute(
                "INSERT INTO users(email,password_hash,trial_started_at) VALUES(?,?,?)",
                (email, generate_password_hash(password), now),
            )
            user_id = cur.lastrowid
            db.execute(
                "INSERT INTO user_consents(user_id,cgu_accepted_at,privacy_accepted_at,cgu_version,privacy_version) VALUES(?,?,?,?,?)",
                (user_id, now, now, current_app.config["CGU_VERSION"], current_app.config["PRIVACY_VERSION"]),
            )
            db.commit()
    except Exception:
        current_app.logger.exception("Account creation failed")
        flash("Impossible de créer ce compte. L'adresse est peut-être déjà utilisée.", "error")
        return render_template("register.html"), 400

    session.clear()
    session["user_id"] = user_id
    session["user_email"] = email
    session["csrf_token"] = __import__("secrets").token_urlsafe(32)
    return redirect(url_for("dashboard"))


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    with get_db(current_app.config["DATABASE_PATH"]) as db:
        user = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    if not user or not check_password_hash(user["password_hash"], password):
        flash("E-mail ou mot de passe incorrect.", "error")
        return render_template("login.html"), 401
    session.clear()
    session["user_id"] = user["id"]
    session["user_email"] = user["email"]
    session["csrf_token"] = __import__("secrets").token_urlsafe(32)
    return redirect(request.args.get("next") or url_for("dashboard"))


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

    # Best-effort cancellation before deleting the local account record.
    if current_app.config["STRIPE_SECRET_KEY"]:
        try:
            import stripe
            stripe.api_key = current_app.config["STRIPE_SECRET_KEY"]
            with get_db(current_app.config["DATABASE_PATH"]) as db:
                user = db.execute("SELECT stripe_customer_id FROM users WHERE id=?", (user_id,)).fetchone()
            if user and user["stripe_customer_id"]:
                subscriptions = stripe.Subscription.list(customer=user["stripe_customer_id"], status="all", limit=100)
                for subscription in subscriptions.data:
                    if subscription.status in {"active", "trialing", "past_due", "unpaid"}:
                        stripe.Subscription.cancel(subscription.id)
        except Exception:
            current_app.logger.exception("Unable to cancel Stripe subscriptions before account deletion")

    with get_db(current_app.config["DATABASE_PATH"]) as db:
        db.execute("DELETE FROM users WHERE id=?", (user_id,))
        db.commit()

    user_folder = (storage_root / "users" / str(user_id)).resolve()
    try:
        user_folder.relative_to(storage_root / "users")
        if user_folder.exists():
            shutil.rmtree(user_folder)
    except (ValueError, OSError):
        current_app.logger.exception("Unable to delete user storage")

    session.clear()
    flash("Compte supprimé. Les fichiers locaux associés ont été supprimés lorsqu'ils étaient accessibles.", "success")
    return redirect(url_for("index"))
