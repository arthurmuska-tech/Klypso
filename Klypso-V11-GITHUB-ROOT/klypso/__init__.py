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
from .media.object_storage import enabled as object_storage_enabled


def create_app(test_config=None):
    app = Flask(__name__, template_folder="../templates", static_folder="../static", static_url_path="/static")
    # Render terminates TLS at the proxy; trust the forwarded scheme/host for absolute OAuth URLs.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)
    if (
        app.config.get("REQUIRE_POSTGRES")
        and app.config.get("SECRET_KEY") in {"", "dev-only-change-me"}
    ):
        raise RuntimeError("Production KLYPSO requires a non-default SECRET_KEY.")
    database_path = str(app.config["DATABASE_PATH"])
    if app.config.get("REQUIRE_POSTGRES") and not database_path.startswith(("postgresql://", "postgres://")):
        raise RuntimeError("Production KLYPSO requires PostgreSQL via DATABASE_URL.")
    if not database_path.startswith(("postgresql://", "postgres://")):
        Path(database_path).parent.mkdir(parents=True, exist_ok=True)
    Path(app.config["STORAGE_PATH"]).mkdir(parents=True, exist_ok=True)
    init_db(database_path)
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

    @app.get("/google5ac38975c108f180.html")
    def google_site_verification():
        from flask import Response
        return Response("google-site-verification: google5ac38975c108f180.html", mimetype="text/html")

    @app.get("/robots.txt")
    def robots_txt():
        from flask import Response
        sitemap_url = f"{app.config['PUBLIC_BASE_URL']}/sitemap.xml"
        return Response(
            f"User-agent: *\\nAllow: /\\nDisallow: /dashboard\\nDisallow: /account\\nDisallow: /api/\\nSitemap: {sitemap_url}\\n",
            mimetype="text/plain",
        )

    @app.get("/sitemap.xml")
    def sitemap_xml():
        from flask import Response
        public = app.config["PUBLIC_BASE_URL"].rstrip("/")
        urls = [
            f"{public}/",
            f"{public}/demo",
            f"{public}/pricing",
            f"{public}/mentions-legales",
            f"{public}/confidentialite",
            f"{public}/cgu",
            f"{public}/cgv",
            f"{public}/contact",
        ]
        body = "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
        body += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        for loc in urls:
            body += f"<url><loc>{loc}</loc></url>"
        body += "</urlset>"
        return Response(body, mimetype="application/xml")

    @app.route("/healthz")
    def healthz():
        import shutil
        version_file = Path(app.root_path).parent / "VERSION"
        version = version_file.read_text(encoding="utf-8").strip() if version_file.exists() else "unknown"
        database_is_postgres = str(app.config["DATABASE_PATH"]).startswith(("postgresql://", "postgres://"))
        database = "postgresql" if database_is_postgres else "sqlite"
        storage = "s3" if object_storage_enabled() else "local"
        email_ready = bool(
            app.config.get("EMAIL_FROM")
            and (app.config.get("RESEND_API_KEY") or app.config.get("EMAIL_SMTP_HOST"))
        )
        google_ready = bool(app.config.get("GOOGLE_CLIENT_ID") and app.config.get("GOOGLE_CLIENT_SECRET"))
        media_tools = {
            "ffmpeg": bool(shutil.which("ffmpeg")),
            "ffprobe": bool(shutil.which("ffprobe")),
        }
        db_status = "ok"
        try:
            with get_db(app.config["DATABASE_PATH"]) as db:
                db.execute("SELECT 1").fetchone()
        except Exception:
            app.logger.exception("Health check database failure")
            db_status = "error"
        status = "ok" if db_status == "ok" else "degraded"
        return {
            "status": status,
            "service": "klypso",
            "version": version,
            "database": database,
            "database_status": db_status,
            "persistent_user_store": database_is_postgres,
            "storage": storage,
            "storage_required": bool(app.config.get("REQUIRE_OBJECT_STORAGE")),
            "object_storage_configured": object_storage_enabled(),
            "worker_mode": app.config.get("AI_WORKER_MODE", "in_process"),
            "google_configured": google_ready,
            "email_configured": email_ready,
            "media_tools": media_tools,
        }, 200 if status == "ok" else 503

    @app.route("/readyz")
    def readyz():
        database = str(app.config["DATABASE_PATH"])
        database_is_postgres = database.startswith(("postgresql://", "postgres://"))
        storage_ready = object_storage_enabled() if app.config.get("REQUIRE_OBJECT_STORAGE") else True
        database_ready = not app.config.get("REQUIRE_POSTGRES") or database_is_postgres
        legal_keys = (
            "LEGAL_ENTITY_NAME", "LEGAL_STATUS", "LEGAL_ADDRESS",
            "LEGAL_PUBLICATION_DIRECTOR", "LEGAL_CONTACT_EMAIL",
            "HOSTER_NAME", "HOSTER_ADDRESS",
        )
        legal_ready = all(str(app.config.get(key) or "").strip() for key in legal_keys)
        if not app.config.get("REQUIRE_LEGAL_CONFIG"):
            legal_ready = True
        try:
            with get_db(app.config["DATABASE_PATH"]) as db:
                db.execute("SELECT 1").fetchone()
        except Exception:
            app.logger.exception("Readiness check database failure")
            return {
                "status": "not_ready",
                "database": "postgresql" if database_is_postgres else "sqlite",
                "database_required": bool(app.config.get("REQUIRE_POSTGRES")),
                "storage_ready": storage_ready,
            }, 503
        if not database_ready or not storage_ready or not legal_ready:
            return {
                "status": "not_ready",
                "database": "postgresql" if database_is_postgres else "sqlite",
                "database_required": bool(app.config.get("REQUIRE_POSTGRES")),
                "storage": "s3" if storage_ready else "local_unavailable",
                "storage_required": bool(app.config.get("REQUIRE_OBJECT_STORAGE")),
                "legal_ready": legal_ready,
                "legal_required": bool(app.config.get("REQUIRE_LEGAL_CONFIG")),
            }, 503
        return {
            "status": "ready",
            "database": "postgresql" if database_is_postgres else "sqlite",
            "storage": "s3" if object_storage_enabled() else "local",
        }, 200

    @app.get("/api/admin/metrics")
    @login_required
    def admin_metrics():
        from flask import jsonify, session
        admins = {item.strip().lower() for item in app.config.get("ADMIN_EMAILS", "").split(",") if item.strip()}
        if session.get("user_email", "").lower() not in admins:
            return jsonify({"error": "Not found"}), 404
        with get_db(app.config["DATABASE_PATH"]) as db:
            metrics = {
                "users_total": db.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"],
                "users_paid": db.execute(
                    "SELECT COUNT(*) AS n FROM users WHERE plan IN ('pro','ultra') AND subscription_status IN ('active','trialing')"
                ).fetchone()["n"],
                "trials_active": db.execute(
                    "SELECT COUNT(*) AS n FROM users WHERE trial_started_at IS NOT NULL"
                ).fetchone()["n"],
                "jobs_total": db.execute("SELECT COUNT(*) AS n FROM jobs").fetchone()["n"],
                "jobs_queued": db.execute("SELECT COUNT(*) AS n FROM jobs WHERE status='queued'").fetchone()["n"],
                "jobs_processing": db.execute("SELECT COUNT(*) AS n FROM jobs WHERE status='processing'").fetchone()["n"],
                "jobs_completed": db.execute("SELECT COUNT(*) AS n FROM jobs WHERE status='completed'").fetchone()["n"],
                "jobs_failed": db.execute("SELECT COUNT(*) AS n FROM jobs WHERE status='failed'").fetchone()["n"],
                "media_total": db.execute("SELECT COUNT(*) AS n FROM media_files").fetchone()["n"],
                "published_total": db.execute("SELECT COUNT(*) AS n FROM publish_queue WHERE status='published'").fetchone()["n"],
                "tracked_metrics": db.execute("SELECT COUNT(*) AS n FROM clip_metrics").fetchone()["n"],
            }
        return jsonify({"ok": True, "metrics": {key: int(value or 0) for key, value in metrics.items()}})
    
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
                "SELECT provider,created_at FROM oauth_identities WHERE user_id=? AND provider=? ORDER BY id",
                (session_user_id(), "google"),
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
