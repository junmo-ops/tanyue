"""Shared durable checkpoints and safe admin settings for managed crawls."""
import copy
import json
import math
from contextlib import contextmanager
from forum_backend.storage.connection import connect_db


@contextmanager
def database(path):
    conn = connect_db(path)
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def ensure_schema(path):
    with database(path) as conn:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS crawl_units (
                job_id TEXT NOT NULL, kind TEXT NOT NULL, target TEXT NOT NULL, page INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'pending', result TEXT NOT NULL DEFAULT '{}', error TEXT NOT NULL DEFAULT '',
                PRIMARY KEY(job_id,kind,target,page)
            );
            CREATE TABLE IF NOT EXISTS crawl_comment_pages (
                tid TEXT NOT NULL, page INTEGER NOT NULL, total_pages INTEGER NOT NULL, saved_count INTEGER NOT NULL,
                PRIMARY KEY(tid,page)
            );
            CREATE TABLE IF NOT EXISTS crawl_touched_threads (
                job_id TEXT NOT NULL, tid TEXT NOT NULL, was_new INTEGER NOT NULL,
                PRIMARY KEY(job_id,tid)
            );
            CREATE TABLE IF NOT EXISTS crawl_admin (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS crawl_presets (id TEXT PRIMARY KEY, name TEXT NOT NULL, steps TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS crawl_schedules (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, preset_id TEXT NOT NULL, mode TEXT NOT NULL,
                every_minutes INTEGER NOT NULL, daily_time TEXT NOT NULL, busy_policy TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 0, next_run REAL NOT NULL, last_run REAL,
                last_result TEXT NOT NULL DEFAULT ''
            );
        ''')
        columns = {row['name'] for row in conn.execute('PRAGMA table_info(crawl_jobs)')}
        for name, declaration in [('settings', "TEXT NOT NULL DEFAULT '{}'"), ('started_at', 'TEXT'),
                                  ('parent_id', "TEXT NOT NULL DEFAULT ''"), ('planned', 'INTEGER NOT NULL DEFAULT 0'),
                                  ('summary', "TEXT NOT NULL DEFAULT ''")]:
            if name not in columns:
                conn.execute(f'ALTER TABLE crawl_jobs ADD COLUMN {name} {declaration}')
        if not conn.execute('SELECT 1 FROM crawl_presets').fetchone():
            conn.execute('INSERT INTO crawl_presets VALUES (?,?,?)',
                         ('daily', '日常更新', json.dumps([{'kind': 'sync'}, {'kind': 'details'}, {'kind': 'comments'}])))


# Only these non-secret fields are editable. Site URLs, credentials and DB paths stay server-owned.
FIELDS = {
    'list_sync': {'workers': (1, 8, 3), 'refresh_pages': (1, 100, 4), 'known_page_streak': (1, 20, 2), 'max_pages_per_fid': (1, 2000, 200)},
    'details': {'workers': (1, 8, 3), 'limit': (1, 100000, 30000)},
    'comments': {'page_workers': (1, 8, 3)},
    'network': {'delay_seconds': (0, 60, 0.5), 'jitter_seconds': (0, 60, 0.5), 'retries': (0, 5, 2), 'retry_backoff_seconds': (0, 120, 3.0)},
}


def safe_settings(config):
    result = {section: {key: config.get(section, {}).get(key, bounds[2]) for key, bounds in fields.items()}
              for section, fields in FIELDS.items()}
    result['comments'].update(pages=config.get('comments', {}).get('pages', 'all'),
                              refresh_existing=config.get('comments', {}).get('refresh_existing', False))
    return result


def validate_settings(values):
    if not isinstance(values, dict) or set(values) != set(FIELDS):
        raise ValueError('采集配置分组不完整')
    for section, fields in FIELDS.items():
        data = values.get(section)
        keys = set(fields) | ({'pages', 'refresh_existing'} if section == 'comments' else set())
        if not isinstance(data, dict) or set(data) != keys:
            raise ValueError(f'{section} 配置字段不正确')
        for key, (minimum, maximum, default) in fields.items():
            value = data[key]
            integer = key not in ('delay_seconds', 'jitter_seconds', 'retry_backoff_seconds')
            if type(value) not in (int, float) or not math.isfinite(value) or not minimum <= value <= maximum or (integer and type(value) is not int):
                raise ValueError(f'{section}.{key} 需在 {minimum}–{maximum} 范围内' + ('，且为整数' if integer else ''))
    pages = values['comments']['pages']
    if pages != 'all' and (type(pages) is not int or not 1 <= pages <= 2000):
        raise ValueError('评论页数需为 all 或 1–2000 的整数')
    if type(values['comments']['refresh_existing']) is not bool:
        raise ValueError('评论刷新开关需为布尔值')
    if values['list_sync']['max_pages_per_fid'] < values['list_sync']['refresh_pages']:
        raise ValueError('单板块页数上限不能小于刷新页数')
    return copy.deepcopy(values)


def select_targets(conn, kind, config):
    limit = int(config.get('details', {}).get('limit', 20))
    if kind == 'details':
        tids = config.get('_detail_tids')
        if tids:
            return conn.execute(f"SELECT tid,fid FROM threads WHERE tid IN ({','.join('?' for _ in tids)}) ORDER BY posted_at DESC,tid DESC", tids).fetchall()
        return conn.execute("SELECT tid,fid FROM threads WHERE detail_status IN ('pending','failed') ORDER BY posted_at DESC,tid DESC LIMIT ?", (limit,)).fetchall()
    comments = config.get('comments', {})
    if comments.get('refresh_existing'):
        return conn.execute('SELECT tid,fid FROM threads WHERE fetch_comments=1 ORDER BY posted_at DESC,tid DESC LIMIT ?', (limit,)).fetchall()
    cap = 2147483647 if str(comments.get('pages', 'all')) == 'all' else int(comments['pages'])
    return conn.execute('''SELECT tid,fid FROM threads t WHERE fetch_comments=1 AND (
        NOT EXISTS (SELECT 1 FROM crawl_comment_pages p WHERE p.tid=t.tid AND p.page=1) OR
        (SELECT COUNT(*) FROM crawl_comment_pages p WHERE p.tid=t.tid AND p.page <= MIN(?,
            (SELECT total_pages FROM crawl_comment_pages WHERE tid=t.tid AND page=1))) <
        MIN(?,(SELECT total_pages FROM crawl_comment_pages WHERE tid=t.tid AND page=1))
    ) ORDER BY posted_at DESC,tid DESC LIMIT ?''', (cap, cap, limit)).fetchall()


def unit(conn, job_id, kind, target, page=0):
    conn.execute('INSERT OR IGNORE INTO crawl_units(job_id,kind,target,page) VALUES (?,?,?,?)', (job_id, kind, str(target), page))
    return conn.execute('SELECT * FROM crawl_units WHERE job_id=? AND kind=? AND target=? AND page=?', (job_id, kind, str(target), page)).fetchone()


def save_unit(conn, job_id, kind, target, page=0, status='succeeded', result=None, error=''):
    conn.execute('UPDATE crawl_units SET status=?,result=?,error=? WHERE job_id=? AND kind=? AND target=? AND page=?',
                 (status, json.dumps(result or {}), str(error)[:2000], job_id, kind, str(target), page))


def progress(conn, row):
    if row['summary'] and row['status'] not in ('queued', 'running', 'stopping'):
        return json.loads(row['summary'])
    records = conn.execute('SELECT kind,status,result,error,target,page FROM crawl_units WHERE job_id=?', (row['id'],)).fetchall()
    units = [r for r in records if r['kind'] != 'comments']
    succeeded = sum(r['status'] == 'succeeded' for r in units)
    failed = sum(r['status'] == 'failed' for r in units)
    stats = {'completed': succeeded, 'failed': failed, 'total': len(units), 'new': 0, 'updated': 0, 'saved_comments': 0,
             'threads_completed': sum(r['kind'] == 'comments' and r['status'] == 'succeeded' for r in records),
             'threads_total': sum(r['kind'] == 'comments' for r in records), 'errors': []}
    for r in units:
        result = json.loads(r['result'])
        for key in ('new', 'updated', 'saved_comments'):
            stats[key] += result.get(key, 0) if r['status'] == 'succeeded' else 0
        if r['status'] == 'failed' and len(stats['errors']) < 20:
            stats['errors'].append({'target': r['target'], 'page': r['page'], 'error': r['error']})
    touched = conn.execute('SELECT COALESCE(SUM(was_new),0),COUNT(*) FROM crawl_touched_threads WHERE job_id=?', (row['id'],)).fetchone()
    stats['new'], stats['updated'] = touched[0], touched[1] - touched[0]
    params = json.loads(row['params'])
    stats['total_known'] = bool(row['planned']) and (row['kind'] in ('details', 'rankings') or (row['kind'] == 'sync' and bool(params.get('pages'))) or
        (row['kind'] == 'comments' and all(json.loads(r['result']).get('total_pages') for r in records if r['kind'] == 'comments')))
    return stats
