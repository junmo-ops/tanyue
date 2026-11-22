"""Discuz site discovery and independently scheduled site runtimes."""
import copy
import json
import re
import shutil
import threading
from html.parser import HTMLParser
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urljoin, urlsplit, urlunsplit
from uuid import uuid4

from forum_backend.config import extract_tid
from forum_backend.crawler import fetch_page
from forum_backend.db import init_db
from forum_backend.parsers import parse_detail_page, parse_topics
from .comment_jobs import CommentJobs
from .crawl_jobs import CrawlJobs
from .rankings import parse_ranking, rank_url


def connection(body):
    raw = body.get('url')
    cookie = body.get('cookie', '')
    if not isinstance(raw, str) or not isinstance(cookie, str) or (cookie and not cookie.isascii()):
        raise ValueError('请输入有效的论坛网址和 Cookie')
    url = urlsplit(raw.strip())
    if (url.scheme not in ('https', 'http') or not url.hostname or url.username is not None
            or any(ord(c) < 32 or c == '\\' for c in raw) or url.query and not url.path.endswith('forum.php')):
        raise ValueError('请填写论坛安装目录的网址，例如 https://example.com/bbs/')
    if any(ord(c) < 32 or ord(c) == 127 for c in cookie):
        raise ValueError('Cookie 必须为单行')
    path = re.sub(r'/(?:forum|index)\.php$', '/', url.path).rstrip('/') + '/'
    return urlunsplit((url.scheme, url.netloc.lower(), path, '', '')), cookie.strip()


class BoardParser(HTMLParser):
    def __init__(self, base):
        super().__init__()
        self.base = base
        self.boards = {}
        self.has_browser_check = False
        self.fid = None
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == 'script':
            src = urlsplit(dict(attrs).get('src') or '').path.lower()
            if re.search(r'(?:^|/)static/safe/js/(?:web|mainv[0-9]+)\.js$', src):
                self.has_browser_check = True
        if tag != 'a':
            return
        self.fid = None
        self.parts = []
        link = urlsplit(urljoin(self.base, dict(attrs).get('href') or ''))
        if link.netloc != urlsplit(self.base).netloc:
            return
        query = parse_qs(link.query)
        if link.path.endswith('/forum.php') and query.get('mod') == ['forumdisplay']:
            self.fid = query.get('fid', [''])[0]
        else:
            match = re.search(r'/forum-(\d+)-\d+\.html$', link.path)
            self.fid = match[1] if match else None

    def handle_data(self, data):
        if self.fid:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag == 'a' and self.fid:
            name = ' '.join(''.join(self.parts).split())
            if name and re.fullmatch(r'[0-9]+', self.fid):
                self.boards.setdefault(self.fid, name)
            self.fid = None


def discover(body):
    base, cookie = connection(body)
    parser = BoardParser(base)
    parser.feed(fetch_page(urljoin(base, 'forum.php'), cookie, timeout=10, retries=0))
    if not parser.boards and parser.has_browser_check:
        raise ValueError('论坛返回了浏览器验证页。请在浏览器中打开该论坛，完成验证并确认能看到板块，'
                         '再在「登录 Cookie」中填写该域名当前的 Cookie 后重试。')
    if not parser.boards:
        raise ValueError('未识别到板块，请检查论坛安装目录、登录权限或页面模板')
    return {'forums': parser.boards}


def probe(body):
    base, cookie = connection(body)
    fid = body.get('fid', '')
    if not isinstance(fid, str) or not re.fullmatch(r'[0-9]+', fid):
        raise ValueError('请选择板块')
    url = urljoin(base, 'forum.php?mod=forumdisplay&fid=' + fid)
    topics = parse_topics(fetch_page(url, cookie, timeout=10, retries=0), url)
    sample = next((t for t in topics if extract_tid(t.url).isdigit()), None)
    if not sample:
        raise ValueError('该板块未读到帖子，可能为空、需要登录或使用了不同的模板')
    tid = extract_tid(sample.url)
    detail_url = urljoin(base, 'forum.php?mod=viewthread&tid=' + tid)
    try:
        html = fetch_page(detail_url, cookie, timeout=10, retries=0)
        detail = parse_detail_page(html, detail_url, tid, 1, '')
        readable = bool(detail['content_text'] or detail['image_urls'] or detail['comments'])
        comments = len(detail['comments'])
    except (ValueError, RuntimeError):
        readable, comments = False, 0
    try:
        html = fetch_page(rank_url(base, 'replies', 'today'), cookie, timeout=10, retries=0)
        parse_ranking(html, 'replies', 'today')
        rankings = True
    except (ValueError, RuntimeError):
        rankings = False
    return {'title': sample.title, 'count': len(topics), 'detail': readable,
            'comments': comments, 'rankings': rankings}


def sites_directory(database_path):
    database = Path(database_path)
    legacy = database.with_name(database.name + '.sites')
    # Keep custom databases in independent namespaces, even in the same folder.
    if database.name != 'forum.db':
        return legacy
    root = database.parent / 'sites'
    if legacy.exists():
        if root.exists() or root.is_symlink():
            raise ValueError(f'新旧站点目录同时存在，请检查 {root} 和 {legacy}')
        legacy.rename(root)
    return root


class SiteRegistry:
    def __init__(self, default):
        self.default = default
        self.root = sites_directory(default.database_path)
        self.lock = threading.RLock()
        self.closed = False
        self.runtimes = {'default': default}
        self.records = {'default': {'id': 'default', 'name': '默认论坛', 'url': default.base_url}}
        if not default.base_url:
            self.records.clear()
            self.runtimes.clear()
        for file in sorted(self.root.glob('*/site.json')):
            record = json.loads(file.read_text(encoding='utf-8'))
            self._activate(file.parent, record)

    def _activate(self, directory, record):
        config = {key: copy.deepcopy(self.default.config[key])
                  for key in ('list_sync', 'details', 'comments', 'network')}
        path = str(directory / 'forum.db')
        env = self.default.environment or 'production'
        config['site'] = {'name': record['name'], 'base_url': record['url'], 'cookie_file': str(directory / 'cookie.txt'),
                          'anonymous_allowed': True}
        config['database'] = {'environment': env, 'paths': {env: path}}
        config['details']['purchase_count_money_fids'] = []
        config['list_sync'].pop('fids', None)
        config['list_sync']['forums'] = record['forums']
        init_db(path).close()
        comments = CommentJobs(path, record['url'], config)
        try:
            jobs = CrawlJobs(path, config)
        except Exception:
            comments.close()
            raise
        self.runtimes[record['id']] = SimpleNamespace(database_path=path, base_url=record['url'],
            environment=env, config=config, comment_jobs=comments, crawl_jobs=jobs)
        self.records[record['id']] = record

    def listing(self):
        with self.lock:
            return {'items': list(self.records.values())}

    def add(self, body):
        base, cookie = connection(body)
        name, forums = body.get('name'), body.get('forums')
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
            raise ValueError('请输入 1 至 80 字的站点名称')
        if not isinstance(forums, dict) or not forums or not all(
            re.fullmatch(r'[0-9]+', fid) and isinstance(label, str) and label.strip() for fid, label in forums.items()
        ):
            raise ValueError('请至少选择一个板块')
        with self.lock:
            if self.closed:
                raise ValueError('服务正在关闭')
            if any(site['url'].rstrip('/') == base.rstrip('/') for site in self.records.values()):
                raise ValueError('此论坛已接入')
            record = {'id': uuid4().hex, 'url': base, 'name': name.strip(), 'forums': forums}
            directory = self.root / record['id']
            directory.mkdir(parents=True, mode=0o700)
            try:
                (directory / 'cookie.txt').write_text(cookie, encoding='utf-8')
                pending = directory / 'pending.json'
                pending.write_text(json.dumps(record, ensure_ascii=False), encoding='utf-8')
                pending.replace(directory / 'site.json')
                self._activate(directory, record)
            except Exception:
                shutil.rmtree(directory)
                raise
            return record

    def close(self):
        with self.lock:
            self.closed = True
            runtimes = [value for key, value in self.runtimes.items() if key != 'default']
        for runtime in runtimes:
            runtime.crawl_jobs.close()
            runtime.comment_jobs.close()
