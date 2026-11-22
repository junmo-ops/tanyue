"""Keep real first/last metric observations per UTC day, in the caller's transaction."""
from datetime import datetime, timezone
import sqlite3


def record_thread_metrics(
    conn: sqlite3.Connection,
    tid: str,
    observed_at: str,
    reply_count: int,
    view_count: int,
) -> None:
    """Do not commit; list data and observations must succeed or roll back together.

    Naive crawler timestamps describe the crawler host's local time. Normalize
    them to fixed-width UTC values so ordering does not depend on their offsets.
    Invalid times/counts do not become fabricated metric observations.
    """
    try:
        value = observed_at.strip()
        if len(value) < 19:
            return
        observed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        observed = observed.astimezone(timezone.utc)
    except (AttributeError, TypeError, ValueError, OverflowError, OSError):
        return
    if isinstance(reply_count, bool) or isinstance(view_count, bool):
        return
    if not isinstance(reply_count, int) or not isinstance(view_count, int) or min(reply_count, view_count) < 0:
        return

    timestamp = observed.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    day = timestamp[:10]
    row = conn.execute(
        """
        SELECT first_observed_at, last_observed_at, first_reply_count,
               last_reply_count, first_view_count, last_view_count, counter_decreased
        FROM thread_metric_daily WHERE tid = ? AND observed_date = ?
        """,
        (tid, day),
    ).fetchone()
    if row is None:
        conn.execute(
            """
            INSERT INTO thread_metric_daily (
                tid, observed_date, first_observed_at, last_observed_at,
                first_reply_count, last_reply_count, first_view_count, last_view_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (tid, day, timestamp, timestamp, reply_count, reply_count, view_count, view_count),
        )
        return

    first_at, last_at, first_replies, last_replies, first_views, last_views, decreased = row
    if timestamp in {first_at, last_at}:
        # Replayed pages and duplicate timestamps cannot establish a new sample.
        # Conflicting counts at the same instant make the day unreliable.
        expected = (first_replies, first_views) if timestamp == first_at else (last_replies, last_views)
        decreased = decreased or (reply_count, view_count) != expected
    elif timestamp < first_at:
        decreased = decreased or reply_count > first_replies or view_count > first_views
        first_at, first_replies, first_views = timestamp, reply_count, view_count
    elif timestamp > last_at:
        decreased = decreased or reply_count < last_replies or view_count < last_views
        last_at, last_replies, last_views = timestamp, reply_count, view_count
    else:
        # Interior samples are no longer retained, so their relative order
        # cannot be reconstructed. Conservatively exclude this day rather than
        # hide a possible reset between two discarded middle observations.
        decreased = True

    conn.execute(
        """
        UPDATE thread_metric_daily SET first_observed_at = ?, last_observed_at = ?,
            first_reply_count = ?, last_reply_count = ?, first_view_count = ?,
            last_view_count = ?, counter_decreased = ?
        WHERE tid = ? AND observed_date = ?
        """,
        (first_at, last_at, first_replies, last_replies, first_views, last_views, int(decreased), tid, day),
    )
