#!/usr/bin/env python3
"""MSI-only revision version derivation and assignment digest."""
import hashlib
import json
import re


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def derive(policy, revision):
    if policy.get('schema') != 1 or policy.get('approved') is not True:
        raise ValueError('MSI version policy is not approved')
    if policy.get('namespace') != 'cloudmeet-msi-v1':
        raise ValueError('MSI namespace required')
    if type(revision) is not int or revision < 1:
        raise ValueError('Positive MSI revision required')
    baseline = policy.get('client_baseline')
    if not isinstance(baseline, str) or not re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)', baseline):
        raise ValueError('Approved MSI baseline required')
    major, minor, patch = map(int, baseline.split('.'))
    if major > 255 or minor > 255 or (patch + revision) * 10 + 9 > 65535:
        raise ValueError('MSI/PE version range exhausted')
    version = f'{major}.{minor}.{(patch + revision) * 10}'
    previous = policy.get('previous_msi_version')
    if not isinstance(previous, str) or tuple(map(int, version.split('.'))) <= tuple(map(int, previous.split('.'))):
        raise ValueError('MSI historical upgrade floor not exceeded')
    code = major * 1000 + minor * 100 + patch
    android_code = code * 1000 + revision * 10
    if type(policy.get('android_base_code', code)) is not int or policy.get('android_base_code', code) != code:
        raise ValueError('Registered Android base code required')
    if type(policy.get('previous_android_code', code)) is not int or android_code <= policy.get('previous_android_code', code):
        raise ValueError('Android historical upgrade floor not exceeded')
    server = policy.get('server_baseline', '11248.0.1')
    if not isinstance(server, str) or not re.fullmatch(r'\d+(?:\.\d+){2,3}', server):
        raise ValueError('Approved server baseline required')
    return {'revision': revision, 'server_version': f'{server}+r{revision}',
            'server_tag': f'{server}-r{revision}', 'client_version': f'{baseline}+r{revision}',
            'android_code': android_code, 'msi_version': version, 'pe_version': version + '.0',
            'version_formula': 2}
