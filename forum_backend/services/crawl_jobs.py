"""Persistent crawl history with one background process at a time."""
import copy
from contextlib import closing
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

from forum_backend.config import configured_fids, forum_display_name
from forum_backend.storage.connection import connect_db
from .crawl_store import database, ensure_schema, progress
from .crawl_admin import CrawlAdminMixin


class CrawlBusy(ValueError):
    pass


class CrawlJobs(CrawlAdminMixin):
    def __init__(self, database_path, config, *, start_background=True):
        self.database_path = database_path
        self.config = copy.deepcopy(config or {})
        self.lock = threading.RLock()
        self.closed = threading.Event()
        self.processes = {}
        self.stop_requested = set()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='crawl-job')
        with closing(connect_db(database_path)) as conn, conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS crawl_jobs (
                id TEXT PRIMARY KEY, kind TEXT NOT NULL, params TEXT NOT NULL,
                status TEXT NOT NULL, log TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                finished_at TEXT
            )''')
            conn.execute('CREATE TABLE IF NOT EXISTS crawl_detail_claims (job_id TEXT NOT NULL, tid TEXT NOT NULL, PRIMARY KEY(job_id, tid))')
            conn.execute("UPDATE crawl_jobs SET status='interrupted', finished_at=CURRENT_TIMESTAMP WHERE status IN ('running', 'stopping')")

        ensure_schema(database_path)
        with database(database_path) as conn:
            if conn.execute('SELECT 1 FROM crawl_detail_claims LIMIT 1').fetchone():
                conn.execute("UPDATE threads SET detail_status='pending' WHERE detail_status='processing' AND tid IN (SELECT c.tid FROM crawl_detail_claims c JOIN crawl_jobs j ON c.job_id=j.id WHERE j.status='interrupted')")
                conn.execute("DELETE FROM crawl_detail_claims WHERE job_id IN (SELECT id FROM crawl_jobs WHERE status='interrupted')")
        self.scheduler = None
        if start_background:
            with self.lock:
                self._dispatch_locked()
            self.scheduler = threading.Thread(target=self._schedule_loop, daemon=True, name='crawl-scheduler')
            self.scheduler.start()

    def list(self):
        with closing(connect_db(self.database_path)) as conn, conn:
            rows = conn.execute("""SELECT * FROM crawl_jobs WHERE status IN ('queued','running','stopping') OR id IN
                (SELECT id FROM crawl_jobs WHERE status NOT IN ('queued','running','stopping') ORDER BY rowid DESC LIMIT 30)
                ORDER BY CASE WHEN status IN ('running','stopping') THEN 0 WHEN status='queued' THEN 1 ELSE 2 END,
                CASE WHEN status='queued' THEN rowid ELSE -rowid END""").fetchall()
            items = []
            for row in rows:
                item = dict(row)
                item.pop('settings', None)
                item.pop('summary', None)
                item['params'] = json.loads(row['params'])
                item['progress'] = progress(conn, row)
                items.append(item)
        return {'items': items,
                'site_name': self.config.get('site', {}).get('name', '默认论坛'),
                'environment': self.config.get('database', {}).get('environment', ''),
                'database': Path(self.database_path).name,
                'forums': [{'value': fid, 'label': forum_display_name(fid, self.config)} for fid in configured_fids(self.config)] if self.config else []}

    def prepare(self, body, settings=None):
        if not isinstance(body, dict):
            raise ValueError('任务参数必须是对象')
        kind = body.get('kind')
        if kind not in ('sync', 'details', 'comments', 'rankings'):
            raise ValueError('请选择有效的采集类型')
        config = copy.deepcopy(self.config)
        if not config:
            raise ValueError('服务未配置爬虫参数')
        for section, values in (settings or self.settings()).items():
            config.setdefault(section, {}).update(values)
        # Always use the API server's database, including test environments.
        config['database'] = {'environment': 'managed', 'paths': {'managed': self.database_path}}
        params = {}
        if kind == 'rankings':
            if set(body) != {'kind'}:
                raise ValueError('排行榜采集不需要额外参数')
            return kind, config, params
        allowed = {'kind', 'fid', 'pages', 'start_page'} if kind == 'sync' else {'kind', 'limit', 'tids'} if kind == 'details' else {'kind', 'limit'}
        if set(body) - allowed:
            raise ValueError('包含不支持的采集参数')
        for key, maximum in [('pages', 2000), ('start_page', 100000), ('limit', 100000)]:
            value = body.get(key)
            if value is not None:
                if type(value) is not int or not 1 <= value <= maximum:
                    raise ValueError(f'{key} 必须是 1 到 {maximum} 的整数')
                params[key] = value
        if kind == 'sync':
            fid = body.get('fid')
            if fid:
                if fid not in configured_fids(config):
                    raise ValueError('请选择已配置的板块')
                params['fid'] = fid
                config['list_sync']['fids'] = [fid]
            if 'start_page' in params and 'pages' not in params:
                raise ValueError('指定起始页时必须填写页数')
            if 'pages' in params:
                config['_manual_list'] = {key: params[key] for key in ('pages', 'start_page') if key in params}
        else:
            if 'limit' in params:
                config['details']['limit'] = params['limit']
            tids = body.get('tids', '')
            if not isinstance(tids, str) or len(tids) > 4000:
                raise ValueError('帖子 ID 格式错误')
            if tids.strip():
                values = list(dict.fromkeys(value.strip() for value in tids.split(',')))
                if not all(value.isascii() and value.isdigit() for value in values):
                    raise ValueError('帖子 ID 请使用英文逗号分隔的数字')
                config['_detail_tids'] = values
                params['tids'] = ','.join(values)
        return kind, config, params

    def submit(self, body):
        return self.enqueue([body])

    def submit_rankings(self):
        with self.lock:
            with database(self.database_path) as conn:
                active = conn.execute("""
                    SELECT id FROM crawl_jobs WHERE kind='rankings'
                    AND status IN ('queued','running','stopping') ORDER BY rowid LIMIT 1
                """).fetchone()
            if active:
                return {'id': active['id']}
            return self.submit({'kind': 'rankings'})

    def enqueue(self, bodies, parent_id=''):
        with self.lock:
            if self.closed.is_set():
                raise ValueError('服务正在关闭')
            settings = self.settings()
            prepared = [self.prepare(body, settings) for body in bodies]
            if not 1 <= len(prepared) <= 10:
                raise ValueError('方案需包含 1–10 个步骤')
            ids = []
            with database(self.database_path) as conn:
                count = conn.execute("SELECT COUNT(*) FROM crawl_jobs WHERE status IN ('queued','running','stopping')").fetchone()[0]
                if count + len(prepared) > 50:
                    raise CrawlBusy('任务队列已满（最多 50 项）')
                for kind, config, params in prepared:
                    job_id = uuid.uuid4().hex
                    ids.append(job_id)
                    conn.execute('INSERT INTO crawl_jobs(id,kind,params,status,settings,parent_id) VALUES (?,?,?,?,?,?)',
                        (job_id, kind, json.dumps(params), 'queued', json.dumps(settings), parent_id))
            self._dispatch_locked()
        return {'id': ids[0], 'ids': ids}

    def _dispatch_locked(self):
        if self.closed.is_set():
            return
        with database(self.database_path) as conn:
            if conn.execute("SELECT 1 FROM crawl_jobs WHERE status IN ('running','stopping')").fetchone():
                return
            row = conn.execute("SELECT * FROM crawl_jobs WHERE status='queued' ORDER BY rowid LIMIT 1").fetchone()
            if row is None:
                return
            try:
                kind, config, _ = self.prepare({'kind': row['kind'], **json.loads(row['params'])}, json.loads(row['settings']) or None)
            except ValueError as exc:
                conn.execute("UPDATE crawl_jobs SET status='failed',finished_at=CURRENT_TIMESTAMP,log=? WHERE id=?", (f'任务配置不可用：{exc}', row['id']))
                return
            conn.execute("UPDATE crawl_jobs SET status='running',started_at=CURRENT_TIMESTAMP WHERE id=?", (row['id'],))
        self.executor.submit(self._run, row['id'], kind, config)

    def resume(self, job_id):
        with self.lock:
            with database(self.database_path) as conn:
                row = conn.execute('SELECT * FROM crawl_jobs WHERE id=?', (job_id,)).fetchone()
                if row is None or row['status'] not in ('failed','partial','cancelled','interrupted'):
                    raise ValueError('只能继续失败、停止或中断的任务')
                if conn.execute("SELECT 1 FROM crawl_jobs WHERE parent_id=? AND status IN ('queued','running','stopping')", (job_id,)).fetchone():
                    raise ValueError('该任务已有续爬任务在队列中')
                if conn.execute("SELECT COUNT(*) FROM crawl_jobs WHERE status IN ('queued','running','stopping')").fetchone()[0] >= 50:
                    raise CrawlBusy('任务队列已满')
                new_id = uuid.uuid4().hex
                conn.execute('INSERT INTO crawl_jobs(id,kind,params,status,settings,parent_id,planned) VALUES (?,?,?,?,?,?,?)',
                    (new_id, row['kind'], row['params'], 'queued', row['settings'], job_id, row['planned']))
                conn.execute("""INSERT INTO crawl_units SELECT ?,kind,target,page,
                    CASE WHEN status='succeeded' THEN status ELSE 'pending' END,result,'' FROM crawl_units WHERE job_id=?""", (new_id, job_id))
                conn.execute('INSERT INTO crawl_touched_threads SELECT ?,tid,was_new FROM crawl_touched_threads WHERE job_id=?', (new_id, job_id))
            self._dispatch_locked()
            return {'id': new_id}

    def stop(self, job_id):
        if not isinstance(job_id, str) or not job_id:
            raise ValueError('缺少任务 ID')
        with self.lock:
            with closing(connect_db(self.database_path)) as conn, conn:
                row = conn.execute('SELECT status FROM crawl_jobs WHERE id=?', (job_id,)).fetchone()
                if row is None:
                    raise ValueError('任务不存在')
                if row['status'] == 'queued':
                    conn.execute("UPDATE crawl_jobs SET status='cancelled',finished_at=CURRENT_TIMESTAMP WHERE id=?", (job_id,))
                    return {'id': job_id, 'status': 'cancelled'}
                if row['status'] not in ('running', 'stopping'):
                    return {'id': job_id, 'status': row['status']}
                self.stop_requested.add(job_id)
                conn.execute("UPDATE crawl_jobs SET status='stopping' WHERE id=?", (job_id,))
            process = self.processes.get(job_id)
            if process is not None and process.poll() is None:
                process.terminate()
                timer = threading.Timer(3, self._kill_if_running, args=(process,))
                timer.daemon = True
                timer.start()
        return {'id': job_id, 'status': 'stopping'}

    @staticmethod
    def _kill_if_running(process):
        if process.poll() is None:
            process.kill()

    def _finish(self, job_id, log, status):
        with self.lock:
            if job_id in self.stop_requested:
                status = 'cancelled'
                log += '\n任务已停止，已入库数据保留。\n'
            # Release only this job's unfinished detail claims after its process exits.
            with closing(connect_db(self.database_path)) as conn, conn:
                claims = conn.execute('SELECT tid FROM crawl_detail_claims WHERE job_id=?', (job_id,)).fetchall()
                if claims:
                    conn.execute("UPDATE threads SET detail_status='pending', detail_error='' WHERE detail_status='processing' AND tid IN (SELECT tid FROM crawl_detail_claims WHERE job_id=?)", (job_id,))
                conn.execute('DELETE FROM crawl_detail_claims WHERE job_id=?', (job_id,))
                row = conn.execute('SELECT * FROM crawl_jobs WHERE id=?', (job_id,)).fetchone()
                stats = progress(conn, row)
                conn.execute('UPDATE crawl_jobs SET summary=? WHERE id=?', (json.dumps(stats), job_id))
                if row and row['kind'] == 'sync' and row['finished_at'] is None and conn.execute("SELECT 1 FROM sqlite_master WHERE name='crawl_runs'").fetchone():
                    conn.execute('''INSERT INTO crawl_runs(kind,started_at,finished_at,success_count,failure_count,error)
                        VALUES ('list',?,CURRENT_TIMESTAMP,?,?,?)''',
                        (row['started_at'] or row['created_at'], stats['new'] + stats['updated'], stats['failed'],
                         '' if status == 'succeeded' else ('任务已停止' if status == 'cancelled' else log[-1000:])))
            self._save(job_id, log, status)
            self.processes.pop(job_id, None)
            self.stop_requested.discard(job_id)
            self._dispatch_locked()

    def _save(self, job_id, log, status='running'):
        with closing(connect_db(self.database_path)) as conn, conn:
            conn.execute("UPDATE crawl_jobs SET log=?,status=CASE WHEN status='stopping' AND ?='running' THEN status ELSE ? END,finished_at=CASE WHEN ?='running' THEN NULL ELSE CURRENT_TIMESTAMP END WHERE id=?",
                         (log[-24000:], status, status, status, job_id))

    def _run(self, job_id, kind, config):
        log = ''
        process = None
        try:
            with self.lock:
                cancelled = job_id in self.stop_requested
                if not cancelled:
                    process = subprocess.Popen(
                        [sys.executable, '-u', '-m', 'forum_backend.services.crawl_worker', kind],
                        cwd=Path(__file__).resolve().parents[2],
                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        text=True, encoding='utf-8', errors='replace',
                        # Popen's encoding only controls the parent side of the pipes.
                        # Pin the child's streams too, including stderr on Windows.
                        env={**os.environ, 'PYTHONIOENCODING': 'utf-8'},
                        start_new_session=True,
                    )
                    self.processes[job_id] = process
            if cancelled:
                self._finish(job_id, log, 'cancelled')
                return
            with process:
                config = {**config, '_crawl_job_id': job_id, '_manager_pid': os.getpid()}
                process.stdin.write(json.dumps(config))
                process.stdin.close()
                for line in process.stdout:
                    log = (log + line)[-24000:]
                    self._save(job_id, log)
                code = process.wait()
            self._finish(job_id, log, 'succeeded' if code == 0 else 'partial' if code == 2 else 'failed')
        except Exception as exc:
            self._finish(job_id, log + f'\n任务执行失败：{exc}', 'failed')

    def close(self):
        self.closed.set()
        if self.scheduler:
            self.scheduler.join(timeout=2)
        # Stop active work on shutdown; queued work stays durable for the next startup.
        with database(self.database_path) as conn:
            ids = [row['id'] for row in conn.execute("SELECT id FROM crawl_jobs WHERE status IN ('running','stopping')")]
        for job_id in ids:
            self.stop(job_id)
        self.executor.shutdown(wait=True)
