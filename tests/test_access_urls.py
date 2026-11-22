import io
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from forum_backend.api.server import lan_ipv4_candidates, print_access_urls, start_lan_listener


class AccessUrlsTests(unittest.TestCase):
    def test_mac_uses_active_lan_interface_not_hostname_loopback(self):
        output = '''lo0: flags=8049
\tinet 127.0.0.1 netmask 0xff000000
en0: flags=8863
\tinet 192.168.1.20 netmask 0xffffff00
\tstatus: active
en1: flags=8863
\tinet 192.168.2.20 netmask 0xffffff00
\tstatus: inactive
utun0: flags=8051
\tinet 10.0.0.1 netmask 0xffffff00
\tstatus: active
'''
        with patch('forum_backend.api.server.sys.platform', 'darwin'), \
             patch('forum_backend.api.server.subprocess.run', return_value=SimpleNamespace(stdout=output)), \
             patch('forum_backend.api.server.socket.getaddrinfo') as dns:
            self.assertEqual(lan_ipv4_candidates(), ['192.168.1.20'])
            dns.assert_not_called()

    def test_unavailable_network_discovery_does_not_break_startup(self):
        with patch('forum_backend.api.server.sys.platform', 'darwin'), \
             patch('forum_backend.api.server.subprocess.run', side_effect=OSError), \
             patch('forum_backend.api.server.socket.getaddrinfo', side_effect=OSError), \
             patch('sys.stdout', new_callable=io.StringIO) as output:
            print_access_urls('0.0.0.0', 8000)
            self.assertIn('http://127.0.0.1:8000', output.getvalue())
            self.assertIn('could not be detected', output.getvalue())
            self.assertNotIn('same LAN can try: http://127.', output.getvalue())

    def test_fallback_filters_invalid_and_duplicate_addresses(self):
        rows = [(None, None, None, None, (ip, 0)) for ip in ['127.0.0.1', '169.254.1.2', '0.0.0.0', '192.168.1.20', '192.168.1.20']]
        with patch('forum_backend.api.server.sys.platform', 'win32'), \
             patch('forum_backend.api.server.socket.getaddrinfo', return_value=rows):
            self.assertEqual(lan_ipv4_candidates(), ['192.168.1.20'])

    def test_auto_listener_binds_one_private_address_and_requires_login(self):
        server = SimpleNamespace(server_port=8000, sites=object(), static_root='web', credential=None)
        with patch('forum_backend.api.server.lan_ipv4_candidates', return_value=['8.8.8.8', '192.168.1.20']), \
             patch('forum_backend.api.server.ThreadingHTTPServer') as listener, \
             patch('forum_backend.api.server.threading.Thread'), patch('builtins.print'):
            lan = start_lan_listener(server)
        self.assertEqual(listener.call_args.args[0], ('192.168.1.20', 8000))
        self.assertTrue(lan.credential.startswith(b'Basic '))
        self.assertIs(lan.sites, server.sites)

    def test_tailnet_identity_must_match_socket_peer(self):
        from forum_backend.api.server import is_tailnet_peer
        response = SimpleNamespace(stdout='{"Node":{"Addresses":["100.64.0.7/32"]}}')
        with patch('forum_backend.api.server.subprocess.run', return_value=response):
            self.assertTrue(is_tailnet_peer('tailscale', '100.64.0.7'))
            self.assertFalse(is_tailnet_peer('tailscale', '100.64.0.8'))
            self.assertFalse(is_tailnet_peer('tailscale', '192.168.1.7'))

    def test_loopback_binding_does_not_advertise_lan_access(self):
        with patch('forum_backend.api.server.lan_ipv4_candidates') as discover, patch('sys.stdout', new_callable=io.StringIO) as output:
            print_access_urls('127.0.0.1', 8000)
            discover.assert_not_called()
            self.assertNotIn('LAN', output.getvalue())
