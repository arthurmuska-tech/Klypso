"""KLYPSO background worker for production media/AI jobs.

Production mode uses PostgreSQL as the durable job queue. The web service only
creates queued jobs; this worker claims them with row-level locking and runs
the existing analysis engine outside the HTTP lifecycle.
"""
import logging
import os
import time

from flask import session

from . import create_app
from .ai_api import _run_analysis_job
from .database import get_db


LOGGER = logging.getLogger("klypso.worker")


def claim_next_job(app):
    with app.app_context():
        with get_db(app.config["DATABASE_PATH"]) as db:
            db.execute("BEGIN IMMEDIATE")
            is_postgres = getattr(db, "is_postgres", False)
            if is_postgres:
                row = db.execute(
                    "SELECT id,user_id FROM jobs "
                    "WHERE status='queued' AND job_type IN ('ai_clip_analysis','ai_montage_analysis') "
                    "ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED"
                ).fetchone()
            else:
                row = db.execute(
                    "SELECT id,user_id FROM jobs "
                    "WHERE status='queued' AND job_type IN ('ai_clip_analysis','ai_montage_analysis') "
                    "ORDER BY id LIMIT 1"
                ).fetchone()
            if not row:
                db.commit()
                return None
            db.execute(
                "UPDATE jobs SET status='processing',error_message=NULL,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (row["id"],),
            )
            db.commit()
            return {"id": int(row["id"]), "user_id": int(row["user_id"])}


def process_job(app, job):
    with app.app_context():
        with app.test_request_context("/"):
            session["user_id"] = job["user_id"]
            try:
                _run_analysis_job(job["id"])
            except Exception:
                LOGGER.exception("Job %s failed", job["id"])
                with get_db(app.config["DATABASE_PATH"]) as db:
                    db.execute(
                        "UPDATE jobs SET status='failed',error_message=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                        ("Background worker failure", job["id"]),
                    )
                    db.commit()


def main():
    app = create_app()
    poll_seconds = max(1, int(os.getenv("WORKER_POLL_SECONDS", "2")))
    LOGGER.info("KLYPSO worker started in %s mode", app.config.get("AI_WORKER_MODE", "in_process"))

    while True:
        job = claim_next_job(app)
        if job:
            LOGGER.info("Processing AI job %s", job["id"])
            process_job(app, job)
            continue
        time.sleep(poll_seconds)


if __name__ == "__main__":
    main()
