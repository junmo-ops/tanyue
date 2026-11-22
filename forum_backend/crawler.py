from __future__ import annotations

import argparse
import datetime as dt
import random
import re
import socket
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.error import URLError
from urllib.parse import urljoin
from urllib.request import Request
from forum_backend.public_http import open_forum

from forum_backend.config import (
    DEFAULT_CONFIG,
    build_page_url,
    build_detail_page_url,
    configured_fids,
    comment_settings,
    detail_settings,
    extract_query_value,
    load_config,
    load_cookie,
    load_runtime_settings,
    parse_bool,
    parse_tid_list,
    resolve_database_path,
    site_settings,
    source_url_from_config,
    list_sync_settings,
)
from forum_backend.db import (
    claim_detail_rows,
    init_db,
    rebuild_recommendation_candidates,
    refresh_recommendation_candidates,
    save_comments,
    update_thread_detail,
    upsert_thread,
)
from forum_backend.parsers import (
    _normalize_text,
    Topic,
    detect_detail_comment_page_count,
    parse_detail_page,
    parse_topics,
)


def fetch_page(
    url: str,
    cookie: str,
    timeout: int = 20,
    retries: int = 2,
    retry_backoff_seconds: float = 2.0,
) -> str:
    """抓取单个页面 HTML，并对临时网络错误做有限重试。"""
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        },
    )
    if cookie:
        request.add_unredirected_header("Cookie", cookie)
    for attempt in range(retries + 1):
        try:
            with open_forum(request, timeout=timeout) as response:
                data = response.read(16 * 1024 * 1024 + 1)
                if len(data) > 16 * 1024 * 1024:
                    raise ValueError("页面超过 16 MiB")
                charset = response.headers.get_content_charset()
                if not charset:
                    meta = re.search(rb'<meta\s[^>]*?charset\s*=\s*["\']?([a-z0-9_-]+)', data[:8192], re.I)
                    charset = meta[1].decode('ascii') if meta else 'utf-8'
                if charset.lower() in ('gb2312', 'gbk'):
                    charset = 'gb18030'
                try:
                    return data.decode(charset, errors='replace')
                except LookupError:
                    return data.decode('utf-8', errors='replace')
        except (URLError, TimeoutError, socket.timeout) as exc:
            if attempt >= retries:
                raise RuntimeError(f"抓取失败：{url}；原因：{exc}") from exc
            wait_seconds = retry_backoff_seconds * (attempt + 1)
            print(f"抓取失败，{wait_seconds:.1f} 秒后重试：{url}")
            time.sleep(wait_seconds)
    raise RuntimeError(f"抓取失败：{url}")


def fetch_list_page(
    page_info: tuple[int, str],
    *,
    start_page: int,
    total_pages: int,
    cookie: str,
    settings: dict,
) -> tuple[int, list[Topic]]:
    """抓取并解析一个列表页，返回页码和帖子列表。"""
    index, page_url = page_info
    current_page = start_page + index - 1
    if index > 1:
        wait_seconds = settings["delay_seconds"] + random.uniform(
            0, settings["jitter_seconds"]
        )
        print(f"等待 {wait_seconds:.1f} 秒后继续")
        time.sleep(wait_seconds)
    print(f"正在抓取列表 {index}/{total_pages}：第 {current_page} 页")
    page_html = fetch_page(
        page_url,
        cookie,
        retries=settings["retries"],
        retry_backoff_seconds=settings["retry_backoff_seconds"],
    )
    topics = parse_topics(page_html, page_url)
    return current_page, topics


def crawl_list_to_db(config: dict) -> dict:
    """依次抓取配置中的板块，自动增量同步或按旧配置抓固定页数。"""
    site = site_settings(config)
    cookie = load_cookie(config.get("_cookie"), config.get("_cookie_file") or site.get("cookie_file"))
    conn = init_db(resolve_database_path(config))
    success_count = 0
    failure_count = 0
    forum_results = []
    run_id = conn.execute("INSERT INTO crawl_runs(kind, started_at) VALUES ('list', CURRENT_TIMESTAMP)").lastrowid
    conn.commit()
    try:
        for fid in configured_fids(config):
            forum_config = {**config}
            forum_config["_fid"] = fid
            try:
                if "_manual_list" in config:
                    result = _crawl_fixed_forum_list(conn, forum_config, cookie)
                else:
                    result = _crawl_incremental_forum_list(conn, forum_config, cookie)
                forum_results.append(result)
                success_count += result["processed_count"]
            except Exception as exc:
                failure_count += 1
                forum_results.append({"fid": fid, "error": str(exc)})
                print(f"fid {fid} 抓取失败，继续下一个板块：{exc}")
        candidate_count = rebuild_recommendation_candidates(conn)
        conn.commit()
        print(f"随机推荐排名缓存已刷新：{candidate_count} 条")
    except Exception as exc:
        conn.rollback()
        conn.execute("UPDATE crawl_runs SET finished_at=CURRENT_TIMESTAMP, error=?, failure_count=? WHERE id=?", (str(exc), failure_count + 1, run_id))
        conn.commit()
        raise
    else:
        errors = '; '.join(item['error'] for item in forum_results if 'error' in item)
        conn.execute("UPDATE crawl_runs SET finished_at=CURRENT_TIMESTAMP, success_count=?, failure_count=?, error=? WHERE id=?", (success_count, failure_count, errors, run_id))
        conn.commit()
    finally:
        conn.close()
    return {
        "success_count": success_count,
        "failure_count": failure_count,
        "forums": forum_results,
    }


def _fetch_list_page_batch(
    source_url: str,
    pages: list[int],
    *,
    cookie: str,
    settings: dict,
    list_workers: int,
    total_pages: int,
) -> list[tuple[int, list[Topic]]]:
    """并发抓取一小批列表页，并按页码排序返回。"""
    page_infos = [(page, build_page_url(source_url, page)) for page in pages]

    def fetch_one(page_info):
        return fetch_list_page(
            page_info,
            start_page=1,
            total_pages=total_pages,
            cookie=cookie,
            settings=settings,
        )

    worker_count = min(list_workers, len(page_infos)) if page_infos else 1
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        results = [future.result() for future in as_completed(
            [executor.submit(fetch_one, page_info) for page_info in page_infos]
        )]
    return sorted(results, key=lambda item: item[0])


def _crawl_fixed_forum_list(conn, config: dict, cookie: str) -> dict:
    """兼容旧配置和手工补数据命令，抓取明确指定的连续页范围。"""
    source_url = source_url_from_config(config)
    settings = load_runtime_settings(config)
    if settings["start_page"] < 1:
        raise ValueError("--start-page must be at least 1")
    if settings["pages"] < 1:
        raise ValueError("--pages must be at least 1")
    fid = extract_query_value(source_url, "fid")
    pages = list(range(settings["start_page"], settings["start_page"] + settings["pages"]))
    list_workers = max(1, int(list_sync_settings(config).get("workers", 1)))
    seen_at = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    processed_count = 0
    results = _fetch_list_page_batch(
        source_url,
        pages,
        cookie=cookie,
        settings=settings,
        list_workers=list_workers,
        total_pages=settings["pages"],
    )
    for current_page, topics in results:
        with conn:
            for topic in topics:
                upsert_thread(conn, topic, current_page, seen_at, fid=fid, commit=False)
        processed_count += len(topics)
    result = {
        "fid": fid,
        "pages": len(results),
        "processed_count": processed_count,
        "mode": "fixed",
    }
    print(f"fid {fid} 固定范围抓取完成：{len(results)} 页，处理 {processed_count} 条")
    return result


def _crawl_incremental_forum_list(conn, config: dict, cookie: str) -> dict:
    """刷新最近页面，并在连续命中已知帖子后自动停止。"""
    source_url = source_url_from_config(config)
    settings = load_runtime_settings(config)
    fid = extract_query_value(source_url, "fid")
    list_sync = list_sync_settings(config)
    refresh_pages = max(1, int(list_sync.get("refresh_pages", 4)))
    known_page_streak = max(1, int(list_sync.get("known_page_streak", 2)))
    max_pages = max(refresh_pages, int(list_sync.get("max_pages_per_fid", 200)))
    list_workers = max(1, int(list_sync.get("workers", 1)))
    existing_tids = {
        str(row[0])
        for row in conn.execute("SELECT tid FROM threads WHERE fid = ?", (fid,)).fetchall()
    }
    seen_this_run: set[str] = set()
    known_streak = 0
    pages_fetched = 0
    stopped = False
    seen_at = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for batch_start in range(1, max_pages + 1, list_workers):
        batch_pages = list(range(batch_start, min(batch_start + list_workers, max_pages + 1)))
        results = _fetch_list_page_batch(
            source_url,
            batch_pages,
            cookie=cookie,
            settings=settings,
            list_workers=list_workers,
            total_pages=max_pages,
        )
        for current_page, topics in results:
            pages_fetched += 1
            if not topics:
                if current_page == 1:
                    raise RuntimeError(f"fid {fid} 首页没有解析到帖子，请检查 Cookie 或页面结构。")
                stopped = True
                print(f"fid {fid} 第 {current_page} 页无帖子，已到板块末页")
                break

            page_tids = {extract_query_value(topic.url, "tid") for topic in topics}
            page_tids.discard("")
            new_on_page = page_tids - existing_tids - seen_this_run
            with conn:
                for topic in topics:
                    upsert_thread(conn, topic, current_page, seen_at, fid=fid, commit=False)
            seen_this_run.update(page_tids)

            if current_page >= refresh_pages:
                known_streak = 0 if new_on_page else known_streak + 1
                if known_streak >= known_page_streak:
                    stopped = True
                    print(f"fid {fid} 已连续 {known_streak} 页没有新帖子，停止增量抓取")
                    break
        if stopped:
            break

    if not stopped and pages_fetched >= max_pages:
        print(f"fid {fid} 达到安全上限 {max_pages} 页，请检查是否存在异常分页")

    new_count = len(seen_this_run - existing_tids)
    updated_count = len(seen_this_run & existing_tids)
    result = {
        "fid": fid,
        "pages": pages_fetched,
        "new_count": new_count,
        "updated_count": updated_count,
        "processed_count": new_count + updated_count,
        "mode": "incremental",
    }
    print(
        f"fid {fid} 增量抓取完成：{pages_fetched} 页，"
        f"新增 {new_count} 条，更新 {updated_count} 条"
    )
    return result


def validate_thread_html(html, tid):
    # Discuz thread/comment pages have post IDs. A login/challenge page must never become a checkpoint.
    if not re.search(r'(?:id=["\'](?:post_|postmessage_)\d+|id=["\']postlist["\'])', html):
        raise ValueError(f'tid={tid} 未识别到帖子内容，请检查登录状态或页面结构')


def fetch_thread_detail(
    row: sqlite3.Row,
    *,
    thread_index: int,
    total_threads: int,
    base_url: str,
    cookie: str,
    settings: dict,
) -> dict:
    """抓取单个帖子的详情指标，不保存评论内容。"""
    tid = row["tid"]
    detail_url = urljoin(
        base_url.rstrip("/") + "/",
        f"forum.php?mod=viewthread&tid={tid}",
    )
    fetched_at = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"正在抓取详情 {thread_index}/{total_threads}：tid={tid}")
    participant_count = 0
    money = 0
    rating = ""
    try:
        if thread_index > 1:
            wait_seconds = settings["delay_seconds"] + random.uniform(
                0, settings["jitter_seconds"]
            )
            print(f"等待 {wait_seconds:.1f} 秒后继续")
            time.sleep(wait_seconds)
        html_text = fetch_page(
            detail_url,
            cookie,
            retries=settings["retries"],
            retry_backoff_seconds=settings["retry_backoff_seconds"],
        )
        validate_thread_html(html_text, tid)
        detail = parse_detail_page(
            html_text,
            detail_url,
            tid=tid,
            comment_page=1,
            fetched_at=fetched_at,
        )
        participant_count = detail["participant_count"]
        money = detail["money"]
        if str(row["fid"]) in settings.get("purchase_count_money_fids", ()) and detail.get("purchase_count"):
            money = detail["purchase_count"]
        rating = detail["rating"]
        return {
            "tid": tid,
            "status": "fetched",
            "fetched_at": fetched_at,
            "participant_count": participant_count,
            "money": money,
            "reward_money": detail["money"],
            "purchase_count": detail.get("purchase_count", 0),
            "rating": rating,
            "error": "",
        }
    except Exception as exc:
        return {
            "tid": tid,
            "status": "failed",
            "fetched_at": fetched_at,
            "participant_count": 0,
            "money": 0,
            "rating": "",
            "error": str(exc),
        }


def fetch_thread_comments(
    row: sqlite3.Row,
    *,
    thread_index: int,
    total_threads: int,
    base_url: str,
    cookie: str,
    comment_pages: int | str,
    comment_page_workers: int,
    database_path: str,
    settings: dict,
    progress_callback=None,
) -> dict:
    """抓取单个帖子的评论分页，并把每页评论及时落库。"""
    tid = row["tid"]
    detail_url = urljoin(
        base_url.rstrip("/") + "/",
        f"forum.php?mod=viewthread&tid={tid}",
    )
    fetched_at = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"正在抓取评论 {thread_index}/{total_threads}：tid={tid}")
    completed_pages = 0
    saved_comments = 0

    def report_progress(status: str, total_pages=None, error: str = "") -> None:
        if progress_callback is None:
            return
        progress_callback(
            {
                "tid": tid,
                "status": status,
                "completed_pages": completed_pages,
                "total_pages": total_pages,
                "saved_comments": saved_comments,
                "error": error,
            }
        )

    try:
        report_progress("running")
        resolved_comment_pages = None if str(comment_pages).lower() == "all" else int(comment_pages)
        if thread_index > 1:
            wait_seconds = settings["delay_seconds"] + random.uniform(
                0, settings["jitter_seconds"]
            )
            print(f"等待 {wait_seconds:.1f} 秒后继续")
            time.sleep(wait_seconds)

        def fetch_comment_page(page: int) -> dict:
            """抓取并解析单个评论分页。"""
            page_url = build_detail_page_url(detail_url, page)
            html_text = fetch_page(
                page_url,
                cookie,
                retries=settings["retries"],
                retry_backoff_seconds=settings["retry_backoff_seconds"],
            )
            validate_thread_html(html_text, tid)
            detail = parse_detail_page(
                html_text,
                detail_url,
                tid=tid,
                comment_page=page,
                fetched_at=fetched_at,
            )
            return {"page": page, "html_text": html_text, "comments": detail["comments"]}

        first_page = fetch_comment_page(1)
        save_comments(database_path, first_page["comments"])
        completed_pages = 1
        saved_comments += len(first_page["comments"])
        if resolved_comment_pages is None:
            # 第一页带有 Discuz 分页链接，先用它判断后续需要提交多少评论页任务。
            resolved_comment_pages = detect_detail_comment_page_count(first_page["html_text"], tid)
        report_progress("running", resolved_comment_pages)

        pages = list(range(2, resolved_comment_pages + 1))
        if pages:
            worker_count = min(max(1, comment_page_workers), len(pages))
            with ThreadPoolExecutor(max_workers=worker_count) as executor:
                pending = set()
                next_page_index = 0

                def submit_next_page() -> None:
                    """向线程池补充下一个待抓评论页任务。"""
                    nonlocal next_page_index
                    if next_page_index >= len(pages):
                        return
                    page = pages[next_page_index]
                    next_page_index += 1
                    pending.add(executor.submit(fetch_comment_page, page))

                for _ in range(worker_count):
                    submit_next_page()

                while pending:
                    future = next(as_completed(pending))
                    pending.remove(future)
                    page_result = future.result()
                    # 每完成一页就立即入库，后续页面失败时也不会丢掉已抓评论。
                    save_comments(database_path, page_result["comments"])
                    completed_pages += 1
                    saved_comments += len(page_result["comments"])
                    report_progress("running", resolved_comment_pages)
                    print(f"评论页已入库：tid={tid}，第 {page_result['page']} 页，{len(page_result['comments'])} 条")
                    if next_page_index < len(pages):
                        if settings["delay_seconds"] or settings["jitter_seconds"]:
                            wait_seconds = settings["delay_seconds"] + random.uniform(
                                0, settings["jitter_seconds"]
                            )
                            print(f"等待 {wait_seconds:.1f} 秒后继续")
                            time.sleep(wait_seconds)
                        submit_next_page()
        report_progress("fetched", resolved_comment_pages)
        return {
            "tid": tid,
            "status": "fetched",
            "fetched_at": fetched_at,
            "error": "",
        }
    except Exception as exc:
        report_progress("failed", error=str(exc))
        return {
            "tid": tid,
            "status": "failed",
            "fetched_at": fetched_at,
            "error": str(exc),
        }


def _fetch_and_update_detail_rows(
    conn: sqlite3.Connection,
    rows: list[sqlite3.Row],
    *,
    base_url: str,
    cookie: str,
    settings: dict,
    detail_workers: int,
    mark_metrics_repaired: bool = False,
) -> dict:
    """Fetch detail metrics for selected rows and update the database."""
    success_count = 0
    failure_count = 0

    def fetch_one(index_and_row):
        thread_index, row = index_and_row
        return fetch_thread_detail(
            row,
            thread_index=thread_index,
            total_threads=len(rows),
            base_url=base_url,
            cookie=cookie,
            settings=settings,
        )

    worker_count = min(detail_workers, len(rows)) if rows else 1
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [
            executor.submit(fetch_one, index_and_row)
            for index_and_row in enumerate(rows, start=1)
        ]
        for future in as_completed(futures):
            detail_result = future.result()
            tid = detail_result["tid"]
            if detail_result["status"] == "fetched":
                update_thread_detail(
                    conn,
                    tid,
                    status="fetched",
                    fetched_at=detail_result["fetched_at"],
                    participant_count=detail_result["participant_count"],
                    money=detail_result["money"],
                    reward_money=detail_result["reward_money"],
                    purchase_count=detail_result["purchase_count"],
                    rating=detail_result["rating"],
                    metrics_repaired_at=detail_result["fetched_at"] if mark_metrics_repaired else None,
                )
                success_count += 1
                print(
                    f"详情已入库：tid={tid}，参与={detail_result['participant_count']}，"
                    f"金钱={detail_result['money']}，评分={detail_result['rating']}"
                )
            else:
                failure_count += 1
                update_thread_detail(
                    conn,
                    tid,
                    status="failed",
                    fetched_at=detail_result["fetched_at"],
                    error=detail_result["error"],
                )
                print(f"详情抓取失败：tid={tid}，{detail_result['error']}")
    return {"success_count": success_count, "failure_count": failure_count}


def crawl_details_to_db(config: dict) -> dict:
    """Fetch detail metrics for missing or manually specified threads."""
    site = site_settings(config)
    details = detail_settings(config)
    base_url = site.get("base_url", "")
    settings = load_runtime_settings(config)
    cookie = load_cookie(config.get("_cookie"), config.get("_cookie_file") or site.get("cookie_file"))
    detail_limit = int(details.get("limit", 20))
    detail_workers = max(1, int(details.get("workers", 1)))
    detail_tids = parse_tid_list(config.get("_detail_tids"))
    conn = init_db(resolve_database_path(config))
    try:
        if detail_tids:
            placeholders = ", ".join("?" for _ in detail_tids)
            rows = conn.execute(
                f"""
                SELECT tid, fid
                FROM threads
                WHERE tid IN ({placeholders})
                ORDER BY posted_at DESC, tid DESC
                """,
                detail_tids,
            ).fetchall()
        else:
            job_id = config.get('_crawl_job_id')
            rows = claim_detail_rows(conn, detail_limit, job_id) if job_id else claim_detail_rows(conn, detail_limit)
        return _fetch_and_update_detail_rows(
            conn,
            rows,
            base_url=base_url,
            cookie=cookie,
            settings=settings,
            detail_workers=detail_workers,
        )
    finally:
        conn.close()


def _detail_runtime(config: dict) -> tuple[str, dict, str, int, int, str]:
    """Load common runtime values for detail repair commands."""
    site = site_settings(config)
    details = detail_settings(config)
    base_url = site.get("base_url", "")
    settings = load_runtime_settings(config)
    cookie = load_cookie(config.get("_cookie"), config.get("_cookie_file") or site.get("cookie_file"))
    detail_limit = int(details.get("limit", 20))
    detail_workers = max(1, int(details.get("workers", 1)))
    database_path = resolve_database_path(config)
    return base_url, settings, cookie, detail_limit, detail_workers, database_path


def repair_low_money_to_db(config: dict) -> dict:
    """Refetch non-sale detail metrics where money is suspiciously low."""
    base_url, settings, cookie, detail_limit, detail_workers, database_path = _detail_runtime(config)
    fids = settings["purchase_count_money_fids"]
    placeholders = ", ".join("?" for _ in fids)
    conn = init_db(database_path)
    try:
        rows = conn.execute(
            f"""
            SELECT tid, fid, money, rating, posted_at, metrics_repaired_at
            FROM threads
            WHERE detail_status = 'fetched'
              AND metrics_repaired_at = ''
              AND fid NOT IN ({placeholders})
              AND money < 10
            ORDER BY
              CASE WHEN rating = '' THEN 1 ELSE 0 END,
              CAST(rating AS INTEGER) DESC,
              posted_at DESC,
              tid DESC
            LIMIT ?
            """,
            (*fids, detail_limit),
        ).fetchall()
        return _fetch_and_update_detail_rows(
            conn,
            rows,
            base_url=base_url,
            cookie=cookie,
            settings=settings,
            detail_workers=detail_workers,
            mark_metrics_repaired=True,
        )
    finally:
        conn.close()


def repair_purchase_money_to_db(config: dict) -> dict:
    """Refetch sale-board details and store purchase count in money."""
    base_url, settings, cookie, detail_limit, detail_workers, database_path = _detail_runtime(config)
    fids = settings["purchase_count_money_fids"]
    placeholders = ", ".join("?" for _ in fids)
    conn = init_db(database_path)
    try:
        rows = conn.execute(
            f"""
            SELECT tid, fid, money, rating, posted_at, metrics_repaired_at
            FROM threads
            WHERE detail_status = 'fetched'
              AND metrics_repaired_at = ''
              AND fid IN ({placeholders})
            ORDER BY
              reply_count DESC,
              view_count DESC,
              posted_at DESC,
              tid DESC
            LIMIT ?
            """,
            (*fids, detail_limit),
        ).fetchall()
        return _fetch_and_update_detail_rows(
            conn,
            rows,
            base_url=base_url,
            cookie=cookie,
            settings=settings,
            detail_workers=detail_workers,
            mark_metrics_repaired=True,
        )
    finally:
        conn.close()


def repair_details_to_db(config: dict) -> dict:
    """Backward-compatible alias for low-money detail repair."""
    return repair_low_money_to_db(config)


def reset_processing_details(config: dict) -> dict:
    """Reset interrupted detail rows so crawl-details can claim them again."""
    conn = init_db(resolve_database_path(config))
    try:
        cursor = conn.execute(
            """
            UPDATE threads
            SET detail_status = 'pending',
                detail_error = ''
            WHERE detail_status = 'processing'
            """
        )
        conn.commit()
        return {"reset_count": cursor.rowcount}
    finally:
        conn.close()

def crawl_comments_to_db(config: dict) -> dict:
    """抓取已开启评论开关的帖子评论。"""
    site = site_settings(config)
    details = detail_settings(config)
    comments = comment_settings(config)
    base_url = site.get("base_url", "")
    settings = load_runtime_settings(config)
    cookie = load_cookie(config.get("_cookie"), config.get("_cookie_file") or site.get("cookie_file"))
    database_path = resolve_database_path(config)
    detail_limit = int(details.get("limit", 20))
    detail_workers = max(1, int(details.get("workers", 1)))
    comment_pages = comments.get("pages", "all")
    comment_page_workers = max(1, int(comments.get("page_workers", 1)))
    refresh_comments = parse_bool(comments.get("refresh_existing"), default=False)
    conn = init_db(database_path)
    success_count = 0
    failure_count = 0
    try:
        if refresh_comments:
            rows = conn.execute(
                """
                SELECT tid
                FROM threads
                WHERE fetch_comments = 1
                ORDER BY posted_at DESC, tid DESC
                LIMIT ?
                """,
                (detail_limit,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT t.tid
                FROM threads t
                WHERE t.fetch_comments = 1
                  AND NOT EXISTS (
                    SELECT 1 FROM comments c WHERE c.tid = t.tid
                  )
                ORDER BY t.posted_at DESC, t.tid DESC
                LIMIT ?
                """,
                (detail_limit,),
            ).fetchall()

        def fetch_one(index_and_row):
            """提交给线程池的评论抓取任务。"""
            thread_index, row = index_and_row
            return fetch_thread_comments(
                row,
                thread_index=thread_index,
                total_threads=len(rows),
                base_url=base_url,
                cookie=cookie,
                comment_pages=comment_pages,
                comment_page_workers=comment_page_workers,
                database_path=database_path,
                settings=settings,
            )

        worker_count = min(detail_workers, len(rows)) if rows else 1
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            comment_results = list(executor.map(fetch_one, enumerate(rows, start=1)))

        for comment_result in comment_results:
            tid = comment_result["tid"]
            if comment_result["status"] == "fetched":
                success_count += 1
            else:
                failure_count += 1
                print(f"评论抓取失败：tid={tid}，{comment_result['error']}")
    finally:
        conn.close()
    return {"success_count": success_count, "failure_count": failure_count}


def _truncate(value: str, limit: int) -> str:
    """把长文本规整后截断到指定长度。"""
    normalized = _normalize_text(value)
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1] + "..."


def main(argv: list[str] | None = None) -> int:
    """命令行入口，分发列表、详情和评论抓取命令。"""
    parser = argparse.ArgumentParser(
        description="同步论坛数据。省略命令时自动增量同步所有板块的帖子列表。",
        epilog="常用命令：details（补详情）、comments（抓已开启的评论）。",
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="sync",
        metavar="command",
        help="可选：details 或 comments；省略时同步帖子列表。",
    )
    parser.add_argument("--config", default=DEFAULT_CONFIG, help="配置文件路径，默认 config.json。")
    parser.add_argument("--url", help="论坛列表 URL。")
    parser.add_argument("--fid", help="只抓取指定板块；不传时按配置中的 fids 依次抓取。")
    parser.add_argument("--cookie", help="从浏览器复制出的 Cookie 字符串。")
    parser.add_argument("--cookie-file", help="包含 Cookie 字符串的文本文件。")
    parser.add_argument("--pages", type=int, help="要抓取的页数，默认 5。")
    parser.add_argument("--start-page", type=int, help="从第几页开始抓取，默认 1。")
    parser.add_argument("--tid", action="append", help="details 时指定帖子 tid，可重复传入，也可用逗号分隔。")
    args = parser.parse_args(argv)

    command_aliases = {
        "crawl-list": "sync",
        "crawl-details": "details",
        "crawl-comments": "comments",
    }
    hidden_maintenance_commands = {
        "repair-details",
        "repair-low-money",
        "repair-purchase-money",
        "reset-processing-details",
        "refresh-recommendations",
    }
    command = command_aliases.get(args.command, args.command)
    if command not in {"sync", "details", "comments", *hidden_maintenance_commands}:
        parser.error(f"未知命令：{args.command}；可用命令为 details、comments，或省略命令。")

    try:
        config = load_config(args.config)
        if args.cookie:
            config = {**config, "_cookie": args.cookie}
        if args.cookie_file:
            config = {**config, "_cookie_file": args.cookie_file}
        if command == "sync":
            if args.url and args.fid:
                raise ValueError("--url 和 --fid 不能同时使用。")
            if args.url:
                config = {**config, "_url": args.url}
            elif args.fid:
                config = {
                    **config,
                    "list_sync": {**list_sync_settings(config), "fids": [args.fid]},
                }
            if args.pages is not None:
                config = {**config, "_manual_list": {"pages": args.pages}}
            if args.start_page is not None:
                if args.pages is None:
                    raise ValueError("使用 --start-page 时必须同时指定 --pages。")
                config["_manual_list"]["start_page"] = args.start_page
            result = crawl_list_to_db(config)
            print(
                f"列表同步完成：处理 {result['success_count']} 条，"
                f"失败板块 {result['failure_count']} 个"
            )
            return 1 if result["failure_count"] else 0
        if command == "details":
            manual_tids = parse_tid_list(args.tid)
            if manual_tids:
                config = {**config, "_detail_tids": manual_tids}
            result = crawl_details_to_db(config)
            print(f"详情入库完成：成功 {result['success_count']} 条，失败 {result['failure_count']} 条")
            return 0
        if command == "repair-details":
            result = repair_details_to_db(config)
            print(f"低金钱详情修复完成：成功 {result['success_count']} 条，失败 {result['failure_count']} 条")
            return 0
        if command == "repair-low-money":
            result = repair_low_money_to_db(config)
            print(f"低金钱详情修复完成：成功 {result['success_count']} 条，失败 {result['failure_count']} 条")
            return 0
        if command == "repair-purchase-money":
            result = repair_purchase_money_to_db(config)
            print(f"购买人数金钱修复完成：成功 {result['success_count']} 条，失败 {result['failure_count']} 条")
            return 0
        if command == "reset-processing-details":
            result = reset_processing_details(config)
            print(f"已重置 processing 详情任务：{result['reset_count']} 条")
            return 0
        if command == "comments":
            result = crawl_comments_to_db(config)
            print(f"评论入库完成：成功 {result['success_count']} 条，失败 {result['failure_count']} 条")
            return 0
        if command == "refresh-recommendations":
            database_path = resolve_database_path(config)
            count = refresh_recommendation_candidates(database_path)
            print(f"随机推荐排名缓存已刷新：{count} 条，数据库：{database_path}")
            return 0
    except (OSError, RuntimeError, ValueError) as exc:
        parser.exit(1, f"错误：{exc}\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
