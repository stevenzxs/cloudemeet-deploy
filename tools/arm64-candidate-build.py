"""Native ARM64 candidate builders. No source rewrites, registry writes or SSH."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'arm64-evidence'
SOURCES = json.loads((ROOT / 'tools/arm64-candidate-sources.json').read_text())
BASES = []


def run(args, cwd=None, env=None):
    subprocess.run(args, cwd=cwd, env=env, check=True, timeout=7200)


def capture(args, cwd=None):
    return subprocess.check_output(args, cwd=cwd, timeout=600)


def checkout(source, destination):
    run(['git', 'init', '-q', str(destination)])
    run(['git', '-C', str(destination), 'fetch', '--depth=1', source['repository'], source['commit']])
    run(['git', '-C', str(destination), 'checkout', '--detach', 'FETCH_HEAD'])
    if capture(['git', '-C', str(destination), 'rev-parse', 'HEAD']).decode().strip() != source['commit']:
        raise RuntimeError('Source identity mismatch')


def resolve_base(reference):
    run(['docker', 'pull', '--platform', 'linux/arm64', reference])
    info = json.loads(capture(['docker', 'image', 'inspect', reference]))[0]
    if (info['Os'], info['Architecture']) != ('linux', 'arm64'):
        raise RuntimeError('Wrong base platform')
    digest = info['RepoDigests'][0]
    BASES.append({'requested': reference, 'resolved': digest, 'image_id': info['Id'], 'platform': 'linux/arm64'})
    return digest


def container_build(base, source, command, evidence_name):
    run(['docker', 'run', '--rm', '--platform', 'linux/arm64',
         '--user', str(os.getuid()) + ':' + str(os.getgid()), '-e', 'HOME=/tmp',
         '-e', 'GOPATH=/tmp/go', '-e', 'GOCACHE=/tmp/go-cache',
         '-v', str(source) + ':/src', '-v', str(EVIDENCE) + ':/evidence',
         '-w', '/src', base, 'bash', '-euc', command])
    (EVIDENCE / (evidence_name + '-builder.json')).write_text(json.dumps({'base': base, 'command': command}, indent=2))


def hashes(root, names):
    return {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
            for name in names if (root / name).is_file()}


def copy_payload(source, destination):
    destination.mkdir()
    # Public payload allowlist only; no .env, source tests, build cache or credentials.
    for pattern in ('*.html', '*.js'):
        for path in source.glob(pattern):
            shutil.copyfile(path, destination / path.name)
    for name in ('fonts', 'images', 'libs', 'static', 'sounds', 'lang'):
        shutil.copytree(source / name, destination / name)
    (destination / 'css').mkdir()
    shutil.copyfile(source / 'css/all.css', destination / 'css/all.css')
    shutil.copyfile(source / 'LICENSE', destination / 'LICENSE')
    (destination / 'resources').mkdir()
    for path in (source / 'resources').glob('*.txt'):
        shutil.copyfile(path, destination / 'resources' / path.name)
    (destination / 'robots.txt').write_text('User-agent: *\nDisallow: /\n')


def build(service, work):
    source = work / 'source'
    context = work / 'context'
    context.mkdir()
    checkout(SOURCES['services'][service], source)
    tracked = ['package-lock.json', '.env', 'pom.xml', 'go.mod', 'go.sum']
    before = hashes(source, tracked)
    if service in ('web', 'app-web'):
        builder = resolve_base('node:24-trixie')
        command = ('npm ci; npm run verify' if service == 'app-web' else 'npm ci; make all')
        container_build(builder, source, command, service)
        shutil.copyfile(source / 'package-lock.json', EVIDENCE / (service + '-package-lock.json'))
        if service == 'app-web':
            runtime = resolve_base('nginx:1.30.6-alpine@sha256:583b7f2fce1cdb8da5ad5c39ebd3c33b98b87d493190e548bdee1fa8c619c311')
            shutil.copytree(source / 'dist', context / 'dist')
            shutil.copyfile(ROOT / 'artifacts/nginx.conf', context / 'nginx.conf')
            # Public VITE configuration is retained verbatim; do not set build overrides.
            (EVIDENCE / 'app-web-public-config.json').write_text(json.dumps({
                'env_sha256': before.get('.env'), 'vite_jitsi_server': next(
                    line.split('=', 1)[1] for line in (source / '.env').read_text().splitlines()
                    if line.startswith('VITE_JITSI_SERVER='))}, indent=2))
        else:
            runtime = resolve_base('ghcr.io/jitsi/base@sha256:48f5eb97cdb15306f4ae0f1d924f6485f3f514d6781aeb86e36601a67aa73781')
            lifecycle = work / 'lifecycle'
            checkout(SOURCES['lifecycle'], lifecycle)
            shutil.copytree(lifecycle / 'web/rootfs', context / 'rootfs')
            copy_payload(source, context / 'payload')
            # Lifecycle requires auxiliary script paths even when ACME is disabled.
            # No ACME script is substituted: fail if the disabled branch requires it.
    elif service == 'api':
        runtime = resolve_base('eclipse-temurin:17-jre-jammy')
        env = dict(os.environ, JAVA_HOME=os.environ.get('JAVA_HOME_17_ARM64', '/usr/lib/jvm/temurin-17-jdk-arm64'))
        env['PATH'] = env['JAVA_HOME'] + '/bin:' + env['PATH']
        # Full tests execute against native ARM64 sqlite-jdbc, without skipping tests.
        run(['bash', '-euc', 'mvn -B -ntp verify'], cwd=source, env=env)
        jars = list((source / 'target').glob('*.jar'))
        if len(jars) != 1:
            raise RuntimeError('Expected exactly one API application JAR')
        shutil.copyfile(jars[0], context / 'app.jar')
        run(['mvn', '-B', '-ntp', 'dependency:tree', '-DoutputFile=' + str(EVIDENCE / 'api-maven-dependencies.txt')], cwd=source, env=env)
        (EVIDENCE / 'api-jar.json').write_text(json.dumps({'sha256': hashlib.sha256(jars[0].read_bytes()).hexdigest()}))
    elif service == 'gateway':
        runtime = resolve_base('debian:trixie-slim@sha256:a72b4433de1cf7d6bae0c4cee74d0547f58601a643b3375f070c51600d63b6b2')
        builder = resolve_base('golang:1.27-trixie')
        container_build(builder, source, '''export GOTOOLCHAIN=local GOMAXPROCS=4
go version
go mod download
go mod verify
go test -race -short -p 2 ./...
go build -p 2 ./...
CGO_ENABLED=0 GOOS=linux GOARCH=arm64 go build -p 2 -trimpath -o /src/caddy-candidate ./cmd/caddy
go version -m /src/caddy-candidate > /evidence/gateway-binary-modules.txt
/src/caddy-candidate list-modules > /evidence/gateway-caddy-modules.txt
go list -m -json all > /evidence/gateway-go-modules.json
''', service)
        shutil.copyfile(source / 'caddy-candidate', context / 'caddy')
    else:
        raise ValueError('Unsupported service')
    after = hashes(source, tracked)
    if before != after:
        raise RuntimeError('Source config or dependency lock changed')
    shutil.copyfile(ROOT / ('tools/arm64-candidate-' + service + '.Dockerfile'), context / 'Dockerfile')
    run(['docker', 'build', '--platform', 'linux/arm64', '--progress', 'plain',
         '--build-arg', 'RUNTIME_BASE=' + runtime,
         '--build-arg', 'SOURCE_COMMIT=' + SOURCES['services'][service]['commit'],
         '-t', 'cloudmeet-ci/' + service, str(context)])
    package_command = ('apk info -v' if service == 'app-web' else 'dpkg-query -W')
    (EVIDENCE / (service + '-runtime-packages.txt')).write_bytes(capture([
        'docker', 'run', '--rm', '--network', 'none', '--entrypoint', 'sh',
        'cloudmeet-ci/' + service, '-c', package_command]))
    (EVIDENCE / (service + '-provenance.json')).write_text(json.dumps({
        'source': SOURCES['services'][service], 'source_dirty': False, 'config_hashes': after,
        'bases': BASES, 'lifecycle': SOURCES['lifecycle'] if service == 'web' else None,
        'context_hashes': {p.relative_to(context).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in context.rglob('*') if p.is_file()},
        'security': 'NOT_CLEARED', 'qualification': 'CANDIDATE_ONLY'}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('service', choices=['web', 'app-web', 'api', 'gateway'])
    args = parser.parse_args()
    if platform.machine() != 'aarch64':
        raise RuntimeError('Use a native ARM64 runner')
    EVIDENCE.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='cloudmeet-arm64-') as directory:
        build(args.service, Path(directory))
