from datetime import datetime, timezone
from flask import current_app
import json

from .database import get_db
from .plans import get_plan


class CreditError(Exception):
    pass


def _now():
    return datetime.now(timezone.utc)


def _month_key(dt):
    return dt.strftime("%Y-%m")


def credit_cost_from_request(request):
    # Four creation modes share the same project workflow:
    # AI clips / clip only use the clip budget; AI montage / montage only
    # reserve more processing headroom for a full timeline.
    mode = request.form.get("mode", "").strip()
    cost = 1
    if mode in {"ai_montage", "montage_only"} or request.form.get("goal") == "studio":
        cost = 2
    # Keep the economy legible: basic clip = 1 credit; heavier renders add cost.
    if request.form.get("output_format", "9:16") in {"1:1", "4:5", "16:9"}:
        cost += 1
    if request.form.get("subtitles") == "on":
        cost += 1
    if request.form.get("brand_kit") == "on":
        cost += 1
    if request.form.get("clean_audio") == "on":
        cost += 1
    return min(cost, 6)


def _sync_balance(db, user_id, plan_key, now):
    plan = get_plan(plan_key)
    row = db.execute(
        "SELECT credit_balance, credit_last_granted_at, credit_month, monthly_clip_count "
        "FROM users WHERE id=?",
        (user_id,),
    ).fetchone()
    if not row:
        raise CreditError("Compte introuvable.")

    balance = int(row["credit_balance"] or 0)
    month = row["credit_month"]
    current_month = _month_key(now)

    if month != current_month:
        balance = 0
        db.execute(
            "UPDATE users SET credit_balance=0, credit_month=?, monthly_clip_count=0, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (current_month, user_id),
        )

    last = None
    if row["credit_last_granted_at"]:
        last = datetime.fromisoformat(row["credit_last_granted_at"].replace("Z", "+00:00"))
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)

    if last is None:
        # Give a new account enough credit for one standard clip immediately.
        balance = min(plan.credit_bank_cap, max(plan.daily_credits, 6))
        days = 0
    else:
        days = max(0, (now.date() - last.date()).days)
    if days:
        balance = min(plan.credit_bank_cap, balance + days * plan.daily_credits)
        db.execute(
            "UPDATE users SET credit_balance=?, credit_last_granted_at=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (balance, now.isoformat(), user_id),
        )
    elif last is None:
        db.execute(
            "UPDATE users SET credit_last_granted_at=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (now.isoformat(), user_id),
        )

    count = db.execute("SELECT monthly_clip_count FROM users WHERE id=?", (user_id,)).fetchone()["monthly_clip_count"]
    return balance, int(count or 0), plan


def consume_clip_credits(user_id, plan_key, cost, metadata=None):
    now = _now()
    with get_db(_db_path := current_app.config["DATABASE_PATH"]) as db:
        db.execute("BEGIN IMMEDIATE")
        balance, count, plan = _sync_balance(db, user_id, plan_key, now)

        if count >= plan.clips_per_month:
            raise CreditError(f"Limite de {plan.clips_per_month} clips atteinte pour ce mois.")
        if balance < cost:
            raise CreditError(
                f"Crédits insuffisants : il te faut {cost} crédits et tu en as {balance}. "
                f"Tes crédits reviennent chaque jour."
            )

        new_balance = balance - cost
        new_count = count + 1
        db.execute(
            "UPDATE users SET credit_balance=?, monthly_clip_count=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (new_balance, new_count, user_id),
        )
        db.execute(
            "INSERT INTO credit_transactions(user_id,amount,balance_after,transaction_type,metadata_json) VALUES(?,?,?,?,?)",
            (user_id, -cost, new_balance, "clip", json.dumps(metadata or {}, ensure_ascii=False)),
        )
        db.commit()
        return {
            "balance": new_balance,
            "monthly_clip_count": new_count,
            "monthly_limit": plan.clips_per_month,
            "cost": cost,
        }


def refund_clip_credits(user_id, cost, metadata=None):
    if cost <= 0:
        return
    with get_db(__import__("flask").current_app.config["DATABASE_PATH"]) as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT credit_balance, monthly_clip_count FROM users WHERE id=?",
            (user_id,),
        ).fetchone()
        if not row:
            return
        new_balance = row["credit_balance"] + cost
        new_count = max(0, row["monthly_clip_count"] - 1)
        db.execute(
            "UPDATE users SET credit_balance=?, monthly_clip_count=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (new_balance, new_count, user_id),
        )
        db.execute(
            "INSERT INTO credit_transactions(user_id,amount,balance_after,transaction_type,metadata_json) VALUES(?,?,?,?,?)",
            (user_id, cost, new_balance, "refund", json.dumps(metadata or {}, ensure_ascii=False)),
        )
        db.commit()


def get_credit_state(user_id, plan_key):
    now = _now()
    with get_db(__import__("flask").current_app.config["DATABASE_PATH"]) as db:
        db.execute("BEGIN IMMEDIATE")
        balance, count, plan = _sync_balance(db, user_id, plan_key, now)
        db.commit()
        return {
            "balance": balance,
            "daily_credits": plan.daily_credits,
            "bank_cap": plan.credit_bank_cap,
            "monthly_clip_count": count,
            "monthly_clip_limit": plan.clips_per_month,
        }
