"""Export candidate bytes and validate bounded provenance; never publish images."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def validate_identity(image, source):
    if (image.get('Os'), image.get('Architecture')) != ('linux', 'arm64'):
        raise ValueError('Candidate must be linux/arm64')
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', image.get('Id', '')):
        raise ValueError('Missing Docker image ID')
    if not re.fullmatch(r'[0-9a-f]{40}', source.get('commit', '')):
        raise ValueError('Source must be pinned to a full Git commit')
    if not source.get('repository', '').startswith('https://github.com/'):
        raise ValueError('Missing source repository')


def validate_archives(records, root, expected):
    names = [record['service'] for record in records]
    if len(names) != len(set(names)) or set(names) != set(expected):
        raise ValueError('Missing or duplicate service archives')
    root = Path(root).resolve()
    for record in records:
        path = (root / record['archive']).resolve()
        if path.parent != root or not path.is_file():
            raise ValueError('Archive must be a file directly inside candidate directory')
        if path.stat().st_size != record['size'] or sha256(path) != record['sha256']:
            raise ValueError('Candidate archive changed: ' + record['service'])


def export(service, source, evidence, output):
    image = json.loads(subprocess.check_output(['docker', 'image', 'inspect', 'cloudmeet-ci/' + service]))[0]
    validate_identity(image, source)
    output.mkdir(parents=True, exist_ok=True)
    archive = output / (service + '.tar.gz')
    # Docker save is read-only and preserves the exact tested image ID.
    with gzip.open(archive, 'wb', compresslevel=1) as compressed:
        process = subprocess.Popen(['docker', 'image', 'save', image['Id']], stdout=subprocess.PIPE)
        try:
            for block in iter(lambda: process.stdout.read(1024 * 1024), b''):
                compressed.write(block)
        finally:
            process.stdout.close()
        if process.wait(timeout=600):
            raise RuntimeError('Docker image export failed')
    record = {'service': service, 'source': source, 'platform': 'linux/arm64',
              'image_id': image['Id'], 'archive': archive.name, 'size': archive.stat().st_size,
              'sha256': sha256(archive), 'status': 'CANDIDATE_NOT_INSTALL_QUALIFIED',
              'scope': 'source build and service smoke; not seven-service/media/security acceptance'}
    (evidence / (service + '-image.json')).write_text(json.dumps(image, indent=2))
    (output / (service + '.json')).write_text(json.dumps(record, indent=2))
    validate_archives([record], output, {service})
    (output / (service + '.sha256')).write_text(record['sha256'] + '  ' + archive.name + '\n')
    return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('services', nargs='+')
    parser.add_argument('--evidence', type=Path, default=Path('arm64-evidence'))
    parser.add_argument('--output', type=Path, default=Path('arm64-candidates'))
    args = parser.parse_args()
    sources = json.loads((Path(__file__).with_name('arm64-candidate-sources.json')).read_text())['services']
    args.evidence.mkdir(exist_ok=True)
    for service in args.services:
        print(json.dumps(export(service, sources[service], args.evidence, args.output)))
