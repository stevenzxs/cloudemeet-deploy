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
    return {'revision': revision, 'server_version': f'{baseline}+r{revision}',
            'server_tag': f'{baseline}-r{revision}', 'version_formula': 2}
