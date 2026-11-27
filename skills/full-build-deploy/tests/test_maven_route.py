import importlib.util
import pathlib
import unittest
import io
import http.client
import threading
import tempfile
import urllib.error
import ssl
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location(
    'maven_route', pathlib.Path(__file__).parents[1] / 'tools' / 'maven-route.py')
route = importlib.util.module_from_spec(spec)
spec.loader.exec_module(route)


class MavenRouteTests(unittest.TestCase):
    def test_gradle_init_covers_settings_plugins_and_included_projects(self):
        text = route.gradle_init('http://127.0.0.1:12345/')
        self.assertIn('beforeSettings', text)
        self.assertIn('pluginManagement.repositories', text)
        self.assertIn('beforeProject', text)
        self.assertIn('buildscript.repositories', text)
        self.assertIn('repo.maven.apache.org', text)
        self.assertIn('repo1.maven.org', text)
        self.assertIn('excludeGroup("com.google.code.gson")', text)
        self.assertIn('allowInsecureProtocol = true', text)
        self.assertIn('http://127.0.0.1:12345/', text)

    def test_tencent_success_never_requests_central(self):
        opener = Mock()
        response, origin = route.fetch_artifact('g/a/1/a-1.pom', opener)
        self.assertIs(response, opener.open.return_value)
        self.assertEqual(origin, route.TENCENT)
        opener.open.assert_called_once_with(route.TENCENT + 'g/a/1/a-1.pom', timeout=60)

    def test_only_404_falls_back_for_same_artifact(self):
        opener = Mock()
        opener.open.side_effect = [urllib.error.HTTPError('url', 404, '', {}, None), Mock()]
        _, origin = route.fetch_artifact('g/a/1/a-1.jar', opener)
        self.assertEqual(origin, route.CENTRAL)
        self.assertEqual([call.args[0] for call in opener.open.call_args_list],
                         [route.TENCENT + 'g/a/1/a-1.jar', route.CENTRAL + 'g/a/1/a-1.jar'])

    def test_http_errors_fail_closed(self):
        for status in (401, 403, 429, 500, 301):
            with self.subTest(status=status):
                opener = Mock()
                opener.open.side_effect = urllib.error.HTTPError('url', status, '', {}, None)
                with self.assertRaises(urllib.error.HTTPError):
                    route.fetch_artifact('a.pom', opener)
                self.assertEqual(opener.open.call_count, 1)

    def test_tls_timeout_and_connection_errors_do_not_fallback(self):
        for error in (urllib.error.URLError('TLS'), ConnectionError(), urllib.error.URLError(ssl.SSLCertVerificationError('fixture'))):
            opener = Mock()
            opener.open.side_effect = error
            with self.assertRaises((OSError, urllib.error.URLError)):
                route.fetch_artifact('a.pom', opener)
            self.assertEqual(opener.open.call_count, 1)

    def test_transient_failures_retry_same_origin_with_bounded_backoff(self):
        for error in (urllib.error.HTTPError('url', 502, '', {}, None),
                      urllib.error.HTTPError('url', 503, '', {}, None),
                      urllib.error.HTTPError('url', 504, '', {}, None),
                      TimeoutError(), urllib.error.URLError(ConnectionResetError())):
            with self.subTest(error=type(error).__name__), patch.object(route.time, 'sleep') as sleep:
                opener = Mock()
                opener.open.side_effect = [error, error, Mock(status=200)]
                records = []
                _, origin = route.fetch_artifact('a.pom', opener, records.append)
                self.assertEqual(origin, route.TENCENT)
                self.assertEqual([c.args[0] for c in opener.open.call_args_list], [route.TENCENT+'a.pom']*3)
                self.assertEqual([c.args[0] for c in sleep.call_args_list], [2, 5])
                self.assertEqual([r['attempt'] for r in records], [1, 2, 3])
                self.assertTrue(all('elapsed_ms' in r and 'origin' in r for r in records))

    def test_central_retry_after_404_and_exhaustion(self):
        records = []
        opener = Mock()
        opener.open.side_effect = [urllib.error.HTTPError('url',404,'',{},None)] + [TimeoutError()]*3
        with patch.object(route.time, 'sleep'), self.assertRaises(TimeoutError):
            route.fetch_artifact('a.pom', opener, records.append)
        self.assertEqual(opener.open.call_count, 4)
        self.assertEqual(records[0]['action'], 'fallback')
        self.assertEqual(records[-1]['action'], 'fail')
        self.assertEqual(records[-1]['origin'], route.CENTRAL)
        self.assertEqual(records[-1]['failure_kind'], 'transport')

    def test_http_retry_exhaustion_never_falls_back(self):
        opener = Mock()
        opener.open.side_effect = urllib.error.HTTPError('url', 502, '', {}, None)
        records = []
        with patch.object(route.time, 'sleep'), self.assertRaises(urllib.error.HTTPError):
            route.fetch_artifact('a.pom', opener, records.append)
        self.assertEqual(opener.open.call_count, 3)
        self.assertTrue(all(r['origin'] == route.TENCENT for r in records))
        self.assertEqual(records[-1]['failure_kind'], 'upstream_http')
        self.assertEqual(records[-1]['action'], 'fail')

    def test_http_616_retries_same_origin_then_succeeds(self):
        opener = Mock()
        error = urllib.error.HTTPError('url', 616, '', {}, None)
        opener.open.side_effect = [error, urllib.error.HTTPError('url', 616, '', {}, None), Mock(status=200)]
        records = []
        with patch.object(route.time, 'sleep') as sleep:
            _, origin = route.fetch_artifact('com/android/a/1/a-1.jar', opener, records.append)
        self.assertEqual(origin, route.TENCENT)
        self.assertEqual([c.args[0] for c in opener.open.call_args_list],
                         [route.TENCENT+'com/android/a/1/a-1.jar']*3)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [2, 5])
        self.assertEqual([r['action'] for r in records], ['retry', 'retry', 'success'])

    def test_http_616_exhaustion_does_not_fallback_to_central(self):
        opener = Mock()
        opener.open.side_effect = urllib.error.HTTPError('url', 616, '', {}, None)
        records = []
        with patch.object(route.time, 'sleep'), self.assertRaises(urllib.error.HTTPError):
            route.fetch_artifact('com/android/a/1/a-1.jar', opener, records.append)
        self.assertEqual(opener.open.call_count, 3)
        self.assertTrue(all(r['origin'] == route.TENCENT for r in records))
        self.assertEqual([r['action'] for r in records], ['retry', 'retry', 'fail'])

    def test_central_recovers_without_changing_artifact(self):
        opener = Mock()
        opener.open.side_effect = [urllib.error.HTTPError('url', 404, '', {}, None),
                                  TimeoutError(), Mock(status=200)]
        with patch.object(route.time, 'sleep') as sleep:
            _, origin = route.fetch_artifact('a.pom.sha1', opener)
        self.assertEqual(origin, route.CENTRAL)
        self.assertEqual([c.args[0] for c in opener.open.call_args_list],
                         [route.TENCENT+'a.pom.sha1', route.CENTRAL+'a.pom.sha1', route.CENTRAL+'a.pom.sha1'])
        sleep.assert_called_once_with(2)

    def test_diagnostics_never_echo_exception_secrets(self):
        records = []
        opener = Mock()
        opener.open.side_effect = urllib.error.URLError('password=fixture-secret https://user:pass@host')
        with self.assertRaises(urllib.error.URLError):
            route.fetch_artifact('a.pom', opener, records.append)
        self.assertNotIn('fixture-secret', str(records))
        self.assertEqual(records[0]['reason'], 'unclassified_transport')

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
        script = (pathlib.Path(__file__).parents[1] / 'scripts' / 'package.sh').read_text(encoding='utf-8')
        self.assertEqual(script.count('"$repo/tools/maven-route.py"'), 3)
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
            self.assertEqual([r['status'] for r in records], [404, 200])
            self.assertEqual(records[0]['action'], 'fallback')
            self.assertEqual(records[-1]['origin'], route.CENTRAL)
        finally:
            connection.close()
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == '__main__':
    unittest.main()
