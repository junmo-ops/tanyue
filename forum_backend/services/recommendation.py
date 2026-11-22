from __future__ import annotations

from forum_backend.db import rebuild_recommendation_candidates
import sqlite3
from .common import Counter, NEGATIVE_TOKEN_STOPWORDS, WORD_PATTERN

def ensure_recommendation_candidates(conn: sqlite3.Connection, database_path: str) -> None:
    """在排名缓存为空或仍是旧格式数据时自动刷新。"""
    row = conn.execute(
        """
        SELECT COUNT(1) AS total,
               SUM(CASE WHEN day_count > 0 AND reply_rank > 0 AND view_rank > 0 THEN 1 ELSE 0 END) AS ranked_total
        FROM thread_recommendation_candidates
        """
    ).fetchone()
    if row["total"] == 0 or row["ranked_total"] != row["total"]:
        rebuild_recommendation_candidates(conn)
        conn.commit()



def title_tokens(title: str) -> set[str]:
    """提取标题中的推荐关键词，并过滤低价值停用词。"""
    return {
        token.lower()
        for token in WORD_PATTERN.findall(title or "")
        if token.lower() not in NEGATIVE_TOKEN_STOPWORDS
        and not token.isdigit()
    }

def is_title_word_ignored(token: str) -> bool:
    normalized = token.lower()
    return (
        normalized in NEGATIVE_TOKEN_STOPWORDS
        or token.isdigit()
        or any(char.isdigit() for char in token)
        or token.isascii() and token.isalpha()
    )


def display_title_words(title: str) -> list[tuple[str, str]]:
    """Extract display words from a title with a normalized key for counting."""
    words = []
    for token in WORD_PATTERN.findall(title or ""):
        normalized = token.lower()
        if is_title_word_ignored(token):
            continue
        words.append((normalized, token))
    return words


def load_feedback_tokens(conn: sqlite3.Connection) -> tuple[set[str], set[str]]:
    """根据用户正负反馈聚合标题关键词偏好。"""
    liked_counts: Counter[str] = Counter()
    disliked_counts: Counter[str] = Counter()
    rows = conn.execute(
        """
        SELECT t.title, tf.feedback
        FROM thread_feedback tf
        JOIN threads t ON t.tid = tf.tid
        WHERE tf.feedback IN ('like', 'dislike')
        """
    ).fetchall()
    for row in rows:
        tokens = title_tokens(row["title"])
        if row["feedback"] == "like":
            liked_counts.update(tokens)
        elif row["feedback"] == "dislike":
            disliked_counts.update(tokens)
    liked_tokens = set(liked_counts)
    confident_disliked_tokens = {
        token
        for token, dislike_count in disliked_counts.items()
        if dislike_count >= 2 and dislike_count - (liked_counts[token] * 2) >= 2
    }
    return liked_tokens, confident_disliked_tokens


def calculate_interest_score(
    row: sqlite3.Row | dict,
    liked_tokens: set[str],
    disliked_tokens: set[str],
) -> int:
    """计算用于推荐排序的兴趣分。"""
    score = 0
    score += min(int(row["reply_count"] or 0), 200) * 2
    score += min(int(row["view_count"] or 0), 5000) // 50
    score += min(int(row["heatlevel"] or 0), 20) * 8

    tokens = title_tokens(row["title"])
    score += len(tokens & liked_tokens) * 80
    score -= len(tokens & disliked_tokens) * 80

    feedback = row["feedback"]
    if feedback == "like":
        score += 1000
    elif feedback == "later":
        score += 260
    if int(row["seen"] or 0):
        score -= 500
    if feedback == "dislike":
        score -= 1000
    return score


def calculate_negative_score(row: sqlite3.Row | dict, disliked_tokens: set[str]) -> int:
    """计算标题命中负反馈关键词的数量。"""
    tokens = title_tokens(row["title"])
    return len(tokens & disliked_tokens)


def add_negative_scores(
    rows: list[sqlite3.Row | dict],
    disliked_tokens: set[str],
) -> list[dict]:
    """给查询结果附加负反馈关键词命中数。"""
    return [
        {**dict(row), "negative_score": calculate_negative_score(row, disliked_tokens)}
        for row in rows
    ]
