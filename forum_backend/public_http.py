"""Fetch forum pages using public destinations, including after DNS resolution."""
from http.client import HTTPConnection, HTTPSConnection
from ipaddress import ip_address
import socket
from urllib.parse import urlsplit
from urllib.request import HTTPHandler, HTTPSHandler, HTTPRedirectHandler, ProxyHandler, build_opener


def public_connect(address, timeout, source_address=None):
    host, port = address
    candidates = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    for _, _, _, _, endpoint in candidates:
        ip = ip_address(endpoint[0])
        if not ip.is_global or ip.is_multicast or getattr(ip, 'ipv4_mapped', None):
            raise ValueError('论坛地址必须指向公共网络')
    error = OSError('未找到论坛地址')
    for family, kind, proto, _, endpoint in candidates:
        sock = socket.socket(family, kind, proto)
        try:
            sock.settimeout(timeout)
            if source_address:
                sock.bind(source_address)
            sock.connect(endpoint)
            return sock
        except OSError as exc:
            error = exc
            sock.close()
    raise error


class PublicHTTPHandler(HTTPHandler):
    def http_open(self, request):
        return self.do_open(connection_factory(HTTPConnection), request)


class PublicHTTPSHandler(HTTPSHandler):
    def https_open(self, request):
        return self.do_open(connection_factory(HTTPSConnection), request)


def connection_factory(cls):
    def create(*args, **kwargs):
        conn = cls(*args, **kwargs)
        conn._create_connection = public_connect
        return conn
    return create


class SameOriginRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        old, new = urlsplit(req.full_url), urlsplit(newurl)
        if (old.scheme, old.netloc.lower()) != (new.scheme, new.netloc.lower()):
            raise ValueError('论坛重定向到其他地址，请使用最终安装地址')
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected and req.has_header('Cookie'):
            redirected.add_unredirected_header('Cookie', req.get_header('Cookie'))
        return redirected


def open_forum(request, timeout):
    url = urlsplit(request.full_url)
    if url.scheme not in ('http', 'https') or url.username is not None or not url.hostname:
        raise ValueError('无效的论坛地址')
    opener = build_opener(ProxyHandler({}), PublicHTTPHandler(), PublicHTTPSHandler(), SameOriginRedirect())
    return opener.open(request, timeout=timeout)
