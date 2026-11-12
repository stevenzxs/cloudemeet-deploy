"""Read-only workspace entry inventory. Does NOT qualify packages or runtime."""
from pathlib import Path
import sys

EXCLUDED = {'.git', '.worktrees', 'history', 'packages', 'clients',
            'node_modules', '__pycache__', 'skills', 'releases', 'migration'}

# Implementation inventory only; deploy/AGENTS.md is the sole policy source.
CATALOG = {'schema_version': 1, 'routes': [
    {'id': 'root-template', 'state': 'template', 'product_delivery_allowed': False,
     'paths': ['deploy/init.py', 'deploy/start.sh', 'deploy/docker-compose.yml',
               'deploy/jitsi-base.yaml']},
    {'id': 'offline-runtime', 'state': 'candidate', 'product_delivery_allowed': False,
      'paths': ['build-tools/offline-runtime/install.py', 'build-tools/offline-runtime/start.py',
                'build-tools/offline-runtime/initialize.py', 'build-tools/offline-runtime/deploy.py',
                'build-tools/package.sh']},
]}


def unregistered(found, registered):
    return sorted(found - registered)


def validate_catalog(catalog):
    errors = []
    if catalog.get('schema_version') != 1:
        errors.append('Unsupported catalog schema')
    seen = set()
    ids = set()
    for route in catalog.get('routes', []):
        if route['id'] in ids:
            errors.append('Duplicate route: ' + route['id'])
        ids.add(route['id'])
        if route['state'] not in {'blocked', 'template', 'candidate'}:
            errors.append('Unknown route state: ' + route['id'])
        if route['product_delivery_allowed'] is not False:
            errors.append('Inventory cannot grant product delivery: ' + route['id'])
        for name in route['paths']:
            if name in seen:
                errors.append('Duplicate path: ' + name)
            seen.add(name)
    if not ids:
        errors.append('Empty catalog')
    return errors


def discover(root):
    found = set()
    for base in ('deploy', 'build-tools'):
        for p in (root / base).rglob('*'):
            rel = p.relative_to(root)
            if any(part in EXCLUDED for part in rel.parts) or not p.is_file():
                continue
            script = p.suffix in {'.py', '.sh'} and (
                 p.name in {'install.py', 'start.py', 'start.sh', 'deploy.py', 'engine.py', 'init.py',
                            'initialize.py', 'package.sh'}
                or p.name.startswith(('assemble-', 'release-')))
            compose = p.name in {'docker-compose.yml', 'jitsi-base.yaml', 'compose.yaml', 'compose.yml'}
            if script or compose:
                found.add(rel.as_posix())
    return found


def check(root):
    catalog = CATALOG
    errors = validate_catalog(catalog)
    registered = {p for route in catalog['routes'] for p in route['paths']}
    errors += ['Unregistered entry: ' + p for p in unregistered(discover(root), registered)]
    errors += ['Missing registered entry: ' + p for p in sorted(registered) if not (root / p).is_file()]
    return errors


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[2]
    errors = check(root)
    print('\n'.join(errors) if errors else 'PASS: registered layout only; NOT package/runtime acceptance')
    sys.exit(bool(errors))
