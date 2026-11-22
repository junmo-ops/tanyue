import pathlib
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from forum_backend.config import resolve_database_path
from forum_backend.db import init_db
from scripts.seed_test_db import seed_test_database


def table_columns(database_path: pathlib.Path, table_name: str) -> list[str]:
    conn = sqlite3.connect(database_path)
    try:
        return [
            row[1]
            for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        ]
    finally:
        conn.close()


class TestDatabaseSetupTests(unittest.TestCase):
    def test_resolve_database_path_uses_selected_environment(self):
        config = {
            "environment": "test",
            "database_path": "data/forum.db",
            "database_paths": {
                "production": "data/forum.db",
                "test": "data/forum.test.db",
            },
        }

        self.assertEqual(resolve_database_path({"database":{"environment":"test", "paths":config["database_paths"]}}), "data/forum.test.db")

    def test_resolve_database_path_rejects_legacy_database_path(self):
        config = {"database_path": "data/forum.db"}

        with self.assertRaises(ValueError):
            resolve_database_path(config)

    def test_seed_test_database_creates_100_threads_with_matching_schema(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            seeded_db = temp_path / "forum.test.db"
            empty_schema_db = temp_path / "empty.db"

            seed_test_database(str(seeded_db), thread_count=100)
            conn = init_db(str(empty_schema_db))
            conn.close()

            conn = sqlite3.connect(seeded_db)
            try:
                thread_count = conn.execute("SELECT COUNT(1) FROM threads").fetchone()[0]
                comment_count = conn.execute("SELECT COUNT(1) FROM comments").fetchone()[0]
                feedback_count = conn.execute("SELECT COUNT(1) FROM thread_feedback").fetchone()[0]
            finally:
                conn.close()

            self.assertEqual(thread_count, 100)
            self.assertGreater(comment_count, 0)
            self.assertGreater(feedback_count, 0)
            self.assertEqual(
                table_columns(seeded_db, "threads"),
                table_columns(empty_schema_db, "threads"),
            )
            self.assertEqual(
                table_columns(seeded_db, "comments"),
                table_columns(empty_schema_db, "comments"),
            )

    def test_seed_script_can_run_from_project_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = pathlib.Path(temp_dir) / "forum.test.db"

            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/seed_test_db.py",
                    "--database-path",
                    str(db_path),
                ],
                cwd=pathlib.Path(__file__).resolve().parents[1],
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            conn = sqlite3.connect(db_path)
            try:
                thread_count = conn.execute("SELECT COUNT(1) FROM threads").fetchone()[0]
            finally:
                conn.close()
            self.assertEqual(thread_count, 100)


if __name__ == "__main__":
    unittest.main()
