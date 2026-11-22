from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from forum_backend.api.server import ForumRequestHandler

from forum_backend.config import load_config, site_cookie
from forum_backend.db import init_db, upsert_thread
from forum_backend.parsers import parse_topics
from forum_backend.services.crawl_store import database
from forum_backend.services.managed_crawler import ManagedCrawler
from forum_backend.services.sites import SiteRegistry, discover, probe


INDEX = '<a href="forum-97-1.html"><b>技术交流</b></a>'
LIST = '<tbody id="normalthread_42"><tr><th><a class="xst" href="thread-42-1-1.html">新站帖子</a></th></tr></tbody>'
DETAIL = '<div id="post_12"><td id="postmessage_12">主楼</td></div><div id="post_13"><td id="postmessage_13">回复</td></div>'
BODY = {'url': 'https://example.test/bbs/forum.php', 'name': '测试论坛', 'forums': {'97': '技术交流'}}


class MultiSiteTests(unittest.TestCase):
    def test_discovery_and_sample(self):
        def fetch(url, cookie, **options):
            self.assertTrue(url.startswith('https://example.test/bbs/'))
            self.assertEqual(cookie, '')
            if 'forumdisplay' in url:
                return LIST
            if 'viewthread' in url:
                return DETAIL
            if 'ranklist' in url:
                return '<p>需要登录</p>'
            return INDEX

        with patch('forum_backend.services.sites.fetch_page', side_effect=fetch):
            self.assertEqual(discover(BODY)['forums'], BODY['forums'])
            result = probe({**BODY, 'fid': '97'})
            self.assertEqual((result['count'], result['title'], result['detail'], result['comments'], result['rankings']),
                             (1, '新站帖子', True, 1, False))
        with patch('forum_backend.services.sites.fetch_page', return_value='<p>请登录</p>'):
            with self.assertRaisesRegex(ValueError, '登录'):
                discover(BODY)
            with self.assertRaisesRegex(ValueError, '登录'):
                probe({**BODY, 'fid': '97'})

    def request(self, registry, site_id=None):
        request = Mock()
        header = f'X-Forum-Site: {site_id}\r\n' if site_id else ''
        request.makefile.return_value = BytesIO(f'GET /api/forums HTTP/1.0\r\n{header}\r\n'.encode())
        chunks = []
        request.sendall.side_effect = chunks.append
        with patch.object(ForumRequestHandler, 'log_message'):
            ForumRequestHandler(request, ('127.0.0.1', 0), SimpleNamespace(sites=registry))
        headers, body = b''.join(chunks).split(b'\r\n\r\n', 1)
        return int(headers.split()[1]), json.loads(body)

    def test_site_scoped_sync_and_restart(self):
        with TemporaryDirectory() as root:
            path = str(Path(root) / 'default.db')
            config = load_config()
            config['list_sync']['forums'] = {'97': '默认板块'}
            config['_cookie'] = 'default-only'
            config['network']['delay_seconds'] = config['network']['jitter_seconds'] = 0
            default = SimpleNamespace(database_path=path, base_url='https://original.test/', environment='test', config=config)
            with init_db(path) as conn:
                topic = parse_topics(LIST.replace('新站帖子', '原站帖子'), default.base_url)[0]
                upsert_thread(conn, topic, 1, 'now', fid='97')
            conn.close()
            registry = SiteRegistry(default)
            try:
                record = registry.add(BODY)
                site = registry.runtimes[record['id']]
                self.assertEqual(site_cookie(site.config), '')
                self.assertNotIn('_cookie', site.config)
                self.assertEqual(site.config['list_sync']['forums'], BODY['forums'])
                status, result = self.request(registry, record['id'])
                self.assertEqual(status, 200)
                self.assertEqual(result['items'], [{'fid': '97', 'forum_name': '技术交流', 'thread_count': 0}])
                self.assertEqual(self.request(registry, 'unknown')[0], 404)
                self.assertEqual(self.request(registry)[0], 200)
                with self.assertRaisesRegex(ValueError, '已接入'):
                    registry.add(BODY)
                job = {'kind': 'sync', 'pages': 1}
                with patch.object(site.crawl_jobs.executor, 'submit'):
                    key = site.crawl_jobs.submit(job)['id']
                    worker = ManagedCrawler(site.crawl_jobs.prepare(job)[1], key, site.database_path)
                    with patch('forum_backend.crawler.fetch_page', return_value=LIST):
                        self.assertEqual(worker.run('sync')['success_count'], 1)
                with database(path) as conn:
                    self.assertEqual(conn.execute("SELECT title FROM threads WHERE tid='42'").fetchone()[0], '原站帖子')
            finally:
                registry.close()
            registry = SiteRegistry(default)
            try:
                site = registry.runtimes[record['id']]
                with database(site.database_path) as conn:
                    self.assertEqual(conn.execute("SELECT title FROM threads WHERE tid='42'").fetchone()[0], '新站帖子')
            finally:
                registry.close()
