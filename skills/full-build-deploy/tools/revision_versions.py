#!/usr/bin/env python3
"""Pure joint version contract plus record validation; no allocation side effects."""
import argparse
import hashlib
import json
import re
from pathlib import Path

REPOSITORY = 'stevenzxs/cloudemeet-deploy'
SERVICES = ('gateway', 'app-web', 'api', 'web', 'prosody', 'jicofo', 'jvb')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def numeric_version(value):
    if not isinstance(value, str) or not re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)', value):
        raise ValueError('Numeric major.minor.patch required')
    return tuple(map(int, value.split('.')))


def derive(policy, revision):
    if policy.get('schema') != 1 or policy.get('approved') is not True:
        raise ValueError('Version policy is not approved/activated')
    if not re.fullmatch(r'[a-z][a-z0-9-]{0,63}', policy.get('namespace', '')):
        raise ValueError('Registered namespace required')
    if type(revision) is not int or revision < 1:
        raise ValueError('Positive integer revision required')
    server = policy.get('server_baseline')
    if not isinstance(server, str) or not re.fullmatch(r'\d+(?:\.\d+){2,3}', server):
        raise ValueError('Approved server baseline required')
    client = policy['client_baseline']
    major, minor, patch = numeric_version(client)
    if major > 255 or minor > 255 or patch + revision > 65535:
        raise ValueError('MSI/PE version range exhausted')
    base = policy['android_base_code']
    if type(base) is not int or base < 1 or minor > 9 or patch > 99 or base != major * 1000 + minor * 100 + patch:
        raise ValueError('Registered Android base code required')
    code = int(str(base) + str(revision))
    previous = policy.get('previous_android_code')
    if type(previous) is not int or not 0 < previous < code <= 2100000000:
        raise ValueError('Android historical upgrade floor unknown or not exceeded')
    msi = f'{major}.{minor}.{patch + revision}'
    if numeric_version(msi) <= numeric_version(policy.get('previous_msi_version')):
        raise ValueError('MSI historical upgrade floor not exceeded')
    return dict(revision=revision, server_version=f'{server}+r{revision}',
                 server_tag=f'{server}-r{revision}', client_version=f'{client}+r{revision}',
                 android_code=code, msi_version=msi, pe_version=msi + '.0')


def validate_request(request):
    if request.get('repository') != REPOSITORY:
        raise ValueError('Repository mismatch')
    if not re.fullmatch(r'[1-9]\d*', request.get('run_id', '')):
        raise ValueError('Real numeric parent Run ID required')
    if not re.fullmatch(r'[0-9a-f]{40}', request.get('configuration_sha', '')):
        raise ValueError('Full configuration SHA required')
    if not request.get('task') or not request.get('workflow'):
        raise ValueError('Task and top-level workflow identity required')
    scope = request.get('scope')
    if not isinstance(scope, list) or not scope or len(scope) != len(set(scope)) or set(scope) - {'server', 'h5', 'electron', 'android'}:
        raise ValueError('Explicit scope required')
    sources = request.get('sources')
    if not isinstance(sources, dict) or not sources or any(not re.fullmatch(r'[0-9a-f]{40}', s) for s in sources.values()):
        raise ValueError('Pinned component sources required')


def validate_record(record, policy, sha, run_id):
    request = record['request']
    validate_request(request)
    if request['configuration_sha'] != sha or request['run_id'] != str(run_id):
        raise ValueError('Allocation belongs to a different configuration/run')
    if record.get('policy_sha256') != digest(policy) or record.get('namespace') != policy['namespace']:
        raise ValueError('Version policy binding mismatch')
    if record['versions'] != derive(policy, record['versions']['revision']):
        raise ValueError('Derived version mismatch')
    expected = dict(record)
    expected.pop('allocation_sha256', None)
    if record.get('allocation_sha256') != digest(expected):
        raise ValueError('Allocation integrity mismatch')
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--record', type=Path, required=True)
    parser.add_argument('--policy', type=Path, required=True)
    parser.add_argument('--sha', required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--scope', choices=['server', 'electron', 'android'], required=True)
    parser.add_argument('--attempt', type=int, required=True)
    parser.add_argument('--github-env', type=Path)
    args = parser.parse_args()
    record = validate_record(json.loads(args.record.read_text()), json.loads(args.policy.read_text()), args.sha, args.run_id)
    if args.scope not in record['request']['scope'] or args.attempt < 1:
        raise ValueError('Scope/attempt mismatch')
    v = record['versions']
    if args.github_env:
        with args.github_env.open('a') as stream:
            stream.write(f"VERSION={v['server_version']}\nBATCH={v['server_tag']}-{args.run_id}-{args.attempt}\n")
    print(json.dumps(record, sort_keys=True))


if __name__ == '__main__':
    main()
