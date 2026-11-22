"""Admin controls: previews, reusable plans, safe settings and in-service schedules."""
import datetime as dt
import json
import logging
import re
import time
import uuid
from forum_backend.config import site_cookie
from pathlib import Path

from forum_backend.config import configured_fids, load_cookie, source_url_from_config
from .crawl_store import database, safe_settings, validate_settings, select_targets
from .rankings import RANK_SCOPES

SHANGHAI = dt.timezone(dt.timedelta(hours=8))


def next_run(schedule, timestamp):
    if schedule['mode'] == 'interval':
        return timestamp + schedule['every_minutes'] * 60
    current = dt.datetime.fromtimestamp(timestamp, SHANGHAI)
    hour, minute = map(int, schedule['daily_time'].split(':'))
    target = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= current:
        target += dt.timedelta(days=1)
    return target.timestamp()


class CrawlAdminMixin:
    def settings(self):
        with database(self.database_path) as conn:
            row = conn.execute("SELECT value FROM crawl_admin WHERE key='settings'").fetchone()
        return json.loads(row['value']) if row else safe_settings(self.config)

    def save_settings(self, body):
        values = validate_settings(body)
        with self.lock, database(self.database_path) as conn:
            conn.execute("INSERT OR REPLACE INTO crawl_admin VALUES ('settings',?)", (json.dumps(values),))
        return {'settings': values}

    def admin(self):
        with database(self.database_path) as conn:
            presets = [{**dict(row), 'steps': json.loads(row['steps'])} for row in conn.execute('SELECT * FROM crawl_presets ORDER BY rowid')]
            schedules = [dict(row) for row in conn.execute('SELECT * FROM crawl_schedules ORDER BY rowid')]
        return {'settings': self.settings(), 'presets': presets, 'schedules': schedules, 'timezone': 'Asia/Shanghai'}

    def preview(self, body):
        kind, config, params = self.prepare(body)
        with database(self.database_path) as conn:
            if kind == 'rankings':
                count = len(RANK_SCOPES)
            else:
                count = None if kind == 'sync' else len(select_targets(conn, kind, config))
            totals = dict(conn.execute("SELECT detail_status,COUNT(*) FROM threads GROUP BY detail_status").fetchall())
        cookie_path = config['site'].get('cookie_file')
        try:
            available = bool(load_cookie(config.get('_cookie'), cookie_path))
        except (OSError, ValueError):
            available = False
        fids = configured_fids(config) if kind == 'sync' else []
        pages = params.get('pages')
        return {'kind': kind, 'target_count': count, 'fids': fids, 'pages': pages * len(fids) if pages else None,
                'incremental': kind == 'sync' and not pages, 'cookie_available': available, 'anonymous_allowed': bool(config['site'].get('anonymous_allowed')),
                'environment': self.config.get('database', {}).get('environment', ''), 'database': Path(self.database_path).name,
                'detail_pending': totals.get('pending', 0), 'detail_failed': totals.get('failed', 0),
                'settings': safe_settings(config), 'note': '预览不访问网站；排队任务会在开始执行时重新确定待处理帖子。'}

    def check_login(self):
        from forum_backend.crawler import fetch_page, parse_topics
        try:
            cookie = site_cookie(self.config)
        except (OSError, ValueError):
            return {'status': 'missing', 'message': 'Cookie 文件不存在或为空，请更新服务配置指向的 Cookie 文件。'}
        try:
            url = source_url_from_config(self.config)
            html = fetch_page(url, cookie, timeout=8, retries=0)
            topics = parse_topics(html, url)
            if not topics:
                return {'status': 'unavailable', 'message': '未识别到帖子列表，可能是 Cookie 过期、访问验证或站点结构变化。'}
            logged_in = bool(re.search(r'(action=logout|mod=logging[^\"\']*logout|退出登录)', html, re.I))
            return {'status': 'ok' if logged_in else 'unknown', 'message': 'Cookie 可读取列表，已识别登录标记。' if logged_in else '列表可以访问，但未识别到登录标记，无法确认 Cookie 是否仍有效。'}
        except Exception:
            return {'status': 'unavailable', 'message': '站点请求失败，请检查域名、网络或 Cookie；没有启动采集。'}

    def save_preset(self, body):
        name = body.get('name', '')
        steps = body.get('steps')
        if not isinstance(name, str) or not name.strip() or len(name) > 60:
            raise ValueError('方案名称需为 1–60 个字符')
        if not isinstance(steps, list) or not 1 <= len(steps) <= 10:
            raise ValueError('方案需包含 1–10 个步骤')
        normalized = [{'kind': kind, **params} for kind, _, params in (self.prepare(step) for step in steps)]
        preset_id = body.get('id') or uuid.uuid4().hex
        if not isinstance(preset_id, str):
            raise ValueError('方案 ID 格式错误')
        with self.lock, database(self.database_path) as conn:
            conn.execute('INSERT OR REPLACE INTO crawl_presets VALUES (?,?,?)', (preset_id, name.strip(), json.dumps(normalized)))
        return {'id': preset_id}

    def delete_preset(self, preset_id):
        with self.lock, database(self.database_path) as conn:
            if conn.execute('SELECT 1 FROM crawl_schedules WHERE preset_id=?', (preset_id,)).fetchone():
                raise ValueError('请先删除引用该方案的定时计划')
            conn.execute('DELETE FROM crawl_presets WHERE id=?', (preset_id,))
        return {'deleted': True}

    def run_preset(self, preset_id):
        with self.lock, database(self.database_path) as conn:
            row = conn.execute('SELECT steps FROM crawl_presets WHERE id=?', (preset_id,)).fetchone()
            if row is None:
                raise ValueError('方案不存在')
            steps = json.loads(row['steps'])
        return self.enqueue(steps)

    def save_schedule(self, body):
        name, mode = body.get('name', ''), body.get('mode')
        minutes, daily = body.get('every_minutes', 60), body.get('daily_time', '09:00')
        enabled, policy = body.get('enabled', False), body.get('busy_policy', 'skip')
        if not isinstance(name, str) or not name.strip() or len(name) > 60:
            raise ValueError('计划名称需为 1–60 个字符')
        if mode not in ('interval', 'daily') or policy not in ('skip', 'queue') or type(enabled) is not bool:
            raise ValueError('定时计划参数不正确')
        if type(minutes) is not int or not 5 <= minutes <= 43200:
            raise ValueError('执行间隔需为 5–43200 分钟')
        if not isinstance(daily, str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', daily):
            raise ValueError('每日时间需为 HH:MM（北京时间）')
        schedule_id = body.get('id') or uuid.uuid4().hex
        if not isinstance(schedule_id, str) or not isinstance(body.get('preset_id'), str):
            raise ValueError('请选择有效方案')
        schedule = {'mode': mode, 'every_minutes': minutes, 'daily_time': daily}
        with self.lock, database(self.database_path) as conn:
            if not conn.execute('SELECT 1 FROM crawl_presets WHERE id=?', (body['preset_id'],)).fetchone():
                raise ValueError('方案不存在')
            conn.execute('''INSERT INTO crawl_schedules(id,name,preset_id,mode,every_minutes,daily_time,busy_policy,enabled,next_run)
                VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,preset_id=excluded.preset_id,
                mode=excluded.mode,every_minutes=excluded.every_minutes,daily_time=excluded.daily_time,
                busy_policy=excluded.busy_policy,enabled=excluded.enabled,next_run=excluded.next_run''',
                (schedule_id, name.strip(), body['preset_id'], mode, minutes, daily, policy, int(enabled), next_run(schedule, time.time())))
        return {'id': schedule_id}

    def delete_schedule(self, schedule_id):
        with self.lock, database(self.database_path) as conn:
            conn.execute('DELETE FROM crawl_schedules WHERE id=?', (schedule_id,))
        return {'deleted': True}

    def tick(self, timestamp=None):
        timestamp = time.time() if timestamp is None else timestamp
        with self.lock:
            if self.closed.is_set():
                return
            with database(self.database_path) as conn:
                due = [dict(row) for row in conn.execute('SELECT * FROM crawl_schedules WHERE enabled=1 AND next_run<=?', (timestamp,))]
            for schedule in due:
                with database(self.database_path) as conn:
                    busy = conn.execute("SELECT 1 FROM crawl_jobs WHERE status IN ('running','stopping','queued')").fetchone()
                    # Claim this occurrence first. After downtime, run at most once, never replay missed intervals.
                    conn.execute('UPDATE crawl_schedules SET next_run=?,last_run=? WHERE id=?',
                                 (next_run(schedule, timestamp), timestamp, schedule['id']))
                result = '已有任务，已跳过本次执行'
                if not busy or schedule['busy_policy'] == 'queue':
                    try:
                        jobs = self.run_preset(schedule['preset_id'])
                        result = f"已加入队列：{len(jobs['ids'])} 个任务"
                    except Exception as exc:
                        result = f'启动失败：{exc}'
                with database(self.database_path) as conn:
                    conn.execute('UPDATE crawl_schedules SET last_result=? WHERE id=?', (result, schedule['id']))

    def _schedule_loop(self):
        while not self.closed.wait(1):
            try:
                self.tick()
                with self.lock:
                    self._dispatch_locked()
            except Exception:
                logging.exception('Crawler scheduler tick failed')
