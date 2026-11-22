import pathlib
import sqlite3
import tempfile
import unittest
from unittest import mock

import forum_api


def create_test_db(path: pathlib.Path) -> None:
    conn = forum_api.init_db(str(path))
    try:
        rows = [
            ("101", "95", "Alpha keyword 完美 笔记", "General", "alice", "1", "2026-05-22", 20, 300, 4, 1, "pending", None, 0, 0, "", 0),
            ("102", "95", "Beta topic 教程", "General", "bob", "2", "2026-05-21", 5, 900, 2, 2, "fetched", None, 8, 10, "6", 1),
            ("103", "96", "Gamma keyword 完美", "Other", "alice", "1", "2026-05-20", 40, 100, 9, 3, "pending", None, 0, 0, "", 0),
            ("105", "95", "Alpha fresh match 笔记", "General", "dave", "4", "2026-05-23", 2, 50, 0, 5, "pending", None, 0, 0, "", 0),
        ]
        conn.executemany(
            """
            INSERT INTO threads (
              tid, fid, title, forum_name, author, author_id, posted_at,
              reply_count, view_count, heatlevel, source_page, detail_status,
              detail_error, participant_count, money, rating, fetch_comments
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.executemany(
            """
            INSERT INTO comments (
              tid, comment_id, author, author_id, posted_at, content_text, source_page, fetched_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("102", "c1", "amy", "11", "2026-05-21 10:00", "First comment", 1, "2026-05-24 10:00"),
                ("102", "c2", "bob", "12", "2026-05-21 10:05", "Second comment", 1, "2026-05-24 10:00"),
            ],
        )
        conn.commit()
    finally:
        conn.close()


def feedback_table_exists(path: pathlib.Path) -> bool:
    conn = sqlite3.connect(path)
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'thread_feedback'"
        ).fetchone()
        return row is not None
    finally:
        conn.close()


class ForumApiTests(unittest.TestCase):
    def test_query_threads_defaults_to_reply_count_desc(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = pathlib.Path(temp_dir) / "forum.db"
            create_test_db(db_path)

            result = forum_api.query_threads(
                str(db_path),
                base_url="https://example.test",
                params={},
            )

        self.assertEqual(result["page"], 1)
        self.assertEqual(result["page_size"], 50)
        self.assertEqual(result["total"], 4)
        self.assertEqual([item["tid"] for item in result["items"]], ["103", "101", "102", "105"])
        self.assertEqual(
            result["items"][0]["official_url"],
            "https://example.test/forum.php?mod=viewthread&tid=103",
        )
        self.assertIsNone(result["items"][0]["feedback"])
        self.assertEqual(result["items"][2]["fetch_comments"], 1)

    def test_query_threads_requires_all_positive_keywords(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = pathlib.Path(temp_dir) / "forum.db"
            create_test_db(db_path)

            result = forum_api.query_threads(
                str(db_path),
                base_url="https://example.test",
                params={"q": "Alpha 101"},
            )

        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["tid"], "101")

    def test_query_threads_can_return_random_recommendations(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = pathlib.Path(temp_dir) / "forum.db"
            create_test_db(db_path)
            conn = sqlite3.connect(db_path)
            try:
                rows = [
                    (
                        str(2000 + index),
                        "95" if index <= 60 else "96",
                        f"Recommend candidate {index}",
                        "General" if index <= 60 else "Other",
                        "tester",
                        "9",
                        f"2026-05-{(index % 25) + 1:02d}",
                        index,
                        index * 10,
                        index % 10,
                        1,
                        "pending",
                        None,
                        0,
                        0,
                        "",
                        0,
                    )
                    for index in range(1, 81)
                ]
                conn.executemany(
                    """
                    INSERT INTO threads (
                      tid, fid, title, forum_name, author, author_id, posted_at,
                      reply_count, view_count, heatlevel, source_page, detail_status,
                      detail_error, participant_count, money, rating, fetch_comments
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    rows,
                )
                conn.commit()
            finally:
                conn.close()

            result = forum_api.query_threads(
                str(db_path),
                base_url="https://example.test",
                params={"recommend": "1", "fid": "95", "page": "3", "page_size": "200"},
            )

        self.assertEqual(result["page"], 1)
        self.assertEqual(result["page_size"], 50)
        self.assertLessEqual(result["total"], 50)
        self.assertEqual(result["total_pages"], 1)
        self.assertLessEqual(len(result["items"]), 50)
        self.assertGreater(len(result["items"]), 0)
        self.assertTrue(all(item["fid"] == "95" for item in result["items"]))

    def test_query_threads_recommendations_can_search_keyword(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = pathlib.Path(temp_dir) / "forum.db"
            create_test_db(db_path)

            result = forum_api.query_threads(
                str(db_path),
                base_url="https://example.test",
                params={"recommend": "1", "q": "Alpha"},
            )

        self.assertGreaterEqual(result["total"], 1)
        self.assertTrue(all("Alpha" in item["title"] or "Alpha" in item["tid"] for item in result["items"]))

    def test_query_threads_recommendations_use_top_half_by_same_day_reply_or_view(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = pathlib.Path(temp_dir) / "forum.db"
            create_test_db(db_path)
            conn = sqlite3.connect(db_path)
            try:
                rows = []
                for index in range(1, 11):
                    rows.append(
                        (
                            f"same-day-{index}",
                            "95",
                            f"Same day candidate {index}",
                            "General",
                            "tester",
                            "9",
                            "2026-05-25 10:00",
                            101 - index,
                            1000 + index,
                            0,
                            1,
                            "pending",
                            None,
                            0,
                            0,
                            "",
                            0,
                        )
                    )
                for index in range(1, 11):
                    rows.append(
                        (
                            f"low-day-{index}",
                            "95",
                            f"Low same day candidate {index}",
                            "General",
                            "tester",
                            "9",
                            "2026-05-25 11:00",
                            index,
                            index,
                            0,
                            1,
                            "pending",
                            None,
                            0,
                            0,
                            "",
                            0,
                        )
                    )
                conn.executemany(
                    """
                    INSERT INTO threads (
                      tid, fid, title, forum_name, author, author_id, posted_at,
                      reply_count, view_count, heatlevel, source_page, detail_status,
                      detail_error, participant_count, money, rating, fetch_comments
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    rows,
                )
                conn.commit()
            finally:
                conn.close()

            result = forum_api.query_threads(
                str(db_path),
                base_url="https://example.test",
                params={
                    "recommend": "1",
                    "fid": "95",
                    "posted_date": "2026-05-25",
                    "show_disliked": "1",
                },
            )

        tids = {item["tid"] for item in result["items"]}
        self.assertEqual(result["total"], 10)
        self.assertTrue({f"same-day-{index}" for index in range(1, 11)}.issubset(tids))
        self.assertTrue(tids.isdisjoint({f"low-day-{index}" for index in range(1, 11)}))

    def test_save_comment_fetch_updates_thread_flag(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = pathlib.Path(temp_dir) / "forum.db"
            create_test_db(db_path)

            saved = forum_api.save_comment_fetch(str(db_path), "101", True)
            result = forum_api.query_threads(
                str(db_path),
                base_url="https://example.test",
                params={"q": "Alpha keyword"},
            )

        self.assertEqual(saved, {"tid": "101", "fetch_comments": 1})
        self.assertEqual(result["items"][0]["fetch_comments"], 1)

    def test_query_thread_detail_returns_comments(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = pathlib.Path(temp_dir) / "forum.db"
            create_test_db(db_path)

            result = forum_api.query_thread_detail(
                str(db_path),
                base_url="https://example.test",
                tid="102",
            )

        self.assertEqual(result["thread"]["tid"], "102")
        self.assertEqual(result["thread"]["official_url"], "https://example.test/forum.php?mod=viewthread&tid=102")
        self.assertEqual(len(result["comments"]), 2)
        self.assertEqual(result["comments"][0]["content_text"], "First comment")

    def test_static_server_falls_back_to_index_for_spa_routes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            (root / "index.html").write_text("<main>app</main>", encoding="utf-8")
            target = forum_api.resolve_static_target(root, "/thread/102")

        self.assertEqual(target.name, "index.html")

    def test_query_threads_filters_and_paginates(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = pathlib.Path(temp_dir) / "forum.db"
            create_test_db(db_path)

            result = forum_api.query_threads(
                str(db_path),
                base_url="https://example.test/",
                params={
                    "q": "keyword",
                    "fid": "95",
                    "author_id": "1",
                    "min_replies": "10",
                    "min_views": "100",
                    "page_size": "1",
                    "page": "1",
                },
            )

        self.assertEqual(result["total"], 1)
        self.assertEqual(result["total_pages"], 1)
        self.assertEqual(result["items"][0]["tid"], "101")

    def test_query_threads_empty_fid_searches_all_forums(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = pathlib.Path(temp_dir) / "forum.db"
            create_test_db(db_path)

            result = forum_api.query_threads(
                str(db_path),
                base_url="https://example.test",
                params={"fid": ""},
            )

        self.assertEqual(result["total"], 4)

    def test_query_threads_excludes_title_keyword(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = pathlib.Path(temp_dir) / "forum.db"
            create_test_db(db_path)

            result = forum_api.query_threads(
                str(db_path),
                base_url="https://example.test",
                params={
                    "q": "Alpha",
                    "exclude_q": "fresh",
                },
            )

        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["tid"], "101")

    def test_query_threads_allows_view_sort_ascending(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = pathlib.Path(temp_dir) / "forum.db"
            create_test_db(db_path)

            result = forum_api.query_threads(
                str(db_path),
                base_url="https://example.test",
                params={"sort": "view_count", "order": "asc"},
            )

        self.assertEqual([item["tid"] for item in result["items"]], ["105", "103", "101", "102"])

    def test_query_threads_can_sort_by_detail_metrics(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = pathlib.Path(temp_dir) / "forum.db"
            create_test_db(db_path)
            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    "UPDATE threads SET participant_count = 20, money = 5, rating = '10' WHERE tid = '103'"
                )
                conn.commit()
            finally:
                conn.close()

            by_participants = forum_api.query_threads(
                str(db_path),
                base_url="https://example.test",
                params={"sort": "participant_count", "order": "desc"},
            )
            by_money = forum_api.query_threads(
                str(db_path),
                base_url="https://example.test",
                params={"sort": "money", "order": "desc"},
            )
            by_rating = forum_api.query_threads(
                str(db_path),
                base_url="https://example.test",
                params={"sort": "rating", "order": "desc"},
            )

        self.assertEqual(by_participants["items"][0]["tid"], "103")
        self.assertEqual(by_money["items"][0]["tid"], "102")
        self.assertEqual(by_rating["items"][0]["tid"], "103")

    def test_query_threads_filters_by_posted_date_before_sorting(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = pathlib.Path(temp_dir) / "forum.db"
            create_test_db(db_path)
            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    """
                    INSERT INTO threads (
                      tid, fid, title, forum_name, author, author_id, posted_at,
                      reply_count, view_count, heatlevel, source_page, detail_status,
                      detail_error, participant_count, money, rating
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "104",
                        "95",
                        "Delta same day",
                        "General",
                        "carol",
                        "3",
                        "2026-05-22 13:45",
                        1,
                        800,
                        1,
                        4,
                        "pending",
                        None,
                        0,
                        0,
                        "",
                    ),
                )
                conn.commit()
            finally:
                conn.close()

            result = forum_api.query_threads(
                str(db_path),
                base_url="https://example.test",
                params={
                    "posted_date": "2026-05-22",
                    "sort": "view_count",
                    "order": "desc",
                },
            )

        self.assertEqual(result["total"], 2)
        self.assertEqual([item["tid"] for item in result["items"]], ["104", "101"])

    def test_query_threads_filters_by_posted_date_range_before_sorting(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = pathlib.Path(temp_dir) / "forum.db"
            create_test_db(db_path)

            result = forum_api.query_threads(
                str(db_path),
                base_url="https://example.test",
                params={
                    "posted_date_from": "2026-05-21",
                    "posted_date_to": "2026-05-22",
                    "sort": "view_count",
                    "order": "desc",
                },
            )

        self.assertEqual(result["total"], 2)
        self.assertEqual([item["tid"] for item in result["items"]], ["102", "101"])

    def test_query_threads_rejects_invalid_sort(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = pathlib.Path(temp_dir) / "forum.db"
            create_test_db(db_path)

            with self.assertRaises(ValueError):
                forum_api.query_threads(
                    str(db_path),
                    base_url="https://example.test",
                    params={"sort": "title; drop table threads"},
                )

    def test_query_threads_rejects_excessive_page(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = pathlib.Path(temp_dir) / "forum.db"
            create_test_db(db_path)

            with self.assertRaises(ValueError):
                forum_api.query_threads(
                    str(db_path),
                    base_url="https://example.test",
                    params={"page": "10001"},
                )

    def test_json_response_for_api_error(self):
        body, status = forum_api.handle_api_threads(
            database_path="missing.db",
            base_url="https://example.test",
            params={"sort": "bad"},
        )

        self.assertEqual(status, 400)
        self.assertIn("error", body)

    def test_json_response_for_database_error_is_generic(self):
        with mock.patch("sys.stderr"):
            body, status = forum_api.handle_api_threads(
                database_path="missing.db",
                base_url="https://example.test",
                params={},
            )

        self.assertEqual(status, 500)
        self.assertEqual(body, {"error": "database error"})

    def test_query_forums_maps_names_from_fid_instead_of_stored_values(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = pathlib.Path(temp_dir) / "forum.db"
            create_test_db(db_path)

            result = forum_api.query_forums(str(db_path), config={"list_sync": {"forums": {"95": "综合讨论区"}}})

        self.assertEqual(
            result,
            {
                "items": [
                    {"fid": "95", "forum_name": "综合讨论区", "thread_count": 3},
                    {"fid": "96", "forum_name": "fid 96", "thread_count": 1},
                ]
            },
        )

    def test_thread_detail_requires_explicit_comment_job(self):
        with tempfile.TemporaryDirectory() as root:
            path = pathlib.Path(root) / 'forum.db'
            create_test_db(path)
            with self.assertRaisesRegex(ValueError, 'comment-jobs'):
                forum_api.query_thread_detail(str(path), 'https://example.test', '101', fetch_missing_comments=True)

    def test_comment_progress_is_scoped_to_database(self):
        forum_api.update_comment_progress('101', scope='a', completed_pages=1, total_pages=2)
        self.assertEqual(forum_api.get_comment_progress('101', 'a')['percent'], 50)
        self.assertEqual(forum_api.get_comment_progress('101', 'b')['percent'], 0)

    def test_handle_api_thread_can_fetch_missing_comments(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = pathlib.Path(temp_dir) / "forum.db"
            create_test_db(db_path)

            with mock.patch("forum_backend.api.services.query_thread_detail") as query_mock:
                query_mock.return_value = {"thread": {}, "comments": [], "comment_fetch": {"status": "skipped"}}
                body, status = forum_api.handle_api_thread(
                    str(db_path),
                    base_url="https://example.test",
                    params={"tid": "101", "fetch_missing_comments": "1"},
                )

        self.assertEqual(status, 200)
        self.assertEqual(body["comment_fetch"]["status"], "skipped")
        self.assertTrue(query_mock.call_args.kwargs["fetch_missing_comments"])

    def test_handle_api_comment_progress_returns_current_progress(self):
        forum_api.reset_comment_progress("101")
        forum_api.update_comment_progress(
            "101",
            status="running",
            completed_pages=2,
            total_pages=5,
            saved_comments=30,
        )

        body, status = forum_api.handle_api_comment_progress(params={"tid": "101"})

        self.assertEqual(status, 200)
        self.assertEqual(body["tid"], "101")
        self.assertEqual(body["status"], "running")
        self.assertEqual(body["completed_pages"], 2)
        self.assertEqual(body["total_pages"], 5)
        self.assertEqual(body["percent"], 40)
        self.assertEqual(body["saved_comments"], 30)

    def test_json_response_for_forums_database_error_is_generic(self):
        with tempfile.TemporaryDirectory() as root, mock.patch("sys.stderr"):
            body, status = forum_api.handle_api_forums(database_path=str(pathlib.Path(root) / "missing.db"))

        self.assertEqual(status, 500)
        self.assertEqual(body, {"error": "database error"})

    def test_ensure_feedback_schema_creates_table(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = pathlib.Path(temp_dir) / "forum.db"
            create_test_db(db_path)

            forum_api.ensure_feedback_schema(str(db_path))

            self.assertTrue(feedback_table_exists(db_path))

    def test_save_feedback_and_query_threads_returns_feedback(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = pathlib.Path(temp_dir) / "forum.db"
            create_test_db(db_path)

            forum_api.save_feedback(str(db_path), "101", "like")
            forum_api.save_seen(str(db_path), "101", True)
            result = forum_api.query_threads(
                str(db_path),
                base_url="https://example.test",
                params={"q": "Alpha"},
            )

        self.assertEqual(result["items"][0]["feedback"], "like")
        self.assertEqual(result["items"][0]["seen"], 1)

    def test_clear_feedback_removes_feedback(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = pathlib.Path(temp_dir) / "forum.db"
            create_test_db(db_path)

            forum_api.save_feedback(str(db_path), "101", "like")
            forum_api.clear_feedback(str(db_path), "101")
            result = forum_api.query_threads(
                str(db_path),
                base_url="https://example.test",
                params={"q": "Alpha keyword", "show_disliked": "1"},
            )

        self.assertIsNone(result["items"][0]["feedback"])

    def test_query_threads_keeps_disliked_rows_visible(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = pathlib.Path(temp_dir) / "forum.db"
            create_test_db(db_path)

            forum_api.save_feedback(str(db_path), "101", "dislike")
            hidden = forum_api.query_threads(
                str(db_path),
                base_url="https://example.test",
                params={"q": "Alpha keyword"},
            )
            shown = forum_api.query_threads(
                str(db_path),
                base_url="https://example.test",
                params={"q": "Alpha keyword", "show_disliked": "1"},
            )

        self.assertEqual(hidden["total"], 0)
        self.assertEqual(shown["total"], 1)
        self.assertEqual(shown["items"][0]["tid"], "101")
        self.assertEqual(shown["items"][0]["feedback"], "dislike")

    def test_query_threads_can_hide_seen_rows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = pathlib.Path(temp_dir) / "forum.db"
            create_test_db(db_path)

            forum_api.save_seen(str(db_path), "101", True)
            result = forum_api.query_threads(
                str(db_path),
                base_url="https://example.test",
                params={"q": "Alpha keyword", "hide_seen": "1"},
            )

        self.assertEqual(result["total"], 0)

    def test_ensure_feedback_schema_migrates_legacy_seen_feedback(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = pathlib.Path(temp_dir) / "forum.db"
            create_test_db(db_path)
            forum_api.ensure_feedback_schema(str(db_path))
            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    "INSERT INTO thread_feedback (tid, feedback) VALUES (?, ?)",
                    ("101", "seen"),
                )
                conn.commit()
            finally:
                conn.close()

            forum_api.ensure_feedback_schema(str(db_path))
            result = forum_api.query_threads(
                str(db_path),
                base_url="https://example.test",
                params={"q": "Alpha keyword", "hide_seen": "1", "show_disliked": "1"},
            )
            shown = forum_api.query_threads(
                str(db_path),
                base_url="https://example.test",
                params={"q": "Alpha keyword", "show_disliked": "1"},
            )

        self.assertEqual(result["total"], 0)
        self.assertIsNone(shown["items"][0]["feedback"])
        self.assertEqual(shown["items"][0]["seen"], 1)

    def test_query_threads_can_show_only_liked_rows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = pathlib.Path(temp_dir) / "forum.db"
            create_test_db(db_path)

            forum_api.save_feedback(str(db_path), "101", "like")
            forum_api.save_seen(str(db_path), "102", True)
            result = forum_api.query_threads(
                str(db_path),
                base_url="https://example.test",
                params={"fid": "95", "only_liked": "1"},
            )

        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["tid"], "101")

    def test_query_title_words_counts_title_tokens(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = pathlib.Path(temp_dir) / "forum.db"
            create_test_db(db_path)

            result = forum_api.query_title_words(
                str(db_path),
                params={"min_count": "2"},
            )

        self.assertEqual(result["total_words"], 2)
        self.assertEqual(result["total_threads"], 4)
        self.assertEqual(
            result["items"],
            [
                {"word": "完美", "count": 2, "thread_count": 2},
                {"word": "笔记", "count": 2, "thread_count": 2},
            ],
        )

    def test_query_title_words_ignores_words_containing_digits(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = pathlib.Path(temp_dir) / "forum.db"
            create_test_db(db_path)
            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    """
                    INSERT INTO threads (
                      tid, fid, title, forum_name, author, author_id, posted_at,
                      reply_count, view_count, heatlevel, source_page, detail_status,
                      detail_error, participant_count, money, rating, fetch_comments
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    ("200", "95", "4K Alpha 1080P Word2 clean 教程", "General", "eve", "5", "2026-05-24", 1, 1, 0, 1, "pending", None, 0, 0, "", 0),
                )
                conn.commit()
            finally:
                conn.close()

            result = forum_api.query_title_words(
                str(db_path),
                params={"q": "clean", "min_count": "1"},
            )

        words = {item["word"] for item in result["items"]}
        self.assertIn("教程", words)
        self.assertNotIn("Alpha", words)
        self.assertNotIn("clean", words)
        self.assertNotIn("4K", words)
        self.assertNotIn("1080P", words)
        self.assertNotIn("Word2", words)

    def test_query_title_words_ignores_english_only_words(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = pathlib.Path(temp_dir) / "forum.db"
            create_test_db(db_path)
            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    """
                    INSERT INTO threads (
                      tid, fid, title, forum_name, author, author_id, posted_at,
                      reply_count, view_count, heatlevel, source_page, detail_status,
                      detail_error, participant_count, money, rating, fetch_comments
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    ("202", "95", "Python SQLite 完美笔记", "General", "eve", "5", "2026-05-24", 1, 1, 0, 1, "pending", None, 0, 0, "", 0),
                )
                conn.commit()
            finally:
                conn.close()

            result = forum_api.query_title_words(
                str(db_path),
                params={"q": "完美笔记", "min_count": "1"},
            )

        words = {item["word"] for item in result["items"]}
        self.assertIn("完美笔记", words)
        self.assertNotIn("OnlyFans", words)
        self.assertNotIn("sqlite", words)

    def test_query_title_words_detects_changed_thread_count(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = pathlib.Path(temp_dir) / "forum.db"
            create_test_db(db_path)

            first = forum_api.query_title_words(
                str(db_path),
                params={"min_count": "1"},
            )

            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    """
                    INSERT INTO threads (
                      tid, fid, title, forum_name, author, author_id, posted_at,
                      reply_count, view_count, heatlevel, source_page, detail_status,
                      detail_error, participant_count, money, rating, fetch_comments
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    ("201", "95", "Delta cached 新增词", "General", "eve", "5", "2026-05-24", 1, 1, 0, 1, "pending", None, 0, 0, "", 0),
                )
                conn.commit()
            finally:
                conn.close()

            cached = forum_api.query_title_words(
                str(db_path),
                params={"min_count": "1"},
            )
            refreshed = forum_api.query_title_words(
                str(db_path),
                params={"min_count": "1", "refresh": "1"},
            )

        cached_words = {item["word"] for item in cached["items"]}
        refreshed_words = {item["word"] for item in refreshed["items"]}
        self.assertEqual(first["total_threads"], 4)
        self.assertEqual(cached["total_threads"], 5)
        self.assertIn("新增词", cached_words)
        self.assertEqual(refreshed["total_threads"], 5)
        self.assertIn("新增词", refreshed_words)

    def test_query_title_words_supports_cached_pagination(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = pathlib.Path(temp_dir) / "forum.db"
            create_test_db(db_path)

            result = forum_api.query_title_words(
                str(db_path),
                params={"min_count": "1", "page": "2", "page_size": "2"},
            )

        self.assertEqual(result["page"], 2)
        self.assertEqual(result["page_size"], 2)
        self.assertEqual(result["total_words"], 3)
        self.assertEqual([item["word"] for item in result["items"]], ["教程"])

    def test_query_title_words_can_filter_by_forum_and_keyword(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = pathlib.Path(temp_dir) / "forum.db"
            create_test_db(db_path)

            result = forum_api.query_title_words(
                str(db_path),
                params={"fid": "95", "q": "fresh", "min_count": "1"},
            )

        self.assertEqual(result["total_threads"], 1)
        self.assertEqual(result["items"][0], {"word": "笔记", "count": 1, "thread_count": 1})

    def test_handle_api_title_words_returns_bad_request_for_invalid_page_size(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = pathlib.Path(temp_dir) / "forum.db"
            create_test_db(db_path)

            body, status = forum_api.handle_api_title_words(
                str(db_path),
                {"page_size": "many"},
            )

        self.assertEqual(status, 400)
        self.assertEqual(body, {"error": "page_size must be an integer"})

    def test_query_threads_can_sort_by_interest_score(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = pathlib.Path(temp_dir) / "forum.db"
            create_test_db(db_path)

            forum_api.save_feedback(str(db_path), "101", "like")
            forum_api.save_feedback(str(db_path), "102", "dislike")
            forum_api.save_seen(str(db_path), "103", True)
            result = forum_api.query_threads(
                str(db_path),
                base_url="https://example.test",
                params={"sort": "interest_score", "order": "desc"},
            )

        tids = [item["tid"] for item in result["items"]]
        self.assertEqual(tids[0], "101")
        self.assertEqual(tids[1], "105")
        self.assertLess(
            result["items"][tids.index("103")]["interest_score"],
            result["items"][tids.index("105")]["interest_score"],
        )

    def test_save_feedback_rejects_invalid_value(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = pathlib.Path(temp_dir) / "forum.db"
            create_test_db(db_path)

            with self.assertRaises(ValueError):
                forum_api.save_feedback(str(db_path), "101", "maybe")

    def test_handle_api_feedback_saves_feedback(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = pathlib.Path(temp_dir) / "forum.db"
            create_test_db(db_path)

            body, status = forum_api.handle_api_feedback(
                str(db_path),
                {"tid": "101", "feedback": "later"},
            )

        self.assertEqual(status, 200)
        self.assertEqual(body, {"tid": "101", "feedback": "later"})

    def test_handle_api_feedback_can_clear_feedback(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = pathlib.Path(temp_dir) / "forum.db"
            create_test_db(db_path)
            forum_api.save_feedback(str(db_path), "101", "later")

            body, status = forum_api.handle_api_feedback(
                str(db_path),
                {"tid": "101", "feedback": ""},
            )

        self.assertEqual(status, 200)
        self.assertEqual(body, {"tid": "101", "feedback": None})

    def test_run_server_handles_keyboard_interrupt_cleanly(self):
        server = mock.Mock()
        server.serve_forever.side_effect = KeyboardInterrupt
        with (
            mock.patch("forum_backend.api.server.ForumServer", return_value=server),
            mock.patch("builtins.print"), mock.patch("forum_backend.api.server.init_db"),
        ):
            forum_api.run_server()

        server.server_close.assert_called_once()

    def test_run_server_listens_on_loopback_by_default(self):
        server = mock.Mock()
        server.serve_forever.side_effect = KeyboardInterrupt
        with (
            mock.patch("forum_backend.api.server.ForumServer", return_value=server) as server_class,
            mock.patch("builtins.print"), mock.patch("forum_backend.api.server.init_db"),
        ):
            forum_api.run_server()

        self.assertEqual(server_class.call_args.args[0], ("127.0.0.1", 8000))


if __name__ == "__main__":
    unittest.main()
