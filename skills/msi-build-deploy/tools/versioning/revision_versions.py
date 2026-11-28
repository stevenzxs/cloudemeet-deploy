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
    return {'revision': revision, 'client_version': f'{baseline}+r{revision}',
            'msi_version': version, 'pe_version': version + '.0', 'version_formula': 2}
