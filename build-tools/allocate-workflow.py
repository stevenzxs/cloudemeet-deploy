#!/usr/bin/env python3
"""Trusted controller adapter for real GitHub run context; no builds or bootstrap."""
import json
import os
from pathlib import Path
import subprocess

from revision_versions import validate_record
from revision_ledger import allocate


def main():
    env = os.environ
    sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    if sha != env['GITHUB_SHA'] or sha != env['MATERIAL_SHA']:
        raise ValueError('Workflow/material SHA mismatch')
    if env['GITHUB_REPOSITORY'] != 'stevenzxs/cloudemeet-deploy' or env['GITHUB_EVENT_NAME'] != 'workflow_dispatch':
        raise ValueError('Only controlled manual runs may allocate')
    if env['GITHUB_REF'] != 'refs/heads/main':
        raise ValueError('Controller accepts reviewed main only; restrict runner group to approved workflows')
    policy = json.loads(Path('config/version-policy.json').read_text())
    sources = json.loads(Path('build-tools/sources.json').read_text())
    identities = {name: item['commit'] for group in ['services', 'clients'] for name, item in sources[group].items()}
    identities['lifecycle'] = sources['lifecycle']['commit']
    scope = json.loads(env['REQUEST_SCOPE'])
    request = dict(repository=env['GITHUB_REPOSITORY'], workflow=env['GITHUB_WORKFLOW_REF'],
                   run_id=env['GITHUB_RUN_ID'], configuration_sha=sha, sources=identities,
                   task='actions-' + env['GITHUB_RUN_ID'], scope=scope)
    inherited = env.get('INHERITED_ASSIGNMENT')
    if inherited:
        record = validate_record(json.loads(inherited), policy, sha, env['GITHUB_RUN_ID'])
        if record['request']['sources'] != identities or not set(scope) <= set(record['request']['scope']):
            raise ValueError('Parent scope/source mismatch')
        request = record['request']
    ledger = Path(env['VERSION_LEDGER'])
    if not ledger.is_absolute() or ledger.resolve().is_relative_to(Path.cwd().resolve()):
        raise ValueError('Repository-external absolute persistent ledger required')
    record = allocate(ledger.resolve(), policy, request, attempt=int(env['GITHUB_RUN_ATTEMPT']),
                      create=not bool(inherited))
    if inherited and record != json.loads(inherited):
        raise ValueError('Inherited record differs from persistent assignment')
    with open(env['GITHUB_OUTPUT'], 'a') as stream:
        stream.write('assignment=' + json.dumps(record, separators=(',', ':')) + '\n')


if __name__ == '__main__':
    main()
