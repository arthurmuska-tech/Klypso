"""KLYPSO production background worker.

The worker consumes durable PostgreSQL jobs outside the HTTP lifecycle.
It also recovers abandoned jobs, heartbeats long-running work, and supports
a one-shot mode for smoke tests and cron-based operational checks.
"""
import logging
import os
import signal
import threading
import time
from datetime import datetime, timedelta, timezone

from flask import session

from . import create_app
from .ai_api import _run_analysis_job
from .database import get_db
from .media.object_storage import enabled as object_storage_enabled


LOGGER = logging.getLogger("klypso.worker")
_STOP = threading.Event()


def _now():
    return datetime.now(timezone.utc)


def _parse_dt(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def recover_stale_jobs(app):
    stale_seconds = max(300, int(app.config.get("JOB_STALE_SECONDS", os.getenv("JOB_STALE_SECONDS", "1800"))))
    max_attempts = max(1, int(app.config.get("JOB_MAX_ATTEMPTS", os.getenv("JOB_MAX_ATTEMPTS", "3"))))
    cutoff = _now() - timedelta(seconds=stale_seconds)
    recovered = 0
    failed = 0
    with app.app_context():
        with get_db(app.config["DATABASE_PATH"]) as db:
            rows = db.execute(
                "SELECT id,attempts,locked_at,heartbeat_at,updated_at FROM jobs "
                "WHERE status='processing' AND job_type IN ('ai_clip_analysis','ai_montage_analysis') "
                "ORDER BY id LIMIT 200"
            ).fetchall()
            for row in rows:
                heartbeat = _parse_dt(row["heartbeat_at"] or row["locked_at"] or row["updated_at"])
                if heartbeat and heartbeat > cutoff:
                    continue
                attempts = int(row["attempts"] or 0)
                if attempts >= max_attempts:
                    db.execute(
                        "UPDATE jobs SET status='failed',error_message=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                        ("Job abandonné après plusieurs tentatives.", row["id"]),
                    )
                    failed += 1
                else:
                    db.execute(
                        "UPDATE jobs SET status='queued',locked_at=NULL,heartbeat_at=NULL,"
                        "error_message=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                        ("Job récupéré après interruption du worker.", row["id"]),
                    )
                    recovered += 1
            db.commit()
    if recovered or failed:
        LOGGER.warning("Recovered %s stale jobs; marked %s as failed", recovered, failed)
    return recovered, failed


def claim_next_job(app):
    with app.app_context():
        with get_db(app.config["DATABASE_PATH"]) as db:
            db.execute("BEGIN IMMEDIATE")
            is_postgres = getattr(db, "is_postgres", False)
            if is_postgres:
                row = db.execute(
                    "SELECT id,user_id,attempts FROM jobs "
                    "WHERE status='queued' AND job_type IN ('ai_clip_analysis','ai_montage_analysis') "
                    "ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED"
                ).fetchone()
            else:
                row = db.execute(
                    "SELECT id,user_id,attempts FROM jobs "
                    "WHERE status='queued' AND job_type IN ('ai_clip_analysis','ai_montage_analysis') "
                    "ORDER BY id LIMIT 1"
                ).fetchone()
            if not row:
                db.commit()
                return None

            attempts = int(row["attempts"] or 0) + 1
            now = _now().isoformat()
            db.execute(
                "UPDATE jobs SET status='processing',attempts=?,locked_at=?,heartbeat_at=?,"
                "error_message=NULL,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (attempts, now, now, row["id"]),
            )
            db.commit()
            return {"id": int(row["id"]), "user_id": int(row["user_id"]), "attempts": attempts}


def _heartbeat(app, user_id, job_id, stop_event):
    interval = max(15, int(os.getenv("WORKER_HEARTBEAT_SECONDS", "30")))
    while not stop_event.wait(interval):
        try:
            with app.app_context():
                with get_db(app.config["DATABASE_PATH"]) as db:
                    db.execute(
                        "UPDATE jobs SET heartbeat_at=?,updated_at=CURRENT_TIMESTAMP "
                        "WHERE id=? AND user_id=? AND status='processing'",
                        (_now().isoformat(), job_id, user_id),
                    )
                    db.commit()
        except Exception:
            LOGGER.exception("Heartbeat failed for job %s", job_id)


def process_job(app, job):
    heartbeat_stop = threading.Event()
    heartbeat = threading.Thread(
        target=_heartbeat,
        args=(app, job["user_id"], job["id"], heartbeat_stop),
        name=f"klypso-heartbeat-{job['id']}",
        daemon=True,
    )
    heartbeat.start()
    try:
        with app.app_context():
            with app.test_request_context("/"):
                session["user_id"] = job["user_id"]
                _run_analysis_job(job["id"])
                with get_db(app.config["DATABASE_PATH"]) as db:
                    current = db.execute(
                        "SELECT status FROM jobs WHERE id=? AND user_id=?",
                        (job["id"], job["user_id"]),
                    ).fetchone()
                    if current and current["status"] == "processing":
                        db.execute(
                            "UPDATE jobs SET status='failed',error_message=?,heartbeat_at=NULL,"
                            "locked_at=NULL,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                            ("Le worker a terminé sans finaliser le job.", job["id"]),
                        )
                        db.commit()
    except Exception:
        LOGGER.exception("Job %s failed", job["id"])
        with app.app_context():
            with get_db(app.config["DATABASE_PATH"]) as db:
                db.execute(
                    "UPDATE jobs SET status='failed',error_message=?,heartbeat_at=NULL,"
                    "locked_at=NULL,updated_at=CURRENT_TIMESTAMP WHERE id=? AND status='processing'",
                    ("Background worker failure", job["id"]),
                )
                db.commit()
    finally:
        heartbeat_stop.set()
        heartbeat.join(timeout=2)


def _install_signal_handlers():
    def stop_handler(signum, _frame):
        LOGGER.info("Received signal %s, stopping worker gracefully.", signum)
        _STOP.set()

    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, stop_handler)


def main():
    app = create_app()
    database_path = str(app.config["DATABASE_PATH"])
    if app.config.get("REQUIRE_POSTGRES") and not database_path.startswith(("postgresql://", "postgres://")):
        raise RuntimeError("Worker production requires PostgreSQL via DATABASE_URL.")
    if app.config.get("REQUIRE_OBJECT_STORAGE") and not object_storage_enabled():
        raise RuntimeError("Worker production requires configured object storage.")
    _install_signal_handlers()
    poll_seconds = max(1, int(os.getenv("WORKER_POLL_SECONDS", "2")))
    once = str(os.getenv("WORKER_ONCE", "")).lower() in {"1", "true", "yes", "on"}
    recovery_interval = max(15, int(os.getenv("WORKER_RECOVERY_INTERVAL_SECONDS", "60")))
    last_recovery = 0.0
    LOGGER.info("KLYPSO worker started in %s mode", app.config.get("AI_WORKER_MODE", "in_process"))

    while not _STOP.is_set():
        now = time.monotonic()
        if now - last_recovery >= recovery_interval:
            recover_stale_jobs(app)
            last_recovery = now

        job = claim_next_job(app)
        if job:
            LOGGER.info("Processing AI job %s (attempt %s)", job["id"], job["attempts"])
            process_job(app, job)
            if once:
                break
            continue

        if once:
            break
        _STOP.wait(poll_seconds)


if __name__ == "__main__":
    main()
