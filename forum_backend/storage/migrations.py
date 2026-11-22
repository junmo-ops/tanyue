"""Versioned startup migrations. Unknown historical metrics stay NULL."""
import sqlite3

LATEST_VERSION = 5


def migrate(conn: sqlite3.Connection, initialize_legacy) -> None:
    conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
    conn.commit()
    version = conn.execute("SELECT COALESCE(MAX(version), 0) FROM schema_migrations").fetchone()[0]
    if version > LATEST_VERSION:
        raise RuntimeError("Database schema is newer than this application")
    if version < 1:
        # Legacy bootstrap uses idempotent DDL and may commit. Mark only after success;
        # an interrupted bootstrap safely reruns on the next startup.
        initialize_legacy()
        with conn:
            conn.execute("INSERT OR IGNORE INTO schema_migrations(version) VALUES (1)")
    if version < 2:
        conn.execute("BEGIN IMMEDIATE")
        try:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(threads)")}
            for name in ("reward_money", "purchase_count"):
                if name not in columns:
                    conn.execute(f"ALTER TABLE threads ADD COLUMN {name} INTEGER")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_comments_tid_page_id ON comments(tid, source_page, comment_id)")
            conn.execute("INSERT OR IGNORE INTO schema_migrations(version) VALUES (2)")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    if version < 3:
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                """
                CREATE TABLE thread_metric_daily (
                  tid TEXT NOT NULL REFERENCES threads(tid) ON DELETE CASCADE,
                  observed_date TEXT NOT NULL,
                  first_observed_at TEXT NOT NULL,
                  last_observed_at TEXT NOT NULL,
                  first_reply_count INTEGER NOT NULL CHECK(first_reply_count >= 0),
                  last_reply_count INTEGER NOT NULL CHECK(last_reply_count >= 0),
                  first_view_count INTEGER NOT NULL CHECK(first_view_count >= 0),
                  last_view_count INTEGER NOT NULL CHECK(last_view_count >= 0),
                  counter_decreased INTEGER NOT NULL DEFAULT 0 CHECK(counter_decreased IN (0, 1)),
                  PRIMARY KEY (tid, observed_date),
                  CHECK(first_observed_at <= last_observed_at)
                )
                """
            )
            conn.execute("CREATE INDEX idx_thread_metric_daily_date ON thread_metric_daily(observed_date, tid)")
            # Current cumulative counts are not historical observations. Begin
            # recording on the next list crawl instead of inventing a baseline.
            conn.execute("INSERT INTO schema_migrations(version) VALUES (3)")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    if version < 4:
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ranking_snapshots (
                    id INTEGER PRIMARY KEY,
                    metric TEXT NOT NULL,
                    period TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    entries TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_ranking_snapshots_scope
                ON ranking_snapshots(metric, period, id DESC)
            """)
            conn.execute("INSERT OR IGNORE INTO schema_migrations(version) VALUES (4)")
    if version < 5:
        conn.execute("BEGIN IMMEDIATE")
        with conn:
            conn.execute("""
                DELETE FROM ranking_snapshots WHERE id IN (
                    SELECT id FROM (
                        SELECT id, ROW_NUMBER() OVER (
                            PARTITION BY metric, period, date(captured_at, '+8 hours')
                            ORDER BY captured_at DESC, id DESC
                        ) AS sequence
                        FROM ranking_snapshots
                    ) WHERE sequence > 1
                )
            """)
            conn.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_ranking_snapshots_day
                ON ranking_snapshots(metric, period, date(captured_at, '+8 hours'))
            """)
            conn.execute("INSERT OR IGNORE INTO schema_migrations(version) VALUES (5)")
