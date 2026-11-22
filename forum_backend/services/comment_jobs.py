"""Persistent, bounded comment tasks for a single API server process."""
import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from forum_backend.storage.connection import connect_db
from .comments import fetch_missing_thread_comments


class CommentJobs:
    def __init__(self, database_path, base_url, config):
        self.database_path, self.base_url, self.config = database_path, base_url, config
        self.lock = threading.Lock()
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='comment-job')
        conn = connect_db(database_path)
        try:
            conn.executescript('''
                CREATE TABLE IF NOT EXISTS comment_jobs (
                  id TEXT PRIMARY KEY, tid TEXT NOT NULL, status TEXT NOT NULL,
                  progress TEXT NOT NULL DEFAULT '{}', error TEXT NOT NULL DEFAULT '',
                  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_comment_jobs_tid ON comment_jobs(tid, updated_at);
            ''')
            conn.execute("UPDATE comment_jobs SET status='failed', error='服务重启，任务已中断，请重新抓取' WHERE status IN ('queued','running')")
            conn.commit()
        finally:
            conn.close()

    def get(self, job_id):
        conn = connect_db(self.database_path)
        try:
            row = conn.execute('SELECT * FROM comment_jobs WHERE id=?', (job_id,)).fetchone()
            if row is None:
                raise ValueError('task not found')
            result = {**json.loads(row['progress']), **dict(row)}
            result.pop('progress', None)
            total = result.get('total_pages') or 0
            result['percent'] = min(100, round(100 * result.get('completed_pages', 0) / total)) if total else 0
            return result
        finally:
            conn.close()

    def submit(self, tid):
        tid = str(tid or '').strip()
        with self.lock:
            conn = connect_db(self.database_path)
            try:
                if not conn.execute('SELECT 1 FROM threads WHERE tid=?', (tid,)).fetchone():
                    raise ValueError('thread not found')
                existing = conn.execute("SELECT id FROM comment_jobs WHERE tid=? AND status IN ('queued','running')", (tid,)).fetchone()
                if existing:
                    return self.get(existing['id'])
                count = conn.execute("SELECT COUNT(*) FROM comment_jobs WHERE status IN ('queued','running')").fetchone()[0]
                if count >= 8:
                    raise ValueError('抓取任务已满，请稍后重试')
                job_id = uuid.uuid4().hex
                conn.execute("INSERT INTO comment_jobs(id,tid,status) VALUES (?,?,'queued')", (job_id, tid))
                conn.commit()
                self.executor.submit(self._run, job_id, tid)
                return self.get(job_id)
            finally:
                conn.close()

    def _update(self, job_id, progress):
        conn = connect_db(self.database_path)
        try:
            conn.execute('UPDATE comment_jobs SET status=?, progress=?, error=?, updated_at=CURRENT_TIMESTAMP WHERE id=?',
                         (progress.get('status', 'running'), json.dumps(progress), progress.get('error', ''), job_id))
            conn.commit()
        finally:
            conn.close()

    def _run(self, job_id, tid):
        try:
            self._update(job_id, {'status': 'running'})
            fetch_missing_thread_comments(self.database_path, self.base_url, tid, self.config,
                                          progress_callback=lambda progress: self._update(job_id, progress))
        except Exception as exc:
            self._update(job_id, {'status': 'failed', 'error': str(exc)})

    def close(self):
        self.executor.shutdown(wait=True)
