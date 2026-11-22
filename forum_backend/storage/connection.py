import sqlite3


def connect_db(database_path: str) -> sqlite3.Connection:
    """Open a connection without running schema changes."""
    conn = sqlite3.connect(database_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn
