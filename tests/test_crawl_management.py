import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from forum_backend.db import init_db
from forum_backend.parsers import Topic
from forum_backend.services.crawl_jobs import CrawlJobs
from forum_backend.services.crawl_store import database
from forum_backend.services.crawl_admin import next_run
from forum_backend.services.managed_crawler import ManagedCrawler


class ManagementTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / 'test.db')
        init_db(self.path).close()
        self.config = {'site': {'base_url': 'https://example.invalid'}, '_cookie': 'test-secret',
                       'database': {'environment': 'test', 'paths': {'test': self.path}},
                       'list_sync': {'fids': ['95'], 'workers': 1, 'refresh_pages': 1, 'known_page_streak': 1, 'max_pages_per_fid': 4},
                       'details': {'workers': 1, 'limit': 10}, 'comments': {'pages': 'all', 'page_workers': 1, 'refresh_existing': False},
                       'network': {'delay_seconds': 0, 'jitter_seconds': 0, 'retries': 0, 'retry_backoff_seconds': 0}}
        self.jobs = CrawlJobs(self.path, self.config, start_background=False)
        self.executor = patch.object(self.jobs.executor, 'submit')
        self.executor.start()

    def tearDown(self):
        self.jobs.close()
        self.executor.stop()
        self.tmp.cleanup()

    def add_thread(self, tid, status='pending', comments=True):
        with database(self.path) as conn:
            conn.execute('INSERT INTO threads(tid,title,fid,detail_status,fetch_comments) VALUES (?,?,?,?,?)', (tid, 'test', '95', status, int(comments)))

    def start(self, body):
        job_id = self.jobs.submit(body)['id']
        config = self.jobs.prepare(body)[1]
        return job_id, ManagedCrawler(config, job_id, self.path)

    def row(self, job_id):
        return next(row for row in self.jobs.list()['items'] if row['id'] == job_id)

    def test_queue_serial_order_and_cancel_queued(self):
        first, _ = self.start({'kind': 'sync'})
        second = self.jobs.submit({'kind': 'details'})['id']
        third = self.jobs.submit({'kind': 'comments'})['id']
        self.assertEqual(self.row(second)['status'], 'queued')
        self.jobs.stop(third)
        self.jobs._finish(first, '', 'succeeded')
        self.assertEqual(self.row(second)['status'], 'running')
        self.assertEqual(self.row(third)['status'], 'cancelled')

    def test_settings_snapshot_and_validation(self):
        settings = self.jobs.settings()
        first, _ = self.start({'kind': 'sync'})
        settings['details']['workers'] = 2
        self.jobs.save_settings(settings)
        second = self.jobs.submit({'kind': 'details'})['id']
        with database(self.path) as conn:
            rows = {row['id']: json.loads(row['settings']) for row in conn.execute('SELECT id,settings FROM crawl_jobs')}
        self.assertEqual(rows[first]['details']['workers'], 1)
        self.assertEqual(rows[second]['details']['workers'], 2)
        settings['network']['delay_seconds'] = float('nan')
        with self.assertRaises(ValueError):
            self.jobs.save_settings(settings)
        self.assertNotIn('test-secret', json.dumps(self.jobs.admin()))
        self.assertEqual(self.config['details']['workers'], 1)

    def test_preview_partial_legacy_comments_and_coverage(self):
        self.add_thread('1')
        self.add_thread('2', status='fetched')
        with database(self.path) as conn:
            conn.execute("INSERT INTO comments(tid,comment_id,fetched_at) VALUES ('1','x','now')")
        self.assertEqual(self.jobs.preview({'kind': 'comments'})['target_count'], 2)
        with database(self.path) as conn:
            conn.executemany('INSERT INTO crawl_comment_pages VALUES (?,?,?,?)', [('1', 1, 2, 1), ('1', 2, 2, 1)])
        self.assertEqual(self.jobs.preview({'kind': 'comments'})['target_count'], 1)
        self.assertEqual(self.jobs.preview({'kind': 'details'})['target_count'], 1)
        self.assertEqual(self.jobs.preview({'kind': 'sync', 'pages': 5})['pages'], 5)

    def test_preset_validation_is_atomic(self):
        with self.assertRaises(ValueError):
            self.jobs.save_preset({'name': 'bad', 'steps': [{'kind': 'sync'}, {'kind': 'bad'}]})
        ids = self.jobs.run_preset('daily')['ids']
        self.assertEqual([self.row(key)['kind'] for key in ids], ['sync', 'details', 'comments'])
        self.assertEqual([self.row(key)['status'] for key in ids], ['running', 'queued', 'queued'])

    def test_schedule_disabled_skip_and_duplicate_tick(self):
        schedule = {'name': 'test', 'preset_id': 'daily', 'mode': 'interval', 'every_minutes': 60,
                    'daily_time': '09:00', 'busy_policy': 'skip', 'enabled': False}
        key = self.jobs.save_schedule(schedule)['id']
        with database(self.path) as conn:
            conn.execute('UPDATE crawl_schedules SET next_run=1 WHERE id=?', (key,))
        self.jobs.tick(100)
        self.assertEqual(len(self.jobs.list()['items']), 0)
        with database(self.path) as conn:
            conn.execute('UPDATE crawl_schedules SET enabled=1 WHERE id=?', (key,))
        self.jobs.tick(100)
        self.jobs.tick(100)
        self.assertEqual(len(self.jobs.list()['items']), 3)
        self.jobs.tick(3700)
        self.assertEqual(len(self.jobs.list()['items']), 3)
        self.assertIn('跳过', self.jobs.admin()['schedules'][0]['last_result'])
        with self.assertRaises(ValueError):
            self.jobs.delete_preset('daily')
        # UTC midnight + 8 = 08:00 in Shanghai; next 09:00 is one hour away.
        self.assertEqual(next_run({'mode': 'daily', 'daily_time': '09:00'}, 0), 3600)

    def test_schedule_queue_policy_and_settings_persist(self):
        self.start({'kind': 'sync'})
        key = self.jobs.save_schedule({'name': 'queue', 'preset_id': 'daily', 'mode': 'daily',
            'daily_time': '09:00', 'enabled': True, 'busy_policy': 'queue'})['id']
        with database(self.path) as conn:
            conn.execute('UPDATE crawl_schedules SET next_run=1 WHERE id=?', (key,))
        self.jobs.tick(100)
        self.assertEqual(len(self.jobs.list()['items']), 4)
        self.assertEqual(sum(row['status'] == 'running' for row in self.jobs.list()['items']), 1)

    def test_restart_preserves_queue_and_marks_active_interrupted(self):
        first, _ = self.start({'kind': 'sync'})
        second = self.jobs.submit({'kind': 'details'})['id']
        self.jobs.close()
        self.executor.stop()
        self.jobs = CrawlJobs(self.path, self.config, start_background=False)
        self.executor = patch.object(self.jobs.executor, 'submit')
        self.executor.start()
        self.assertEqual(self.row(first)['status'], 'interrupted')
        self.assertEqual(self.row(second)['status'], 'queued')
        with self.jobs.lock:
            self.jobs._dispatch_locked()
        self.assertEqual(self.row(second)['status'], 'running')

    def test_details_resume_only_failed_targets(self):
        self.add_thread('1'); self.add_thread('2')
        job_id, runner = self.start({'kind': 'details'})
        def fetch(row, **kwargs):
            return {'tid': row['tid'], 'status': 'failed' if row['tid'] == '2' else 'fetched', 'error': 'test failure',
                    'fetched_at': 'now', 'participant_count': 1, 'money': 1, 'reward_money': 1, 'purchase_count': 0, 'rating': ''}
        with patch('forum_backend.services.managed_crawler.crawler.fetch_thread_detail', side_effect=fetch):
            result = runner.run('details')
        self.assertEqual(result, {'success_count': 1, 'failure_count': 1})
        self.jobs._finish(job_id, '', 'partial')
        resumed = self.jobs.resume(job_id)['id']
        calls = []
        def success(row, **kwargs):
            calls.append(row['tid']); return {**fetch(row), 'status': 'fetched'}
        with patch('forum_backend.services.managed_crawler.crawler.fetch_thread_detail', side_effect=success):
            ManagedCrawler(self.jobs.prepare({'kind': 'details'})[1], resumed, self.path).run('details')
        self.assertEqual(calls, ['2'])
        self.assertEqual(self.row(resumed)['progress']['completed'], 2)

    def test_comment_page_failure_then_resume_skips_saved_pages(self):
        self.add_thread('10')
        job_id, runner = self.start({'kind': 'comments'})
        requests = []
        def fetch(url, *args, **kwargs):
            from urllib.parse import parse_qs, urlparse
            page = int(parse_qs(urlparse(url).query).get('page', ['1'])[0])
            requests.append(page)
            if page == 2 and requests.count(2) == 1:
                raise RuntimeError('temporary failure')
            return '<div id="postlist">test</div>'
        def parse(html, url, tid, comment_page, fetched_at):
            return {'comments': [{'tid': tid, 'comment_id': str(comment_page), 'source_page': comment_page, 'fetched_at': fetched_at}]}
        with patch('forum_backend.services.managed_crawler.crawler.fetch_page', side_effect=fetch), \
             patch('forum_backend.services.managed_crawler.crawler.parse_detail_page', side_effect=parse), \
             patch('forum_backend.services.managed_crawler.crawler.detect_detail_comment_page_count', return_value=3):
            result = runner.run('comments')
            self.assertEqual(result['failure_count'], 1)
            self.assertEqual(self.row(job_id)['progress']['completed'], 2)
            self.jobs._finish(job_id, '', 'partial')
            resumed = self.jobs.resume(job_id)['id']
            ManagedCrawler(self.jobs.prepare({'kind': 'comments'})[1], resumed, self.path).run('comments')
        self.assertEqual(requests, [1, 2, 3, 2])
        self.assertEqual(self.jobs.preview({'kind': 'comments'})['target_count'], 0)
        with database(self.path) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM comments').fetchone()[0], 3)

    def test_login_html_is_not_a_successful_comment_checkpoint(self):
        self.add_thread('1')
        job_id, runner = self.start({'kind': 'comments'})
        with patch('forum_backend.services.managed_crawler.crawler.fetch_page', return_value='<form>login</form>'):
            result = runner.run('comments')
        self.assertEqual(result['failure_count'], 1)
        with database(self.path) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM crawl_comment_pages').fetchone()[0], 0)

    def test_fixed_list_retry_only_missing_page(self):
        job_id, runner = self.start({'kind': 'sync', 'pages': 3})
        requests = []
        def fetch(pair, **kwargs):
            page = pair[0]; requests.append(page)
            if page == 2 and requests.count(2) == 1:
                raise RuntimeError('temporary failure')
            return page, [Topic(title=f'page {page}', url=f'https://example.invalid/forum.php?tid={page}', author='test', posted_at='2026-10-01', replies=0)]
        with patch('forum_backend.services.managed_crawler.crawler.fetch_list_page', side_effect=fetch):
            self.assertEqual(runner.run('sync')['failure_count'], 1)
            self.jobs._finish(job_id, '', 'partial')
            resumed = self.jobs.resume(job_id)['id']
            ManagedCrawler(self.jobs.prepare({'kind': 'sync', 'pages': 3})[1], resumed, self.path).run('sync')
        self.assertEqual(requests, [1, 2, 3, 2])
        self.assertEqual(self.row(resumed)['progress']['new'], 3)
        self.assertTrue(self.row(resumed)['progress']['total_known'])

    def test_incremental_boundary_uses_committed_checkpoint(self):
        job_id, runner = self.start({'kind': 'sync'})
        requests = []
        def fetch(pair, **kwargs):
            page = pair[0]; requests.append(page)
            if page == 2 and requests.count(2) == 1:
                raise RuntimeError('temporary failure')
            return page, [Topic(title='same', url='https://example.invalid/forum.php?tid=1', author='test', posted_at='2026-10-01', replies=0)]
        with patch('forum_backend.services.managed_crawler.crawler.fetch_list_page', side_effect=fetch):
            runner.run('sync'); self.jobs._finish(job_id, '', 'partial')
            resumed = self.jobs.resume(job_id)['id']
            ManagedCrawler(self.jobs.prepare({'kind': 'sync'})[1], resumed, self.path).run('sync')
        self.assertEqual(requests, [1, 2, 2])
        self.assertFalse(self.row(resumed)['progress']['total_known'])

    def test_list_statistics_deduplicate_posts_across_pages(self):
        self.add_thread('1')
        job_id, runner = self.start({'kind': 'sync', 'pages': 2})
        topics = [Topic(title='same', url=f'https://example.invalid/forum.php?tid={tid}', author='test', posted_at='2026-10-01', replies=0) for tid in ('1', '2')]
        with patch('forum_backend.services.managed_crawler.crawler.fetch_list_page', side_effect=lambda pair, **kwargs: (pair[0], topics)):
            runner.run('sync')
        stats = self.row(job_id)['progress']
        self.assertEqual((stats['new'], stats['updated']), (1, 1))
        self.jobs._finish(job_id, '', 'succeeded')
        self.assertEqual(self.row(job_id)['progress'], stats)

    def test_comment_transaction_rolls_back_before_checkpoint(self):
        self.add_thread('1')
        job_id, runner = self.start({'kind': 'comments'})
        from forum_backend.db import upsert_comment
        def broken_save(conn, comment, **kwargs):
            upsert_comment(conn, comment, **kwargs)
            raise RuntimeError('simulated write failure')
        comments = [{'tid': '1', 'comment_id': 'c', 'fetched_at': 'now'}]
        with patch('forum_backend.services.managed_crawler.crawler.fetch_page', return_value='<div id="postlist"></div>'), \
             patch('forum_backend.services.managed_crawler.crawler.parse_detail_page', return_value={'comments': comments}), \
             patch('forum_backend.services.managed_crawler.crawler.detect_detail_comment_page_count', return_value=1), \
             patch('forum_backend.services.managed_crawler.upsert_comment', side_effect=broken_save):
            runner.run('comments')
        with database(self.path) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM comments').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM crawl_comment_pages').fetchone()[0], 0)

    def test_duplicate_resume_and_queue_limit(self):
        job_id, _ = self.start({'kind': 'sync'})
        self.jobs._finish(job_id, '', 'partial')
        self.jobs.resume(job_id)
        with self.assertRaises(ValueError):
            self.jobs.resume(job_id)
        for _ in range(49):
            self.jobs.submit({'kind': 'details'})
        with self.assertRaises(ValueError):
            self.jobs.submit({'kind': 'comments'})
        self.assertEqual(sum(row['status'] in ('running', 'queued') for row in self.jobs.list()['items']), 50)


if __name__ == '__main__':
    unittest.main()
