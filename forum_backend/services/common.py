from __future__ import annotations

import json
import re
import sqlite3
import sys
import threading
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin

from forum_backend.config import (
    DEFAULT_CONFIG,
    load_config,
    comment_settings,
    forum_display_name,
    load_cookie,
    load_runtime_settings,
    network_settings,
    resolve_database_path,
    site_settings,
)
from forum_backend.db import (
    connect_db,
    ensure_recommendation_schema,
    init_db,
    rebuild_recommendation_candidates,
    refresh_recommendation_candidates,
)


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
ALLOWED_SORTS = {
    "reply_count",
    "view_count",
    "heatlevel",
    "participant_count",
    "money",
    "reward_money",
    "purchase_count",
    "rating",
    "posted_at",
    "interest_score",
}
ALLOWED_FEEDBACK = {"like", "dislike", "later"}
MAX_PAGE = 10000
DEFAULT_RECOMMEND_TOP_PERCENT = 50
WORD_PATTERN = re.compile(r"[A-Za-z0-9\u4e00-\u9fff]{2,}")
TITLE_WORD_STATS_VERSION = 1
COMMENT_PROGRESS_LOCK = threading.Lock()
COMMENT_PROGRESS: dict[str, dict] = {}
NEGATIVE_TOKEN_STOPWORDS = {
    "整理",
    "合集",
    "最新",
    "配额",
    "ed2k",
    "115ed2k",
    "115",
    "magnet",
    "磁力",
    "中字",
    "英语中字",
    "回复有金",
    "自转",
    "自整理",
    "新作",
}


def official_thread_url(base_url: str, tid: str) -> str:
    """根据站点域名和 tid 拼出官方帖子详情链接。"""
    return urljoin(base_url.rstrip("/") + "/", f"forum.php?mod=viewthread&tid={tid}")


def _first(params: dict, name: str, default: str = "") -> str:
    """从 parse_qs 或 JSON body 风格参数中取第一个值。"""
    value = params.get(name, default)
    if isinstance(value, list):
        return value[0] if value else default
    return value


def split_keywords(value: str) -> list[str]:
    """把空格、中文逗号、顿号等分隔的关键词拆成列表。"""
    return [
        part.strip()
        for part in re.split(r"[\s,，、;；]+", value or "")
        if part.strip()
    ]


def _positive_int(params: dict, name: str, default: int, maximum: int | None = None) -> int:
    """解析正整数查询参数，并按需限制最大值。"""
    raw = _first(params, name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value < 1:
        raise ValueError(f"{name} must be at least 1")
    if maximum is not None:
        value = min(value, maximum)
    return value


def _nonnegative_int(params: dict, name: str) -> int | None:
    """解析可选的非负整数查询参数，未传时返回 None。"""
    raw = _first(params, name, "")
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value < 0:
        raise ValueError(f"{name} must be at least 0")
    return value


def _recommend_top_percent(params: dict) -> int:
    """解析随机推荐同日排名百分比，默认取前 50%。"""
    raw = _first(params, "recommend_top_percent", str(DEFAULT_RECOMMEND_TOP_PERCENT))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError("recommend_top_percent must be an integer") from exc
    if value < 1 or value > 100:
        raise ValueError("recommend_top_percent must be between 1 and 100")
    return value


def _parse_date(value: str, name: str) -> date:
    """校验并解析 YYYY-MM-DD 日期参数。"""
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be YYYY-MM-DD") from exc
