#!/usr/bin/env python3
"""Validate server assignment identity, derivation, and integrity."""
import json
import os
from pathlib import Path

from repository_counter import digest
from revision_versions import derive


record = json.loads(os.environ['ASSIGNMENT'])
request = record['request']
policy = json.loads((Path(__file__).resolve().parents[2] / 'config/version-policy.json').read_text(encoding='utf-8'))
if record.get('namespace') != policy.get('namespace') or request.get('run_id') != os.environ['GITHUB_RUN_ID']:
    raise ValueError('Server assignment identity mismatch')
expected = dict(record)
signature = expected.pop('allocation_sha256', None)
if signature != digest(expected) or record.get('versions') != derive(policy, record['versions']['revision']):
    raise ValueError('Server assignment integrity/version mismatch')
if request.get('scope') != ['server'] or int(os.environ['ATTEMPT']) < 1:
    raise ValueError('Server assignment scope/attempt mismatch')
