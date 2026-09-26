import secrets
import string
from datetime import datetime, timezone
from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from .auth import login_required
from .database import get_db
from .plans import get_plan, promo_active, promo_ends_at

promo_bp = Blueprint("promo", __name__)


def normalize_code(value):
    return "".join((value or "").upper().split())


def generate_code(prefix="KLYPSO"):
    alphabet = string.ascii_uppercase + string.digits
    suffix = "-".join("".join(secrets.choice(alphabet) for _ in range(4)) for _ in range(2))
    return f"{prefix}-{suffix}"


def _parse_date(value):
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def effective_plan_key(user):
    now = datetime.now(timezone.utc)
    if user["promo_plan"] and user["promo_started_at"] and user["promo_duration_weeks"]:
        if promo_active(user["promo_started_at"], user["promo_duration_weeks"], now):
            return user["promo_plan"]
    if user["plan"] in {"pro", "ultra"} and user["subscription_status"] in {"active", "trialing"}:
        return user["plan"]
    if user["trial_started_at"]:
        from .plans import trial_active, TRIAL_PLAN
        if trial_active(user["trial_started_at"], now):
            return TRIAL_PLAN
    return "free"


@promo_bp.post("/promo/redeem")
@login_required
def redeem():
    code = normalize_code(request.form.get("code"))
    if not code or len(code) > 64:
        flash("Code promo invalide.", "error")
        return redirect(url_for("account"))

    user_id = session["user_id"]
    now_dt = datetime.now(timezone.utc)
    now = now_dt.isoformat()
    with get_db(current_app.config["DATABASE_PATH"]) as db:
        db.execute("BEGIN IMMEDIATE")
        promo = db.execute(
            "SELECT * FROM promo_codes WHERE code=? AND active=1 AND used_count < max_redemptions",
            (code,),
        ).fetchone()
        if not promo:
            flash("Code promo invalide, expiré ou déjà utilisé.", "error")
            return redirect(url_for("account"))

        expiry = _parse_date(promo["expires_at"])
        if expiry and now_dt >= expiry:
            db.execute("UPDATE promo_codes SET active=0 WHERE id=?", (promo["id"],))
            db.commit()
            flash("Ce code promo est expiré.", "error")
            return redirect(url_for("account"))

        already = db.execute(
            "SELECT 1 FROM promo_redemptions WHERE promo_code_id=? AND user_id=?",
            (promo["id"], user_id),
        ).fetchone()
        if already:
            db.commit()
            flash("Ce code promo a déjà été utilisé sur ce compte.", "error")
            return redirect(url_for("account"))

        db.execute(
            "INSERT INTO promo_redemptions(promo_code_id,user_id) VALUES(?,?)",
            (promo["id"], user_id),
        )
        db.execute(
            "UPDATE promo_codes SET used_count=used_count+1, active=CASE WHEN used_count+1 >= max_redemptions THEN 0 ELSE active END WHERE id=?",
            (promo["id"],),
        )
        db.execute(
            "UPDATE users SET promo_plan=?, promo_started_at=?, promo_duration_weeks=?, promo_code_id=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (promo["plan"], now, promo["duration_weeks"], promo["id"], user_id),
        )
        db.commit()

    end = promo_ends_at(now, promo["duration_weeks"])
    flash(f"Code activé : {get_plan(promo['plan']).name} offert jusqu'au {end.astimezone(timezone.utc).strftime('%d/%m/%Y')}.", "success")
    return redirect(url_for("account"))


def _is_admin():
    email = session.get("user_email", "").lower()
    admins = {x.strip().lower() for x in current_app.config["ADMIN_EMAILS"].split(",") if x.strip()}
    return bool(admins and email in admins)


@promo_bp.get("/admin/promo-codes")
@login_required
def admin_codes():
    if not _is_admin():
        return render_template("errors/404.html"), 404
    with get_db(current_app.config["DATABASE_PATH"]) as db:
        codes = db.execute("SELECT * FROM promo_codes ORDER BY id DESC").fetchall()
    return render_template("promo_admin.html", codes=codes)


@promo_bp.post("/admin/promo-codes/create")
@login_required
def create_code():
    if not _is_admin():
        return render_template("errors/404.html"), 404
    plan = request.form.get("plan", "pro")
    try:
        weeks = int(request.form.get("weeks", "4"))
        max_redemptions = int(request.form.get("max_redemptions", "1"))
    except ValueError:
        flash("Durée ou nombre d'utilisations invalide.", "error")
        return redirect(url_for("promo.admin_codes"))
    if plan not in {"pro", "ultra"} or not 1 <= weeks <= 52 or not 1 <= max_redemptions <= 10000:
        flash("Paramètres de code promo invalides.", "error")
        return redirect(url_for("promo.admin_codes"))
    code = normalize_code(request.form.get("code")) or generate_code()
    expires_at = request.form.get("expires_at") or None
    if expires_at:
        try:
            datetime.fromisoformat(expires_at).replace(tzinfo=timezone.utc)
        except ValueError:
            flash("Date d'expiration invalide.", "error")
            return redirect(url_for("promo.admin_codes"))
    with get_db(current_app.config["DATABASE_PATH"]) as db:
        try:
            db.execute(
                "INSERT INTO promo_codes(code,plan,duration_weeks,max_redemptions,expires_at) VALUES(?,?,?,?,?)",
                (code, plan, weeks, max_redemptions, expires_at),
            )
            db.commit()
        except Exception:
            flash("Impossible de créer ce code : il existe peut-être déjà.", "error")
            return redirect(url_for("promo.admin_codes"))
    flash(f"Code créé : {code}", "success")
    return redirect(url_for("promo.admin_codes"))
