import pytest

from klypso import create_app
from klypso.credits import refund_clip_credits
from klypso.database import get_db


def test_clip_credit_refund_is_idempotent_and_does_not_change_monthly_quota(tmp_path):
    db_path = tmp_path / "klypso.sqlite3"
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "DATABASE_PATH": str(db_path),
            "STORAGE_PATH": str(tmp_path / "storage"),
            "SESSION_COOKIE_SECURE": False,
        }
    )

    with app.app_context():
        with get_db(app.config["DATABASE_PATH"]) as db:
            cur = db.execute(
                "INSERT INTO users(email,password_hash,credit_balance,monthly_clip_count) VALUES(?,?,?,?)",
                ("refund@example.com", "hash", 5, 3),
            )
            user_id = cur.lastrowid
            db.commit()

        refund_clip_credits(
            user_id,
            2,
            {"reason": "ai_analysis_failed", "job_id": 42},
        )
        refund_clip_credits(
            user_id,
            2,
            {"reason": "ai_analysis_failed", "job_id": 42},
        )

        with get_db(app.config["DATABASE_PATH"]) as db:
            user = db.execute(
                "SELECT credit_balance,monthly_clip_count FROM users WHERE id=?",
                (user_id,),
            ).fetchone()
            refunds = db.execute(
                "SELECT COUNT(*) AS n FROM credit_transactions "
                "WHERE user_id=? AND transaction_type='refund'",
                (user_id,),
            ).fetchone()

    assert user["credit_balance"] == 7
    assert user["monthly_clip_count"] == 3
    assert refunds["n"] == 1
