from __future__ import annotations

import sqlite3
from pathlib import Path

from forum_backend.parsers import Topic
from forum_backend.config import extract_tid
from forum_backend.storage.connection import connect_db
from forum_backend.storage.metrics import record_thread_metrics

def init_db(database_path: str) -> sqlite3.Connection:
    """初始化数据库 schema，并返回启用 Row 工厂的连接。"""
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect_db(str(path))
    from forum_backend.storage.migrations import migrate
    try:
        migrate(conn, lambda: _initialize_legacy_schema(conn, database_path))
    except Exception:
        conn.close()
        raise
    return conn


def _initialize_legacy_schema(conn: sqlite3.Connection, database_path: str) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS threads (
          tid TEXT PRIMARY KEY,
          fid TEXT NOT NULL DEFAULT '',
          title TEXT NOT NULL,
          forum_name TEXT NOT NULL DEFAULT '',
          author TEXT,
          author_id TEXT NOT NULL DEFAULT '',
          posted_at TEXT,
          reply_count INTEGER NOT NULL DEFAULT 0,
          view_count INTEGER NOT NULL DEFAULT 0,
          heatlevel INTEGER NOT NULL DEFAULT 0,
          source_page INTEGER,
          detail_status TEXT NOT NULL DEFAULT 'pending',
          detail_error TEXT,
          participant_count INTEGER NOT NULL DEFAULT 0,
          money INTEGER NOT NULL DEFAULT 0,
          rating TEXT NOT NULL DEFAULT '',
          fetch_comments INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS comments (
          tid TEXT NOT NULL,
          comment_id TEXT NOT NULL,
          author TEXT,
          author_id TEXT NOT NULL DEFAULT '',
          posted_at TEXT,
          content_text TEXT,
          source_page INTEGER,
          fetched_at TEXT NOT NULL,
          PRIMARY KEY (tid, comment_id)
        );

        CREATE TABLE IF NOT EXISTS crawl_runs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          kind TEXT NOT NULL,
          started_at TEXT NOT NULL,
          finished_at TEXT,
          start_page INTEGER,
          pages INTEGER,
          success_count INTEGER NOT NULL DEFAULT 0,
          failure_count INTEGER NOT NULL DEFAULT 0,
          error TEXT
        );

        CREATE TABLE IF NOT EXISTS thread_recommendation_candidates (
          tid TEXT PRIMARY KEY,
          posted_date TEXT NOT NULL,
          reply_rank INTEGER NOT NULL DEFAULT 0,
          view_rank INTEGER NOT NULL DEFAULT 0,
          day_count INTEGER NOT NULL DEFAULT 0,
          refreshed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_threads_posted_at ON threads(posted_at);
        CREATE INDEX IF NOT EXISTS idx_threads_source_page ON threads(source_page);
        CREATE INDEX IF NOT EXISTS idx_threads_detail_status ON threads(detail_status);
        CREATE INDEX IF NOT EXISTS idx_threads_reply_count ON threads(reply_count);
        CREATE INDEX IF NOT EXISTS idx_thread_recommendation_candidates_posted_date
        ON thread_recommendation_candidates(posted_date);
        CREATE INDEX IF NOT EXISTS idx_comments_tid ON comments(tid);
        """
    )
    _migrate_threads_schema(conn)
    _ensure_column(conn, "threads", "fid", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "threads", "forum_name", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "threads", "author_id", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "threads", "heatlevel", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "threads", "participant_count", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "threads", "money", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "threads", "rating", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "threads", "metrics_repaired_at", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "threads", "fetch_comments", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "comments", "author_id", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "threads", "list_fetched_at", "TEXT NOT NULL DEFAULT ''")
    ensure_recommendation_schema(conn)
    _ensure_performance_indexes(conn)
    conn.commit()
    from forum_backend.storage.schema import ensure_feedback_schema, ensure_title_word_stats_schema
    ensure_feedback_schema(database_path)
    ensure_title_word_stats_schema(conn)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS data_versions (name TEXT PRIMARY KEY, revision INTEGER NOT NULL DEFAULT 0);
        INSERT OR IGNORE INTO data_versions(name) VALUES ('titles');
        CREATE TRIGGER IF NOT EXISTS titles_inserted AFTER INSERT ON threads BEGIN
          UPDATE data_versions SET revision=revision+1 WHERE name='titles';
        END;
        CREATE TRIGGER IF NOT EXISTS titles_deleted AFTER DELETE ON threads BEGIN
          UPDATE data_versions SET revision=revision+1 WHERE name='titles';
        END;
        CREATE TRIGGER IF NOT EXISTS titles_changed AFTER UPDATE OF title ON threads
        WHEN OLD.title IS NOT NEW.title BEGIN
          UPDATE data_versions SET revision=revision+1 WHERE name='titles';
        END;
    """)
    conn.commit()


def _ensure_performance_indexes(conn: sqlite3.Connection) -> None:
    """补齐查询和排序常用字段上的索引。"""
    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_threads_view_count ON threads(view_count);
        CREATE INDEX IF NOT EXISTS idx_threads_participant_count ON threads(participant_count);
        CREATE INDEX IF NOT EXISTS idx_threads_money ON threads(money);
        CREATE INDEX IF NOT EXISTS idx_threads_fid_reply_count ON threads(fid, reply_count);
        CREATE INDEX IF NOT EXISTS idx_threads_fid_posted_at ON threads(fid, posted_at);
        CREATE INDEX IF NOT EXISTS idx_threads_fetch_comments ON threads(fetch_comments);
        """
    )


def ensure_recommendation_schema(conn: sqlite3.Connection) -> None:
    """确保随机推荐候选池表和辅助索引存在。"""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS thread_recommendation_candidates (
          tid TEXT PRIMARY KEY,
          posted_date TEXT NOT NULL,
          reply_rank INTEGER NOT NULL DEFAULT 0,
          view_rank INTEGER NOT NULL DEFAULT 0,
          day_count INTEGER NOT NULL DEFAULT 0,
          refreshed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_thread_recommendation_candidates_posted_date
        ON thread_recommendation_candidates(posted_date);
        """
    )
    _ensure_column(conn, "thread_recommendation_candidates", "reply_rank", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "thread_recommendation_candidates", "view_rank", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "thread_recommendation_candidates", "day_count", "INTEGER NOT NULL DEFAULT 0")


def rebuild_recommendation_candidates(conn: sqlite3.Connection) -> int:
    """在当前连接内重建随机推荐每日排名数据。"""
    ensure_recommendation_schema(conn)
    conn.execute("DELETE FROM thread_recommendation_candidates")
    conn.execute(
        """
        INSERT INTO thread_recommendation_candidates (
          tid, posted_date, reply_rank, view_rank, day_count, refreshed_at
        )
        SELECT tid, posted_date, reply_rank, view_rank, day_count, CURRENT_TIMESTAMP
        FROM (
          SELECT t.tid,
                 substr(t.posted_at, 1, 10) AS posted_date,
                 ROW_NUMBER() OVER (
                   PARTITION BY substr(t.posted_at, 1, 10)
                   ORDER BY t.reply_count DESC, t.tid DESC
                 ) AS reply_rank,
                 ROW_NUMBER() OVER (
                   PARTITION BY substr(t.posted_at, 1, 10)
                   ORDER BY t.view_count DESC, t.tid DESC
                 ) AS view_rank,
                 COUNT(1) OVER (
                   PARTITION BY substr(t.posted_at, 1, 10)
                 ) AS day_count
          FROM threads t
          WHERE t.posted_at IS NOT NULL
            AND t.posted_at != ''
        )
        """
    )
    return conn.execute(
        "SELECT COUNT(1) FROM thread_recommendation_candidates"
    ).fetchone()[0]


def refresh_recommendation_candidates(database_path: str) -> int:
    """重建随机推荐候选池，返回候选帖子数量。"""
    conn = init_db(database_path)
    try:
        count = rebuild_recommendation_candidates(conn)
        conn.commit()
        return count
    finally:
        conn.close()


def _migrate_threads_schema(conn: sqlite3.Connection) -> None:
    """把旧版 threads 表迁移到当前精简 schema。"""
    existing = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(threads)").fetchall()
    }
    obsolete = {
        "first_seen_at",
        "last_seen_at",
        "detail_fetched_at",
        "url_path",
        "content_text",
        "image_urls_json",
    }
    required = {
        "fid",
        "heatlevel",
        "forum_name",
        "author_id",
        "participant_count",
        "money",
        "rating",
        "fetch_comments",
    }
    if not (obsolete & existing) and required.issubset(existing):
        return

    # 旧版 SQLite 运行时不能随意删除列，所以把旧数据迁到当前字段的新表。
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS threads_new (
          tid TEXT PRIMARY KEY,
          fid TEXT NOT NULL DEFAULT '',
          title TEXT NOT NULL,
          forum_name TEXT NOT NULL DEFAULT '',
          author TEXT,
          author_id TEXT NOT NULL DEFAULT '',
          posted_at TEXT,
          reply_count INTEGER NOT NULL DEFAULT 0,
          view_count INTEGER NOT NULL DEFAULT 0,
          heatlevel INTEGER NOT NULL DEFAULT 0,
          source_page INTEGER,
          detail_status TEXT NOT NULL DEFAULT 'pending',
          detail_error TEXT,
          participant_count INTEGER NOT NULL DEFAULT 0,
          money INTEGER NOT NULL DEFAULT 0,
          rating TEXT NOT NULL DEFAULT '',
          fetch_comments INTEGER NOT NULL DEFAULT 0
        );
        """
    )
    # Copy, drop and rename are one transaction: interruption cannot leave
    # the original table deleted while its replacement is still unrenamed.
    with conn:
        _copy_threads_to_new_schema(conn, existing)
        conn.execute("DROP TABLE threads")
        conn.execute("ALTER TABLE threads_new RENAME TO threads")
        for name, column in (
            ("posted_at", "posted_at"), ("source_page", "source_page"),
            ("detail_status", "detail_status"), ("reply_count", "reply_count"),
        ):
            conn.execute(f"CREATE INDEX IF NOT EXISTS idx_threads_{name} ON threads({column})")
    _ensure_performance_indexes(conn)


def _copy_threads_to_new_schema(conn: sqlite3.Connection, existing: set[str]) -> None:
    """把旧 threads 表中仍然有用的列复制到新表。"""
    columns = [
        ("tid", "''"),
        ("fid", "''"),
        ("title", "''"),
        ("forum_name", "''"),
        ("author", "NULL"),
        ("author_id", "''"),
        ("posted_at", "NULL"),
        ("reply_count", "0"),
        ("view_count", "0"),
        ("heatlevel", "0"),
        ("source_page", "NULL"),
        ("detail_status", "'pending'"),
        ("detail_error", "NULL"),
        ("participant_count", "0"),
        ("money", "0"),
        ("rating", "''"),
        ("fetch_comments", "0"),
    ]
    target_columns = ", ".join(name for name, _ in columns)
    source_parts = []
    for name, default in columns:
        if name == "rating" and name in existing:
            # 旧评分值可能带正负号；当前界面按正数排序，迁移时统一归一化。
            source_parts.append(
                "CASE "
                "WHEN rating IS NULL OR rating = '' THEN '' "
                "WHEN instr(rating, '-') > 0 THEN replace(replace(rating, '+', ''), '-', '') "
                "ELSE replace(rating, '+', '') "
                "END"
            )
        else:
            source_parts.append(name if name in existing else default)
    source_columns = ", ".join(source_parts)
    conn.execute(
        f"""
        INSERT OR REPLACE INTO threads_new ({target_columns})
        SELECT {source_columns}
        FROM threads
        """
    )


def _ensure_column(
    conn: sqlite3.Connection,
    table_name: str,
    column_name: str,
    column_definition: str,
) -> None:
    """在已有表缺少字段时追加字段，用于小步兼容迁移。"""
    existing = {
        row["name"]
        for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name not in existing:
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}")


def upsert_thread(
    conn: sqlite3.Connection,
    topic: Topic,
    source_page: int,
    seen_at: str,
    forum_name: str = "",
    fid: str = "",
    *,
    commit: bool = True,
) -> None:
    """插入或更新列表页解析出的帖子基础信息。"""
    tid = extract_tid(topic.url)
    if not tid:
        raise ValueError(f"无法从帖子链接提取 tid：{topic.url}")
    conn.execute(
        """
        INSERT INTO threads (
          tid, fid, title, forum_name, author, author_id, posted_at, reply_count, view_count,
          heatlevel, source_page, list_fetched_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(tid) DO UPDATE SET
          fid = excluded.fid,
          title = excluded.title,
          forum_name = excluded.forum_name,
          author = excluded.author,
          author_id = excluded.author_id,
          posted_at = excluded.posted_at,
          reply_count = excluded.reply_count,
          view_count = excluded.view_count,
          heatlevel = excluded.heatlevel,
          source_page = excluded.source_page,
          list_fetched_at = excluded.list_fetched_at
        """,
        (
            tid,
            fid,
            topic.title,
            forum_name,
            topic.author,
            topic.author_id,
            topic.posted_at,
            topic.replies,
            topic.views,
            topic.heatlevel,
            source_page,
            seen_at,
        ),
    )
    record_thread_metrics(conn, tid, seen_at, topic.replies, topic.views)
    if commit:
        conn.commit()


def upsert_comment(conn: sqlite3.Connection, comment: dict, *, commit: bool = True) -> None:
    """插入或更新单条评论，按 tid 和 comment_id 去重。"""
    conn.execute(
        """
        INSERT INTO comments (
          tid, comment_id, author, author_id, posted_at, content_text, source_page, fetched_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(tid, comment_id) DO UPDATE SET
          author = excluded.author,
          author_id = excluded.author_id,
          posted_at = excluded.posted_at,
          content_text = excluded.content_text,
          source_page = excluded.source_page,
          fetched_at = excluded.fetched_at
        """,
        (
            comment["tid"],
            comment["comment_id"],
            comment.get("author", ""),
            comment.get("author_id", ""),
            comment.get("posted_at", ""),
            comment.get("content_text", ""),
            comment.get("source_page", 1),
            comment["fetched_at"],
        ),
    )
    if commit:
        conn.commit()


def save_comments(database_path: str, comments: list[dict]) -> None:
    """把一批评论写入数据库；空列表直接跳过。"""
    if not comments:
        return
    conn = connect_db(database_path)
    try:
        with conn:
            for comment in comments:
                upsert_comment(conn, comment, commit=False)
    finally:
        conn.close()


def update_thread_detail(
    conn: sqlite3.Connection,
    tid: str,
    status: str,
    fetched_at: str,
    content_text: str = "",
    image_urls: list[str] | None = None,
    participant_count: int = 0,
    money: int = 0,
    rating: str = "",
    error: str = "",
    metrics_repaired_at: str | None = None,
    reward_money: int | None = None,
    purchase_count: int | None = None,
) -> None:
    """更新帖子详情抓取状态和详情页指标。"""
    conn.execute(
        """
        UPDATE threads
        SET detail_status = ?,
            detail_error = ?,
            participant_count = ?,
            money = ?,
            rating = ?,
            reward_money = COALESCE(?, reward_money),
            purchase_count = COALESCE(?, purchase_count),
            metrics_repaired_at = CASE
              WHEN ? IS NULL THEN metrics_repaired_at
              ELSE ?
            END
        WHERE tid = ?
        """,
        (
            status,
            error,
            participant_count,
            money,
            rating,
            reward_money,
            purchase_count,
            metrics_repaired_at,
            metrics_repaired_at,
            tid,
        ),
    )
    conn.commit()


def claim_detail_rows(conn: sqlite3.Connection, limit: int, job_id: str | None = None) -> list[sqlite3.Row]:
    """领取一批待抓详情的帖子，并把状态标记为 processing。"""
    # 用立即事务一次性预留任务，避免多个详情爬虫抓取同一个帖子。
    conn.execute("BEGIN IMMEDIATE")
    try:
        rows = conn.execute(
            """
            SELECT tid, fid
            FROM threads
            WHERE detail_status IN ('pending', 'failed')
            ORDER BY posted_at DESC, tid DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        if rows:
            placeholders = ", ".join("?" for _ in rows)
            conn.execute(
                f"UPDATE threads SET detail_status = 'processing', detail_error = '' WHERE tid IN ({placeholders})",
                [row["tid"] for row in rows],
            )
        if job_id:
            conn.executemany('INSERT INTO crawl_detail_claims(job_id, tid) VALUES (?, ?)',
                             [(job_id, row['tid']) for row in rows])
        conn.commit()
        return rows
    except Exception:
        conn.rollback()
        raise
