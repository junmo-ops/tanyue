from __future__ import annotations

from forum_backend.config import site_cookie
from .common import (
    COMMENT_PROGRESS,
    COMMENT_PROGRESS_LOCK,
    DEFAULT_CONFIG,
    comment_settings,
    connect_db,
    load_config,
    load_runtime_settings,
    network_settings,
    official_thread_url,
    site_settings,
    sqlite3,
)


def _default_comment_progress(tid: str) -> dict:
    return {
        "tid": tid,
        "status": "idle",
        "completed_pages": 0,
        "total_pages": 0,
        "percent": 0,
        "saved_comments": 0,
        "error": "",
    }


def update_comment_progress(tid: str, *, scope='', **updates) -> dict:
    tid = str(tid).strip()
    if not tid:
        raise ValueError("tid is required")
    with COMMENT_PROGRESS_LOCK:
        progress = {**_default_comment_progress(tid), **COMMENT_PROGRESS.get((scope, tid), {})}
        progress.update({key: value for key, value in updates.items() if value is not None})
        total_pages = int(progress.get("total_pages") or 0)
        completed_pages = int(progress.get("completed_pages") or 0)
        progress["completed_pages"] = completed_pages
        progress["total_pages"] = total_pages
        progress["percent"] = min(100, round(completed_pages * 100 / total_pages)) if total_pages else 0
        COMMENT_PROGRESS[scope, tid] = progress
        return dict(progress)


def reset_comment_progress(tid: str, scope='') -> dict:
    tid = str(tid).strip()
    if not tid:
        raise ValueError("tid is required")
    with COMMENT_PROGRESS_LOCK:
        COMMENT_PROGRESS[scope, tid] = _default_comment_progress(tid)
        return dict(COMMENT_PROGRESS[scope, tid])


def get_comment_progress(tid: str, scope='') -> dict:
    tid = str(tid).strip()
    if not tid:
        raise ValueError("tid is required")
    with COMMENT_PROGRESS_LOCK:
        return dict(COMMENT_PROGRESS.get((scope, tid), _default_comment_progress(tid)))


def fetch_missing_thread_comments(
    database_path: str,
    base_url: str,
    tid: str,
    config: dict | None = None,
    progress_callback=None,
) -> dict:
    """Fetch comments for one thread when the local database has none."""
    from forum_backend.crawler import fetch_thread_comments

    config = config or load_config(DEFAULT_CONFIG)
    site = site_settings(config)
    comments = comment_settings(config)
    network = network_settings(config)
    cookie = site_cookie(config)
    comment_pages = comments.get("pages", "all")
    comment_page_workers = max(1, int(comments.get("page_workers", 3)))
    settings = load_runtime_settings(config)
    settings["delay_seconds"] = float(network.get("delay_seconds", 0.2))
    settings["jitter_seconds"] = float(network.get("jitter_seconds", 0.2))
    row_base_url = site.get("base_url") or base_url

    conn = connect_db(database_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            """
            SELECT tid
            FROM threads
            WHERE tid = ?
            """,
            (tid,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise ValueError("thread not found")

    reset_comment_progress(tid, str(database_path))
    return fetch_thread_comments(
        row,
        thread_index=1,
        total_threads=1,
        base_url=row_base_url,
        cookie=cookie,
        comment_pages=comment_pages,
        comment_page_workers=comment_page_workers,
        database_path=database_path,
        settings=settings,
        progress_callback=progress_callback or (lambda progress: update_comment_progress(scope=str(database_path), **progress)),
    )


def query_thread_detail(
    database_path: str,
    base_url: str,
    tid: str,
    *,
    fetch_missing_comments: bool = False,
    config: dict | None = None,
    params: dict | None = None,
) -> dict:
    """Read a bounded comment page; filters apply to the complete comment set."""
    from .common import _first, _positive_int, split_keywords, forum_display_name
    tid = str(tid or "").strip()
    if not tid:
        raise ValueError("tid is required")
    params = params or {}
    page = _positive_int(params, "page", 1)
    page_size = _positive_int(params, "page_size", 50, maximum=200)
    conn = connect_db(database_path)
    try:
        conn.execute("BEGIN")
        thread = conn.execute("SELECT * FROM threads WHERE tid=?", (tid,)).fetchone()
        if thread is None:
            raise ValueError("thread not found")
        total_comments = conn.execute("SELECT COUNT(*) FROM comments WHERE tid=?", (tid,)).fetchone()[0]
        clauses, values = ["tid=?"], [tid]
        for name, operator in (("q", "> 0"), ("exclude_q", "= 0")):
            for keyword in split_keywords(_first(params, name, "")):
                clauses.append(f"instr(lower(COALESCE(content_text, '')), ?) {operator}")
                values.append(keyword.lower())
        where = " AND ".join(clauses)
        total = conn.execute(f"SELECT COUNT(*) FROM comments WHERE {where}", values).fetchone()[0]
        page = min(page, max(1, (total + page_size - 1) // page_size))
        comments = conn.execute(
            f"SELECT * FROM comments WHERE {where} ORDER BY source_page, comment_id LIMIT ? OFFSET ?",
            [*values, page_size, (page - 1) * page_size],
        ).fetchall()
    finally:
        conn.close()
    if fetch_missing_comments and not total_comments:
        raise ValueError("use POST /api/comment-jobs to fetch comments")
    thread_item = dict(thread)
    thread_item["official_url"] = official_thread_url(base_url, tid)
    thread_item["forum_name"] = forum_display_name(thread_item["fid"], config, fallback=thread_item["forum_name"])
    return {
        "thread": thread_item,
        "comments": [dict(comment) for comment in comments],
        "total": total,
        "total_comments": total_comments,
        "page": page,
        "page_size": page_size,
        "comment_fetch": {"status": "skipped", "error": ""},
    }
