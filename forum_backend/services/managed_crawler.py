"""Managed execution: reuse fetchers/parsers, checkpoint committed pages and targets."""
import datetime as dt
import json
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin

from forum_backend import crawler
from forum_backend.config import (configured_fids, site_cookie, load_runtime_settings,
                                  source_url_from_config, build_detail_page_url, extract_query_value)
from forum_backend.db import upsert_thread, upsert_comment, update_thread_detail, rebuild_recommendation_candidates
from .crawl_store import database, select_targets, unit, save_unit
from .rankings import PERIOD_LABELS, RANK_LABELS, RANK_SCOPES, parse_ranking, rank_url


def now():
    return dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def pause(settings):
    time.sleep(settings['delay_seconds'] + random.uniform(0, settings['jitter_seconds']))


class ManagedCrawler:
    def __init__(self, config, job_id, path):
        self.config, self.job_id, self.path = config, job_id, path
        self.settings = load_runtime_settings(config)
        self.cookie = site_cookie(config)

    def targets(self, kind):
        with database(self.path) as conn:
            planned = conn.execute('SELECT planned FROM crawl_jobs WHERE id=?', (self.job_id,)).fetchone()[0]
            if not planned:
                conn.execute('BEGIN IMMEDIATE')
                for row in select_targets(conn, kind, self.config):
                    unit(conn, self.job_id, kind, row['tid'])
                conn.execute('UPDATE crawl_jobs SET planned=1 WHERE id=?', (self.job_id,))
            rows = conn.execute('''SELECT t.tid,t.fid FROM crawl_units u JOIN threads t ON u.target=t.tid
                WHERE u.job_id=? AND u.kind=? AND u.status!='succeeded' ORDER BY t.posted_at DESC,t.tid DESC''', (self.job_id, kind)).fetchall()
            if kind == 'details':
                for row in rows:
                    conn.execute("UPDATE threads SET detail_status='processing' WHERE tid=?", (row['tid'],))
                    conn.execute('INSERT OR IGNORE INTO crawl_detail_claims VALUES (?,?)', (self.job_id, row['tid']))
        return rows

    def details(self):
        rows = self.targets('details')
        def fetch(pair):
            index, row = pair
            return crawler.fetch_thread_detail(row, thread_index=index + 1, total_threads=len(rows),
                base_url=self.config['site']['base_url'], cookie=self.cookie, settings=self.settings)
        with ThreadPoolExecutor(max_workers=self.config['details'].get('workers', 3)) as pool:
            futures = [pool.submit(fetch, pair) for pair in enumerate(rows)]
            for future in as_completed(futures):
                result = future.result()
                tid = result['tid']
                with database(self.path) as conn:
                    if result['status'] == 'fetched':
                        update_thread_detail(conn, tid, status='fetched', fetched_at=result['fetched_at'],
                            participant_count=result['participant_count'], money=result['money'], reward_money=result['reward_money'],
                            purchase_count=result['purchase_count'], rating=result['rating'])
                        save_unit(conn, self.job_id, 'details', tid)
                    else:
                        conn.execute("UPDATE threads SET detail_status='failed',detail_error=? WHERE tid=?", (result['error'], tid))
                        save_unit(conn, self.job_id, 'details', tid, status='failed', error=result['error'])
                print(f"详情 {'完成' if result['status'] == 'fetched' else '失败'}：{tid}", flush=True)

    def sync(self):
        config = self.config
        fids = configured_fids(config)
        manual = config.get('_manual_list')
        start = int(manual.get('start_page', 1)) if manual else 1
        count = int(manual['pages']) if manual else config['list_sync'].get('max_pages_per_fid', 200)
        with database(self.path) as conn:
            if manual:
                for fid in fids:
                    for page in range(start, start + count):
                        unit(conn, self.job_id, 'sync', fid, page)
            conn.execute('UPDATE crawl_jobs SET planned=1 WHERE id=?', (self.job_id,))
        for fid in fids:
            known = 0
            source = source_url_from_config({**config, '_fid': fid})
            # Bounded batches retain list concurrency without buffering an entire forum.
            workers = config['list_sync'].get('workers', 3)
            done = False
            for offset in range(start, start + count, workers):
                pages = range(offset, min(offset + workers, start + count))
                with database(self.path) as conn:
                    saved = {page: dict(unit(conn, self.job_id, 'sync', fid, page)) for page in pages}
                def fetch(page):
                    pause(self.settings)
                    return crawler.fetch_list_page((page, crawler.build_page_url(source, page)), start_page=1,
                        total_pages=count, cookie=self.cookie, settings={**self.settings, 'delay_seconds': 0, 'jitter_seconds': 0})
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    futures = {page: pool.submit(fetch, page) for page in pages if saved[page]['status'] != 'succeeded'}
                    for page in pages:
                        try:
                            if saved[page]['status'] == 'succeeded':
                                result = json.loads(saved[page]['result'])
                            else:
                                _, topics = futures[page].result()
                                if not topics and page == 1:
                                    raise ValueError('首页未识别到帖子，请检查登录状态或页面结构')
                                with database(self.path) as conn:
                                    new = updated = 0
                                    for topic in topics:
                                        tid = extract_query_value(topic.url, 'tid')
                                        exists = conn.execute('SELECT 1 FROM threads WHERE tid=?', (tid,)).fetchone()
                                        conn.execute('INSERT OR IGNORE INTO crawl_touched_threads VALUES (?,?,?)', (self.job_id, tid, int(not bool(exists))))
                                        new += not bool(exists)
                                        updated += bool(exists)
                                        upsert_thread(conn, topic, page, now(), fid=fid, commit=False)
                                    result = {'new': new, 'updated': updated, 'empty': not topics}
                                    save_unit(conn, self.job_id, 'sync', fid, page, result=result)
                                print(f'板块 {fid} 第 {page} 页完成：新增 {new}，更新 {updated}', flush=True)
                            if not manual:
                                known = known + 1 if page >= config['list_sync'].get('refresh_pages', 4) and not result['new'] else 0
                                if result['empty'] or known >= config['list_sync'].get('known_page_streak', 2):
                                    done = True
                                    break
                        except Exception as exc:
                            with database(self.path) as conn:
                                save_unit(conn, self.job_id, 'sync', fid, page, status='failed', error=str(exc))
                            print(f'板块 {fid} 第 {page} 页失败：{exc}', flush=True)
                            if not manual:
                                done = True  # Do not skip a failed boundary page; resume retries it.
                                break
                if done:
                    # Speculative pages were never committed and must not inflate the progress total.
                    with database(self.path) as conn:
                        conn.execute("DELETE FROM crawl_units WHERE job_id=? AND kind='sync' AND target=? AND page>? AND status='pending'", (self.job_id, fid, page))
                    break
        with database(self.path) as conn:
            rebuild_recommendation_candidates(conn)

    def comments(self):
        rows = self.targets('comments')
        with ThreadPoolExecutor(max_workers=self.config['details'].get('workers', 3)) as pool:
            for _ in pool.map(self.comment_thread, rows):
                pass

    def comment_thread(self, row):
        tid = row['tid']
        url = urljoin(self.config['site']['base_url'].rstrip('/') + '/', f'forum.php?mod=viewthread&tid={tid}')
        refresh = self.config['comments'].get('refresh_existing', False)
        cap = self.config['comments'].get('pages', 'all')
        def fetch(page):
            pause(self.settings)
            html = crawler.fetch_page(build_detail_page_url(url, page), self.cookie, retries=self.settings['retries'],
                                      retry_backoff_seconds=self.settings['retry_backoff_seconds'])
            crawler.validate_thread_html(html, tid)
            detail = crawler.parse_detail_page(html, url, tid=tid, comment_page=page, fetched_at=now())
            return detail['comments'], crawler.detect_detail_comment_page_count(html, tid)
        def saved(page):
            with database(self.path) as conn:
                item = unit(conn, self.job_id, 'comment_page', tid, page)
                if item['status'] == 'succeeded':
                    return json.loads(item['result'])
                old = conn.execute('SELECT * FROM crawl_comment_pages WHERE tid=? AND page=?', (tid, page)).fetchone()
                if old and not refresh:
                    result = {'total_pages': old['total_pages'], 'saved_comments': 0, 'reused': True}
                    save_unit(conn, self.job_id, 'comment_page', tid, page, result=result)
                    return result
            return None
        def commit_page(page, comments, total):
            with database(self.path) as conn:
                for comment in comments:
                    upsert_comment(conn, comment, commit=False)
                conn.execute('INSERT OR REPLACE INTO crawl_comment_pages VALUES (?,?,?,?)', (tid, page, total, len(comments)))
                result = {'total_pages': total, 'saved_comments': len(comments)}
                save_unit(conn, self.job_id, 'comment_page', tid, page, result=result)
            print(f'评论 {tid} 第 {page} 页完成：{len(comments)} 条', flush=True)
            return result
        try:
            first = saved(1)
            if not first:
                comments, total = fetch(1)
                first = commit_page(1, comments, total)
            total = first['total_pages']
            goal = total if str(cap) == 'all' else min(total, int(cap))
            with database(self.path) as conn:
                save_unit(conn, self.job_id, 'comments', tid, status='running', result={'total_pages': goal})
                for page in range(2, goal + 1):
                    unit(conn, self.job_id, 'comment_page', tid, page)
            pages = [page for page in range(2, goal + 1) if not saved(page)]
            with ThreadPoolExecutor(max_workers=self.config['comments'].get('page_workers', 3)) as pool:
                futures = {pool.submit(fetch, page): page for page in pages}
                for future in as_completed(futures):
                    page = futures[future]
                    try:
                        comments, _ = future.result()
                        commit_page(page, comments, total)
                    except Exception as exc:
                        with database(self.path) as conn:
                            save_unit(conn, self.job_id, 'comment_page', tid, page, status='failed', error=str(exc))
                        print(f'评论 {tid} 第 {page} 页失败：{exc}', flush=True)
            with database(self.path) as conn:
                missing = conn.execute("SELECT COUNT(*) FROM crawl_units WHERE job_id=? AND kind='comment_page' AND target=? AND status!='succeeded'", (self.job_id, tid)).fetchone()[0]
                save_unit(conn, self.job_id, 'comments', tid, status='failed' if missing else 'succeeded', result={'total_pages': goal})
        except Exception as exc:
            with database(self.path) as conn:
                save_unit(conn, self.job_id, 'comment_page', tid, 1, status='failed', error=str(exc))
                save_unit(conn, self.job_id, 'comments', tid, status='failed', error=str(exc))
            print(f'评论 {tid} 抓取失败：{exc}', flush=True)

    def rankings(self):
        with database(self.path) as conn:
            pending = []
            for metric, period in RANK_SCOPES:
                target = f'{metric}/{period}'
                if unit(conn, self.job_id, 'rankings', target)['status'] != 'succeeded':
                    pending.append((metric, period, target))
            conn.execute('UPDATE crawl_jobs SET planned=1 WHERE id=?', (self.job_id,))

        base_url = self.config['site']['base_url']
        for index, (metric, period, target) in enumerate(pending):
            if index:
                pause(self.settings)
            label = f'{PERIOD_LABELS[period]}{RANK_LABELS[metric]}榜'
            try:
                html = crawler.fetch_page(
                    rank_url(base_url, metric, period), self.cookie,
                    retries=self.settings['retries'],
                    retry_backoff_seconds=self.settings['retry_backoff_seconds'],
                )
                entries = parse_ranking(html, metric, period)
            except (RuntimeError, ValueError) as exc:
                with database(self.path) as conn:
                    save_unit(conn, self.job_id, 'rankings', target, status='failed', error=str(exc))
                print(f'{label}采集失败：{exc}')
                continue
            captured_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
            with database(self.path) as conn:
                conn.execute('''
                    INSERT INTO ranking_snapshots(metric, period, captured_at, entries) VALUES (?,?,?,?)
                    ON CONFLICT(metric, period, date(captured_at, '+8 hours')) DO UPDATE SET
                        captured_at=excluded.captured_at,
                        entries=excluded.entries
                    WHERE excluded.captured_at >= ranking_snapshots.captured_at
                ''', (metric, period, captured_at, json.dumps(entries, ensure_ascii=False)))
                save_unit(conn, self.job_id, 'rankings', target)
            print(f'{label}已保存，共 {len(entries)} 条')

    def run(self, kind):
        getattr(self, kind)()
        with database(self.path) as conn:
            rows = conn.execute("SELECT status,COUNT(*) AS n FROM crawl_units WHERE job_id=? AND kind=? GROUP BY status", (self.job_id, kind)).fetchall()
        counts = {row['status']: row['n'] for row in rows}
        return {'success_count': counts.get('succeeded', 0), 'failure_count': counts.get('failed', 0)}
