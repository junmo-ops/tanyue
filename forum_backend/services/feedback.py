from __future__ import annotations

from forum_backend.storage.schema import ensure_feedback_schema

from .common import (
    ALLOWED_FEEDBACK,
    connect_db,
)




def save_feedback(database_path: str, tid: str, feedback: str) -> dict:
    """保存用户对单个帖子的反馈标记。"""
    tid = str(tid).strip()
    feedback = str(feedback).strip()
    if not tid:
        raise ValueError("tid is required")
    if feedback not in ALLOWED_FEEDBACK:
        raise ValueError("invalid feedback")

    conn = connect_db(database_path)
    try:
        conn.execute(
            """
            INSERT INTO thread_feedback (tid, feedback, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(tid) DO UPDATE SET
              feedback = excluded.feedback,
              updated_at = CURRENT_TIMESTAMP
            """,
            (tid, feedback),
        )
        conn.commit()
    finally:
        conn.close()
    return {"tid": tid, "feedback": feedback}


def clear_feedback(database_path: str, tid: str) -> dict:
    """清除单个帖子的反馈标记。"""
    tid = str(tid).strip()
    if not tid:
        raise ValueError("tid is required")

    conn = connect_db(database_path)
    try:
        conn.execute(
            """
            INSERT INTO thread_feedback (tid, feedback, updated_at)
            VALUES (?, '', CURRENT_TIMESTAMP)
            ON CONFLICT(tid) DO UPDATE SET
              feedback = '',
              updated_at = CURRENT_TIMESTAMP
            """,
            (tid,),
        )
        conn.commit()
    finally:
        conn.close()
    return {"tid": tid, "feedback": None}


def save_seen(database_path: str, tid: str, seen) -> dict:
    """保存单个帖子的已看状态，独立于兴趣反馈。"""
    tid = str(tid).strip()
    if not tid:
        raise ValueError("tid is required")
    seen_value = 1 if seen in {True, 1, "1", "true", "yes", "on"} else 0

    conn = connect_db(database_path)
    try:
        conn.execute(
            """
            INSERT INTO thread_feedback (tid, feedback, seen, updated_at)
            VALUES (?, '', ?, CURRENT_TIMESTAMP)
            ON CONFLICT(tid) DO UPDATE SET
              seen = excluded.seen,
              updated_at = CURRENT_TIMESTAMP
            """,
            (tid, seen_value),
        )
        conn.commit()
    finally:
        conn.close()
    return {"tid": tid, "seen": seen_value}


def save_comment_fetch(database_path: str, tid: str, enabled) -> dict:
    """保存帖子是否需要后续抓取评论的开关。"""
    tid = str(tid).strip()
    if not tid:
        raise ValueError("tid is required")
    fetch_comments = 1 if enabled in {True, 1, "1", "true", "yes", "on"} else 0

    conn = connect_db(database_path)
    try:
        conn.execute(
            "UPDATE threads SET fetch_comments = ? WHERE tid = ?",
            (fetch_comments, tid),
        )
        conn.commit()
    finally:
        conn.close()
    return {"tid": tid, "fetch_comments": fetch_comments}
