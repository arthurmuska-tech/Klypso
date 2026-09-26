from pathlib import Path
from flask import Flask, render_template
from .config import Config
from .database import init_db, get_db
from .auth import auth_bp, login_required
from .legal import legal_bp
from .promo import promo_bp
from .billing import billing_bp
from .clips import clips_bp
from .studio import studio_bp
from .security import register_security, csrf_token
from .promo import effective_plan_key
from .plans import get_plan


def create_app(test_config=None):
    app = Flask(__name__, template_folder="../templates", static_folder="../static", static_url_path="/static")
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)
    Path(app.config["DATABASE_PATH"]).parent.mkdir(parents=True, exist_ok=True)
    Path(app.config["STORAGE_PATH"]).mkdir(parents=True, exist_ok=True)
    init_db(app.config["DATABASE_PATH"])
    register_security(app)
    app.register_blueprint(auth_bp)
    app.register_blueprint(legal_bp)
    app.register_blueprint(promo_bp)
    app.register_blueprint(billing_bp)
    app.register_blueprint(clips_bp)
    app.register_blueprint(studio_bp)

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
            "csrf_token": csrf_token,
            "public_base_url": app.config["PUBLIC_BASE_URL"],
            "current_plan": plan,
        }

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/healthz")
    def healthz():
        return {"status": "ok", "service": "klypso", "version": "10.0.0"}, 200

    @app.route("/dashboard")
    @login_required
    def dashboard():
        with get_db(app.config["DATABASE_PATH"]) as db:
            user = db.execute("SELECT * FROM users WHERE id=?", (session_user_id(),)).fetchone()
            jobs = db.execute(
                "SELECT * FROM jobs WHERE user_id=? ORDER BY id DESC LIMIT 8",
                (session_user_id(),),
            ).fetchall()
        plan_key = effective_plan_key(user)
        return render_template("dashboard.html", user=user, plan=get_plan(plan_key), plan_key=plan_key, jobs=jobs)

    @app.route("/upload", methods=["GET", "POST"])
    def upload():
        from .clips import handle_upload
        return handle_upload()

    @app.route("/account")
    @login_required
    def account():
        return render_template("account.html")

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
