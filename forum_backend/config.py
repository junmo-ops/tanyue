from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Iterable
from urllib.parse import urlencode, urljoin, urlparse, urlunparse, parse_qsl

DEFAULT_CONFIG = str(Path(__file__).resolve().parents[1] / "config.json")

@lru_cache(maxsize=1)
def _default_forum_names() -> dict:
    return load_config().get("list_sync", {}).get("forums", {})


def forum_display_name(fid: str, config: dict | None = None, *, fallback: str | None = None) -> str:
    """Return the configured display label for a forum id."""
    normalized_fid = str(fid).strip()
    names = (config or {}).get("list_sync", {}).get("forums")
    if names is None:
        names = _default_forum_names()
    return names.get(normalized_fid) or fallback or f"fid {normalized_fid}"


def extract_tid(url: str) -> str:
    """从帖子详情 URL 中提取 tid 参数。"""
    return extract_query_value(url, "tid")


def extract_query_value(url: str, name: str) -> str:
    """从 URL 查询参数中读取指定字段，缺失时返回空字符串。"""
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if name == 'tid' and not query.get(name):
        match = re.search(r'/thread-([0-9]+)-[0-9]+-[0-9]+\.html$', parsed.path)
        return match[1] if match else ''
    return query.get(name, "")


def build_page_url(base_url: str, page: int) -> str:
    """基于列表页 URL 构造指定页码的 URL。"""
    if page < 1:
        raise ValueError("--pages must be at least 1")
    if page == 1:
        return base_url

    parsed = urlparse(base_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if page > 1:
        query["page"] = str(page)
    return urlunparse(parsed._replace(query=urlencode(query)))


def build_detail_page_url(detail_url: str, page: int) -> str:
    """基于详情页 URL 构造指定评论分页的 URL。"""
    if page <= 1:
        return detail_url
    parsed = urlparse(detail_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["page"] = str(page)
    return urlunparse(parsed._replace(query=urlencode(query)))


def build_source_url(base_url: str, forum_path: str) -> str:
    """把域名和论坛列表路径拼成完整抓取入口。"""
    if not base_url:
        raise ValueError("配置缺少 base_url。")
    if not forum_path:
        raise ValueError("配置缺少 forum_path。")
    return urljoin(base_url.rstrip("/") + "/", forum_path.lstrip("/"))


def source_url_from_config(config: dict, override_url: str | None = None) -> str:
    """从配置或临时覆盖参数中解析最终列表页 URL。"""
    if override_url:
        return override_url
    if config.get("_url"):
        return str(config["_url"])
    fid = str(config.get("_fid") or configured_fids(config)[0]).strip()
    forum_path = f"/forum.php?{urlencode({'mod': 'forumdisplay', 'fid': fid, 'filter': 'author', 'orderby': 'dateline'})}"
    return build_source_url(site_settings(config).get("base_url", ""), forum_path)


def configured_fids(config: dict) -> list[str]:
    """读取去重后的板块 ID 列表。"""
    if config.get("_url"):
        fid = extract_query_value(str(config["_url"]), "fid")
        if not fid:
            raise ValueError("列表 URL 缺少 fid。")
        return [fid]

    settings = list_sync_settings(config)
    raw_fids = settings.get("fids")
    if "fids" not in settings:
        raw_fids = list(settings.get("forums", {}))
    if isinstance(raw_fids, (str, int)):
        raw_fids = [raw_fids]
    if not isinstance(raw_fids, list):
        raise ValueError("配置 fids 必须是数组。")

    fids: list[str] = []
    for value in raw_fids:
        fid = str(value).strip()
        if fid and fid not in fids:
            fids.append(fid)

    if not fids:
        raise ValueError("配置必须包含至少一个板块。")
    return fids


def config_section(config: dict, name: str) -> dict:
    """读取必需的配置分组，并拒绝缺失或类型错误的分组。"""
    section = config.get(name)
    if not isinstance(section, dict):
        raise ValueError(f"配置缺少对象分组：{name}")
    return section


def site_settings(config: dict) -> dict:
    return config_section(config, "site")


def database_settings(config: dict) -> dict:
    return config_section(config, "database")


def list_sync_settings(config: dict) -> dict:
    return config_section(config, "list_sync")


def detail_settings(config: dict) -> dict:
    return config_section(config, "details")


def comment_settings(config: dict) -> dict:
    return config_section(config, "comments")


def network_settings(config: dict) -> dict:
    return config_section(config, "network")


def iter_page_urls(
    base_url: str,
    start_page: int,
    pages: int,
) -> Iterable[str]:
    """按起始页和页数连续生成列表页 URL。"""
    if start_page < 1:
        raise ValueError("--start-page must be at least 1")
    if pages < 1:
        raise ValueError("--pages must be at least 1")

    for page in range(start_page, start_page + pages):
        yield build_page_url(base_url, page)


def load_cookie(cookie_value: str | None, cookie_file: str | None) -> str:
    """优先使用命令行 Cookie，否则从 Cookie 文件读取登录态。"""
    if cookie_value and cookie_value.strip():
        return cookie_value.strip()

    if cookie_file:
        cookie = Path(cookie_file).read_text(encoding="utf-8").strip()
        if cookie:
            return cookie

    raise ValueError("请通过 --cookie 或 --cookie-file 提供登录 Cookie。")


def site_cookie(config: dict) -> str:
    site = site_settings(config)
    path = config.get('_cookie_file') or site.get('cookie_file')
    if site.get('anonymous_allowed') and not config.get('_cookie'):
        return Path(path).read_text(encoding='utf-8').strip() if path else ''
    return load_cookie(config.get('_cookie'), path)


def load_config(config_file: str = DEFAULT_CONFIG) -> dict:
    """读取 JSON 配置文件，文件不存在时返回空配置。"""
    path = Path(config_file)
    if not path.exists():
        if path != Path(DEFAULT_CONFIG):
            return {}
        path = path.with_name("config.example.json")
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"配置文件不是合法 JSON：{config_file}；原因：{exc}") from exc
    if not isinstance(config, dict):
        raise ValueError("配置文件顶层必须是 JSON 对象。")
    for section_name in ("site", "database", "list_sync", "details", "comments", "network"):
        config_section(config, section_name)
    forums = list_sync_settings(config).get("forums", {})
    if not isinstance(forums, dict) or any(
        not fid.strip() or fid != fid.strip() or not isinstance(name, str) or not name.strip()
        for fid, name in forums.items()
    ):
        raise ValueError("配置 list_sync.forums 必须是板块 ID 到非空名称的映射。")
    root = path.resolve().parent
    site = config.get("site", {})
    if site.get("cookie_file"):
        site["cookie_file"] = str((root / site["cookie_file"]).resolve())
    paths = config.get("database", {}).get("paths", {})
    for environment, database_path in paths.items():
        paths[environment] = str((root / database_path).resolve())
    return config


def resolve_database_path(config: dict) -> str:
    """根据当前环境解析 SQLite 数据库路径。"""
    settings = database_settings(config)
    environment = str(settings.get("environment", "")).strip()
    database_paths = settings.get("paths")
    if not environment:
        raise ValueError("配置缺少 database.environment。")
    if not isinstance(database_paths, dict):
        raise ValueError("配置 database.paths 必须是对象。")
    database_path = database_paths.get(environment)
    if database_path:
        return str(database_path)
    raise ValueError(f"配置的 database.environment 没有对应路径：{environment}")


def load_runtime_settings(config: dict) -> dict:
    """从配置中提取爬虫运行时参数并转换为数字类型。"""
    network = network_settings(config)
    manual_list = config.get("_manual_list", {})
    return {
        "purchase_count_money_fids": config.get("details", {}).get("purchase_count_money_fids", []),
        "start_page": int(manual_list.get("start_page", 1)),
        "pages": int(manual_list.get("pages", 5)),
        "delay_seconds": float(network.get("delay_seconds", 1.5)),
        "jitter_seconds": float(network.get("jitter_seconds", 1.0)),
        "retries": int(network.get("retries", 2)),
        "retry_backoff_seconds": float(network.get("retry_backoff_seconds", 2.0)),
    }


def parse_bool(value, default: bool = False) -> bool:
    """把配置里的布尔开关兼容解析为 Python bool。"""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def parse_tid_list(values) -> list[str]:
    """把逗号分隔或重复传入的 tid 参数整理成去重列表。"""
    if not values:
        return []
    if isinstance(values, str):
        values = [values]
    tids: list[str] = []
    for value in values:
        for tid in str(value).split(","):
            tid = tid.strip()
            if tid and tid not in tids:
                tids.append(tid)
    return tids
