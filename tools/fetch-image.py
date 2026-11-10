"""Export an official registry's ARM64 image as a digest-verified Docker archive.

Usage: python fetch-image.py library/caddy 2.10.2-alpine output.tar
Uses Docker Hub by default; registry and tag prefix can be overridden for GHCR.
"""
import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile
import urllib.request

repo, tag, output = sys.argv[1:4]
registry = sys.argv[4] if len(sys.argv) > 4 else 'registry-1.docker.io'
token_url = ('https://ghcr.io/token?service=ghcr.io' if registry == 'ghcr.io'
             else 'https://auth.docker.io/token?service=registry.docker.io')
token_url += f'&scope=repository:{repo}:pull'
token = json.load(urllib.request.urlopen(token_url, timeout=60))['token']
accept = ', '.join(('application/vnd.oci.image.index.v1+json',
                    'application/vnd.docker.distribution.manifest.list.v2+json',
                    'application/vnd.oci.image.manifest.v1+json',
                    'application/vnd.docker.distribution.manifest.v2+json'))


def get(kind, ref):
    request = urllib.request.Request(f'https://{registry}/v2/{repo}/{kind}/{ref}',
                                    headers={'Authorization': f'Bearer {token}', 'Accept': accept})
    with urllib.request.urlopen(request, timeout=180) as response:
        content = response.read()
    if ref.startswith('sha256:') and hashlib.sha256(content).hexdigest() != ref[7:]:
        raise RuntimeError(f'Digest mismatch: {ref}')
    return content


index = json.loads(get('manifests', tag))
if 'manifests' in index:
    platform = next(m for m in index['manifests']
                    if m.get('platform', {}).get('architecture') == 'arm64'
                    and m['platform'].get('os') == 'linux')
    manifest_digest = platform['digest']
    manifest = json.loads(get('manifests', manifest_digest))
else:
    raise RuntimeError('Expected multi-platform index')

image_tag = f'{repo.removeprefix("library/")}:{tag}' if registry != 'ghcr.io' else f'{registry}/{repo}:{tag}'
with tarfile.open(output, 'w') as archive:
    def add(name, content):
        info = tarfile.TarInfo(name)
        info.size = len(content)
        archive.addfile(info, io.BytesIO(content))

    config = get('blobs', manifest['config']['digest'])
    config_name = manifest['config']['digest'][7:] + '.json'
    if json.loads(config)['architecture'] != 'arm64':
        raise RuntimeError('Wrong image architecture')
    add(config_name, config)
    layers = []
    for layer in manifest['layers']:
        name = layer['digest'][7:] + '/layer.tar'
        print(f'{image_tag}: {layer["digest"]} ({layer["size"]} bytes)', flush=True)
        add(name, get('blobs', layer['digest']))
        layers.append(name)
    add('manifest.json', json.dumps([{'Config': config_name, 'RepoTags': [image_tag], 'Layers': layers}]).encode())
Path(output + '.json').write_text(json.dumps({'image': image_tag, 'platform': 'linux/arm64',
                                             'manifest_digest': manifest_digest}, indent=2))
print(f'Exported {image_tag}: {manifest_digest}', flush=True)
