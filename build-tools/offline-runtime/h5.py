"""Shared H5 public-material contract; no network, Docker, secrets or allocation."""
import hashlib
import copy
import json
import os
from pathlib import Path
import re
import shutil
from urllib.parse import urlsplit

PUBLIC_FILES = ('index.html', 'src/app.mjs', 'src/core.mjs', 'src/session.mjs', 'src/style.css')


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def describe(root, identity):
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError('H5 root must be a real directory')
    for field in ('source_commit', 'configuration_commit'):
        if not re.fullmatch('[0-9a-f]{40}', identity.get(field, '')):
            raise ValueError('Pinned H5 identity required')
    if not isinstance(identity.get('version_assignment'), dict) or not identity['version_assignment']:
        raise ValueError('Parent version assignment required')
    files = set()
    for path in root.rglob('*'):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise ValueError('H5 links/special files prohibited')
        name = path.relative_to(root).as_posix()
        if path.is_dir() and name != 'src':
            raise ValueError('Unexpected H5 directory')
        if path.is_file():
            files.add(name)
    if files != set(PUBLIC_FILES):
        raise ValueError('Exact H5 public inventory required')
    return dict(identity, contract=1, path='/cm/h5/',
                files={name: {'sha256': sha256(root/name), 'bytes': (root/name).stat().st_size}
                       for name in PUBLIC_FILES})


def verify(root, record, identity):
    if record != describe(root, identity):
        raise ValueError('H5 source/configuration/assignment/content mismatch')


def verify_package(root, manifest):
    record = manifest.get('h5')
    if not isinstance(record, dict):
        raise ValueError('Joint delivery requires H5 evidence')
    verify(Path(root)/'h5/public', record, {
        'source_commit': record.get('source_commit'),
        'configuration_commit': manifest.get('deployment_commit'),
        'version_assignment': manifest.get('version_assignment')})


def gateway_caddy(text):
    marker = '    @business path '
    if text.count(marker) != 1 or '/cm/h5' in text or '(meeting_routes)' not in text:
        raise ValueError('Reviewed gateway route insertion point required')
    snippet = '''    redir /cm/h5 /cm/h5/ 308
    handle_path /cm/h5/* {
        root * /srv/cloudmeet-h5/current
        header {
            Cache-Control "no-store"
            Referrer-Policy "no-referrer"
            X-Content-Type-Options "nosniff"
            Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'self'"
            Permissions-Policy "camera=(self), microphone=(self)"
        }
        @h5modules path *.mjs
        header @h5modules Content-Type application/javascript
        file_server
    }
'''
    return text.replace(marker, snippet+marker, 1)


def prepare_release(runtime, source, record, origin):
    parsed = urlsplit(origin)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.path or parsed.query or parsed.fragment):
        raise ValueError('H5 requires the approved HTTPS origin')
    identity = {key: record.get(key) for key in
                ('source_commit', 'configuration_commit', 'version_assignment')}
    verify(source, record, identity)
    runtime = Path(runtime)
    if runtime.is_symlink() or any(p.is_symlink() for p in runtime.parents):
        raise ValueError('H5 runtime ancestors must not be links')
    runtime.mkdir(parents=True, exist_ok=True, mode=0o755)
    runtime.chmod(0o755)
    releases = runtime/'releases'
    if releases.is_symlink():
        raise ValueError('H5 releases must not be a link')
    releases.mkdir(exist_ok=True, mode=0o755)
    releases.chmod(0o755)
    key = hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()
    release = releases/key
    if release.exists() or release.is_symlink():
        raise ValueError('H5 release already exists; immutable content retained')
    release.mkdir(mode=0o755)
    release.chmod(0o755)
    for name in PUBLIC_FILES:
        target = release/name
        target.parent.mkdir(exist_ok=True, mode=0o755)
        target.parent.chmod(0o755)
        shutil.copyfile(Path(source)/name, target)
        target.chmod(0o644)
    (release/'runtime-config.json').write_text(json.dumps({'jitsiOrigin': origin})+'\n')
    (release/'runtime-config.json').chmod(0o644)
    (release/'release.json').write_text(json.dumps(record, sort_keys=True)+'\n')
    (release/'release.json').chmod(0o644)
    return release


def activate(runtime, release):
    runtime, release = Path(runtime), Path(release)
    if release.parent != runtime/'releases' or release.is_symlink() or not release.is_dir():
        raise ValueError('H5 activation requires a prepared local release')
    current = runtime/'current'
    if current.exists() and not current.is_symlink():
        raise ValueError('H5 current must be a managed relative link')
    previous = os.readlink(current) if current.is_symlink() else None
    if previous is not None and not re.fullmatch(r'releases/[0-9a-f]{64}', previous):
        raise ValueError('Unrecognized H5 current pointer')
    pending = runtime/'current.pending'
    if pending.exists() or pending.is_symlink():
        raise ValueError('Concurrent or interrupted H5 activation')
    pending.symlink_to('releases/'+release.name, target_is_directory=True)
    os.replace(pending, current)
    return previous


def require_compose_delta(old, new, first):
    before, after = copy.deepcopy(old), copy.deepcopy(new)
    for data in (before, after):
        data.pop('name', None)
        for service in data.get('services', {}).values():
            service.pop('image', None)
    volume = './h5-runtime:/srv/cloudmeet-h5:ro'
    if first:
        mounts = after['services']['gateway'].get('volumes', [])
        if mounts.count(volume) != 1:
            raise ValueError('Exact H5 readonly parent mount required')
        mounts.remove(volume)
    if before != after:
        raise ValueError('Unrelated Compose migration refused')


def require_gateway_delta(before, template, first):
    # Compare the public template while keeping the actual target TLS lines intact.
    # Only an existing explicit certificate pair may stand in for template tls internal.
    expected = gateway_caddy(before) if first else before
    def public_template(text):
        return re.sub(r'(?m)^([ \t]*)tls /config/cloudmeet-cert/first-install/server\.crt /config/cloudmeet-cert/first-install/server\.key[ \t]*$',
                      r'\1tls internal', text)
    if public_template(expected) != template:
        raise ValueError('Unrelated gateway configuration migration refused')


def restore_pointer(runtime, previous):
    runtime = Path(runtime)
    if previous is None:
        current = runtime/'current'
        if not current.is_symlink():
            raise ValueError('Cannot restore unrecognized H5 pointer')
        current.unlink()
    elif re.fullmatch(r'releases/[0-9a-f]{64}', previous):
        activate(runtime, runtime/previous)
    else:
        raise ValueError('Unsafe previous H5 pointer')
