#!/usr/bin/env python3
"""Android-only revision version derivation and assignment digest."""
import hashlib
import json
import re


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def derive(policy, revision):
    if policy.get('schema') != 1 or policy.get('approved') is not True:
        raise ValueError('Android version policy is not approved')
    if policy.get('namespace') != 'cloudmeet-android-v1':
        raise ValueError('Android namespace required')
    if type(revision) is not int or revision < 1:
        raise ValueError('Positive Android revision required')
    client = policy.get('client_baseline')
    if not isinstance(client, str) or not re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)', client):
        raise ValueError('Approved Android client baseline required')
    major, minor, patch = map(int, client.split('.'))
    base = policy.get('android_base_code')
    previous = policy.get('previous_android_code')
    if (major > 255 or minor > 9 or patch > 99 or type(base) is not int
            or base != major * 1000 + minor * 100 + patch):
        raise ValueError('Registered Android base code required')
    code = base * 1000 + revision * 10
    if type(previous) is not int or not 0 < previous < code <= 2100000000:
        raise ValueError('Android historical upgrade floor unknown or not exceeded')
    major, minor, patch = map(int, client.split('.'))
    msi = f'{major}.{minor}.{(patch + revision) * 10}'
    if previous_msi := policy.get('previous_msi_version'):
        if tuple(map(int, msi.split('.'))) <= tuple(map(int, previous_msi.split('.'))):
            raise ValueError('MSI historical upgrade floor not exceeded')
    server = policy.get('server_baseline', '11248.0.1')
    return {'revision': revision, 'server_version': f'{server}+r{revision}',
            'server_tag': f'{server}-r{revision}', 'client_version': f'{client}+r{revision}',
            'android_code': code, 'msi_version': msi, 'pe_version': msi + '.0',
            'version_formula': 2}
