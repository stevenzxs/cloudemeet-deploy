"""Run Maven through the approved Tencent mirror with Central fallback."""
import argparse
import http.server
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import threading
import time
import ssl
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

TENCENT = 'https://mirrors.cloud.tencent.com/nexus/repository/maven-public/'
CENTRAL = 'https://repo.maven.apache.org/maven2/'


def settings_xml(url, existing=None):
    """Preserve user servers/proxies/profiles; refuse conflicting mirror policies."""
    root = ET.fromstring(existing) if existing else ET.Element('settings')
    # Normalize the optional Maven namespace for insertion/serialization.
    for element in root.iter():
        element.tag = element.tag.split('}')[-1]
    if root.tag != 'settings':
        raise ValueError('Expected Maven settings')
    mirrors = root.find('mirrors')
    if mirrors is None:
        mirrors = ET.SubElement(root, 'mirrors')
    for mirror in mirrors:
        patterns = (mirror.findtext('mirrorOf') or '').split(',')
        if any(p.strip() in ('central', '*', 'external:*', 'external:http:*') for p in patterns):
            raise ValueError('Existing Central mirror must be reviewed before routing')
    if any(node.text == 'cloudmeet-central' for node in root.iter('id')):
        raise ValueError('Reserved Maven routing ID already exists')
    mirror = ET.SubElement(mirrors, 'mirror')
    for key, value in [('id', 'cloudmeet-central'), ('mirrorOf', 'central'), ('url', url)]:
        ET.SubElement(mirror, key).text = value
    profiles = root.find('profiles')
    if profiles is None:
        profiles = ET.SubElement(root, 'profiles')
    profile = ET.SubElement(profiles, 'profile')
    ET.SubElement(profile, 'id').text = 'cloudmeet-central'
    for group, item in [('repositories', 'repository'), ('pluginRepositories', 'pluginRepository')]:
        repository = ET.SubElement(ET.SubElement(profile, group), item)
        ET.SubElement(repository, 'id').text = 'central'
        ET.SubElement(repository, 'url').text = CENTRAL
        ET.SubElement(ET.SubElement(repository, 'releases'), 'checksumPolicy').text = 'fail'
    active = root.find('activeProfiles')
    if active is None:
        active = ET.SubElement(root, 'activeProfiles')
    ET.SubElement(active, 'activeProfile').text = 'cloudmeet-central'
    return ET.tostring(root, encoding='unicode')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never silently redirect dependency requests to an unreviewed origin.
        return None


def failure_reason(error):
    """Allowlisted categories only: exception messages can contain credentials."""
    reason = error.reason if isinstance(error, urllib.error.URLError) else error
    if isinstance(reason, ssl.SSLError):
        return 'tls_error'
    if isinstance(reason, TimeoutError):
        return 'timeout'
    if isinstance(reason, ConnectionResetError):
        return 'connection_reset'
    return 'unclassified_transport'


def fetch_artifact(relative, opener, audit=lambda record: None):
    """Only an explicit Tencent 404 permits a request to Central."""
    for origin in (TENCENT, CENTRAL):
        for attempt in range(1, 4):
            started = time.monotonic()
            record = {'artifact': relative, 'origin': origin, 'attempt': attempt,
                      'timestamp': time.time()}
            try:
                response = opener.open(origin + relative, timeout=60)
            except (OSError, urllib.error.URLError) as error:
                http_error = isinstance(error, urllib.error.HTTPError)
                status = error.code if http_error else 502
                reason = 'http_status' if http_error else failure_reason(error)
                transient = status in (502, 503, 504, 616) if http_error else reason in ('timeout', 'connection_reset')
                fallback = http_error and status == 404 and origin == TENCENT
                retry = transient and attempt < 3
                record.update(status=status, failure_kind='upstream_http' if http_error else 'transport',
                              exception_type=type(error).__name__, reason=reason,
                              elapsed_ms=round((time.monotonic()-started)*1000),
                              action='fallback' if fallback else 'retry' if retry else 'fail')
                audit(record)
                if http_error:
                    error.close()
                if fallback:
                    break
                if retry:
                    time.sleep((2, 5)[attempt-1])
                    continue
                raise
            record.update(status=response.status, elapsed_ms=round((time.monotonic()-started)*1000),
                          action='success')
            audit(record)
            return response, origin
    raise AssertionError('unreachable')


def artifact_path(raw):
    parsed = urllib.parse.urlsplit(raw)
    path = urllib.parse.unquote(parsed.path)
    if (parsed.scheme or parsed.netloc or parsed.query or parsed.fragment
            or not path.startswith('/') or '\\' in path
            or any(part in ('.', '..') for part in path.split('/'))
            or any(ord(char) < 32 for char in path)):
        raise ValueError('Invalid Maven artifact path')
    return urllib.parse.quote(path.lstrip('/'), safe='/@:+-._~')


def handler_factory(opener, audit):
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            self.serve(False)

        def do_HEAD(self):
            self.serve(True)

        def serve(self, head):
            try:
                relative = artifact_path(self.path)
            except ValueError:
                self.send_error(400)
                return
            try:
                response, origin = fetch_artifact(relative, opener, audit)
            except urllib.error.HTTPError as error:
                self.send_error(error.code)
                return
            except (OSError, urllib.error.URLError):
                self.send_error(502)
                return
            with response:
                self.send_response(response.status)
                # Do not forward credentials, cookies or upstream proxy headers.
                for key in ('Content-Length', 'Content-Type', 'Last-Modified'):
                    if response.headers.get(key):
                        self.send_header(key, response.headers[key])
                self.end_headers()
                if not head:
                    try:
                        while chunk := response.read(64 * 1024):
                            self.wfile.write(chunk)
                    except OSError:
                        self.close_connection = True
    return Handler


def gradle_init(url):
    """Route Central and the portal's Gson dependency without replacing private repos."""
    return '''
def routeRepositories = { repos ->
    def configureRepo = { repo ->
        if (repo instanceof org.gradle.api.artifacts.repositories.MavenArtifactRepository) {
            def host = repo.url.host
            if (host in ['repo.maven.apache.org', 'repo1.maven.org']) {
                repo.url = ROUTE_URL
                repo.allowInsecureProtocol = true
            }
            if (host == 'plugins.gradle.org') {
                repo.content { excludeGroup("com.google.code.gson") }
            }
        }
    }
    repos.all(configureRepo)
    repos.maven {
        name = 'CloudMeetCentralRoute'
        url = ROUTE_URL
        allowInsecureProtocol = true
        content { includeGroup("com.google.code.gson") }
    }
}
gradle.beforeSettings { settings ->
    routeRepositories(settings.pluginManagement.repositories)
}
gradle.settingsEvaluated { settings ->
    routeRepositories(settings.dependencyResolutionManagement.repositories)
}
gradle.beforeProject { project ->
    routeRepositories(project.buildscript.repositories)
    routeRepositories(project.repositories)
}
'''.replace('ROUTE_URL', json.dumps(url))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit', required=True)
    parser.add_argument('--gradle-command', action='store_true')
    parser.add_argument('maven_args', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.maven_args
    if command[:1] == ['--']:
        command = command[1:]
    if not command:
        parser.error('Maven arguments required')
    audit_path = pathlib.Path(args.audit)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    lock = threading.Lock()
    with audit_path.open('x', encoding='utf-8') as stream:
        def audit(record):
            with lock:
                stream.write(json.dumps(record) + '\n')
                stream.flush()
        opener = urllib.request.build_opener(NoRedirect())
        server = http.server.ThreadingHTTPServer(
            ('127.0.0.1', 0), handler_factory(opener, audit))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory(prefix='cloudmeet-maven-') as folder:
                if args.gradle_command:
                    init = pathlib.Path(folder) / 'central.init.gradle'
                    init.write_text(gradle_init(f'http://127.0.0.1:{server.server_port}/'), encoding='utf-8')
                    env = dict(os.environ, CLOUDMEET_GRADLE_INIT=str(init))
                    return subprocess.call(command, env=env)
                settings = pathlib.Path(folder) / 'settings.xml'
                user_settings = pathlib.Path.home() / '.m2' / 'settings.xml'
                settings.write_text(settings_xml(
                    f'http://127.0.0.1:{server.server_port}/',
                    user_settings.read_text(encoding='utf-8') if user_settings.exists() else None),
                    encoding='utf-8')
                settings.chmod(0o600)
                executable = shutil.which('mvn')
                if not executable:
                    raise RuntimeError('Maven executable not found')
                return subprocess.call([executable, '-s', str(settings), *command])
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == '__main__':
    raise SystemExit(main())
