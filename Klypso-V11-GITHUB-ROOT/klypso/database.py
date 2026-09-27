import sqlite3
from contextlib import contextmanager
from pathlib import Path
import re
import os
from threading import Lock

_POSTGRES_POOLS = {}
_POSTGRES_POOL_LOCK = Lock()

def _pg_sql(sql):
    """Convert SQLite qmark placeholders to psycopg placeholders outside strings."""
    text = str(sql)
    out = []
    in_single = False
    escaped = False
    for char in text:
        if char == "'" and not escaped:
            in_single = not in_single
        if char == "?" and not in_single:
            out.append("%s")
        else:
            out.append(char)
        escaped = (char == "\\") and not escaped
        if char != "\\":
            escaped = False
    return "".join(out)


POSTGRES_ID_TABLES = {
    "users", "oauth_identities", "email_codes", "credit_transactions",
    "promo_codes", "promo_redemptions", "user_consents", "media_files",
    "jobs", "clip_feedback", "projects", "clip_metrics",
    "publish_queue", "social_connections",
}


class CompatCursor:
    def __init__(self, cursor, buffered=None, lastrowid=None):
        self._cursor = cursor
        self._buffered = buffered or []
        self.lastrowid = lastrowid

    def __getattr__(self, name):
        return getattr(self._cursor, name)

    def fetchone(self):
        if self._buffered:
            return self._buffered.pop(0)
        return self._cursor.fetchone()

    def fetchall(self):
        if self._buffered:
            rows = self._buffered + list(self._cursor.fetchall())
            self._buffered = []
            return rows
        return self._cursor.fetchall()


class CompatConnection:
    def __init__(self, conn):
        self._conn = conn
        self.is_postgres = True

    def execute(self, sql, params=()):
        sql = str(sql)
        statement = _pg_sql(sql).strip()
        if statement.upper() == "BEGIN IMMEDIATE":
            statement = "BEGIN"
        params = tuple(params or ())
        match = re.match(r"INSERT\s+INTO\s+([A-Za-z_][A-Za-z0-9_]*)", statement, re.I)
        buffered = []
        lastrowid = None
        if match and match.group(1).lower() in POSTGRES_ID_TABLES and " RETURNING " not in statement.upper():
            statement = statement.rstrip().rstrip(";") + " RETURNING id"
        cursor = self._conn.cursor()
        cursor.execute(statement, params)
        if match and match.group(1).lower() in POSTGRES_ID_TABLES and " RETURNING id" in statement.upper():
            row = cursor.fetchone()
            if row is not None:
                lastrowid = row["id"] if isinstance(row, dict) else row[0]
                buffered = [row]
        return CompatCursor(cursor, buffered=buffered, lastrowid=lastrowid)

    def executescript(self, script):
        statements = [item.strip() for item in str(script).split(";") if item.strip()]
        for statement in statements:
            statement = statement.replace(
                "INTEGER PRIMARY KEY AUTOINCREMENT",
                "BIGSERIAL PRIMARY KEY",
            )
            self.execute(statement)
        return None

    def executemany(self, sql, seq_of_params):
        return self._conn.executemany(_pg_sql(sql).strip(), seq_of_params)

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()

    def close(self):
        return self._conn.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    auth_provider TEXT NOT NULL DEFAULT 'email',
    email_verified_at TEXT,
    plan TEXT NOT NULL DEFAULT 'free',
    trial_started_at TEXT,
    stripe_customer_id TEXT,
    subscription_status TEXT NOT NULL DEFAULT 'none',
    trial_plan TEXT NOT NULL DEFAULT 'pro',
    promo_plan TEXT,
    promo_started_at TEXT,
    promo_duration_weeks INTEGER,
    promo_code_id INTEGER,
    credit_balance INTEGER NOT NULL DEFAULT 0,
    credit_last_granted_at TEXT,
    credit_month TEXT,
    monthly_clip_count INTEGER NOT NULL DEFAULT 0,
    display_name TEXT NOT NULL DEFAULT '',
    avatar_url TEXT,
    last_login_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS oauth_identities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    provider TEXT NOT NULL CHECK(provider IN ('google')),
    subject TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(provider, subject)
);
CREATE TABLE IF NOT EXISTS email_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL,
    purpose TEXT NOT NULL CHECK(purpose IN ('register','login')),
    code_hash TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    used_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_email_codes_lookup ON email_codes(email, purpose, created_at);

CREATE TABLE IF NOT EXISTS credit_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    amount INTEGER NOT NULL,
    balance_after INTEGER NOT NULL,
    transaction_type TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_credit_transactions_user ON credit_transactions(user_id, created_at);

CREATE TABLE IF NOT EXISTS promo_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    plan TEXT NOT NULL CHECK(plan IN ('pro', 'ultra')),
    duration_weeks INTEGER NOT NULL CHECK(duration_weeks BETWEEN 1 AND 52),
    max_redemptions INTEGER NOT NULL DEFAULT 1 CHECK(max_redemptions > 0),
    used_count INTEGER NOT NULL DEFAULT 0 CHECK(used_count >= 0),
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
    expires_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS promo_redemptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    promo_code_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    redeemed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(promo_code_id) REFERENCES promo_codes(id) ON DELETE CASCADE,
    UNIQUE(promo_code_id, user_id)
);
CREATE TABLE IF NOT EXISTS user_consents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    cgu_accepted_at TEXT NOT NULL,
    privacy_accepted_at TEXT NOT NULL,
    cgu_version TEXT NOT NULL DEFAULT '2026-09-26',
    privacy_version TEXT NOT NULL DEFAULT '2026-09-26',
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS media_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    original_name TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'uploaded',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    job_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    payload_json TEXT NOT NULL DEFAULT '{}',
    result_json TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS clip_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    job_id INTEGER,
    candidate_id TEXT NOT NULL,
    decision TEXT NOT NULL CHECK(decision IN ('keep','reject')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    timeline_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS stripe_events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    processed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS creator_ai_profiles (
    user_id INTEGER PRIMARY KEY,
    profile_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS clip_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    job_id INTEGER,
    candidate_id TEXT,
    platform TEXT NOT NULL DEFAULT 'unknown',
    views INTEGER NOT NULL DEFAULT 0,
    likes INTEGER NOT NULL DEFAULT 0,
    comments INTEGER NOT NULL DEFAULT 0,
    shares INTEGER NOT NULL DEFAULT 0,
    avg_watch_seconds REAL,
    completion_rate REAL,
    recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_clip_metrics_user ON clip_metrics(user_id, recorded_at);

CREATE TABLE IF NOT EXISTS publish_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    media_id INTEGER NOT NULL,
    job_id INTEGER,
    candidate_id TEXT,
    platform TEXT NOT NULL CHECK(platform IN ('youtube','tiktok','instagram','x')),
    scheduled_for TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'scheduled' CHECK(status IN ('scheduled','processing','published','needs_connection','failed','cancelled')),
    title TEXT NOT NULL DEFAULT '',
    caption TEXT NOT NULL DEFAULT '',
    hashtags TEXT NOT NULL DEFAULT '',
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    published_at TEXT,
    remote_url TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY(media_id) REFERENCES media_files(id) ON DELETE CASCADE,
    FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_publish_queue_user ON publish_queue(user_id, scheduled_for);
CREATE INDEX IF NOT EXISTS idx_publish_queue_due ON publish_queue(status, scheduled_for);
CREATE INDEX IF NOT EXISTS idx_publish_queue_processing ON publish_queue(status, updated_at);

CREATE TABLE IF NOT EXISTS social_connections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    platform TEXT NOT NULL CHECK(platform IN ('youtube','tiktok','instagram','x')),
    access_token_enc TEXT,
    refresh_token_enc TEXT,
    expires_at TEXT,
    account_id TEXT,
    account_name TEXT,
    scopes TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(user_id, platform)
);
CREATE INDEX IF NOT EXISTS idx_social_connections_user ON social_connections(user_id, platform);
CREATE TABLE IF NOT EXISTS rate_limit_buckets (
    rate_key TEXT PRIMARY KEY,
    window_start INTEGER NOT NULL,
    hit_count INTEGER NOT NULL DEFAULT 0
);
"""


def _postgres_pool(url):
    with _POSTGRES_POOL_LOCK:
        pool = _POSTGRES_POOLS.get(url)
        if pool is None:
            from psycopg_pool import ConnectionPool
            max_size = max(2, int(os.getenv("POSTGRES_POOL_MAX_SIZE", "8")))
            pool = ConnectionPool(
                conninfo=str(url),
                min_size=1,
                max_size=max_size,
                timeout=20,
                open=True,
                kwargs={"row_factory": __import__("psycopg.rows", fromlist=["dict_row"]).dict_row},
            )
            _POSTGRES_POOLS[url] = pool
        return pool


def connect(path):
    if str(path).startswith(("postgresql://", "postgres://")):
        from psycopg.rows import dict_row
        return CompatConnection(_postgres_pool(str(path)).getconn())
    conn = sqlite3.connect(path, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def _add_column_if_missing(conn, table, column, declaration):
    if getattr(conn, "is_postgres", False):
        row = conn.execute(
            "SELECT 1 FROM information_schema.columns WHERE table_name=%s AND column_name=%s LIMIT 1",
            (table, column),
        ).fetchone()
        if row is None:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")
        return
    columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")


def _seed_creator_promo_codes(conn):
    """Seed one-use Pro codes supplied securely through Render environment variables."""
    raw = os.environ.get("KLYPSO_CREATOR_PROMO_CODES", "")
    codes = [item.strip().upper() for item in raw.split(",") if item.strip()]
    if not codes:
        return
    for code in dict.fromkeys(codes):
        if len(code) > 64:
            continue
        exists = conn.execute("SELECT 1 FROM promo_codes WHERE code=? LIMIT 1", (code,)).fetchone()
        if exists:
            continue
        conn.execute(
            "INSERT INTO promo_codes(code,plan,duration_weeks,max_redemptions,expires_at) VALUES(?,?,?,?,?)",
            (code, "pro", 4, 1, None),
        )


def init_db(path):
    if not str(path).startswith(("postgresql://", "postgres://")):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    with get_db(path) as conn:
        conn.executescript(SCHEMA)
        _add_column_if_missing(conn, "users", "auth_provider", "TEXT NOT NULL DEFAULT 'email'")
        _add_column_if_missing(conn, "users", "email_verified_at", "TEXT")
        _add_column_if_missing(conn, "promo_codes", "expires_at", "TEXT")
        _add_column_if_missing(conn, "user_consents", "cgu_version", "TEXT NOT NULL DEFAULT '2026-09-26'")
        _add_column_if_missing(conn, "user_consents", "privacy_version", "TEXT NOT NULL DEFAULT '2026-09-26'")
        _add_column_if_missing(conn, "users", "credit_balance", "INTEGER NOT NULL DEFAULT 0")
        _add_column_if_missing(conn, "users", "credit_last_granted_at", "TEXT")
        _add_column_if_missing(conn, "users", "credit_month", "TEXT")
        _add_column_if_missing(conn, "users", "monthly_clip_count", "INTEGER NOT NULL DEFAULT 0")
        _add_column_if_missing(conn, "users", "display_name", "TEXT NOT NULL DEFAULT ''")
        _add_column_if_missing(conn, "users", "avatar_url", "TEXT")
        _add_column_if_missing(conn, "users", "last_login_at", "TEXT")
        _add_column_if_missing(conn, "clip_metrics", "queue_id", "INTEGER")
        _add_column_if_missing(conn, "jobs", "attempts", "INTEGER NOT NULL DEFAULT 0")
        _add_column_if_missing(conn, "jobs", "locked_at", "TEXT")
        _add_column_if_missing(conn, "jobs", "heartbeat_at", "TEXT")
        conn.execute("UPDATE users SET display_name=substr(email,1,instr(email,'@')-1) WHERE display_name='' AND instr(email,'@')>1")
        _seed_creator_promo_codes(conn)
        conn.commit()


@contextmanager
def get_db(path):
    path = str(path)
    if path.startswith(("postgresql://", "postgres://")):
        pool = _postgres_pool(path)
        raw = pool.getconn()
        conn = CompatConnection(raw)
        try:
            yield conn
        finally:
            try:
                conn.rollback()
            except Exception:
                pass
            pool.putconn(raw)
        return
    conn = connect(path)
    try:
        yield conn
    finally:
        conn.close()
