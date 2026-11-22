"""Read and archive Discuz thread rankings in their original order."""
from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlencode, urlparse

from forum_backend.config import build_source_url
from .crawl_store import database

RANK_METRICS = ('replies', 'views', 'sharetimes', 'favtimes', 'heats')
RANK_PERIODS = ('today', 'thisweek', 'thismonth', 'all')
RANK_SCOPES = tuple((metric, period) for metric in RANK_METRICS for period in RANK_PERIODS)
RANK_LABELS = dict(zip(RANK_METRICS, ('回复', '查看', '分享', '收藏', '热度')))
PERIOD_LABELS = dict(zip(RANK_PERIODS, ('今日', '本周', '本月', '全部')))


def rank_url(base_url, metric, period):
    query = urlencode({'mod': 'ranklist', 'type': 'thread', 'view': metric, 'orderby': period})
    return build_source_url(base_url, f'misc.php?{query}')


class RankingParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.period_links = set()
        self.active_period = None
        self.empty = False
        self.rows = []
        self.row = None
        self.cell = None

    def handle_starttag(self, tag, attrs):
        attr = dict(attrs)
        classes = (attr.get('class') or '').split()
        if tag == 'div' and 'emp' in classes:
            self.empty = True
        if tag == 'tr':
            self.row = []
            self.cell = None
        if tag in ('td', 'th') and self.row is not None:
            self.cell = {'parts': [], 'href': '', 'rank': False}
            self.row.append(self.cell)
        if tag == 'span' and self.cell is not None and 'ranks' in classes:
            self.cell['rank'] = True
        if tag == 'a':
            href = attr.get('href') or ''
            if self.cell is not None and not self.cell['href']:
                self.cell['href'] = href
            query = parse_qs(urlparse(href).query)
            if query.get('mod') == ['ranklist'] and query.get('type') == ['thread'] and attr.get('id') in ('86400', '604800', '2592000', 'all'):
                scope = (query.get('view', [''])[0], query.get('orderby', [''])[0])
                self.period_links.add(scope)
                if 'a' in classes:
                    self.active_period = scope

    def handle_data(self, data):
        if self.cell is not None:
            self.cell['parts'].append(data)

    def handle_endtag(self, tag):
        if tag in ('td', 'th'):
            self.cell = None
        if tag == 'tr' and self.row is not None:
            if self.row and self.row[0]['rank']:
                self.rows.append(self.row)
            self.row = None
            self.cell = None


def parse_ranking(html, metric, period):
    parser = RankingParser()
    parser.feed(html)
    parser.close()
    if (parser.active_period != (metric, period)
            or not all((metric, key) in parser.period_links for key in RANK_PERIODS)
            or not (parser.rows or parser.empty)):
        raise ValueError('未识别到所选榜单，请检查论坛登录状态或访问验证')

    entries = []
    seen = set()
    for row in parser.rows:
        if len(row) != 5:
            raise ValueError('论坛榜单列结构有变化')
        rank, title, forum, author_and_date, value = [
            ' '.join(''.join(cell['parts']).split()) for cell in row
        ]
        tid = parse_qs(urlparse(row[1]['href']).query).get('tid', [''])[0]
        if not tid:
            match = re.search(r'(?:^|/)thread-(\d+)-\d+-\d+\.html$', urlparse(row[1]['href']).path)
            tid = match[1] if match else ''
        value = value.replace(',', '').replace('，', '')
        if (rank != str(len(entries) + 1) or not re.fullmatch(r'[0-9]+', tid)
                or tid in seen or not title or not re.fullmatch(r'[0-9]+', value)):
            raise ValueError('论坛榜单的名次、帖子或数值格式有变化')
        seen.add(tid)
        entries.append({
            'rank': int(rank), 'tid': tid, 'title': title, 'forum': forum,
            'author_and_date': author_and_date, 'value': int(value),
        })
    return entries


def read_rankings(path, base_url, metric, period, snapshot_id=None):
    if (metric, period) not in RANK_SCOPES:
        raise ValueError('无效的排行榜类型或周期')
    with database(path) as conn:
        conn.execute('BEGIN')
        snapshots = conn.execute('''
            SELECT id, captured_at FROM ranking_snapshots
            WHERE metric=? AND period=? ORDER BY id DESC
        ''', (metric, period)).fetchall()
        if snapshot_id:
            selected = next((row for row in snapshots if row['id'] == snapshot_id), None)
            if selected is None:
                raise ValueError('找不到这份榜单快照')
        else:
            selected = snapshots[0] if snapshots else None
        entries = []
        if selected:
            entries = json.loads(conn.execute(
                'SELECT entries FROM ranking_snapshots WHERE id=?', (selected['id'],)
            ).fetchone()['entries'])
        job = conn.execute("""
            SELECT id, status, log FROM crawl_jobs WHERE kind='rankings'
            ORDER BY CASE WHEN status IN ('queued', 'running', 'stopping') THEN 0 ELSE 1 END, rowid DESC LIMIT 1
        """).fetchone()
        summary = None
        if job:
            records = conn.execute('SELECT status, target, error FROM crawl_units WHERE job_id=?', (job['id'],)).fetchall()
            scope = next((row for row in records if row['target'] == f'{metric}/{period}'), None)
            log_lines = job['log'].strip().splitlines()
            summary = {
                'status': job['status'],
                'completed': sum(row['status'] == 'succeeded' for row in records),
                'failed': sum(row['status'] == 'failed' for row in records),
                'total': len(RANK_SCOPES),
                'scope_error': scope['error'] if scope and scope['status'] == 'failed' else '',
                'error': log_lines[-1] if job['status'] == 'failed' and not records and log_lines else '',
            }

    for entry in entries:
        entry['url'] = build_source_url(base_url, f"forum.php?mod=viewthread&tid={entry['tid']}")
    return {
        'snapshot': dict(selected) if selected else None,
        'snapshots': [dict(row) for row in snapshots],
        'entries': entries,
        'source_url': rank_url(base_url, metric, period),
        'job': summary,
    }
