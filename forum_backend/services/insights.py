"""Read-only discovery insights over collected samples, never whole-site claims."""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from statistics import median

from .common import _first, connect_db, forum_display_name, official_thread_url
from .recommendation import title_tokens

MAX_PERIOD_ROWS = 200_000
MAX_HISTORY_ROWS = 200_000
SUMMARY_SQL = """t.tid, t.title, t.fid, t.forum_name, t.author, t.author_id,
    t.posted_at, t.reply_count, t.view_count, tf.feedback, COALESCE(tf.seen, 0) AS seen"""
SAMPLE_NOTE = '仅统计已采集且未标记为不感兴趣的帖子；两个周期的采集范围可能不同，样本变化不代表全站趋势。'


def _integer(params, name, default, low, high):
    raw = str(_first(params, name, str(default)))
    if not raw.isascii() or not raw.isdecimal():
        raise ValueError(f'{name} must be an integer between {low} and {high}')
    value = int(raw)
    if value < low or value > high:
        raise ValueError(f'{name} must be between {low} and {high}')
    return value


def _period(params):
    days = _integer(params, 'days', 14, 1, 365)
    offset = _integer(params, 'period', 0, 0, 1000)
    raw = _first(params, 'anchor', '') or date.today().isoformat()
    try:
        anchor = date.fromisoformat(raw)
        if anchor.isoformat() != raw:
            raise ValueError()
        end = anchor - timedelta(days=days * offset)
        start = end - timedelta(days=days - 1)
        previous_end = start - timedelta(days=1)
        previous_start = start - timedelta(days=days)
        end_exclusive = end + timedelta(days=1)
    except (ValueError, OverflowError, TypeError) as exc:
        raise ValueError('anchor or period is outside the supported date range') from exc
    return days, start, end, previous_start, previous_end, end_exclusive


def _summary(row, base_url, config=None):
    result = {key: row[key] for key in (
        'tid', 'title', 'fid', 'forum_name', 'author', 'author_id', 'posted_at',
        'reply_count', 'view_count', 'feedback', 'seen',
    )}
    result['forum_name'] = forum_display_name(result['fid'], config, fallback=result['forum_name'])
    result['official_url'] = official_thread_url(base_url, result['tid'])
    return result


def _cohort_ranks(items):
    """Competition ranks within a board/day; ties do not invent distinctions."""
    groups = defaultdict(list)
    for item in items:
        groups[(item['fid'], item['posted_at'][:10])].append(item)
    ranks = {}
    for group in groups.values():
        n = len(group)
        metrics = {}
        for field in ('reply_count', 'view_count'):
            counts = Counter(item[field] for item in group)
            earlier = 0
            metrics[field] = {}
            for value in sorted(counts, reverse=True):
                metrics[field][value] = earlier + 1
                earlier += counts[value]
        for item in group:
            # A zero metric is not evidence of popularity, even if every row ties.
            positive_ranks = [metrics[key][item[key]] for key in metrics if item[key] > 0]
            rank = min(positive_ranks) if positive_ranks else n + 1
            hot = bool(positive_ranks) and rank <= max(1, math.ceil(n * .25))
            ranks[item['tid']] = {'hot': hot, 'rank': rank, 'size': n, 'percentile': round(100 * rank / n, 1) if n >= 5 else None}
    return ranks


def _missed(items, ranks):
    candidates = [item for item in items if not item['seen'] and ranks[item['tid']]['hot']]
    candidates.sort(key=lambda i: (
        i['feedback'] == 'like', ranks[i['tid']]['size'] >= 5,
        -ranks[i['tid']]['rank'] / ranks[i['tid']]['size'], i['reply_count'], i['view_count'], i['tid'],
    ), reverse=True)
    selected = []
    for item in candidates[:20]:
        rank = ranks[item['tid']]
        reason = (f"同板块同日 {rank['size']} 篇中，回复或浏览排名前 {rank['percentile']:g}%"
                  if rank['size'] >= 5 else f"同板块同日仅 {rank['size']} 篇样本，按现有互动精选")
        selected.append({**item, 'percentile': rank['percentile'], 'reason': reason})
    return {'total': len(candidates), 'items': selected}


def _topic_words(title):
    return {word for word in title_tokens(title) if 2 <= len(word) <= 12 and not any(c.isdigit() for c in word)}


def _topics(current, previous):
    current_counts, previous_counts = Counter(), Counter()
    examples = defaultdict(list)
    for item in current:
        for word in _topic_words(item['title']):
            current_counts[word] += 1
            # Keep only representative posts rather than duplicating the whole cohort.
            examples[word].append(item)
            examples[word].sort(key=lambda i: (i['reply_count'], i['view_count']), reverse=True)
            del examples[word][3:]
    for item in previous:
        previous_counts.update(_topic_words(item['title']))
    results = []
    for word, count in current_counts.items():
        if count < 3:
            continue
        share = count / len(current) * 100
        previous_share = previous_counts[word] / len(previous) * 100 if previous else 0
        change = share - previous_share
        if change <= 0:
            continue
        results.append({'word': word, 'count': count, 'previous_count': previous_counts[word],
                        'share': round(share, 2), 'previous_share': round(previous_share, 2),
                        'change_pp': round(change, 2), 'items': examples[word]})
    results.sort(key=lambda item: (-item['change_pp'], -item['count'], item['word']))
    # No earlier sample means no meaningful comparison, even if a word exists now.
    return results[:8] if previous else []


def _authors(items, ranks):
    groups = defaultdict(list)
    for item in items:
        if item['author_id'] and item['author_id'] != '0':
            groups[item['author_id']].append(item)
    results = []
    for author_id, group in groups.items():
        if len(group) < 2:
            continue
        group.sort(key=lambda i: (i['feedback'] == 'like', ranks[i['tid']]['hot'], i['reply_count']), reverse=True)
        hot_count = sum(ranks[i['tid']]['hot'] for i in group)
        results.append({'author_id': author_id, 'author': group[0]['author'] or f'作者 {author_id}',
                        'count': len(group), 'liked_count': sum(i['feedback'] == 'like' for i in group),
                        'hot_count': hot_count, 'median_replies': median(i['reply_count'] for i in group),
                        'items': group[:3]})
    results.sort(key=lambda i: (i['liked_count'], i['hot_count'] / i['count'], i['count'], i['median_replies']), reverse=True)
    return results[:8]


def _growth(conn, base_url, start, end_exclusive, fid, config=None):
    note = '仅比较所选周期内实际采集到的首末观测；各帖观测区间不同，不能还原每天走势。计数回落的帖子不参与排名。'
    empty = {'status': 'insufficient', 'tracked_count': 0, 'eligible_count': 0, 'items': [],
             'note': '该周期还没有足够的历史观测；更新版本后至少采集同一帖子两次，才能比较真实增长。'}
    exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='thread_metric_daily'").fetchone()
    if not exists:
        return empty
    try:
        begin_utc = datetime.combine(start, time.min).astimezone(timezone.utc)
        end_utc = datetime.combine(end_exclusive, time.min).astimezone(timezone.utc)
    except (OverflowError, OSError, ValueError) as exc:
        raise ValueError('period is outside the supported timezone range') from exc
    begin_iso = begin_utc.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
    end_iso = end_utc.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
    rows = conn.execute("""
        SELECT m.* FROM thread_metric_daily m JOIN threads t ON t.tid=m.tid
        LEFT JOIN thread_feedback tf ON tf.tid=t.tid
        WHERE m.observed_date >= ? AND m.observed_date <= ?
          AND (? = '' OR t.fid=?) AND COALESCE(tf.feedback, '') != 'dislike'
        ORDER BY m.tid, m.observed_date LIMIT ?
        """, (begin_utc.date().isoformat(), end_utc.date().isoformat(), fid, fid, MAX_HISTORY_ROWS + 1)).fetchall()
    if len(rows) > MAX_HISTORY_ROWS:
        raise ValueError('该范围的历史观测过多，请缩短周期或选择一个板块')
    histories = {}
    for row in rows:
        endpoints = []
        for prefix in ('first', 'last'):
            observed = row[f'{prefix}_observed_at']
            if begin_iso <= observed < end_iso:
                endpoints.append((observed, row[f'{prefix}_reply_count'], row[f'{prefix}_view_count']))
        if not endpoints:
            continue
        history = histories.setdefault(row['tid'], {'first': endpoints[0], 'last': endpoints[0], 'invalid': False})
        history['invalid'] |= bool(row['counter_decreased'])
        for endpoint in endpoints:
            previous = history['last']
            if endpoint[1] < previous[1] or endpoint[2] < previous[2]:
                history['invalid'] = True
            if endpoint[0] == previous[0] and endpoint[1:] != previous[1:]:
                history['invalid'] = True
            history['last'] = endpoint
    candidates = []
    eligible = 0
    for tid, history in histories.items():
        first, last = history['first'], history['last']
        if history['invalid'] or first[0] >= last[0]:
            continue
        eligible += 1
        reply_growth, view_growth = last[1] - first[1], last[2] - first[2]
        if reply_growth > 0 or view_growth > 0:
            candidates.append({'tid': tid, 'reply_growth': reply_growth, 'view_growth': view_growth,
                               'from': first[0], 'to': last[0]})
    candidates.sort(key=lambda i: (i['reply_growth'], i['view_growth'], i['tid']), reverse=True)
    candidates = candidates[:20]
    summaries = {}
    if candidates:
        ids = [item['tid'] for item in candidates]
        result = conn.execute(f"SELECT {SUMMARY_SQL} FROM threads t LEFT JOIN thread_feedback tf ON tf.tid=t.tid WHERE t.tid IN ({','.join('?' for _ in ids)})", ids)
        summaries = {row['tid']: _summary(row, base_url, config) for row in result}
    return {'status': 'ready' if eligible else 'insufficient', 'tracked_count': len(histories),
            'eligible_count': eligible, 'items': [{**summaries[item['tid']], **item} for item in candidates],
            'note': note if eligible else empty['note']}


def query_insights(database_path: str, base_url: str, params: dict, *, config: dict | None = None) -> dict:
    days, start, end, previous_start, previous_end, end_exclusive = _period(params)
    fid = str(_first(params, 'fid', '')).strip()
    preview = _first(params, 'mode', 'full') == 'preview'
    conn = connect_db(database_path)
    try:
        conn.execute('PRAGMA query_only = ON')
        conn.execute('BEGIN')
        rows = conn.execute(f"""
            SELECT {SUMMARY_SQL} FROM threads t LEFT JOIN thread_feedback tf ON tf.tid=t.tid
            WHERE t.posted_at >= ? AND t.posted_at < ?
              AND (? = '' OR t.fid=?) AND COALESCE(tf.feedback, '') != 'dislike'
            ORDER BY t.posted_at DESC, t.tid DESC LIMIT ?
            """, ((start if preview else previous_start).isoformat(), end_exclusive.isoformat(), fid, fid, MAX_PERIOD_ROWS + 1)).fetchall()
        if len(rows) > MAX_PERIOD_ROWS:
            raise ValueError('该范围的帖子过多，请缩短周期或选择一个板块')
        current, previous = [], []
        for row in rows:
            (current if row['posted_at'][:10] >= start.isoformat() else previous).append(_summary(row, base_url, config))
        ranks = _cohort_ranks(current)
        if preview:
            missed = _missed(current, ranks)
            growth = _growth(conn, base_url, start, end_exclusive, fid, config)
            return {
                'missed': {**missed, 'items': missed['items'][:2]},
                'growth': {**growth, 'items': growth['items'][:2]},
            }
        daily = Counter(item['posted_at'][:10] for item in current)
        forums = Counter(item['fid'] for item in current)
        forum_names = {item['fid']: item['forum_name'] for item in current}
        latest = conn.execute("SELECT MAX(list_fetched_at) FROM threads WHERE ? = '' OR fid=?", (fid, fid)).fetchone()[0]
        return {
            'period': {'from': start.isoformat(), 'to': end.isoformat(), 'previous_from': previous_start.isoformat(),
                       'previous_to': previous_end.isoformat(), 'days': days},
            'scope': {'fid': fid, 'latest_fetched_at': latest, 'note': SAMPLE_NOTE},
            'overview': {'total': len(current), 'previous_total': len(previous),
                         'unseen': sum(not i['seen'] for i in current), 'liked': sum(i['feedback'] == 'like' for i in current),
                         'daily': [{'date': (start + timedelta(days=n)).isoformat(), 'count': daily[(start + timedelta(days=n)).isoformat()]} for n in range(days)],
                         'forums': [{'fid': key, 'forum_name': forum_names[key], 'count': count} for key, count in forums.most_common()]},
            'missed': _missed(current, ranks), 'topics': _topics(current, previous),
            'authors': _authors(current, ranks), 'growth': _growth(conn, base_url, start, end_exclusive, fid, config),
        }
    finally:
        conn.close()
