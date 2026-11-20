"""Run Maven with Central-only, artifact-level Aliyun/404 fallback routing."""
import argparse
import http.server
import json
import pathlib
import shutil
import subprocess
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ALIYUN = 'https://maven.aliyun.com/repository/public/'
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


def fetch_artifact(relative, opener):
    """Only an explicit Aliyun 404 permits a request to Central."""
    for origin in (ALIYUN, CENTRAL):
        try:
            response = opener.open(origin + relative, timeout=60)
            return response, origin
        except urllib.error.HTTPError as error:
            status = error.code
            error.close()
            if origin == ALIYUN and status == 404:
                continue
            raise
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
                response, origin = fetch_artifact(relative, opener)
            except urllib.error.HTTPError as error:
                audit({'artifact': relative, 'status': error.code})
                self.send_error(error.code)
                return
            except (OSError, urllib.error.URLError):
                audit({'artifact': relative, 'status': 502})
                self.send_error(502)
                return
            with response:
                audit({'artifact': relative, 'origin': origin, 'status': response.status})
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit', required=True)
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
