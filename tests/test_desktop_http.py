import http.client
import json
import tempfile
import threading
import unittest
import urllib.request
import http.cookiejar
from pathlib import Path

from desktop_app import create_server
from desktop_service import DesktopService


class LocalHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.server = create_server(DesktopService(Path(self.temp.name), roots=[]))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.origin = self.server.origin
        self.cookie = self.server.cookie_name + '=' + self.server.token

    def request(self, method, path, data=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port)
        payload = json.dumps(data).encode() if data is not None else None
        connection.request(method, path, body=payload, headers=headers or {})
        response = connection.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return result

    def test_private_api_requires_session(self):
        self.assertEqual(self.request('GET', '/api/health')[0], 401)

    def test_session_requires_valid_token_and_exact_origin(self):
        headers = {'Origin': self.origin, 'Content-Type': 'application/json'}
        self.assertEqual(self.request('POST', '/api/session', {'token': 'wrong'}, headers)[0], 401)
        status, response, _ = self.request('POST', '/api/session', {'token': self.server.token}, headers)
        self.assertEqual(status, 200)
        self.assertIn('HttpOnly', response['Set-Cookie'])
        self.assertIn('SameSite=Strict', response['Set-Cookie'])

    def test_cross_origin_mutation_is_rejected_even_with_cookie(self):
        headers = {'Origin': 'https://unrelated.example', 'Cookie': self.cookie}
        self.assertEqual(self.request('POST', '/api/discover', {}, headers)[0], 403)

    def test_wrong_host_is_rejected(self):
        self.assertEqual(self.request('GET', '/', headers={'Host': 'unrelated.example'})[0], 403)

    def test_traversal_and_arbitrary_download_are_rejected(self):
        headers = {'Cookie': self.cookie}
        self.assertEqual(self.request('GET', '/%2e%2e/native_export.py', headers=headers)[0], 404)
        self.assertEqual(self.request('GET', '/api/download?id=unknown&kind=md', headers=headers)[0], 400)

    def test_authenticated_health_and_discovery(self):
        self.assertEqual(self.request('GET', '/api/health', headers={'Cookie': self.cookie})[0], 200)
        status, _, body = self.request('POST', '/api/discover', {}, {'Origin': self.origin, 'Cookie': self.cookie})
        self.assertEqual(status, 202)
        self.assertIn('job', json.loads(body))

    def test_two_instances_share_browser_without_invalidating_sessions(self):
        second = create_server(DesktopService(Path(self.temp.name) / 'second', roots=[]))
        threading.Thread(target=second.serve_forever, daemon=True).start()
        self.addCleanup(second.server_close)
        self.addCleanup(second.shutdown)
        browser = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        for server in (self.server, second):
            request = urllib.request.Request(server.origin + '/api/session', data=json.dumps({'token': server.token}).encode(), headers={'Origin': server.origin})
            with browser.open(request) as response:
                self.assertEqual(response.status, 200)
        for server in (self.server, second):
            with browser.open(server.origin + '/api/health') as response:
                self.assertEqual(response.status, 200)
