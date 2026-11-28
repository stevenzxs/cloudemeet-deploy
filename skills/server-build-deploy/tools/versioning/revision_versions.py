#!/usr/bin/env python3
"""Server-only revision version derivation and assignment digest."""
import hashlib
import json
import re


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def derive(policy, revision):
    if policy.get('schema') != 1 or policy.get('approved') is not True:
        raise ValueError('Server version policy is not approved')
    if policy.get('namespace') != 'cloudmeet-server-v1':
        raise ValueError('Server namespace required')
    if type(revision) is not int or revision < 1:
        raise ValueError('Positive server revision required')
    baseline = policy.get('server_baseline')
    if not isinstance(baseline, str) or not re.fullmatch(r'\d+(?:\.\d+){2,3}', baseline):
        raise ValueError('Approved server baseline required')
    client = policy.get('client_baseline', '1.0.21')
    if not isinstance(client, str) or not re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)', client):
        raise ValueError('Approved client baseline required')
    major, minor, patch = map(int, client.split('.'))
    base = policy.get('android_base_code', major * 1000 + minor * 100 + patch)
    if type(base) is not int or minor > 9 or patch > 99 or base != major * 1000 + minor * 100 + patch:
        raise ValueError('Registered Android base code required')
    android_code = base * 1000 + revision * 10
    previous_android = policy.get('previous_android_code', base * 1000)
    if type(previous_android) is not int or android_code <= previous_android or android_code > 2100000000:
        raise ValueError('Android historical upgrade floor unknown or not exceeded')
    msi = f'{major}.{minor}.{(patch + revision) * 10}'
    previous_msi = policy.get('previous_msi_version', client)
    if tuple(map(int, msi.split('.'))) <= tuple(map(int, previous_msi.split('.'))):
        raise ValueError('MSI historical upgrade floor not exceeded')
    return {'revision': revision, 'server_version': f'{baseline}+r{revision}',
            'server_tag': f'{baseline}-r{revision}', 'client_version': f'{client}+r{revision}',
            'android_code': android_code, 'msi_version': msi, 'pe_version': msi + '.0',
            'version_formula': 2}
