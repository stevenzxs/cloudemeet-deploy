#!/usr/bin/env python3
"""Bind the server allocator to trusted GitHub Actions run context."""
import json
import os
from pathlib import Path
import subprocess

from repository_counter import allocate
from revision_versions import digest


def source_identities(sources):
    identities = {name: item['commit'] for name, item in sources['services'].items()}
    identities['lifecycle'] = sources['lifecycle']['commit']
    identities['server'] = digest(identities)
    return identities


def main():
    env = os.environ
    sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    if sha != env['MATERIAL_SHA'] or sha != env['GITHUB_SHA']:
        raise ValueError('Workflow/material SHA mismatch')
    if env['GITHUB_REPOSITORY'] != 'stevenzxs/cloudemeet-deploy' or env['GITHUB_EVENT_NAME'] != 'workflow_dispatch':
        raise ValueError('Only controlled server manual runs may allocate')
    if json.loads(env['REQUEST_SCOPE']) != ['server']:
        raise ValueError('Server-only scope required')
    root = Path(__file__).resolve().parents[2]
    sources = json.loads((root / 'sources.json').read_text(encoding='utf-8'))
    identities = source_identities(sources)
    request = dict(repository=env['GITHUB_REPOSITORY'], workflow=env['GITHUB_WORKFLOW_REF'],
                   run_id=env['GITHUB_RUN_ID'], configuration_sha=sha,
                   task='actions-' + env['GITHUB_RUN_ID'], scope=['server'], sources=identities)
    record = allocate(root / 'config/version-policy.json', request,
                      attempt=int(env['GITHUB_RUN_ATTEMPT']),
                      remote=env.get('LEDGER_REMOTE', 'https://github.com/stevenzxs/cloudemeet-deploy.git'))
    contract = json.loads(env['EXPECTED_ORIGIN_CONTRACT'])
    with open(env['GITHUB_OUTPUT'], 'a', encoding='utf-8') as stream:
        stream.write('assignment=' + json.dumps(record, separators=(',', ':')) + '\n')
        stream.write('origin_contract=' + json.dumps(contract, separators=(',', ':')) + '\n')


if __name__ == '__main__':
    main()
