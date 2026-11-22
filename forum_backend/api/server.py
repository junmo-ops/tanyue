from __future__ import annotations

import base64
import hmac
import os
import gzip
import hashlib
import json
import ipaddress
import mimetypes
import re
import socket
import shutil
import secrets
import threading
import sqlite3
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from forum_backend.config import configured_fids, database_settings
from forum_backend.services.comment_jobs import CommentJobs
from forum_backend.services.crawl_jobs import CrawlBusy, CrawlJobs
from forum_backend.services.sites import SiteRegistry, discover, probe
from forum_backend.services.rankings import read_rankings

from forum_backend.api.services import (
    DEFAULT_CONFIG,
    DEFAULT_HOST,
    DEFAULT_PORT,
    handle_api_comment_fetch,
    handle_api_comment_progress,
    handle_api_feedback,
    handle_api_forums,
    handle_api_insights,
    handle_api_seen,
    handle_api_status,
    handle_api_thread,
    handle_api_threads,
    handle_api_title_words,
    init_db,
    load_config,
    resolve_database_path,
    site_settings,
)

def resolve_static_target(static_root: Path, path: str) -> Path | None:
    """解析静态资源路径，并为前端 SPA 路由回退到 index.html。"""
    if path in {"", "/"}:
        path = "/index.html"
    relative = path.lstrip("/")
    root = static_root.resolve()
    target = (static_root / relative).resolve()
    if root != target and root not in target.parents:
        return None
    if target.exists() and target.is_file():
        return target
    # 非 API 的未知路径按前端路由处理，统一回退到 index.html。
    index = (static_root / "index.html").resolve()
    if (root == index or root in index.parents) and index.exists() and index.is_file():
        return index
    return None


class ForumRequestHandler(BaseHTTPRequestHandler):
    """本地论坛浏览器的 HTTP 请求处理器。"""

    server_version = "ForumApi/1.0"

    def _authorized(self):
        host = self.headers.get('Host', '')
        if getattr(self.server, 'local_only', False) and host.split(':')[0].lower() not in ('localhost', '127.0.0.1'):
            self.send_error(403)
            return False
        trusted = getattr(self.server, 'trusted_subnet', None)
        if trusted is not None:
            if (host.partition(':')[0] != self.server.server_address[0]
                    or ipaddress.ip_address(self.client_address[0]) not in trusted):
                self.send_error(403)
                return False
        cli = getattr(self.server, 'tailscale_cli', None)
        if cli and (host.partition(':')[0] != self.server.server_address[0]
                    or not is_tailnet_peer(cli, self.client_address[0])):
            self.send_error(403)
            return False
        origin = self.headers.get('Origin')
        if self.command == 'POST' and origin and origin not in ('http://' + host, 'https://' + host):
            self.send_error(403)
            return False
        credential = getattr(self.server, 'credential', None)
        if credential and not hmac.compare_digest(self.headers.get('Authorization', '').encode(), credential):
            self.send_response(401)
            self.send_header('WWW-Authenticate', 'Basic realm="Discuz Reader", charset="UTF-8"')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            return False
        return True

    def _select_site(self):
        key = self.headers.get('X-Forum-Site', 'default')
        self.site = self.server.sites.runtimes.get(key)
        if self.site is None:
            self._send_json({'error': '站点不存在'}, 404)
            return False
        return True

    def do_GET(self) -> None:
        """处理查询类 API 和静态资源请求。"""
        if not self._authorized():
            return
        parsed = urlparse(self.path)
        if parsed.path == '/api/sites':
            self._send_json(self.server.sites.listing(), 200)
            return
        if parsed.path.startswith('/api/') and not self._select_site():
            return
        if parsed.path == '/api/rankings':
            params = parse_qs(parsed.query)
            try:
                snapshot = params.get('snapshot', [''])[0]
                if snapshot and not re.fullmatch(r'[1-9][0-9]{0,18}', snapshot):
                    raise ValueError('无效的快照编号')
                body = read_rankings(
                    self.site.database_path, self.site.base_url,
                    params.get('metric', ['replies'])[0], params.get('period', ['today'])[0],
                    int(snapshot) if snapshot else None,
                )
                self._send_json(body, 200)
            except ValueError as exc:
                self._send_json({'error': str(exc)}, 400)
            except sqlite3.Error as exc:
                print(f'database error: {exc}', file=sys.stderr)
                self._send_json({'error': '榜单数据库暂时不可用，请稍后重试'}, 500)
            return
        if parsed.path == '/api/crawl-admin':
            self._send_json(self.site.crawl_jobs.admin(), 200)
            return
        if parsed.path == '/api/crawl-jobs':
            self._send_json(self.site.crawl_jobs.list(), 200)
            return
        if parsed.path == '/api/comment-jobs':
            try:
                job_id = parse_qs(parsed.query).get('id', [''])[0]
                self._send_json(self.site.comment_jobs.get(job_id), 200)
            except ValueError as exc:
                self._send_json({'error': str(exc)}, 404)
            except sqlite3.Error as exc:
                print(f'database error: {exc}', file=sys.stderr)
                self._send_json({'error': 'database error'}, 500)
            return
        if parsed.path == "/api/insights":
            body, status = handle_api_insights(
                self.site.database_path, self.site.base_url, parse_qs(parsed.query),
                config=self.site.config,
            )
            self._send_json(body, status)
            return
        if parsed.path == "/api/threads":
            params = {key: values for key, values in parse_qs(parsed.query).items()}
            body, status = handle_api_threads(
                self.site.database_path,
                self.site.base_url,
                params,
                config=self.site.config,
            )
            self._send_json(body, status)
            return
        if parsed.path == "/api/thread":
            params = {key: values for key, values in parse_qs(parsed.query).items()}
            body, status = handle_api_thread(
                self.site.database_path,
                self.site.base_url,
                params,
                config=self.site.config,
            )
            self._send_json(body, status)
            return
        if parsed.path == "/api/forums":
            config = self.site.config
            fids = tuple(configured_fids(config)) if config else ()
            body, status = handle_api_forums(self.site.database_path, fids, config=config)
            self._send_json(body, status)
            return
        if parsed.path == "/api/status":
            body, status = handle_api_status(self.site.database_path, self.site.environment)
            self._send_json(body, status)
            return
        if parsed.path == "/api/title-words":
            params = {key: values for key, values in parse_qs(parsed.query).items()}
            body, status = handle_api_title_words(self.site.database_path, params)
            self._send_json(body, status)
            return
        if parsed.path == "/api/comment-progress":
            params = {key: values for key, values in parse_qs(parsed.query).items()}
            body, status = handle_api_comment_progress(params, str(self.site.database_path))
            self._send_json(body, status)
            return
        self._serve_static(parsed.path)

    def do_POST(self) -> None:
        """处理会修改本地状态的 JSON API。"""
        if not self._authorized():
            return
        parsed = urlparse(self.path)
        site_actions = {'/api/sites': self.server.sites.add,
                        '/api/sites/discover': discover, '/api/sites/probe': probe}
        if parsed.path in site_actions:
            if self.headers.get_content_type() != 'application/json':
                self._send_json({'error': '需要 application/json'}, 415)
                return
            try:
                body = self._read_json_body()
                if body is None:
                    raise ValueError('无效的 JSON 对象')
                self._send_json(site_actions[parsed.path](body), 200)
            except (RuntimeError, ValueError, OSError) as exc:
                self._send_json({'error': str(exc)}, 400)
            return
        if not self._select_site():
            return
        crawl_actions = {
            '/api/crawl-jobs': self.site.crawl_jobs.submit,
            '/api/rankings/refresh': lambda body: self.site.crawl_jobs.submit_rankings(),
            '/api/crawl-jobs/stop': lambda body: self.site.crawl_jobs.stop(body.get('id')),
            '/api/crawl-jobs/resume': lambda body: self.site.crawl_jobs.resume(body.get('id')),
            '/api/crawl-jobs/preview': self.site.crawl_jobs.preview,
            '/api/crawl-admin/settings': self.site.crawl_jobs.save_settings,
            '/api/crawl-admin/check-login': lambda body: self.site.crawl_jobs.check_login(),
            '/api/crawl-admin/presets': self.site.crawl_jobs.save_preset,
            '/api/crawl-admin/presets/run': lambda body: self.site.crawl_jobs.run_preset(body.get('id')),
            '/api/crawl-admin/presets/delete': lambda body: self.site.crawl_jobs.delete_preset(body.get('id')),
            '/api/crawl-admin/schedules': self.site.crawl_jobs.save_schedule,
            '/api/crawl-admin/schedules/delete': lambda body: self.site.crawl_jobs.delete_schedule(body.get('id')),
        }
        if parsed.path in crawl_actions:
            # Require JSON so cross-origin HTML forms cannot launch crawls.
            if self.headers.get('Content-Type', '').split(';')[0].strip() != 'application/json':
                self._send_json({'error': '需要 application/json'}, 415)
                return
            body = self._read_json_body()
            if body is None:
                self._send_json({'error': 'invalid json object'}, 400)
                return
            try:
                result = crawl_actions[parsed.path](body)
                self._send_json(result, 202)
            except CrawlBusy as exc:
                self._send_json({'error': str(exc)}, 409)
            except ValueError as exc:
                self._send_json({'error': str(exc)}, 400)
            except sqlite3.Error:
                self._send_json({'error': '数据库暂时不可用，请稍后重试'}, 500)
            return
        if parsed.path == '/api/comment-jobs':
            body = self._read_json_body()
            if not isinstance(body, dict):
                self._send_json({'error': 'invalid json object'}, 400)
                return
            try:
                self._send_json(self.site.comment_jobs.submit(body.get('tid')), 202)
            except ValueError as exc:
                self._send_json({'error': str(exc)}, 400)
            except sqlite3.Error as exc:
                print(f'database error: {exc}', file=sys.stderr)
                self._send_json({'error': 'database error'}, 500)
            return
        if parsed.path == "/api/feedback":
            body = self._read_json_body()
            if body is None:
                self._send_json({"error": "invalid json"}, 400)
                return
            payload, status = handle_api_feedback(self.site.database_path, body)
            self._send_json(payload, status)
            return
        if parsed.path == "/api/seen":
            body = self._read_json_body()
            if body is None:
                self._send_json({"error": "invalid json"}, 400)
                return
            payload, status = handle_api_seen(self.site.database_path, body)
            self._send_json(payload, status)
            return
        if parsed.path == "/api/comment-fetch":
            body = self._read_json_body()
            if body is None:
                self._send_json({"error": "invalid json"}, 400)
                return
            payload, status = handle_api_comment_fetch(self.site.database_path, body)
            self._send_json(payload, status)
            return
        self.send_error(404)

    def _read_json_body(self) -> dict | None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if not 0 <= length <= 1024 * 1024:
            return None
        raw_body = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw_body.decode("utf-8"))
            return body if isinstance(body, dict) else None
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None

    def _send_json(self, body: dict, status: int) -> None:
        """按 UTF-8 JSON 格式返回响应。"""
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Vary", "X-Forum-Site")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _serve_static(self, path: str) -> None:
        """返回前端构建产物中的静态文件。"""
        static_root = self.server.static_root
        target = resolve_static_target(static_root, path)
        if target is None:
            self.send_error(404)
            return

        content = target.read_bytes()
        content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        accepted_encodings = {
            encoding.strip().lower()
            for encoding in self.headers.get("Accept-Encoding", "").split(",")
        }
        compress = (
            "gzip" in accepted_encodings
            and len(content) >= 1024
            and (content_type.startswith("text/") or content_type in {
                "application/javascript", "application/json", "image/svg+xml",
            })
        )
        if compress:
            content = gzip.compress(content, compresslevel=5, mtime=0)
        etag = '"' + hashlib.sha256(content).hexdigest() + '"'
        versioned_asset = (
            target.parent == Path(self.server.static_root).resolve() / "assets"
            and re.search(r"-[A-Za-z0-9_-]{8,}\.(?:js|css)$", target.name)
        )
        validators = self.headers.get("If-None-Match", "").split(",")
        not_modified = any(value.strip().removeprefix("W/") in {etag, "*"} for value in validators)
        self.send_response(304 if not_modified else 200)
        self.send_header("Content-Type", content_type)
        self.send_header("Vary", "Accept-Encoding")
        self.send_header("ETag", etag)
        self.send_header("Cache-Control", "public, max-age=31536000, immutable" if versioned_asset else "no-cache")
        if compress:
            self.send_header("Content-Encoding", "gzip")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        if not not_modified:
            self.wfile.write(content)


class ForumServer(ThreadingHTTPServer):
    """携带数据库路径、站点域名和静态目录的 HTTPServer。"""

    def __init__(
        self,
        server_address,
        handler_class,
        database_path: str,
        base_url: str,
        static_root: Path,
        environment: str = "",
        config: dict | None = None,
    ):
        """初始化服务实例，并保存请求处理器需要的运行时配置。"""
        self.local_only = server_address[0] in ('127.0.0.1', 'localhost')
        password = os.environ.get('FORUM_PASSWORD', '')
        if not self.local_only and not password:
            raise ValueError('局域网或远程访问需要先设置 FORUM_PASSWORD')
        self.credential = b'Basic ' + base64.b64encode(('admin:' + password).encode()) if password else None
        super().__init__(server_address, handler_class)
        self.database_path = database_path
        self.base_url = base_url
        self.static_root = static_root
        self.environment = environment
        self.config = config
        self.comment_jobs = CommentJobs(database_path, base_url, config)
        self.crawl_jobs = CrawlJobs(database_path, config)
        self.sites = SiteRegistry(self)


def lan_ipv4_candidates(subnets=None) -> list[str]:
    """Best-effort local interface discovery; never advertise loopback addresses."""
    candidates = []
    if sys.platform == 'darwin':
        try:
            output = subprocess.run(['/sbin/ifconfig'], capture_output=True, text=True,
                                    timeout=2, check=True).stdout
            interface = ''
            addresses = []
            active = False
            # Only physical Ethernet/Wi-Fi interfaces; skip loopback and VPN tunnels.
            for line in [*output.splitlines(), 'end:']:
                if line and not line[0].isspace():
                    if interface.startswith('en') and active:
                        candidates.extend(addresses)
                    interface = line.split(':', 1)[0]
                    addresses, active = [], False
                parts = line.split()
                if len(parts) >= 2 and parts[0] == 'inet':
                    addresses.append(parts[1])
                    if subnets is not None and interface.startswith('en') and len(parts) >= 4 and parts[2] == 'netmask':
                        try:
                            mask = str(ipaddress.IPv4Address(int(parts[3], 16)))
                            subnets[parts[1]] = ipaddress.IPv4Network((parts[1], mask), strict=False)
                        except ValueError:
                            pass
                if parts == ['status:', 'active']:
                    active = True
        except (OSError, subprocess.SubprocessError):
            pass
    if not candidates:
        try:
            candidates.extend(item[4][0] for item in socket.getaddrinfo(
                socket.gethostname(), None, socket.AF_INET, socket.SOCK_STREAM))
        except OSError:
            pass
    result = []
    for value in candidates:
        try:
            address = ipaddress.IPv4Address(value)
        except ipaddress.AddressValueError:
            continue
        if not (address.is_loopback or address.is_unspecified or address.is_link_local or address.is_multicast) and value not in result:
            result.append(value)
    return result


def print_access_urls(host: str, port: int) -> None:
    local_host = '127.0.0.1' if host == '0.0.0.0' else host
    print(f'Serving local forum browser at http://{local_host}:{port}')
    if host == '0.0.0.0':
        addresses = lan_ipv4_candidates()
        if addresses:
            for address in addresses:
                print(f'Other devices on the same LAN can try: http://{address}:{port}/admin')
        else:
            print(f'LAN access is enabled on port {port}, but the LAN IP could not be detected.')
            print(f'Check this computer\'s Network settings, then use http://<LAN-IP>:{port}/admin')


def start_lan_listener(server, trusted_subnet=None, *, private_access=False):
    networks = tuple(ipaddress.ip_network(cidr) for cidr in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16'))
    subnets = {}
    for address in lan_ipv4_candidates(subnets):
        if not any(ipaddress.ip_address(address) in network for network in networks):
            continue
        network = subnets.get(address)
        if private_access and (not network or not any(network.subnet_of(private) for private in networks)):
            continue
        try:
            lan = ThreadingHTTPServer((address, server.server_port), ForumRequestHandler)
        except OSError:
            continue
        lan.sites = server.sites
        lan.static_root = server.static_root
        lan.credential = None if private_access else server.credential
        lan.trusted_subnet = None
        if (not lan.credential and network and (private_access or str(network) == trusted_subnet)
                and any(network.subnet_of(private) for private in networks)):
            lan.trusted_subnet = network
        if not lan.credential and not lan.trusted_subnet:
            password = secrets.token_urlsafe(9)
            lan.credential = b'Basic ' + base64.b64encode(('admin:' + password).encode())
            print(f'手机登录密码：{password}')
        login = '本地子网免密' if lan.trusted_subnet else '用户名：admin'
        print(f'同一局域网访问：http://{address}:{server.server_port}/ （{login}）')
        threading.Thread(target=lan.serve_forever, daemon=True).start()
        return lan
    print('未找到可监听的私有局域网地址，当前仅支持本机访问。')
    return None


TAILNET_V4 = ipaddress.ip_network('100.64.0.0/10')


def is_tailnet_peer(cli, peer):
    try:
        if ipaddress.ip_address(peer) not in TAILNET_V4:
            return False
        result = subprocess.run([cli, 'whois', '--json', peer], check=True,
                                capture_output=True, text=True, timeout=3)
        node = json.loads(result.stdout).get('Node') or {}
        return peer + '/32' in node.get('Addresses', [])
    except (OSError, ValueError, subprocess.SubprocessError):
        return False


def start_tailnet_listener(server):
    cli = shutil.which('tailscale')
    if not cli and Path('/Applications/Tailscale.app/Contents/MacOS/Tailscale').is_file():
        cli = '/Applications/Tailscale.app/Contents/MacOS/Tailscale'
    if not cli:
        return None
    try:
        result = subprocess.run([cli, 'ip', '-4'], check=True, capture_output=True, text=True, timeout=3)
        address = ipaddress.IPv4Address(result.stdout.strip())
        if address not in TAILNET_V4:
            return None
        tailnet = ThreadingHTTPServer((str(address), server.server_port), ForumRequestHandler)
    except (OSError, ValueError, subprocess.SubprocessError):
        print('Tailscale 入口未开启，请确认 Tailscale 已连接后重新启动坛阅。')
        return None
    tailnet.sites = server.sites
    tailnet.static_root = server.static_root
    tailnet.tailscale_cli = cli
    threading.Thread(target=tailnet.serve_forever, daemon=True).start()
    print(f'Tailscale 访问：http://{address}:{server.server_port}/')
    return tailnet


def run_server(config_path: str = DEFAULT_CONFIG, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, *, auto_lan: bool = False) -> None:
    """启动本地 API 与前端静态文件服务。"""
    config = load_config(config_path)
    database_path = resolve_database_path(config)
    base_url = site_settings(config).get("base_url", "")
    environment = str(database_settings(config).get("environment", ""))
    static_root = Path(__file__).resolve().parents[2] / "web"
    conn = init_db(database_path)
    conn.close()
    server = ForumServer((host, port), ForumRequestHandler, database_path, base_url, static_root, environment, config)
    lan = tailnet = None
    private_access = (auto_lan and host == DEFAULT_HOST
                      and config.get('server', {}).get('private_network_access') is True)
    try:
        print_access_urls(host, server.server_port)
        if private_access:
            server.credential = None
            lan = start_lan_listener(server, private_access=True)
            tailnet = start_tailnet_listener(server)
        elif auto_lan and host == DEFAULT_HOST and (sys.stdout.isatty() or server.credential):
            lan = start_lan_listener(server, config.get('server', {}).get('trusted_lan_subnet'))
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nLocal forum browser stopped.")
    finally:
        for listener in (lan, tailnet):
            if listener is not None:
                listener.shutdown()
                listener.server_close()
        server.sites.close()
        server.crawl_jobs.close()
        server.comment_jobs.close()
        server.server_close()


if __name__ == "__main__":
    run_server()
