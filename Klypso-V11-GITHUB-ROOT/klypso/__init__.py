from pathlib import Path
import json
from flask import Flask, render_template, redirect, url_for
from werkzeug.middleware.proxy_fix import ProxyFix
from .config import Config
from .database import init_db, get_db
from .auth import auth_bp, login_required, init_oauth
from .legal import legal_bp
from .promo import promo_bp
from .billing import billing_bp
from .clips import clips_bp
from .studio import studio_bp
from .ai_api import ai_bp
from .publisher import publisher_bp
from .security import register_security, csrf_token
from .promo import effective_plan_key
from .plans import get_plan
from .credits import get_credit_state


def create_app(test_config=None):
    app = Flask(__name__, template_folder="../templates", static_folder="../static", static_url_path="/static")
    # Render terminates TLS at the proxy; trust the forwarded scheme/host for absolute OAuth URLs.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)
    Path(app.config["DATABASE_PATH"]).parent.mkdir(parents=True, exist_ok=True)
    Path(app.config["STORAGE_PATH"]).mkdir(parents=True, exist_ok=True)
    init_db(app.config["DATABASE_PATH"])
    register_security(app)
    init_oauth(app)
    app.register_blueprint(auth_bp)
    app.register_blueprint(legal_bp)
    app.register_blueprint(promo_bp)
    app.register_blueprint(billing_bp)
    app.register_blueprint(clips_bp)
    app.register_blueprint(studio_bp)
    app.register_blueprint(ai_bp)
    app.register_blueprint(publisher_bp)

    @app.context_processor
    def inject_globals():
        from flask import session
        user = None
        plan = get_plan("free")
        if session.get("user_id"):
            try:
                with get_db(app.config["DATABASE_PATH"]) as db:
                    user = db.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
                if user:
                    plan = get_plan(effective_plan_key(user))
            except Exception:
                app.logger.exception("Unable to load workspace context")
        return {
            "current_user": session.get("user_email"),
            "current_display_name": session.get("user_name"),
            "current_auth_provider": session.get("auth_provider"),
            "csrf_token": csrf_token,
            "public_base_url": app.config["PUBLIC_BASE_URL"],
            "current_plan": plan,
        }

    @app.route("/")
    def index():
        # The root URL is the public presentation page. Logged-in users go straight to their workspace.
        if session_user_id():
            return redirect(url_for("dashboard"))
        return render_template("index.html")

    @app.route("/healthz")
    def healthz():
        version_file = Path(app.root_path).parent / "VERSION"
        version = version_file.read_text(encoding="utf-8").strip() if version_file.exists() else "unknown"
        return {"status": "ok", "service": "klypso", "version": version}, 200

    @app.route("/demo")
    def public_demo():
        return render_template("demo.html")

    @app.route("/dashboard")
    @login_required
    def dashboard():
        from flask import flash, session
        try:
            with get_db(app.config["DATABASE_PATH"]) as db:
                user = db.execute("SELECT * FROM users WHERE id=?", (session_user_id(),)).fetchone()
                jobs = db.execute(
                    "SELECT * FROM jobs WHERE user_id=? ORDER BY id DESC LIMIT 8",
                    (session_user_id(),),
                ).fetchall()
                creator_profile = db.execute(
                    "SELECT profile_json,updated_at FROM creator_ai_profiles WHERE user_id=?",
                    (session_user_id(),),
                ).fetchone()
        except Exception:
            app.logger.exception("Unable to load dashboard data")
            return render_template("errors/500.html"), 500
        if user is None:
            session.clear()
            flash("Ta session a expiré. Reconnecte-toi pour revenir à ton espace.", "error")
            return redirect(url_for("auth.login"))
        plan_key = effective_plan_key(user)
        try:
            credits = get_credit_state(user["id"], plan_key)
        except Exception:
            # L'accueil ne doit pas tomber sur la page 500 à cause d'un état de crédits.
            # On affiche un état neutre et laisse les pages de crédits gérer leur propre synchronisation.
            app.logger.exception("Unable to load credit state for dashboard")
            plan = get_plan(plan_key)
            credits = {
                "balance": 0,
                "daily_credits": plan.daily_credits,
                "bank_cap": plan.credit_bank_cap,
                "monthly_clip_count": 0,
                "monthly_clip_limit": plan.clips_per_month,
            }
        creator_dna = {}
        if creator_profile:
            try:
                creator_dna = json.loads(creator_profile["profile_json"] or "{}")
                creator_dna["updated_at"] = creator_profile["updated_at"]
            except (TypeError, ValueError, json.JSONDecodeError):
                creator_dna = {}
        return render_template(
            "dashboard.html",
            user=user,
            plan=get_plan(plan_key),
            plan_key=plan_key,
            jobs=jobs,
            credits=credits,
            creator_dna=creator_dna,
        )

    @app.route("/upload", methods=["GET", "POST"])
    @login_required
    def upload():
        from .clips import handle_upload
        return handle_upload()

    @app.route("/payments")
    @login_required
    def payments():
        return redirect(url_for("billing.payments"))

    @app.route("/account")
    @login_required
    def account():
        with get_db(app.config["DATABASE_PATH"]) as db:
            user = db.execute("SELECT * FROM users WHERE id=?", (session_user_id(),)).fetchone()
            oauth_rows = db.execute(
                "SELECT provider,created_at FROM oauth_identities WHERE user_id=? ORDER BY id",
                (session_user_id(),),
            ).fetchall()
        return render_template("account.html", user=user, oauth_identities=oauth_rows)

    @app.post("/account/profile")
    @login_required
    def update_account_profile():
        from flask import flash, request, session
        name = " ".join(request.form.get("display_name", "").split())[:80]
        if not name:
            flash("Le nom affiché ne peut pas être vide.", "error")
            return redirect(url_for("account"))
        with get_db(app.config["DATABASE_PATH"]) as db:
            db.execute("UPDATE users SET display_name=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (name, session_user_id()))
            db.commit()
        session["user_name"] = name
        flash("Profil mis à jour.", "success")
        return redirect(url_for("account"))

    @app.route("/brand-kit")
    @login_required
    def brand_kit():
        return render_template("brand_kit.html")

    @app.errorhandler(404)
    def not_found(error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(413)
    def too_large(error):
        return render_template("errors/413.html"), 413

    @app.errorhandler(500)
    def internal_error(error):
        app.logger.exception("Unhandled application error")
        return render_template("errors/500.html"), 500

    return app


def session_user_id():
    from flask import session
    return session.get("user_id")
