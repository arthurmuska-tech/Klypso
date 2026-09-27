#!/usr/bin/env python3
"""One-shot migration from a KLYPSO SQLite database to PostgreSQL.

Usage:
  SQLITE_PATH=/path/to/klypso.sqlite3 DATABASE_URL=postgresql://... python scripts/migrate_sqlite_to_postgres.py

The script initializes the PostgreSQL schema, copies application tables, and resets
PostgreSQL sequences for integer-id tables. It does not copy secrets or media files;
move media to durable object storage separately.
"""
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from klypso.database import connect, init_db, POSTGRES_ID_TABLES


TABLES = [
    "users",
    "oauth_identities",
    "email_codes",
    "credit_transactions",
    "promo_codes",
    "promo_redemptions",
    "user_consents",
    "media_files",
    "jobs",
    "clip_feedback",
    "projects",
    "stripe_events",
    "creator_ai_profiles",
    "clip_metrics",
    "publish_queue",
    "social_connections",
    "rate_limit_buckets",
]


def main():
    sqlite_path = os.environ.get("SQLITE_PATH", "").strip()
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not sqlite_path or not database_url:
        raise SystemExit("SQLITE_PATH et DATABASE_URL sont requis.")
    if not Path(sqlite_path).is_file():
        raise SystemExit(f"SQLite introuvable: {sqlite_path}")

    init_db(database_url)
    source = sqlite3.connect(sqlite_path)
    source.row_factory = sqlite3.Row
    destination = connect(database_url)

    try:
        with source:
            for table in TABLES:
                columns = [row[1] for row in source.execute(f"PRAGMA table_info({table})").fetchall()]
                if not columns:
                    continue
                rows = source.execute(f"SELECT {','.join(columns)} FROM {table}").fetchall()
                if not rows:
                    continue
                placeholders = ",".join(["%s"] * len(columns))
                quoted = ",".join(columns)
                for row in rows:
                    destination.execute(
                        f"INSERT INTO {table} ({quoted}) VALUES ({placeholders}) ON CONFLICT DO NOTHING",
                        tuple(row[column] for column in columns),
                    )
                destination.commit()

        for table in sorted(POSTGRES_ID_TABLES):
            if table in TABLES:
                destination.execute(
                    f"SELECT setval(pg_get_serial_sequence('{table}','id'), COALESCE((SELECT MAX(id) FROM {table}), 1), true)"
                )
        destination.commit()
    finally:
        source.close()
        destination.close()

    print("Migration SQLite → PostgreSQL terminée.")


if __name__ == "__main__":
    main()
