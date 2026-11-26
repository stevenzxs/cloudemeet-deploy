#!/usr/bin/env python3
"""Trusted controller adapter for real GitHub run context; no builds or bootstrap."""
import json
import os
from pathlib import Path
import subprocess

from repository_counter import allocate
from revision_versions import validate_record


def configuration_sha():
    return subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()


def main():
    env = os.environ
    sha = configuration_sha()
    if sha != env['GITHUB_SHA'] or sha != env['MATERIAL_SHA']:
        raise ValueError('Workflow/material SHA mismatch')
    if env['GITHUB_REPOSITORY'] != 'stevenzxs/cloudemeet-deploy' or env['GITHUB_EVENT_NAME'] != 'workflow_dispatch':
        raise ValueError('Only controlled manual runs may allocate')
    if env['GITHUB_REF'] != 'refs/heads/main':
        raise ValueError('Controller accepts reviewed main only; ledger writes require reviewed workflow')
    skill_root = Path(__file__).resolve().parents[1]
    policy = json.loads((skill_root / 'config/version-policy.json').read_text(encoding='utf-8'))
    sources = json.loads((skill_root / 'sources.json').read_text(encoding='utf-8'))
    identities = {name: item['commit'] for group in ['services', 'clients'] for name, item in sources[group].items()}
    identities['lifecycle'] = sources['lifecycle']['commit']
    identities['h5'] = json.loads((skill_root / 'config/h5-source.json').read_text(encoding='utf-8'))['commit']
    scope = json.loads(env['REQUEST_SCOPE'])
    request = dict(repository=env['GITHUB_REPOSITORY'], workflow=env['GITHUB_WORKFLOW_REF'],
                   run_id=env['GITHUB_RUN_ID'], configuration_sha=sha, sources=identities,
                   task='actions-' + env['GITHUB_RUN_ID'], scope=scope)
    inherited = env.get('INHERITED_ASSIGNMENT')
    if inherited:
        record = validate_record(json.loads(inherited), policy, sha, env['GITHUB_RUN_ID'])
        if record['request']['sources'] != identities or not set(scope) <= set(record['request']['scope']):
            raise ValueError('Parent scope/source mismatch')
    else:
        remote = env.get('LEDGER_REMOTE', 'https://github.com/stevenzxs/cloudemeet-deploy.git')
        record = allocate(skill_root / 'config/version-policy.json', request,
                          attempt=int(env['GITHUB_RUN_ATTEMPT']), remote=remote)
    with open(env['GITHUB_OUTPUT'], 'a', encoding='utf-8') as stream:
        stream.write('assignment=' + json.dumps(record, separators=(',', ':')) + '\n')
        if env.get('EXPECTED_ORIGIN_CONTRACT'):
            contract = json.loads(env['EXPECTED_ORIGIN_CONTRACT'])
            stream.write('origin_contract=' + json.dumps(contract, separators=(',', ':')) + '\n')


if __name__ == '__main__':
    main()
