import importlib.util
import pathlib
import unittest
import io
import http.client
import threading
import tempfile
import urllib.error
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location(
    'maven_route', pathlib.Path(__file__).parents[1] / 'maven-route.py')
route = importlib.util.module_from_spec(spec)
spec.loader.exec_module(route)


class MavenRouteTests(unittest.TestCase):
    def test_aliyun_success_never_requests_central(self):
        opener = Mock()
        response, origin = route.fetch_artifact('g/a/1/a-1.pom', opener)
        self.assertIs(response, opener.open.return_value)
        self.assertEqual(origin, route.ALIYUN)
        opener.open.assert_called_once_with(route.ALIYUN + 'g/a/1/a-1.pom', timeout=60)

    def test_only_404_falls_back_for_same_artifact(self):
        opener = Mock()
        opener.open.side_effect = [urllib.error.HTTPError('url', 404, '', {}, None), Mock()]
        _, origin = route.fetch_artifact('g/a/1/a-1.jar', opener)
        self.assertEqual(origin, route.CENTRAL)
        self.assertEqual([call.args[0] for call in opener.open.call_args_list],
                         [route.ALIYUN + 'g/a/1/a-1.jar', route.CENTRAL + 'g/a/1/a-1.jar'])

    def test_http_errors_fail_closed(self):
        for status in (401, 403, 429, 500, 502, 301):
            with self.subTest(status=status):
                opener = Mock()
                opener.open.side_effect = urllib.error.HTTPError('url', status, '', {}, None)
                with self.assertRaises(urllib.error.HTTPError):
                    route.fetch_artifact('a.pom', opener)
                self.assertEqual(opener.open.call_count, 1)

    def test_tls_timeout_and_connection_errors_do_not_fallback(self):
        for error in (urllib.error.URLError('TLS'), TimeoutError(), ConnectionError()):
            opener = Mock()
            opener.open.side_effect = error
            with self.assertRaises((OSError, urllib.error.URLError)):
                route.fetch_artifact('a.pom', opener)
            self.assertEqual(opener.open.call_count, 1)

    def test_both_missing_preserves_failure(self):
        opener = Mock()
        opener.open.side_effect = urllib.error.HTTPError('url', 404, '', {}, None)
        with self.assertRaises(urllib.error.HTTPError):
            route.fetch_artifact('a.pom', opener)
        self.assertEqual(opener.open.call_count, 2)

    def test_paths_cannot_escape_fixed_upstreams(self):
        for path in ('https://evil/a', '//evil/a', '/../a', '/%2e%2e/a', '/a?url=x', '/a%5cb', '/a%00'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                route.artifact_path(path)
        self.assertEqual(route.artifact_path('/org/example/a.pom.sha1'), 'org/example/a.pom.sha1')

    def test_all_maven_builds_use_router(self):
        script = (pathlib.Path(__file__).parents[1] / 'package.sh').read_text(encoding='utf-8')
        self.assertEqual(script.count('"$tools/maven-route.py"'), 2)
        self.assertNotIn('; mvn -B', script)

    def test_settings_preserve_private_repositories_credentials_and_proxies(self):
        xml = '''<settings xmlns="http://maven.apache.org/SETTINGS/1.0.0">
        <servers><server><id>private</id><password>fixture</password></server></servers>
        <proxies><proxy><host>proxy.example</host></proxy></proxies>
        <mirrors><mirror><id>private</id><mirrorOf>internal</mirrorOf></mirror></mirrors>
        <profiles><profile><id>company</id><repositories><repository><id>internal</id>
        <url>https://private.example</url></repository></repositories></profile></profiles>
        </settings>'''
        root = route.ET.fromstring(route.settings_xml('http://127.0.0.1:123/', xml))
        self.assertEqual(root.findtext('servers/server/password'), 'fixture')
        self.assertEqual(root.findtext('proxies/proxy/host'), 'proxy.example')
        self.assertEqual(root.findtext('profiles/profile/repositories/repository/url'), 'https://private.example')
        mirrors = root.findall('mirrors/mirror')
        self.assertEqual([m.findtext('mirrorOf') for m in mirrors], ['internal', 'central'])
        checks = root.findall('.//checksumPolicy')
        self.assertEqual([item.text for item in checks], ['fail', 'fail'])

    def test_conflicting_mirror_requires_review(self):
        for pattern in ('central', '*', 'external:*'):
            with self.assertRaises(ValueError):
                route.settings_xml('http://127.0.0.1:123/',
                                   f'<settings><mirrors><mirror><mirrorOf>{pattern}</mirrorOf></mirror></mirrors></settings>')

    def test_runner_passes_settings_and_preserves_maven_exit_status(self):
        with tempfile.TemporaryDirectory() as folder:
            home = pathlib.Path(folder)
            def command(argv):
                self.assertEqual(argv[0], '/tool/mvn')
                root = route.ET.fromstring(pathlib.Path(argv[2]).read_text(encoding='utf-8'))
                self.assertEqual(root.findtext('mirrors/mirror/mirrorOf'), 'central')
                self.assertTrue(root.findtext('mirrors/mirror/url').startswith('http://127.0.0.1:'))
                self.assertEqual(argv[3:], ['-B', 'validate'])
                return 7
            with patch.object(route.pathlib.Path, 'home', return_value=home), \
                    patch.object(route.shutil, 'which', return_value='/tool/mvn'), \
                    patch.object(route.subprocess, 'call', side_effect=command), \
                    patch('sys.argv', ['maven-route.py', '--audit', str(home / 'audit.jsonl'), '--', '-B', 'validate']):
                self.assertEqual(route.main(), 7)

    def test_http_proxy_returns_exact_bytes_and_audits_fallback(self):
        opener = Mock()
        response = io.BytesIO(b'<project>fixed bytes</project>')
        response.status = 200
        response.headers = {'Content-Length': '30', 'Set-Cookie': 'never-forward'}
        # Use the real byte length, not a fixture that can mask truncation.
        response.headers['Content-Length'] = str(len(response.getvalue()))
        opener.open.side_effect = [urllib.error.HTTPError('url', 404, '', {}, None), response]
        records = []
        server = route.http.server.ThreadingHTTPServer(
            ('127.0.0.1', 0), route.handler_factory(opener, records.append))
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
        try:
            connection.request('GET', '/g/a/1/a.pom')
            result = connection.getresponse()
            self.assertEqual(result.status, 200)
            self.assertEqual(result.read(), b'<project>fixed bytes</project>')
            self.assertIsNone(result.getheader('Set-Cookie'))
            self.assertEqual(records, [{'artifact': 'g/a/1/a.pom',
                                        'origin': route.CENTRAL, 'status': 200}])
        finally:
            connection.close()
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == '__main__':
    unittest.main()
