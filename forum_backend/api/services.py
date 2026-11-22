from __future__ import annotations

from forum_backend.services.common import *  # noqa: F401,F403 - legacy public exports



from forum_backend.services.common import official_thread_url, _first, split_keywords, _positive_int, _nonnegative_int, _recommend_top_percent, _parse_date
from forum_backend.services.feedback import ensure_feedback_schema, save_feedback, clear_feedback, save_seen, save_comment_fetch
from forum_backend.services.recommendation import ensure_recommendation_candidates
from forum_backend.services.recommendation import title_tokens, is_title_word_ignored, display_title_words, load_feedback_tokens, calculate_interest_score, calculate_negative_score, add_negative_scores
from forum_backend.services.comments import _default_comment_progress, update_comment_progress, reset_comment_progress, get_comment_progress, fetch_missing_thread_comments, query_thread_detail
from forum_backend.services.threads import query_threads, query_forums, query_data_status
from forum_backend.services.insights import query_insights
from forum_backend.services.words import collect_title_word_stats, ensure_title_word_stats_schema, title_word_stats_cache_valid, rebuild_title_word_stats, query_cached_title_words, query_live_title_words, query_title_words

def handle_api_insights(database_path: str, base_url: str, params: dict, *, config: dict | None = None) -> tuple[dict, int]:
    try:
        return query_insights(database_path, base_url, params, config=config), 200
    except ValueError as exc:
        return {"error": str(exc)}, 400
    except sqlite3.Error as exc:
        print(f"database error: {exc}", file=sys.stderr)
        return {"error": "database error"}, 500


def handle_api_threads(database_path: str, base_url: str, params: dict, *, config: dict | None = None) -> tuple[dict, int]:
    """处理帖子列表 API，并把业务异常转换成 HTTP 状态。"""
    try:
        return query_threads(database_path, base_url, params, config=config), 200
    except ValueError as exc:
        return {"error": str(exc)}, 400
    except sqlite3.Error as exc:
        print(f"database error: {exc}", file=sys.stderr)
        return {"error": "database error"}, 500


def handle_api_thread(database_path: str, base_url: str, params: dict, config: dict | None = None) -> tuple[dict, int]:
    """处理单帖详情 API。"""
    try:
        fetch_missing_comments = _first(params, "fetch_missing_comments", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        return query_thread_detail(
            database_path,
            base_url,
            _first(params, "tid"),
            fetch_missing_comments=fetch_missing_comments,
            config=config,
            params=params,
        ), 200
    except ValueError as exc:
        return {"error": str(exc)}, 400
    except sqlite3.Error as exc:
        print(f"database error: {exc}", file=sys.stderr)
        return {"error": "database error"}, 500


def handle_api_comment_progress(params: dict, scope='') -> tuple[dict, int]:
    """处理评论抓取进度 API。"""
    try:
        return get_comment_progress(_first(params, "tid"), scope), 200
    except ValueError as exc:
        return {"error": str(exc)}, 400


def handle_api_status(database_path: str, environment: str) -> tuple[dict, int]:
    try:
        return query_data_status(database_path, environment), 200
    except (sqlite3.Error, OSError, ValueError) as exc:
        return {"error": str(exc)}, 400


def handle_api_forums(database_path: str, configured: tuple[str, ...] = (), *, config: dict | None = None) -> tuple[dict, int]:
    """处理板块列表 API。"""
    try:
        return query_forums(database_path, configured, config=config), 200
    except sqlite3.Error as exc:
        print(f"database error: {exc}", file=sys.stderr)
        return {"error": "database error"}, 500


def handle_api_title_words(database_path: str, params: dict) -> tuple[dict, int]:
    """Handle title word statistics API requests."""
    try:
        return query_title_words(database_path, params), 200
    except ValueError as exc:
        return {"error": str(exc)}, 400
    except sqlite3.Error as exc:
        print(f"database error: {exc}", file=sys.stderr)
        return {"error": "database error"}, 500


def handle_api_feedback(database_path: str, body: dict) -> tuple[dict, int]:
    """处理保存或取消反馈的 API。"""
    try:
        tid = _first(body, "tid")
        feedback = _first(body, "feedback")
        if not feedback:
            return clear_feedback(database_path, tid), 200
        return save_feedback(database_path, tid, feedback), 200
    except ValueError as exc:
        return {"error": str(exc)}, 400
    except sqlite3.Error as exc:
        print(f"database error: {exc}", file=sys.stderr)
        return {"error": "database error"}, 500


def handle_api_seen(database_path: str, body: dict) -> tuple[dict, int]:
    """处理保存已看状态的 API。"""
    try:
        return save_seen(database_path, _first(body, "tid"), _first(body, "seen", "1")), 200
    except ValueError as exc:
        return {"error": str(exc)}, 400
    except sqlite3.Error as exc:
        print(f"database error: {exc}", file=sys.stderr)
        return {"error": "database error"}, 500


def handle_api_comment_fetch(database_path: str, body: dict) -> tuple[dict, int]:
    """处理评论抓取开关 API。"""
    try:
        return save_comment_fetch(
            database_path,
            _first(body, "tid"),
            _first(body, "fetch_comments"),
        ), 200
    except ValueError as exc:
        return {"error": str(exc)}, 400
    except sqlite3.Error as exc:
        print(f"database error: {exc}", file=sys.stderr)
        return {"error": "database error"}, 500
