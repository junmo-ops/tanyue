from __future__ import annotations

from .common import (
    ALLOWED_SORTS,
    DEFAULT_RECOMMEND_TOP_PERCENT,
    MAX_PAGE,
    Path,
    _first,
    _nonnegative_int,
    _parse_date,
    _positive_int,
    _recommend_top_percent,
    connect_db,
    datetime,
    forum_display_name,
    official_thread_url,
    split_keywords,
    sqlite3,
    timedelta,
)
from .recommendation import ensure_recommendation_candidates
from .recommendation import title_tokens, is_title_word_ignored, display_title_words, load_feedback_tokens, calculate_interest_score, calculate_negative_score, add_negative_scores

def query_threads(database_path: str, base_url: str, params: dict, *, config: dict | None = None) -> dict:
    """查询帖子列表，支持筛选、排序、分页和随机推荐模式。"""
    page = _positive_int(params, "page", 1)
    if page > MAX_PAGE:
        raise ValueError(f"page must be at most {MAX_PAGE}")
    page_size = _positive_int(params, "page_size", 50, maximum=200)
    recommend = _first(params, "recommend", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    sort = _first(params, "sort", "reply_count")
    order = _first(params, "order", "desc").lower()
    if sort not in ALLOWED_SORTS:
        raise ValueError("invalid sort")
    if order not in {"asc", "desc"}:
        raise ValueError("invalid order")

    where = []
    values = []
    for keyword in split_keywords(_first(params, "q", "")):
        where.append("(t.title LIKE ? OR t.tid LIKE ?)")
        values.extend([f"%{keyword}%", f"%{keyword}%"])
    for exclude_q in split_keywords(_first(params, "exclude_q", "")):
        where.append("t.title NOT LIKE ?")
        values.append(f"%{exclude_q}%")
    fid = _first(params, "fid", "").strip()
    if fid:
        where.append("t.fid = ?")
        values.append(fid)
    author_id = _first(params, "author_id", "").strip()
    if author_id:
        where.append("t.author_id = ?")
        values.append(author_id)
    posted_date = _first(params, "posted_date", "").strip()
    if posted_date:
        _parse_date(posted_date, "posted_date")
        where.append("t.posted_at LIKE ?")
        values.append(f"{posted_date}%")
    posted_date_from = _first(params, "posted_date_from", "").strip()
    if posted_date_from:
        where.append("t.posted_at >= ?")
        values.append(_parse_date(posted_date_from, "posted_date_from").isoformat())
    posted_date_to = _first(params, "posted_date_to", "").strip()
    if posted_date_to:
        next_day = _parse_date(posted_date_to, "posted_date_to") + timedelta(days=1)
        where.append("t.posted_at < ?")
        values.append(next_day.isoformat())
    min_replies = _nonnegative_int(params, "min_replies")
    if min_replies is not None:
        where.append("t.reply_count >= ?")
        values.append(min_replies)
    min_views = _nonnegative_int(params, "min_views")
    if min_views is not None:
        where.append("t.view_count >= ?")
        values.append(min_views)
    show_disliked = _first(params, "show_disliked", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if not show_disliked:
        where.append("(tf.feedback IS NULL OR tf.feedback != 'dislike')")
    hide_seen = _first(params, "hide_seen", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if hide_seen:
        where.append("COALESCE(tf.seen, 0) = 0")
    only_liked = _first(params, "only_liked", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if only_liked:
        where.append("tf.feedback = 'like'")
    where_sql = " WHERE " + " AND ".join(where) if where else ""
    recommendation_filter_sql = "AND" if where else "WHERE"
    offset = (page - 1) * page_size
    recommend_top_percent = _recommend_top_percent(params) if recommend else DEFAULT_RECOMMEND_TOP_PERCENT
    conn = connect_db(database_path)
    conn.row_factory = sqlite3.Row
    try:
        if recommend:
            ensure_recommendation_candidates(conn, database_path)
            page = 1
            page_size = 50
            rows = conn.execute(
                f"""
                SELECT t.tid, t.fid, t.title, t.forum_name, t.author, t.author_id, t.posted_at,
                       t.reply_count, t.view_count, t.heatlevel, t.source_page, t.detail_status,
                       t.participant_count, t.money, t.reward_money, t.purchase_count, t.rating, t.fetch_comments, tf.feedback,
                       COALESCE(tf.seen, 0) AS seen,
                       0 AS interest_score
                FROM thread_recommendation_candidates rc
                JOIN threads t ON t.tid = rc.tid
                LEFT JOIN thread_feedback tf USING (tid)
                {where_sql}
                {recommendation_filter_sql} (
                  rc.reply_rank <= ((rc.day_count * ? + 99) / 100)
                  OR rc.view_rank <= ((rc.day_count * ? + 99) / 100)
                )
                ORDER BY RANDOM()
                LIMIT 50
                """,
                [*values, recommend_top_percent, recommend_top_percent],
            ).fetchall()
            total = len(rows)
        elif sort == "interest_score":
            rows = conn.execute(
                f"""
                SELECT tid, fid, title, forum_name, author, author_id, posted_at,
                       reply_count, view_count, heatlevel, source_page, detail_status,
                       participant_count, money, reward_money, purchase_count, rating, fetch_comments, tf.feedback,
                       COALESCE(tf.seen, 0) AS seen
                FROM threads t
                LEFT JOIN thread_feedback tf USING (tid)
                {where_sql}
                """,
                values,
            ).fetchall()
            liked_tokens, disliked_tokens = load_feedback_tokens(conn)
            all_rows = add_negative_scores(rows, disliked_tokens)
            total = len(all_rows)
            all_rows = [
                {
                    **row,
                    "interest_score": calculate_interest_score(row, liked_tokens, disliked_tokens),
                }
                for row in all_rows
            ]
            reverse = order == "desc"
            all_rows.sort(
                key=lambda row: (row["interest_score"], str(row["tid"])),
                reverse=reverse,
            )
            rows = all_rows[offset : offset + page_size]
        else:
            order_expr = "CAST(rating AS INTEGER)" if sort == "rating" else sort
            total = conn.execute(
                f"""
                SELECT COUNT(1)
                FROM threads t
                LEFT JOIN thread_feedback tf USING (tid)
                {where_sql}
                """,
                values,
            ).fetchone()[0]
            rows = conn.execute(
                f"""
                SELECT tid, fid, title, forum_name, author, author_id, posted_at,
                       reply_count, view_count, heatlevel, source_page, detail_status,
                       participant_count, money, reward_money, purchase_count, rating, fetch_comments, tf.feedback,
                       COALESCE(tf.seen, 0) AS seen,
                       0 AS interest_score
                FROM threads t
                LEFT JOIN thread_feedback tf USING (tid)
                {where_sql}
                ORDER BY {order_expr} {order.upper()}, tid DESC
                LIMIT ? OFFSET ?
                """,
                [*values, page_size, offset],
            ).fetchall()
    finally:
        conn.close()

    items = []
    for row in rows:
        item = dict(row)
        item["forum_name"] = forum_display_name(item["fid"], config, fallback=item["forum_name"])
        item["feedback"] = item.get("feedback") or None
        item["official_url"] = official_thread_url(base_url, row["tid"])
        items.append(item)

    total_pages = (total + page_size - 1) // page_size if total else 0
    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
    }


def query_forums(database_path: str, configured: tuple[str, ...] = (), *, config: dict | None = None) -> dict:
    """查询已采集和已配置的板块及其帖子数量。"""
    conn = connect_db(database_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT fid, COUNT(1) AS thread_count
            FROM threads
            WHERE fid != ''
            GROUP BY fid
            ORDER BY CAST(fid AS INTEGER), fid
            """
        ).fetchall()
    finally:
        conn.close()

    counts = {row["fid"]: row["thread_count"] for row in rows}
    for fid in configured:
        counts.setdefault(fid, 0)
    return {
        "items": [
            {
                "fid": fid,
                "forum_name": forum_display_name(fid, config),
                "thread_count": count,
            }
            for fid, count in counts.items()
        ]
    }


def query_data_status(database_path: str, environment: str) -> dict:
    """返回当前数据库环境、规模和最近同步状态。"""
    conn = connect_db(database_path)
    conn.row_factory = sqlite3.Row
    try:
        thread_count = conn.execute("SELECT COUNT(1) FROM threads").fetchone()[0]
        latest_posted_at = conn.execute("SELECT MAX(posted_at) FROM threads").fetchone()[0]
        last_run = conn.execute(
            """
            SELECT kind, started_at, finished_at, success_count, failure_count, error
            FROM crawl_runs
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
    finally:
        conn.close()

    path = Path(database_path)
    return {
        "environment": str(environment or ""),
        "database_name": path.name,
        "thread_count": thread_count,
        "latest_posted_at": latest_posted_at or "",
        "database_modified_at": (
            datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds") if path.exists() else ""
        ),
        "last_sync": dict(last_run) if last_run else None,
    }
