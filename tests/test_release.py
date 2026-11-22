import base64
from io import BytesIO
import json
import os
from pathlib import Path
import socket
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.request import Request

from forum_backend.api.server import ForumRequestHandler, ForumServer
from forum_backend.config import load_config
from forum_backend.public_http import SameOriginRedirect, public_connect
from forum_backend.services.sites import SiteRegistry


class ReleaseTests(unittest.TestCase):
    def request(self, server, headers):
        conn = Mock()
        conn.makefile.return_value = BytesIO(f'GET /api/sites HTTP/1.0\r\n{headers}\r\n\r\n'.encode())
        chunks = []
        conn.sendall.side_effect = chunks.append
        with patch.object(ForumRequestHandler, 'log_message'):
            ForumRequestHandler(conn, ('127.0.0.1', 0), server)
        return b''.join(chunks)

    def test_empty_install_and_first_forum_survive_restart(self):
        with tempfile.TemporaryDirectory() as root:
            default = SimpleNamespace(config=load_config(), base_url='', database_path=str(Path(root)/'forum.db'), environment='test')
            registry = SiteRegistry(default)
            try:
                self.assertEqual(registry.listing()['items'], [])
                record = registry.add({'url':'https://example.test/', 'name':'论坛', 'forums':{'1':'讨论'}})
            finally:
                registry.close()
            reopened = SiteRegistry(default)
            try:
                self.assertEqual(reopened.listing()['items'], [record])
            finally:
                reopened.close()

    def test_management_auth_and_host(self):
        credential = b'Basic ' + base64.b64encode(b'admin:test-only')
        sites = SimpleNamespace(listing=lambda: {'items':[]})
        server = SimpleNamespace(local_only=False, credential=credential, sites=sites)
        self.assertIn(b'401 Unauthorized', self.request(server, 'Host: reader'))
        self.assertIn(b'200 OK', self.request(server, 'Host: reader\r\nAuthorization: ' + credential.decode()))
        server.local_only, server.credential = True, None
        self.assertIn(b'403 Forbidden', self.request(server, 'Host: unrelated.example'))
        with patch.dict(os.environ, {'FORUM_PASSWORD':''}), self.assertRaisesRegex(ValueError, 'FORUM_PASSWORD'):
            ForumServer(('0.0.0.0', 0), ForumRequestHandler, '', '', Path('.'))

    def test_private_destinations_and_cross_origin_redirects_are_rejected(self):
        with patch('socket.getaddrinfo', return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', 443))]), patch('socket.socket') as connect:
            with self.assertRaises(ValueError):
                public_connect(('forum.example', 443), 1)
            connect.assert_not_called()
        request = Request('https://example.test/a')
        request.add_unredirected_header('Cookie', 'test-only')
        with self.assertRaises(ValueError):
            SameOriginRedirect().redirect_request(request, None, 302, '', {}, 'https://other.example/b')
