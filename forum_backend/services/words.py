from __future__ import annotations

from forum_backend.storage.schema import ensure_title_word_stats_schema

from .common import (
    Counter,
    MAX_PAGE,
    TITLE_WORD_STATS_VERSION,
    _first,
    _positive_int,
    connect_db,
    split_keywords,
    sqlite3,
)
from .recommendation import display_title_words


def query_random_title_words(conn: sqlite3.Connection) -> dict:
    if not title_word_stats_cache_valid(conn):
        rebuild_title_word_stats(conn)
    # The cached words already exclude stopwords, numbers and format codes.
    # Prefer recurring short topics over one-off title fragments.
    rows = conn.execute(
        """
        SELECT display_word AS word FROM title_word_stats
        WHERE thread_count >= 3 AND length(display_word) BETWEEN 2 AND 12
        ORDER BY RANDOM() LIMIT 30
        """
    ).fetchall()
    return {"items": [dict(row) for row in rows], "mode": "random"}

def collect_title_word_stats(rows: list[sqlite3.Row]) -> tuple[list[dict], int]:
    counts: Counter[str] = Counter()
    thread_counts: Counter[str] = Counter()
    display_words: dict[str, str] = {}
    for row in rows:
        words = display_title_words(row["title"])
        counts.update(normalized for normalized, _display in words)
        thread_counts.update({normalized for normalized, _display in words})
        for normalized, display in words:
            display_words.setdefault(normalized, display)

    items = [
        {
            "normalized": word,
            "word": display_words[word],
            "count": count,
            "thread_count": thread_counts[word],
        }
        for word, count in counts.items()
    ]
    items.sort(key=lambda item: (-item["count"], item["word"].lower()))
    return items, len(rows)


def title_word_stats_cache_valid(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT value FROM title_word_stats_meta WHERE key = 'version'"
    ).fetchone()
    if not row or row["value"] != str(TITLE_WORD_STATS_VERSION):
        return False
    cached = conn.execute("SELECT value FROM title_word_stats_meta WHERE key='data_revision'").fetchone()
    revision = conn.execute("SELECT revision FROM data_versions WHERE name='titles'").fetchone()[0]
    return cached is not None and cached[0] == str(revision)


def rebuild_title_word_stats(conn: sqlite3.Connection) -> int:
    # Hold a consistent source snapshot until the derived rows are committed.
    conn.execute("BEGIN IMMEDIATE")
    revision = conn.execute("SELECT revision FROM data_versions WHERE name='titles'").fetchone()[0]
    rows = conn.execute(
        """
        SELECT tid, title
        FROM threads
        """
    ).fetchall()
    items, total_threads = collect_title_word_stats(rows)
    conn.execute("DELETE FROM title_word_stats")
    conn.executemany(
        """
        INSERT INTO title_word_stats (normalized_word, display_word, count, thread_count)
        VALUES (?, ?, ?, ?)
        """,
        [
            (item["normalized"], item["word"], item["count"], item["thread_count"])
            for item in items
        ],
    )
    conn.executemany(
        """
        INSERT OR REPLACE INTO title_word_stats_meta (key, value)
        VALUES (?, ?)
        """,
        [
            ("version", str(TITLE_WORD_STATS_VERSION)),
            ("data_revision", str(revision)),
            ("thread_count", str(total_threads)),
        ],
    )
    conn.commit()
    return total_threads


def query_cached_title_words(
    conn: sqlite3.Connection,
    page: int,
    page_size: int,
    min_count: int,
    refresh: bool,
) -> dict:
    if refresh or not title_word_stats_cache_valid(conn):
        rebuild_title_word_stats(conn)
    rows = conn.execute(
        """
        SELECT display_word AS word, count, thread_count
        FROM title_word_stats
        WHERE count >= ?
        ORDER BY count DESC, lower(display_word)
        LIMIT ? OFFSET ?
        """,
        (min_count, page_size, (page - 1) * page_size),
    ).fetchall()
    total_words = conn.execute(
        "SELECT COUNT(1) FROM title_word_stats WHERE count >= ?",
        (min_count,),
    ).fetchone()[0]
    total_threads = int(
        conn.execute(
            "SELECT value FROM title_word_stats_meta WHERE key = 'thread_count'"
        ).fetchone()["value"]
    )
    return {
        "items": [dict(row) for row in rows],
        "total_words": total_words,
        "total_threads": total_threads,
        "page": page,
        "page_size": page_size,
        "total_pages": (total_words + page_size - 1) // page_size if total_words else 0,
        "min_count": min_count,
        "cached": True,
    }


def query_live_title_words(
    conn: sqlite3.Connection,
    where_sql: str,
    values: list,
    page: int,
    page_size: int,
    min_count: int,
) -> dict:
    rows = conn.execute(
        f"""
        SELECT tid, title
        FROM threads
        {where_sql}
        """,
        values,
    ).fetchall()
    items, total_threads = collect_title_word_stats(rows)
    items = [item for item in items if item["count"] >= min_count]
    start = (page - 1) * page_size
    paged_items = items[start : start + page_size]
    return {
        "items": [
            {
                "word": item["word"],
                "count": item["count"],
                "thread_count": item["thread_count"],
            }
            for item in paged_items
        ],
        "total_words": len(items),
        "total_threads": total_threads,
        "page": page,
        "page_size": page_size,
        "total_pages": (len(items) + page_size - 1) // page_size if items else 0,
        "min_count": min_count,
        "cached": False,
    }


def query_title_words(database_path: str, params: dict) -> dict:
    """Count lightweight title words across matching threads."""
    page = _positive_int(params, "page", 1)
    if page > MAX_PAGE:
        raise ValueError(f"page must be at most {MAX_PAGE}")
    page_size = _positive_int(params, "page_size", 50, maximum=200)
    min_count = _positive_int(params, "min_count", 1, maximum=10000)
    refresh = _first(params, "refresh", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    where = []
    values = []
    fid = _first(params, "fid", "").strip()
    if fid:
        where.append("fid = ?")
        values.append(fid)
    for keyword in split_keywords(_first(params, "q", "")):
        where.append("title LIKE ?")
        values.append(f"%{keyword}%")
    where_sql = " WHERE " + " AND ".join(where) if where else ""

    conn = connect_db(database_path)
    conn.row_factory = sqlite3.Row
    try:
        if _first(params, "mode", "") == "random":
            return query_random_title_words(conn)
        if not where:
            return query_cached_title_words(conn, page, page_size, min_count, refresh)
        return query_live_title_words(conn, where_sql, values, page, page_size, min_count)
    finally:
        conn.close()
