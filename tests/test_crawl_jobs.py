import copy
import io
import os
import json
from pathlib import Path
import tempfile
import subprocess
import sys
import time
import unittest
from unittest.mock import patch, MagicMock

from forum_backend.services.crawl_jobs import CrawlBusy, CrawlJobs
from forum_backend.services import crawl_worker


class CrawlJobsTests(unittest.TestCase):
    def wait_status(self, status):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            row = self.jobs.list()['items'][0]
            if row['status'] == status:
                return row
            time.sleep(0.02)
        self.fail(f'Expected {status}, got {row}')

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.config = {
            'site': {}, 'database': {'environment': 'production', 'paths': {'production': 'do-not-use.db'}},
            'list_sync': {'fids': ['95', '2']}, 'details': {'limit': 20}, 'comments': {}, 'network': {},
        }
        self.original = copy.deepcopy(self.config)
        self.jobs = CrawlJobs(str(Path(self.tmp.name) / 'test.db'), self.config, start_background=False)

    def tearDown(self):
        self.jobs.close()
        self.tmp.cleanup()

    def test_overrides_are_temporary_and_database_is_pinned(self):
        kind, config, params = self.jobs.prepare({'kind': 'sync', 'fid': '95', 'pages': 3, 'start_page': 5})
        self.assertEqual(config['_manual_list'], {'pages': 3, 'start_page': 5})
        self.assertEqual(config['list_sync']['fids'], ['95'])
        self.assertEqual(config['database']['paths']['managed'], self.jobs.database_path)
        self.assertEqual(self.config, self.original)
        self.assertNotIn('_manual_list', self.jobs.prepare({'kind': 'sync'})[1])

    def test_validation(self):
        for body in [{'kind': 'shell'}, {'kind': 'sync', 'start_page': 2},
                     {'kind': 'sync', 'pages': True}, {'kind': 'sync', 'fid': '999'},
                     {'kind': 'comments', 'limit': 0}, {'kind': 'details', 'tids': '12;ls'},
                     {'kind': 'comments', 'tids': '12'}, {'kind': 'sync', 'url': 'http://other'}]:
            with self.subTest(body=body), self.assertRaises(ValueError):
                self.jobs.prepare(body)

    def test_duplicate_guard_and_restart_history(self):
        with patch.object(self.jobs.executor, 'submit'):
            result = self.jobs.submit({'kind': 'details', 'tids': '123,456'})
            queued = self.jobs.submit({'kind': 'comments'})
            self.assertEqual(self.jobs.list()['items'][1]['status'], 'queued')
            self.jobs.stop(queued['id'])
        self.jobs.close()
        self.jobs = CrawlJobs(self.jobs.database_path, self.config, start_background=False)
        row = next(item for item in self.jobs.list()['items'] if item['id'] == result['id'])
        self.assertEqual(row['id'], result['id'])
        self.assertEqual(row['status'], 'interrupted')
        self.assertEqual(row['params']['tids'], '123,456')

    def test_process_output_and_partial_failure(self):
        with patch.object(self.jobs.executor, 'submit'):
            result = self.jobs.submit({'kind': 'comments'})
        process = MagicMock()
        process.stdout = io.StringIO('page saved\nfinished\n')
        process.wait.return_value = 2
        process.__enter__.return_value = process
        with patch('forum_backend.services.crawl_jobs.subprocess.Popen', return_value=process):
            self.jobs._run(result['id'], 'comments', self.config)
        row = self.jobs.list()['items'][0]
        self.assertEqual(row['status'], 'partial')
        self.assertIn('page saved', row['log'])
        self.assertIsNotNone(row['finished_at'])

    def test_worker_reports_partial_failures(self):
        with patch.object(crawl_worker, 'crawl_details_to_db', return_value={'success_count': 1, 'failure_count': 1}), \
             patch('sys.argv', ['worker', 'details']), patch('sys.stdin', io.StringIO(json.dumps(self.config))), patch('sys.stdout', io.StringIO()):
            self.assertEqual(crawl_worker.main(), 2)

    def test_child_logs_use_utf8_even_with_legacy_parent_encoding(self):
        with patch.object(self.jobs.executor, 'submit'):
            result = self.jobs.submit({'kind': 'comments'})
        original_popen = subprocess.Popen
        script = (
            'import sys; sys.stdin.read(); '
            'print("评论已入库：中文测试 ✅", flush=True); '
            'print("错误日志：重试失败", file=sys.stderr, flush=True)'
        )
        def spawn(args, **kwargs):
            # Keep the production pipe/environment options and execute a local fixture.
            return original_popen([*args[:args.index('-m')], '-c', script], **kwargs)
        with patch.dict(os.environ, {'PYTHONIOENCODING': 'gbk'}), \
             patch('forum_backend.services.crawl_jobs.subprocess.Popen', side_effect=spawn):
            self.jobs._run(result['id'], 'comments', self.config)
            self.assertEqual(os.environ['PYTHONIOENCODING'], 'gbk')
        row = self.jobs.list()['items'][0]
        self.assertEqual(row['status'], 'succeeded', row['log'])
        self.assertIn('评论已入库：中文测试 ✅', row['log'])
        self.assertIn('错误日志：重试失败', row['log'])
        self.assertNotIn('\ufffd', row['log'])

    def test_real_worker_completes_empty_detail_job_without_network(self):
        from forum_backend.db import init_db
        init_db(self.jobs.database_path).close()
        config = self.jobs.prepare({'kind': 'details'})[1]
        config['_cookie'] = 'test-only-placeholder'
        with patch.object(self.jobs.executor, 'submit'):
            result = self.jobs.submit({'kind': 'details'})
        self.jobs._run(result['id'], 'details', config)
        row = self.jobs.list()['items'][0]
        self.assertEqual(row['status'], 'succeeded', row['log'])
        self.assertIn('0', row['log'])

    def test_stop_before_process_starts_and_duplicate_stop(self):
        with patch.object(self.jobs.executor, 'submit'):
            result = self.jobs.submit({'kind': 'sync'})
        self.assertEqual(self.jobs.stop(result['id'])['status'], 'stopping')
        self.jobs.stop(result['id'])
        with patch.object(self.jobs.executor, 'submit'):
            queued = self.jobs.submit({'kind': 'comments'})
            self.jobs.stop(queued['id'])
        with patch('forum_backend.services.crawl_jobs.subprocess.Popen') as spawn:
            self.jobs._run(result['id'], 'sync', self.config)
            spawn.assert_not_called()
        self.assertEqual(self.jobs.stop(result['id'])['status'], 'cancelled')
        with self.assertRaises(ValueError):
            self.jobs.stop('missing')

    def test_stop_real_process_preserves_logs_and_allows_next_task(self):
        original_popen = subprocess.Popen
        processes = []
        def spawn(args, **kwargs):
            process = original_popen([sys.executable, '-u', '-c',
                'import sys,time; sys.stdin.read(); print("saved page", flush=True); time.sleep(30)'], **kwargs)
            processes.append(process)
            return process
        try:
            with patch('forum_backend.services.crawl_jobs.subprocess.Popen', side_effect=spawn):
                result = self.jobs.submit({'kind': 'sync'})
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline and 'saved page' not in self.jobs.list()['items'][0]['log']:
                    time.sleep(0.02)
                self.jobs.stop(result['id'])
                row = self.wait_status('cancelled')
                self.assertIn('saved page', row['log'])
                self.assertIsNotNone(row['finished_at'])
                self.assertIsNotNone(processes[0].poll())
            with patch.object(self.jobs.executor, 'submit'):
                self.jobs.submit({'kind': 'comments'})
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                process.wait()

    def test_stop_releases_only_owned_unfinished_details(self):
        from forum_backend.db import init_db, claim_detail_rows
        conn = init_db(self.jobs.database_path)
        try:
            for tid, status in [('1', 'pending'), ('2', 'pending'), ('3', 'processing')]:
                conn.execute('INSERT INTO threads(tid,title,fid,detail_status) VALUES (?,?,?,?)', (tid, 'test', '95', status))
            conn.commit()
            with patch.object(self.jobs.executor, 'submit'):
                result = self.jobs.submit({'kind': 'details'})
            claim_detail_rows(conn, 10, result['id'])
            conn.execute("UPDATE threads SET detail_status='fetched' WHERE tid='1'")
            conn.commit()
            self.jobs.stop(result['id'])
            self.jobs._run(result['id'], 'details', self.config)
            rows = dict(conn.execute('SELECT tid,detail_status FROM threads').fetchall())
            self.assertEqual(rows, {'1': 'fetched', '2': 'pending', '3': 'processing'})
        finally:
            conn.close()
