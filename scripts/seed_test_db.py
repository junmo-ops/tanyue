from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from forum_backend.api.services import ensure_feedback_schema
from forum_backend.db import init_db


DEFAULT_TEST_DB = "data/forum.test.db"


def seed_test_database(database_path: str = DEFAULT_TEST_DB, thread_count: int = 100) -> None:
    """重新生成测试数据库，并填充帖子、评论和反馈样本。"""
    path = Path(database_path)
    if path.exists():
        # 测试库是可重建资产，先删除可避免旧数据影响新一轮验证。
        path.unlink()

    conn = init_db(str(path))
    try:
        _insert_threads(conn, thread_count)
        _insert_comments(conn, thread_count)
    finally:
        conn.close()

    ensure_feedback_schema(str(path))
    _insert_feedback(str(path), thread_count)


def _insert_threads(conn: sqlite3.Connection, thread_count: int) -> None:
    """插入覆盖多板块、多状态和多指标分布的测试帖子。"""
    forums = [
        ("901", "示例技术交流"),
        ("902", "示例日常分享"),
        ("903", "示例工具笔记"),
        ("904", "示例作品展示"),
    ]
    statuses = ["pending", "fetched", "failed"]
    rows = []
    for index in range(1, thread_count + 1):
        fid, forum_name = forums[(index - 1) % len(forums)]
        status = statuses[index % len(statuses)]
        tid = str(9000000 + index)
        rows.append(
            (
                tid,
                fid,
                f"测试帖子 {index:03d} - {forum_name} 关键词样本",
                forum_name,
                f"测试作者{(index % 12) + 1}",
                str(1000 + (index % 12) + 1),
                f"2026-05-{((index - 1) % 25) + 1:02d} {index % 24:02d}:00",
                (index * 7) % 260,
                120 + index * 43,
                index % 12,
                (index - 1) // 20 + 1,
                status,
                "测试失败样本" if status == "failed" else None,
                (index * 3) % 80,
                (index * 5) % 160,
                str((index * 2) % 30) if index % 4 else "",
                1 if index % 5 == 0 else 0,
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


def _insert_comments(conn: sqlite3.Connection, thread_count: int) -> None:
    """给部分帖子插入评论，用于详情页和评论筛选验证。"""
    rows = []
    for index in range(1, thread_count + 1):
        if index % 5 != 0:
            continue
        tid = str(9000000 + index)
        for comment_index in range(1, 4):
            rows.append(
                (
                    tid,
                    f"{tid}-{comment_index}",
                    f"评论用户{comment_index}",
                    str(2000 + comment_index),
                    f"2026-05-{((index - 1) % 25) + 1:02d} {comment_index + 9:02d}:30",
                    f"这是测试帖子 {index:03d} 的第 {comment_index} 条评论内容。",
                    comment_index,
                    "2026-05-25 12:00:00",
                )
            )
    conn.executemany(
        """
        INSERT INTO comments (
          tid, comment_id, author, author_id, posted_at, content_text, source_page, fetched_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()


def _insert_feedback(database_path: str, thread_count: int) -> None:
    """给部分帖子插入反馈样本，用于推荐和隐藏规则验证。"""
    feedback_values = ["like", "dislike", "seen", "later"]
    conn = sqlite3.connect(database_path)
    try:
        rows = []
        for index in range(1, thread_count + 1):
            if index % 7 != 0:
                continue
            rows.append((str(9000000 + index), feedback_values[index % len(feedback_values)]))
        conn.executemany(
            """
            INSERT INTO thread_feedback (tid, feedback, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            """,
            rows,
        )
        conn.commit()
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    """命令行入口，生成指定路径和规模的测试数据库。"""
    parser = argparse.ArgumentParser(description="生成本地测试 SQLite 数据库。")
    parser.add_argument("--database-path", default=DEFAULT_TEST_DB)
    parser.add_argument("--threads", type=int, default=100)
    args = parser.parse_args(argv)

    seed_test_database(args.database_path, thread_count=args.threads)
    print(f"测试数据库已生成：{args.database_path}，帖子 {args.threads} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
