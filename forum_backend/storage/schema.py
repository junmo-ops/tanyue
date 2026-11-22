import sqlite3
from .connection import connect_db

def ensure_feedback_schema(database_path: str) -> None:
    """确保本地反馈表存在，兼容已有旧数据库。"""
    conn = connect_db(database_path)
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS thread_feedback (
              tid TEXT PRIMARY KEY,
              feedback TEXT NOT NULL,
              seen INTEGER NOT NULL DEFAULT 0,
              updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_thread_feedback_feedback
            ON thread_feedback(feedback);
            """
        )
        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(thread_feedback)").fetchall()
        }
        if "seen" not in columns:
            conn.execute(
                "ALTER TABLE thread_feedback ADD COLUMN seen INTEGER NOT NULL DEFAULT 0"
            )
        conn.execute(
            """
            UPDATE thread_feedback
            SET seen = 1,
                feedback = '',
                updated_at = CURRENT_TIMESTAMP
            WHERE feedback = 'seen'
            """
        )
        conn.commit()
    finally:
        conn.close()


def ensure_title_word_stats_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS title_word_stats (
          normalized_word TEXT PRIMARY KEY,
          display_word TEXT NOT NULL,
          count INTEGER NOT NULL,
          thread_count INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS title_word_stats_meta (
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_title_word_stats_count
          ON title_word_stats(count DESC, display_word);
        """
    )
