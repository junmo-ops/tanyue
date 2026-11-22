import pathlib
import sqlite3
import socket
import tempfile
import unittest
from concurrent.futures import Future
from unittest import mock
from urllib.error import URLError

import hot_forum


SAMPLE_HTML = """
<html>
  <body>
    <table id="threadlisttableid">
      <tbody id="normalthread_101">
        <tr>
          <th class="common">
            <img class="preview" src="data/attachment/forum/202605/21/thumb.jpg">
            <img src="static/image/common/heatlevel.gif" title="热度: 9">
            <a class="s xst" href="forum.php?mod=viewthread&tid=101&extra=page%3D1">First &amp; Topic</a>
          </th>
          <td class="by">
            <cite><a href="home.php?mod=space&uid=1">alice</a></cite>
            <em><span>2026-05-20</span></em>
          </td>
          <td class="num"><a>12</a><em>88</em></td>
        </tr>
      </tbody>
      <tbody id="normalthread_102">
        <tr>
          <th class="common">
            <img src="static/image/common/heatlevel.gif" title="2">
            <a class="s xst" href="https://forum.example.test/forum.php?mod=viewthread&tid=102">Second Topic</a>
          </th>
          <td class="by">
            <cite><a href="home.php?mod=space&uid=2">bob</a></cite>
            <em><span>昨天 12:00</span></em>
          </td>
          <td class="num"><a>3</a><em>20</em></td>
        </tr>
      </tbody>
      <tbody id="normalthread_103">
        <tr>
          <th class="common">
            <img src="static/image/common/heatlevel.gif" title="热度 27">
            <a class="s xst" href="forum.php?mod=viewthread&tid=103">Thread With Pages</a>
            <span class="tps">&nbsp;...<a>2</a><a>3</a><a>4</a><a>5</a></span>
          </th>
          <td class="by">
            <cite><a href="home.php?mod=space&uid=3">poster</a></cite>
            <em><span><span title="2026-05-18">3&nbsp;天前</span></span></em>
          </td>
          <td class="num"><a>42</a><em>17410</em></td>
          <td class="by">
            <cite><a href="home.php?mod=space&username=last">last_reply_user</a></cite>
            <em><a><span title="2026-05-20 00:36">昨天&nbsp;00:36</span></a></em>
          </td>
        </tr>
      </tbody>
    </table>
  </body>
</html>
"""

DETAIL_HTML = """
<html>
  <body>
    <div id="postlist">
      <div id="post_9001">
        <td class="t_f" id="postmessage_9001">
          第一段正文<br>
          第二段正文
          <img src="data/attachment/forum/202605/22/detail.jpg">
        </td>
      </div>
      <div id="post_9002">
        <div class="authi"><a class="xw1" href="home.php?mod=space&uid=9002">commenter</a></div>
        <em id="authorposton9002">发表于 2026-05-22 12:30</em>
        <td class="t_f" id="postmessage_9002">评论内容 A</td>
      </div>
      <div id="post_9003">
        <div class="authi"><a class="xw1" href="home.php?mod=space&uid=9003">second</a></div>
        <em id="authorposton9003">发表于 2026-05-22 12:40</em>
        <td class="t_f" id="postmessage_9003">评论内容 B</td>
      </div>
    </div>
  </body>
</html>
"""

class HotForumTests(unittest.TestCase):
    def test_build_page_url_adds_page_parameter(self):
        url = hot_forum.build_page_url(
            "https://forum.example.test/forum.php?mod=forumdisplay&fid=95",
            3,
        )

        self.assertEqual(
            url,
            "https://forum.example.test/forum.php?mod=forumdisplay&fid=95&page=3",
        )

    def test_build_page_url_keeps_first_page_unchanged(self):
        base = "https://forum.example.test/forum.php?mod=forumdisplay&fid=95"

        self.assertEqual(hot_forum.build_page_url(base, 1), base)

    def test_build_source_url_combines_base_url_and_forum_path(self):
        url = hot_forum.build_source_url(
            "https://new.example.com/",
            "/forum.php?mod=forumdisplay&fid=95",
        )

        self.assertEqual(url, "https://new.example.com/forum.php?mod=forumdisplay&fid=95")

    def test_source_url_from_config_builds_fixed_forum_path_from_fid(self):
        url = hot_forum.source_url_from_config(
            {
                "site": {"base_url": "https://new.example.com/"},
                "list_sync": {"forums": {"97": "技术"}},
            }
        )

        self.assertEqual(
            url,
            "https://new.example.com/forum.php?mod=forumdisplay&fid=97&filter=author&orderby=dateline",
        )

    def test_source_url_from_config_requires_fid(self):
        with self.assertRaisesRegex(ValueError, "板块"):
            hot_forum.source_url_from_config({"list_sync": {"forums": {}}})

    def test_iter_page_urls_starts_from_requested_page(self):
        urls = list(
            hot_forum.iter_page_urls(
                "https://forum.example.test/forum.php?mod=forumdisplay&fid=95",
                start_page=6,
                pages=3,
            )
        )

        self.assertEqual(
            urls,
            [
                "https://forum.example.test/forum.php?mod=forumdisplay&fid=95&page=6",
                "https://forum.example.test/forum.php?mod=forumdisplay&fid=95&page=7",
                "https://forum.example.test/forum.php?mod=forumdisplay&fid=95&page=8",
            ],
        )

    def test_iter_page_urls_rejects_invalid_start_page(self):
        with self.assertRaises(ValueError):
            list(
                hot_forum.iter_page_urls(
                    "https://forum.example.test/forum.php?mod=forumdisplay&fid=95",
                    start_page=0,
                    pages=3,
                )
            )





    def test_parse_topics_extracts_discuz_thread_rows(self):
        topics = hot_forum.parse_topics(
            SAMPLE_HTML,
            "https://new.example.com/forum.php?mod=forumdisplay&fid=95",
        )

        self.assertEqual(len(topics), 3)
        self.assertEqual(topics[0].title, "First & Topic")
        self.assertEqual(
            topics[0].url,
            "https://new.example.com/forum.php?mod=viewthread&tid=101&extra=page%3D1",
        )
        self.assertEqual(topics[0].author, "alice")
        self.assertEqual(topics[0].author_id, "1")
        self.assertEqual(topics[0].posted_at, "2026-05-20")
        self.assertEqual(topics[0].replies, 12)
        self.assertEqual(topics[0].views, 88)
        self.assertEqual(topics[0].heatlevel, 9)
        self.assertEqual(
            topics[0].preview_url,
            "https://new.example.com/data/attachment/forum/202605/21/thumb.jpg",
        )

    def test_parse_topics_uses_first_by_cell_for_author_and_post_time(self):
        topics = hot_forum.parse_topics(
            SAMPLE_HTML,
            "https://forum.example.test/forum.php?mod=forumdisplay&fid=95",
        )

        topic = topics[2]
        self.assertEqual(topic.title, "Thread With Pages")
        self.assertEqual(topic.author, "poster")
        self.assertEqual(topic.author_id, "3")
        self.assertEqual(topic.posted_at, "2026-05-18")
        self.assertEqual(topic.views, 17410)
        self.assertEqual(topic.heatlevel, 27)
        self.assertNotEqual(topic.author, "last_reply_user")
        self.assertNotIn("...2345", topic.posted_at)




    def test_load_cookie_prefers_direct_value(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cookie_file = pathlib.Path(temp_dir) / "cookie.txt"
            cookie_file.write_text("from=file", encoding="utf-8")

            cookie = hot_forum.load_cookie("from=argument", str(cookie_file))

        self.assertEqual(cookie, "from=argument")

    def test_load_cookie_reads_cookie_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cookie_file = pathlib.Path(temp_dir) / "cookie.txt"
            cookie_file.write_text("session=abc\n", encoding="utf-8")

            cookie = hot_forum.load_cookie(None, str(cookie_file))

        self.assertEqual(cookie, "session=abc")

    def test_load_cookie_rejects_missing_cookie(self):
        with self.assertRaises(ValueError):
            hot_forum.load_cookie(None, None)

    def test_load_config_reads_json_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = pathlib.Path(temp_dir) / "config.json"
            config_file.write_text(pathlib.Path(hot_forum.DEFAULT_CONFIG).with_name("config.example.json").read_text(), encoding="utf-8")

            config = hot_forum.load_config(str(config_file))

        self.assertEqual(config["list_sync"]["forums"], {})
        self.assertEqual(config["database"]["paths"]["production"], str(config_file.parent.resolve() / "data/forum.db"))

    def test_load_config_missing_file_returns_empty_config(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = pathlib.Path(temp_dir) / "missing.json"

            self.assertEqual(hot_forum.load_config(str(config_file)), {})




    def test_fetch_page_retries_with_backoff(self):
        with mock.patch("forum_backend.crawler.open_forum") as urlopen_mock, mock.patch(
            "forum_backend.crawler.time.sleep"
        ) as sleep_mock, mock.patch("builtins.print"):
            urlopen_mock.side_effect = [
                URLError("temporary"),
                URLError("temporary"),
                mock.MagicMock(
                    __enter__=mock.Mock(
                        return_value=mock.Mock(
                            headers=mock.Mock(get_content_charset=mock.Mock(return_value="utf-8")),
                            read=mock.Mock(return_value=b"<html></html>"),
                        )
                    ),
                    __exit__=mock.Mock(return_value=None),
                ),
            ]

            html = hot_forum.fetch_page(
                "https://example.test/forum",
                "session=abc",
                retries=2,
                retry_backoff_seconds=1.5,
            )

        self.assertEqual(html, "<html></html>")
        self.assertEqual(sleep_mock.call_args_list, [mock.call(1.5), mock.call(3.0)])

    def test_fetch_page_retries_socket_timeout(self):
        with mock.patch("forum_backend.crawler.open_forum") as urlopen_mock, mock.patch(
            "forum_backend.crawler.time.sleep"
        ) as sleep_mock, mock.patch("builtins.print"):
            urlopen_mock.side_effect = [
                socket.timeout("timed out"),
                mock.MagicMock(
                    __enter__=mock.Mock(
                        return_value=mock.Mock(
                            headers=mock.Mock(get_content_charset=mock.Mock(return_value="utf-8")),
                            read=mock.Mock(return_value=b"ok"),
                        )
                    ),
                    __exit__=mock.Mock(return_value=None),
                ),
            ]

            html = hot_forum.fetch_page(
                "https://example.test/forum",
                "session=abc",
                retries=1,
                retry_backoff_seconds=2.0,
            )

        self.assertEqual(html, "ok")
        self.assertEqual(sleep_mock.call_args_list, [mock.call(2.0)])

    def test_init_db_creates_forum_tables(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = pathlib.Path(temp_dir) / "forum.db"
            conn = hot_forum.init_db(str(db_path))
            try:
                table_names = {
                    row[0]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }
            finally:
                conn.close()

        self.assertIn("threads", table_names)
        self.assertIn("comments", table_names)
        self.assertIn("crawl_runs", table_names)

    def test_init_db_threads_schema_uses_domain_fields_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = pathlib.Path(temp_dir) / "forum.db"
            conn = hot_forum.init_db(str(db_path))
            try:
                columns = {
                    row["name"] for row in conn.execute("PRAGMA table_info(threads)")
                }
            finally:
                conn.close()

        self.assertIn("posted_at", columns)
        self.assertIn("fid", columns)
        self.assertIn("author_id", columns)
        self.assertIn("heatlevel", columns)
        self.assertIn("fetch_comments", columns)
        self.assertNotIn("url_path", columns)
        self.assertNotIn("content_text", columns)
        self.assertNotIn("image_urls_json", columns)
        self.assertNotIn("first_seen_at", columns)
        self.assertNotIn("last_seen_at", columns)
        self.assertNotIn("detail_fetched_at", columns)

    def test_init_db_comments_schema_includes_author_id(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = pathlib.Path(temp_dir) / "forum.db"
            conn = hot_forum.init_db(str(db_path))
            try:
                columns = {
                    row["name"] for row in conn.execute("PRAGMA table_info(comments)")
                }
            finally:
                conn.close()

        self.assertIn("author_id", columns)

    def test_init_db_migrates_legacy_threads_schema(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = pathlib.Path(temp_dir) / "forum.db"
            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    """
                    CREATE TABLE threads (
                      tid TEXT PRIMARY KEY,
                      title TEXT NOT NULL,
                      url_path TEXT NOT NULL,
                      author TEXT,
                      posted_at TEXT,
                      reply_count INTEGER NOT NULL DEFAULT 0,
                      view_count INTEGER NOT NULL DEFAULT 0,
                      source_page INTEGER,
                      first_seen_at TEXT NOT NULL,
                      last_seen_at TEXT NOT NULL,
                      detail_status TEXT NOT NULL DEFAULT 'pending',
                      detail_fetched_at TEXT,
                      detail_error TEXT,
                      content_text TEXT,
                      image_urls_json TEXT NOT NULL DEFAULT '[]'
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT INTO threads (
                      tid, title, url_path, author, posted_at, reply_count,
                      view_count, source_page, first_seen_at, last_seen_at,
                      detail_status, detail_fetched_at, content_text
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "101",
                        "Legacy title",
                        "/forum.php?mod=viewthread&tid=101",
                        "alice",
                        "2026-05-20",
                        12,
                        88,
                        6,
                        "2026-05-22 10:00:00",
                        "2026-05-22 11:00:00",
                        "fetched",
                        "2026-05-22 12:00:00",
                        "legacy detail",
                    ),
                )
                conn.commit()
            finally:
                conn.close()

            conn = hot_forum.init_db(str(db_path))
            try:
                columns = {
                    row["name"] for row in conn.execute("PRAGMA table_info(threads)")
                }
                row = conn.execute(
                    "SELECT tid, title, fid, author_id, posted_at, heatlevel, detail_status FROM threads"
                ).fetchone()
            finally:
                conn.close()

        self.assertNotIn("first_seen_at", columns)
        self.assertNotIn("last_seen_at", columns)
        self.assertNotIn("detail_fetched_at", columns)
        self.assertNotIn("url_path", columns)
        self.assertNotIn("content_text", columns)
        self.assertNotIn("image_urls_json", columns)
        self.assertEqual(row["tid"], "101")
        self.assertEqual(row["posted_at"], "2026-05-20")
        self.assertEqual(row["fid"], "")
        self.assertEqual(row["author_id"], "")
        self.assertEqual(row["heatlevel"], 0)
        self.assertEqual(row["detail_status"], "fetched")

    def test_upsert_thread_inserts_and_updates_without_losing_detail(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = pathlib.Path(temp_dir) / "forum.db"
            conn = hot_forum.init_db(str(db_path))
            try:
                first = hot_forum.Topic(
                    title="First title",
                    url="https://example.test/forum.php?mod=viewthread&tid=101&extra=page%3D1",
                    author="alice",
                    author_id="1",
                    posted_at="2026-05-20",
                    replies=12,
                    views=88,
                )
                hot_forum.upsert_thread(
                    conn,
                    first,
                    source_page=3,
                    seen_at="2026-05-22 10:00:00",
                    forum_name="示例讨论板块",
                    fid="95",
                )
                conn.execute(
                    "UPDATE threads SET detail_status = ? WHERE tid = ?",
                    ("fetched", "101"),
                )
                second = hot_forum.Topic(
                    title="Updated title",
                    url="https://example.test/forum.php?mod=viewthread&tid=101&extra=page%3D2",
                    author="alice",
                    author_id="1",
                    posted_at="2026-05-20",
                    replies=19,
                    views=120,
                )
                hot_forum.upsert_thread(
                    conn,
                    second,
                    source_page=4,
                    seen_at="2026-05-22 11:00:00",
                    forum_name="示例讨论板块",
                    fid="95",
                )
                row = conn.execute(
                    """
                    SELECT tid, title, fid, forum_name, author_id, reply_count, view_count,
                           heatlevel, source_page, detail_status
                    FROM threads WHERE tid = ?
                    """,
                    ("101",),
                ).fetchone()
            finally:
                conn.close()

        self.assertEqual(row["tid"], "101")
        self.assertEqual(row["title"], "Updated title")
        self.assertEqual(row["fid"], "95")
        self.assertEqual(row["forum_name"], "示例讨论板块")
        self.assertEqual(row["author_id"], "1")
        self.assertEqual(row["reply_count"], 19)
        self.assertEqual(row["view_count"], 120)
        self.assertEqual(row["heatlevel"], 0)
        self.assertEqual(row["source_page"], 4)
        self.assertEqual(row["detail_status"], "fetched")

    def test_upsert_comment_inserts_and_updates_by_tid_and_comment_id(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = pathlib.Path(temp_dir) / "forum.db"
            conn = hot_forum.init_db(str(db_path))
            try:
                hot_forum.upsert_comment(
                    conn,
                    {
                        "tid": "101",
                        "comment_id": "101-1-1",
                        "author": "bob",
                        "author_id": "9",
                        "posted_at": "2026-05-21",
                        "content_text": "first",
                        "source_page": 1,
                        "fetched_at": "2026-05-22 10:00:00",
                    },
                )
                hot_forum.upsert_comment(
                    conn,
                    {
                        "tid": "101",
                        "comment_id": "101-1-1",
                        "author": "bob",
                        "author_id": "10",
                        "posted_at": "2026-05-21",
                        "content_text": "updated",
                        "source_page": 1,
                        "fetched_at": "2026-05-22 11:00:00",
                    },
                )
                rows = conn.execute(
                    "SELECT author_id, content_text, fetched_at FROM comments WHERE tid = ?",
                    ("101",),
                ).fetchall()
            finally:
                conn.close()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["author_id"], "10")
        self.assertEqual(rows[0]["content_text"], "updated")
        self.assertEqual(rows[0]["fetched_at"], "2026-05-22 11:00:00")

    def test_crawl_list_to_db_fetches_pages_and_stores_threads(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = pathlib.Path(temp_dir) / "forum.db"
            config = {
                'site': {'base_url': 'https://example.test', 'cookie_file': 'cookie.txt'},
                'database': {'environment': 'test', 'paths': {'test': str(db_path)}},
                'network': {'delay_seconds': 0, 'jitter_seconds': 0, 'retries': 0, 'retry_backoff_seconds': 0},
                'list_sync': {'forums': {'95': 'General'}, 'workers': 1},
                'details': {'limit': 10, 'workers': 1},
                'comments': {'pages': 'all', 'page_workers': 1},
                '_manual_list': {'pages': 2, 'start_page': 6}
            }

            with mock.patch("forum_backend.crawler.load_cookie", return_value="session=abc"), mock.patch(
                "forum_backend.crawler.fetch_page", return_value=SAMPLE_HTML
            ), mock.patch("builtins.print"):
                result = hot_forum.crawl_list_to_db(config)

            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                rows = conn.execute(
                    "SELECT tid, title, fid, forum_name, author_id, source_page, reply_count, heatlevel FROM threads ORDER BY tid"
                ).fetchall()
            finally:
                conn.close()

        self.assertEqual(result["success_count"], 6)
        self.assertEqual({row["fid"] for row in rows}, {"95"})
        self.assertEqual({row["source_page"] for row in rows}, {7})
        self.assertEqual({row["author_id"] for row in rows}, {"1", "2", "3"})
        self.assertEqual({row["forum_name"] for row in rows}, {""})
        self.assertEqual({row["tid"] for row in rows}, {"101", "102", "103"})
        self.assertEqual({row["reply_count"] for row in rows}, {3, 12, 42})
        self.assertEqual({row["heatlevel"] for row in rows}, {2, 9, 27})

    def test_crawl_list_to_db_uses_list_workers(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = pathlib.Path(temp_dir) / "forum.db"
            config = {
                'site': {'base_url': 'https://example.test', 'cookie_file': 'cookie.txt'},
                'database': {'environment': 'test', 'paths': {'test': str(db_path)}},
                'network': {'delay_seconds': 0, 'jitter_seconds': 0, 'retries': 0, 'retry_backoff_seconds': 0},
                'list_sync': {'forums': {'95': 'General'}, 'workers': 2},
                'details': {'limit': 10, 'workers': 1},
                'comments': {'pages': 'all', 'page_workers': 1},
                '_manual_list': {'pages': 3, 'start_page': 1}
            }

            max_workers_seen = []

            class InlineExecutor:
                def __init__(self, max_workers):
                    max_workers_seen.append(max_workers)

                def __enter__(self):
                    return self

                def __exit__(self, *_args):
                    return False

                def submit(self, func, row):
                    future = Future()
                    future.set_result(func(row))
                    return future

            with mock.patch("forum_backend.crawler.load_cookie", return_value="session=abc"), mock.patch(
                "forum_backend.crawler.fetch_page", return_value=SAMPLE_HTML
            ), mock.patch("forum_backend.crawler.ThreadPoolExecutor", InlineExecutor), mock.patch("builtins.print"):
                result = hot_forum.crawl_list_to_db(config)

        self.assertEqual(result["success_count"], 9)
        self.assertEqual(max_workers_seen, [2])

    def test_crawl_list_to_db_commits_fixed_pages_in_page_order(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = pathlib.Path(temp_dir) / "forum.db"
            config = {
                'site': {'base_url': 'https://example.test', 'cookie_file': 'cookie.txt'},
                'database': {'environment': 'test', 'paths': {'test': str(db_path)}},
                'network': {'delay_seconds': 0, 'jitter_seconds': 0, 'retries': 0, 'retry_backoff_seconds': 0},
                'list_sync': {'forums': {'95': 'General'}, 'workers': 2},
                'details': {'limit': 10, 'workers': 1},
                'comments': {'pages': 'all', 'page_workers': 1},
                '_manual_list': {'pages': 2, 'start_page': 1}
            }
            submitted = []

            class ObservedExecutor:
                def __init__(self, max_workers):
                    self.max_workers = max_workers

                def __enter__(self):
                    return self

                def __exit__(self, *_args):
                    return False

                def submit(self, func, page_info):
                    future = Future()
                    future.set_result(func(page_info))
                    submitted.append(future)
                    return future

            def observed_as_completed(futures):
                yield from reversed(list(futures))

            with mock.patch("forum_backend.crawler.load_cookie", return_value="session=abc"), mock.patch(
                "forum_backend.crawler.fetch_page", return_value=SAMPLE_HTML
            ), mock.patch("forum_backend.crawler.ThreadPoolExecutor", ObservedExecutor), mock.patch(
                "forum_backend.crawler.as_completed", side_effect=observed_as_completed
            ), mock.patch("builtins.print"):
                result = hot_forum.crawl_list_to_db(config)

            with sqlite3.connect(db_path) as conn:
                pages = conn.execute("SELECT DISTINCT source_page FROM threads").fetchall()
        self.assertEqual(result["success_count"], 6)
        self.assertEqual(len(submitted), 2)
        self.assertEqual(pages, [(2,)])

    def test_main_dispatches_crawl_list_command(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = pathlib.Path(temp_dir) / "config.json"
            config_file.write_text(pathlib.Path(hot_forum.DEFAULT_CONFIG).with_name("config.example.json").read_text(), encoding="utf-8")

            with mock.patch("forum_backend.crawler.crawl_list_to_db") as crawl_mock:
                crawl_mock.return_value = {"success_count": 3, "failure_count": 0}
                status = hot_forum.main(["crawl-list", "--config", str(config_file)])

        self.assertEqual(status, 0)
        crawl_mock.assert_called_once()

    def test_parse_detail_page_extracts_main_text_images_and_comments(self):
        detail = hot_forum.parse_detail_page(
            DETAIL_HTML,
            "https://example.test/forum.php?mod=viewthread&tid=101",
            tid="101",
            comment_page=1,
            fetched_at="2026-05-22 13:00:00",
        )

        self.assertIn("第一段正文", detail["content_text"])
        self.assertIn("第二段正文", detail["content_text"])
        self.assertEqual(
            detail["image_urls"],
            ["https://example.test/data/attachment/forum/202605/22/detail.jpg"],
        )
        self.assertEqual(len(detail["comments"]), 2)
        self.assertEqual(detail["comments"][0]["comment_id"], "9002")
        self.assertEqual(detail["comments"][0]["author"], "commenter")
        self.assertEqual(detail["comments"][0]["author_id"], "9002")
        self.assertEqual(detail["comments"][0]["posted_at"], "2026-05-22 12:30")
        self.assertEqual(detail["comments"][0]["content_text"], "评论内容 A")

    def test_parse_detail_page_extracts_post_metrics(self):
        html_text = """
<html><body>
  <div id="postlist">
    <td class="t_f" id="postmessage_9001">Body text</td>
    <div class="postact">参与人数 12 金钱 +88 评分 +6</div>
  </div>
</body></html>
"""

        detail = hot_forum.parse_detail_page(
            html_text,
            "https://example.test/forum.php?mod=viewthread&tid=101",
            tid="101",
            comment_page=1,
            fetched_at="2026-05-22 13:00:00",
        )

        self.assertEqual(detail["participant_count"], 12)
        self.assertEqual(detail["money"], 88)
        self.assertEqual(detail["rating"], "6")

    def test_parse_detail_page_treats_first_postmessage_as_main_content(self):
        html_text = """
<html><body>
  <div id="postlist">
    <td class="t_f" id="postmessage_64520795">
      <font>主楼正文</font><br />
      <font>第二行</font><br />
      <img src="static/image/common/none.gif" file="https://img.example.test/main.jpg" zoomfile="https://img.example.test/main.jpg" />
    </td>
    <div class="authi"><a class="xw1">commenter</a></div>
    <em id="authorposton64543623">发表于 2026-05-22 12:30</em>
    <td class="t_f" id="postmessage_64543623">评论正文</td>
  </div>
</body></html>
"""

        detail = hot_forum.parse_detail_page(
            html_text,
            "https://example.test/forum.php?mod=viewthread&tid=101",
            tid="101",
            comment_page=1,
            fetched_at="2026-05-22 13:00:00",
        )

        self.assertIn("主楼正文", detail["content_text"])
        self.assertIn("第二行", detail["content_text"])
        self.assertEqual(detail["image_urls"], ["https://img.example.test/main.jpg"])
        self.assertEqual(len(detail["comments"]), 1)
        self.assertEqual(detail["comments"][0]["content_text"], "评论正文")

    def test_detect_detail_comment_page_count_reads_discuz_page_links(self):
        html_text = """
<html><body>
  <div class="pg">
    <a href="forum.php?mod=viewthread&tid=101&page=2">2</a>
    <a href="forum.php?mod=viewthread&tid=101&page=8">8</a>
    <a href="forum.php?mod=viewthread&tid=102&page=99">other</a>
  </div>
</body></html>
"""

        self.assertEqual(hot_forum.detect_detail_comment_page_count(html_text, "101"), 8)

    def test_parse_topics_extracts_heatlevel_from_title_even_without_heatlevel_filename(self):
        html_text = """
<html><body>
  <table id="threadlisttableid">
    <tbody id="normalthread_201">
      <tr>
        <th class="common">
          <img src="static/image/common/hot_3.gif" title="热度 31">
          <a class="s xst" href="forum.php?mod=viewthread&tid=201">Hot Topic</a>
        </th>
        <td class="by"><cite><a>alice</a></cite><em><span title="2026-05-22 12:00">刚刚</span></em></td>
        <td class="num"><a>1</a><em>2</em></td>
      </tr>
    </tbody>
  </table>
</body></html>
"""

        topics = hot_forum.parse_topics(
            html_text,
            "https://example.test/forum.php?mod=forumdisplay&fid=95",
        )

        self.assertEqual(topics[0].heatlevel, 31)

    def test_crawl_details_to_db_fetches_pending_thread_metrics_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = pathlib.Path(temp_dir) / "forum.db"
            conn = hot_forum.init_db(str(db_path))
            try:
                hot_forum.upsert_thread(
                    conn,
                    hot_forum.Topic(
                        title="Needs detail",
                        url="https://example.test/forum.php?mod=viewthread&tid=101",
                        author="alice",
                        posted_at="2026-05-20",
                        replies=2,
                    ),
                    source_page=6,
                    seen_at="2026-05-22 10:00:00",
                )
            finally:
                conn.close()

            config = {
                'site': {'base_url': 'https://example.test', 'cookie_file': 'cookie.txt'},
                'database': {'environment': 'test', 'paths': {'test': str(db_path)}},
                'network': {'delay_seconds': 0, 'jitter_seconds': 0, 'retries': 0, 'retry_backoff_seconds': 0},
                'list_sync': {'forums': {'95': 'General'}, 'workers': 1},
                'details': {'limit': 1, 'workers': 1},
                'comments': {'pages': 'all', 'page_workers': 1}
            }

            with mock.patch("forum_backend.crawler.load_cookie", return_value="session=abc"), mock.patch(
                "forum_backend.crawler.fetch_page", return_value=DETAIL_HTML
            ), mock.patch("builtins.print"):
                result = hot_forum.crawl_details_to_db(config)

            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                thread = conn.execute(
                    """
                    SELECT detail_status, participant_count, money, rating
                    FROM threads WHERE tid = ?
                    """,
                    ("101",),
                ).fetchone()
                comments = conn.execute(
                    "SELECT comment_id, author_id, content_text, source_page FROM comments WHERE tid = ? ORDER BY comment_id",
                    ("101",),
                ).fetchall()
            finally:
                conn.close()

        self.assertEqual(result["success_count"], 1)
        self.assertEqual(thread["detail_status"], "fetched")
        self.assertEqual(thread["participant_count"], 0)
        self.assertEqual(thread["money"], 0)
        self.assertEqual(thread["rating"], "")
        self.assertEqual(len(comments), 0)

    def test_crawl_details_to_db_skips_comments_by_default(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = pathlib.Path(temp_dir) / "forum.db"
            conn = hot_forum.init_db(str(db_path))
            try:
                hot_forum.upsert_thread(
                    conn,
                    hot_forum.Topic(
                        title="No comments by default",
                        url="https://example.test/forum.php?mod=viewthread&tid=101",
                        author="alice",
                        posted_at="2026-05-20",
                        replies=2,
                    ),
                    source_page=6,
                    seen_at="2026-05-22 10:00:00",
                )
            finally:
                conn.close()

            config = {
                'site': {'base_url': 'https://example.test', 'cookie_file': 'cookie.txt'},
                'database': {'environment': 'test', 'paths': {'test': str(db_path)}},
                'network': {'delay_seconds': 0, 'jitter_seconds': 0, 'retries': 0, 'retry_backoff_seconds': 0},
                'list_sync': {'forums': {'95': 'General'}, 'workers': 1},
                'details': {'limit': 1, 'workers': 1},
                'comments': {'pages': 'all', 'page_workers': 1}
            }

            with mock.patch("forum_backend.crawler.load_cookie", return_value="session=abc"), mock.patch(
                "forum_backend.crawler.fetch_page", return_value=DETAIL_HTML
            ) as fetch_mock, mock.patch("builtins.print"):
                result = hot_forum.crawl_details_to_db(config)

            conn = sqlite3.connect(db_path)
            try:
                comment_count = conn.execute(
                    "SELECT COUNT(1) FROM comments WHERE tid = ?",
                    ("101",),
                ).fetchone()[0]
            finally:
                conn.close()

        self.assertEqual(result["success_count"], 1)
        self.assertEqual(comment_count, 0)
        fetch_mock.assert_called_once()

    def test_crawl_details_to_db_never_saves_comments(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = pathlib.Path(temp_dir) / "forum.db"
            conn = hot_forum.init_db(str(db_path))
            try:
                hot_forum.upsert_thread(
                    conn,
                    hot_forum.Topic(
                        title="Details only",
                        url="https://example.test/forum.php?mod=viewthread&tid=101",
                        author="alice",
                        posted_at="2026-05-20",
                        replies=2,
                    ),
                    source_page=6,
                    seen_at="2026-05-22 10:00:00",
                )
            finally:
                conn.close()

            config = {
                'site': {'base_url': 'https://example.test', 'cookie_file': 'cookie.txt'},
                'database': {'environment': 'test', 'paths': {'test': str(db_path)}},
                'network': {'delay_seconds': 0, 'jitter_seconds': 0, 'retries': 0, 'retry_backoff_seconds': 0},
                'list_sync': {'forums': {'95': 'General'}, 'workers': 1},
                'details': {'limit': 1, 'workers': 1},
                'comments': {'pages': 'all', 'page_workers': 1}
            }

            with mock.patch("forum_backend.crawler.load_cookie", return_value="session=abc"), mock.patch(
                "forum_backend.crawler.fetch_page", return_value=DETAIL_HTML
            ) as fetch_mock, mock.patch("builtins.print"):
                result = hot_forum.crawl_details_to_db(config)

            conn = sqlite3.connect(db_path)
            try:
                comment_count = conn.execute(
                    "SELECT COUNT(1) FROM comments WHERE tid = ?",
                    ("101",),
                ).fetchone()[0]
            finally:
                conn.close()

        self.assertEqual(result["success_count"], 1)
        self.assertEqual(comment_count, 0)
        fetch_mock.assert_called_once()

    def test_crawl_comments_to_db_fetches_only_enabled_threads(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = pathlib.Path(temp_dir) / "forum.db"
            conn = hot_forum.init_db(str(db_path))
            try:
                for tid, enabled in [("101", 1), ("102", 0)]:
                    hot_forum.upsert_thread(
                        conn,
                        hot_forum.Topic(
                            title=f"Thread {tid}",
                            url=f"https://example.test/forum.php?mod=viewthread&tid={tid}",
                            author="alice",
                            posted_at=f"2026-05-{tid[-2:]}",
                            replies=2,
                        ),
                        source_page=6,
                        seen_at="2026-05-22 10:00:00",
                    )
                    conn.execute(
                        "UPDATE threads SET fetch_comments = ? WHERE tid = ?",
                        (enabled, tid),
                    )
                conn.commit()
            finally:
                conn.close()

            config = {
                'site': {'base_url': 'https://example.test', 'cookie_file': 'cookie.txt'},
                'database': {'environment': 'test', 'paths': {'test': str(db_path)}},
                'network': {'delay_seconds': 0, 'jitter_seconds': 0, 'retries': 0, 'retry_backoff_seconds': 0},
                'list_sync': {'forums': {'95': 'General'}, 'workers': 1},
                'details': {'limit': 20, 'workers': 1},
                'comments': {'pages': 'all', 'page_workers': 1}
            }

            with mock.patch("forum_backend.crawler.load_cookie", return_value="session=abc"), mock.patch(
                "forum_backend.crawler.fetch_page", return_value=DETAIL_HTML
            ), mock.patch("builtins.print"):
                result = hot_forum.crawl_comments_to_db(config)

            conn = sqlite3.connect(db_path)
            try:
                comment_tids = {
                    row[0] for row in conn.execute("SELECT DISTINCT tid FROM comments")
                }
            finally:
                conn.close()

        self.assertEqual(result["success_count"], 1)
        self.assertEqual(comment_tids, {"101"})

    def test_crawl_comments_to_db_defaults_to_all_detected_comment_pages(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = pathlib.Path(temp_dir) / "forum.db"
            conn = hot_forum.init_db(str(db_path))
            try:
                hot_forum.upsert_thread(
                    conn,
                    hot_forum.Topic(
                        title="Thread 101",
                        url="https://example.test/forum.php?mod=viewthread&tid=101",
                        author="alice",
                        posted_at="2026-05-20",
                        replies=2,
                    ),
                    source_page=6,
                    seen_at="2026-05-22 10:00:00",
                )
                conn.execute("UPDATE threads SET fetch_comments = 1 WHERE tid = ?", ("101",))
                conn.commit()
            finally:
                conn.close()

            config = {
                'site': {'base_url': 'https://example.test', 'cookie_file': 'cookie.txt'},
                'database': {'environment': 'test', 'paths': {'test': str(db_path)}},
                'network': {'delay_seconds': 0, 'jitter_seconds': 0, 'retries': 0, 'retry_backoff_seconds': 0},
                'list_sync': {'forums': {'95': 'General'}, 'workers': 1},
                'details': {'limit': 10, 'workers': 1},
                'comments': {'pages': 'all', 'page_workers': 1}
            }
            fetched_urls = []

            def fake_fetch(url, *_args, **_kwargs):
                fetched_urls.append(url)
                return DETAIL_HTML + """
                    <div class="pg">
                      <a href="forum.php?mod=viewthread&tid=101&page=2">2</a>
                      <a href="forum.php?mod=viewthread&tid=101&page=4">4</a>
                    </div>
                """

            with mock.patch("forum_backend.crawler.load_cookie", return_value="session=abc"), mock.patch(
                "forum_backend.crawler.fetch_page", side_effect=fake_fetch
            ), mock.patch("builtins.print"):
                result = hot_forum.crawl_comments_to_db(config)

        self.assertEqual(result["success_count"], 1)
        self.assertEqual(len(fetched_urls), 4)
        self.assertTrue(fetched_urls[0].endswith("tid=101"))
        self.assertIn("page=4", fetched_urls[-1])

    def test_fetch_thread_comments_reports_page_progress(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = pathlib.Path(temp_dir) / "forum.db"
            conn = hot_forum.init_db(str(db_path))
            try:
                hot_forum.upsert_thread(
                    conn,
                    hot_forum.Topic(
                        title="Thread 101",
                        url="https://example.test/forum.php?mod=viewthread&tid=101",
                        author="alice",
                        posted_at="2026-05-20",
                        replies=2,
                    ),
                    source_page=6,
                    seen_at="2026-05-22 10:00:00",
                )
                row = conn.execute("SELECT tid FROM threads WHERE tid = ?", ("101",)).fetchone()
            finally:
                conn.close()

            def fake_fetch(url, *_args, **_kwargs):
                suffix = "" if "page=" not in url else f" {url.rsplit('page=', 1)[1]}"
                return DETAIL_HTML + f"""
                    <div class="pg">
                      <a href="forum.php?mod=viewthread&tid=101&page=2">2</a>
                      <a href="forum.php?mod=viewthread&tid=101&page=3">3</a>
                    </div>
                    <div id="post_page_marker">{suffix}</div>
                """

            events = []

            with mock.patch("forum_backend.crawler.fetch_page", side_effect=fake_fetch), mock.patch("builtins.print"):
                result = hot_forum.fetch_thread_comments(
                    row,
                    thread_index=1,
                    total_threads=1,
                    base_url="https://example.test",
                    cookie="session=abc",
                    comment_pages="all",
                    comment_page_workers=1,
                    database_path=str(db_path),
                    settings={
                        "delay_seconds": 0,
                        "jitter_seconds": 0,
                        "retries": 0,
                        "retry_backoff_seconds": 0,
                    },
                    progress_callback=events.append,
                )

        self.assertEqual(result["status"], "fetched")
        self.assertEqual(events[0]["status"], "running")
        self.assertEqual(events[0]["completed_pages"], 0)
        self.assertEqual(events[1]["completed_pages"], 1)
        self.assertEqual(events[1]["total_pages"], 3)
        self.assertEqual(events[-1]["status"], "fetched")
        self.assertEqual(events[-1]["completed_pages"], 3)
        self.assertEqual(events[-1]["total_pages"], 3)

    def test_crawl_comments_to_db_uses_detail_workers(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = pathlib.Path(temp_dir) / "forum.db"
            conn = hot_forum.init_db(str(db_path))
            try:
                for tid in ["101", "102", "103"]:
                    hot_forum.upsert_thread(
                        conn,
                        hot_forum.Topic(
                            title=f"Thread {tid}",
                            url=f"https://example.test/forum.php?mod=viewthread&tid={tid}",
                            author="alice",
                            posted_at=f"2026-05-{tid[-2:]}",
                            replies=2,
                        ),
                        source_page=6,
                        seen_at="2026-05-22 10:00:00",
                    )
                    conn.execute("UPDATE threads SET fetch_comments = 1 WHERE tid = ?", (tid,))
                conn.commit()
            finally:
                conn.close()

            config = {
                'site': {'base_url': 'https://example.test', 'cookie_file': 'cookie.txt'},
                'database': {'environment': 'test', 'paths': {'test': str(db_path)}},
                'network': {'delay_seconds': 0, 'jitter_seconds': 0, 'retries': 0, 'retry_backoff_seconds': 0},
                'list_sync': {'forums': {'95': 'General'}, 'workers': 1},
                'details': {'limit': 3, 'workers': 2},
                'comments': {'pages': 'all', 'page_workers': 1}
            }
            max_workers_seen = []

            class InlineExecutor:
                def __init__(self, max_workers):
                    max_workers_seen.append(max_workers)

                def __enter__(self):
                    return self

                def __exit__(self, *_args):
                    return False

                def map(self, func, rows):
                    return [func(row) for row in rows]

            with mock.patch("forum_backend.crawler.load_cookie", return_value="session=abc"), mock.patch(
                "forum_backend.crawler.fetch_page", return_value=DETAIL_HTML
            ), mock.patch("forum_backend.crawler.ThreadPoolExecutor", InlineExecutor), mock.patch("builtins.print"):
                result = hot_forum.crawl_comments_to_db(config)

        self.assertEqual(result["success_count"], 3)
        self.assertEqual(max_workers_seen, [2])

    def test_crawl_details_to_db_can_fetch_manual_tids(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = pathlib.Path(temp_dir) / "forum.db"
            conn = hot_forum.init_db(str(db_path))
            try:
                for tid, status in [("101", "pending"), ("102", "fetched"), ("103", "pending")]:
                    hot_forum.upsert_thread(
                        conn,
                        hot_forum.Topic(
                            title=f"Thread {tid}",
                            url=f"https://example.test/forum.php?mod=viewthread&tid={tid}",
                            author="alice",
                            posted_at=f"2026-05-{tid[-2:]}",
                            replies=2,
                        ),
                        source_page=6,
                        seen_at="2026-05-22 10:00:00",
                    )
                    conn.execute(
                        "UPDATE threads SET detail_status = ? WHERE tid = ?",
                        (status, tid),
                    )
                conn.commit()
            finally:
                conn.close()

            config = {
                'site': {'base_url': 'https://example.test', 'cookie_file': 'cookie.txt'},
                'database': {'environment': 'test', 'paths': {'test': str(db_path)}},
                'network': {'delay_seconds': 0, 'jitter_seconds': 0, 'retries': 0, 'retry_backoff_seconds': 0},
                'list_sync': {'forums': {'95': 'General'}, 'workers': 1},
                'details': {'limit': 10, 'workers': 1},
                'comments': {'pages': 'all', 'page_workers': 1},
                '_detail_tids': ['102']
            }

            fetched_urls = []

            def fake_fetch(url, *_args, **_kwargs):
                fetched_urls.append(url)
                return DETAIL_HTML

            with mock.patch("forum_backend.crawler.load_cookie", return_value="session=abc"), mock.patch(
                "forum_backend.crawler.fetch_page", side_effect=fake_fetch
            ), mock.patch("builtins.print"):
                result = hot_forum.crawl_details_to_db(config)

            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                rows = conn.execute(
                    "SELECT tid, detail_status FROM threads ORDER BY tid"
                ).fetchall()
            finally:
                conn.close()

        self.assertEqual(result["success_count"], 1)
        self.assertEqual([row["detail_status"] for row in rows], ["pending", "fetched", "pending"])
        self.assertEqual(len(fetched_urls), 1)
        self.assertIn("tid=102", fetched_urls[0])

    def test_crawl_details_to_db_uses_detail_workers(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = pathlib.Path(temp_dir) / "forum.db"
            conn = hot_forum.init_db(str(db_path))
            try:
                for tid in ["101", "102", "103"]:
                    hot_forum.upsert_thread(
                        conn,
                        hot_forum.Topic(
                            title=f"Thread {tid}",
                            url=f"https://example.test/forum.php?mod=viewthread&tid={tid}",
                            author="alice",
                            posted_at=f"2026-05-{tid[-2:]}",
                            replies=2,
                        ),
                        source_page=6,
                        seen_at="2026-05-22 10:00:00",
                    )
            finally:
                conn.close()

            config = {
                'site': {'base_url': 'https://example.test', 'cookie_file': 'cookie.txt'},
                'database': {'environment': 'test', 'paths': {'test': str(db_path)}},
                'network': {'delay_seconds': 0, 'jitter_seconds': 0, 'retries': 0, 'retry_backoff_seconds': 0},
                'list_sync': {'forums': {'95': 'General'}, 'workers': 1},
                'details': {'limit': 3, 'workers': 2},
                'comments': {'pages': 'all', 'page_workers': 1}
            }

            max_workers_seen = []

            class InlineExecutor:
                def __init__(self, max_workers):
                    max_workers_seen.append(max_workers)

                def __enter__(self):
                    return self

                def __exit__(self, *_args):
                    return False

                def submit(self, func, row):
                    future = Future()
                    future.set_result(func(row))
                    return future

            with mock.patch("forum_backend.crawler.load_cookie", return_value="session=abc"), mock.patch(
                "forum_backend.crawler.fetch_page", return_value=DETAIL_HTML
            ), mock.patch("forum_backend.crawler.ThreadPoolExecutor", InlineExecutor), mock.patch("builtins.print"):
                result = hot_forum.crawl_details_to_db(config)

        self.assertEqual(result["success_count"], 3)
        self.assertEqual(max_workers_seen, [2])

    def test_claim_detail_rows_marks_pending_rows_as_processing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = pathlib.Path(temp_dir) / "forum.db"
            conn = hot_forum.init_db(str(db_path))
            try:
                for tid, status in [("101", "pending"), ("102", "failed"), ("103", "pending")]:
                    hot_forum.upsert_thread(
                        conn,
                        hot_forum.Topic(
                            title=f"Thread {tid}",
                            url=f"https://example.test/forum.php?mod=viewthread&tid={tid}",
                            author="alice",
                            posted_at=f"2026-05-{tid[-2:]}",
                            replies=2,
                        ),
                        source_page=6,
                        seen_at="2026-05-22 10:00:00",
                    )
                    conn.execute(
                        "UPDATE threads SET detail_status = ? WHERE tid = ?",
                        (status, tid),
                    )
                conn.commit()

                first_claim = hot_forum.claim_detail_rows(conn, limit=2)
                second_claim = hot_forum.claim_detail_rows(conn, limit=2)
                statuses = {
                    row["tid"]: row["detail_status"]
                    for row in conn.execute("SELECT tid, detail_status FROM threads")
                }
            finally:
                conn.close()

        self.assertEqual([row["tid"] for row in first_claim], ["103", "102"])
        self.assertEqual([row["tid"] for row in second_claim], ["101"])
        self.assertEqual(statuses["103"], "processing")
        self.assertEqual(statuses["102"], "processing")
        self.assertEqual(statuses["101"], "processing")

    def test_main_dispatches_crawl_details_command(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = pathlib.Path(temp_dir) / "config.json"
            config_file.write_text(pathlib.Path(hot_forum.DEFAULT_CONFIG).with_name("config.example.json").read_text(), encoding="utf-8")

            with mock.patch("forum_backend.crawler.crawl_details_to_db") as crawl_mock, mock.patch(
                "builtins.print"
            ):
                crawl_mock.return_value = {"success_count": 1, "failure_count": 0}
                status = hot_forum.main(["crawl-details", "--config", str(config_file)])

        self.assertEqual(status, 0)
        crawl_mock.assert_called_once()

    def test_main_passes_manual_tids_to_crawl_details(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = pathlib.Path(temp_dir) / "config.json"
            config_file.write_text(pathlib.Path(hot_forum.DEFAULT_CONFIG).with_name("config.example.json").read_text(), encoding="utf-8")

            with mock.patch("forum_backend.crawler.crawl_details_to_db") as crawl_mock, mock.patch(
                "builtins.print"
            ):
                crawl_mock.return_value = {"success_count": 1, "failure_count": 0}
                status = hot_forum.main([
                    "crawl-details",
                    "--config",
                    str(config_file),
                    "--tid",
                    "101,102",
                    "--tid",
                    "103",
                ])

        self.assertEqual(status, 0)
        self.assertEqual(crawl_mock.call_args.args[0]["_detail_tids"], ["101", "102", "103"])





if __name__ == "__main__":
    unittest.main()
