#!/usr/bin/env python3
"""Append-only Git ledger. Missing branch/anchor is fatal; never bootstrap on allocate."""
from contextlib import closing
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import tempfile
import time
import random

from revision_versions import derive, digest, validate_record, validate_request

BRANCH = 'cloudmeet-revision-ledger'


def validate_state(state, policy):
    if set(state) != {'schema', 'namespace', 'policy_sha256', 'records', 'attempts'}:
        raise ValueError('Unexpected ledger schema')
    if state['schema'] != 1 or state['namespace'] != policy['namespace'] or state['policy_sha256'] != digest(policy):
        raise ValueError('Ledger policy mismatch')
    runs = set()
    for n, record in enumerate(state['records'], 1):
        request = record['request']
        validate_record(record, policy, request['configuration_sha'], request['run_id'])
        if record['versions']['revision'] != n or request['run_id'] in runs:
            raise ValueError('Missing/duplicate allocation history')
        runs.add(request['run_id'])
    seen = set()
    for item in state['attempts']:
        if not isinstance(item, list) or len(item) != 2:
            raise ValueError('Invalid attempt entry')
        run, attempt = item
        if run not in runs or type(attempt) is not int or attempt < 1 or (run, attempt) in seen:
            raise ValueError('Invalid/duplicate attempt')
        seen.add((run, attempt))
    if runs != {item[0] for item in seen}:
        raise ValueError('Missing attempt evidence')
    return state


def export_sqlite(path, policy):
    """Read-only export, preserving allocation objects; no number is allocated."""
    path = Path(path).resolve(strict=True)
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as con:
        con.execute('BEGIN')
        if con.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise ValueError('SQLite integrity failure')
        if con.execute('SELECT policy_hash,namespace FROM identity').fetchall() != [(digest(policy), policy['namespace'])]:
            raise ValueError('SQLite policy mismatch')
        rows = con.execute('SELECT run_id,revision,record FROM allocations ORDER BY revision').fetchall()
        records = []
        for run, revision, payload in rows:
            record = json.loads(payload)
            if record['request']['run_id'] != run or record['versions']['revision'] != revision:
                raise ValueError('SQLite row mismatch')
            records.append(record)
        attempts = [list(row) for row in con.execute('SELECT run_id,attempt FROM attempts ORDER BY run_id,attempt')]
    return validate_state(dict(schema=1, namespace=policy['namespace'], policy_sha256=digest(policy),
                               records=records, attempts=attempts), policy)


def git(root, *args, check=True):
    env = os.environ.copy()
    header = env.pop('LEDGER_AUTH_HEADER', None)
    if header:
        env.update(GIT_CONFIG_COUNT='1', GIT_CONFIG_KEY_0='http.https://github.com/.extraheader',
                   GIT_CONFIG_VALUE_0=header)
    return subprocess.run(['git', '-C', str(root), *args], text=True, capture_output=True,
                          env=env, check=check, timeout=60)


def read_history(root, tip, anchor, policy):
    if git(root, 'merge-base', '--is-ancestor', anchor, tip, check=False).returncode:
        raise ValueError('Ledger is behind or diverged from approved migration anchor')
    commits = git(root, 'rev-list', '--reverse', f'{anchor}..{tip}').stdout.splitlines()
    previous = None
    parent = None
    for commit in [anchor, *commits]:
        if parent and git(root, 'show', '-s', '--format=%P', commit).stdout.strip() != parent:
            raise ValueError('Ledger history must be linear')
        tree = git(root, 'ls-tree', commit).stdout.strip()
        if not re.fullmatch(r'100644 blob [0-9a-f]{40}\tledger.json', tree):
            raise ValueError('Ledger branch must contain only regular ledger.json')
        state = validate_state(json.loads(git(root, 'show', f'{commit}:ledger.json').stdout), policy)
        if previous:
            for key in ['records', 'attempts']:
                if state[key][:len(previous[key])] != previous[key]:
                    raise ValueError('Ledger history is not append-only')
        previous, parent = state, commit
    if previous is None:
        raise ValueError('Missing ledger state')
    return previous


def allocate(remote, policy, request, *, anchor, attempt=1, create=True, retries=8):
    validate_request(request)
    if not re.fullmatch(r'[0-9a-f]{40}', anchor or ''):
        raise ValueError('Approved full migration anchor SHA required')
    if type(attempt) is not int or attempt < 1 or type(retries) is not int or retries < 1:
        raise ValueError('Positive attempt/retries required')
    with tempfile.TemporaryDirectory(prefix='cloudmeet-ledger-') as directory:
        root = Path(directory)
        git(root, 'init')
        git(root, 'remote', 'add', 'origin', remote)
        git(root, 'config', 'user.name', 'CloudMeet revision allocator')
        git(root, 'config', 'user.email', 'cloudmeet-allocator@users.noreply.github.com')
        # Authentication is passed through Git's environment config, never disk/argv/URL.
        for retry in range(retries):
            git(root, 'fetch', '--no-tags', 'origin', f'refs/heads/{BRANCH}')
            tip = git(root, 'rev-parse', 'FETCH_HEAD').stdout.strip()
            state = read_history(root, tip, anchor, policy)
            prior = next((r for r in state['records'] if r['request']['run_id'] == request['run_id']), None)
            if prior:
                if prior['request'] != request:
                    raise ValueError('Run identity reused with different immutable inputs')
                record = prior
            else:
                if not create:
                    raise ValueError('Parent allocation absent; inherited jobs cannot allocate')
                record = dict(namespace=policy['namespace'], policy_sha256=digest(policy), request=request,
                              versions=derive(policy, len(state['records']) + 1))
                record['allocation_sha256'] = digest(record)
                state['records'].append(record)
            entry = [request['run_id'], attempt]
            if prior and entry in state['attempts']:
                return record
            state['attempts'].append(entry)
            validate_state(state, policy)
            git(root, 'checkout', '--detach', tip)
            (root / 'ledger.json').write_text(json.dumps(state, sort_keys=True, indent=2) + '\n')
            git(root, 'add', 'ledger.json')
            git(root, 'commit', '-m', f"Record run {request['run_id']} attempt {attempt}")
            candidate = git(root, 'rev-parse', 'HEAD').stdout.strip()
            # Normal fast-forward push is the CAS: candidate has exactly fetched tip as parent.
            result = git(root, 'push', 'origin', f'{candidate}:refs/heads/{BRANCH}', check=False)
            if not result.returncode:
                git(root, 'fetch', '--no-tags', 'origin', f'refs/heads/{BRANCH}')
                current = git(root, 'rev-parse', 'FETCH_HEAD').stdout.strip()
                confirmed = read_history(root, current, anchor, policy)
                if record not in confirmed['records'] or entry not in confirmed['attempts']:
                    raise ValueError('Published allocation readback mismatch')
                return record
            # Includes ambiguous network failures: re-fetch and reuse committed identity on retry.
            # Non-contention failures remain bounded and fail closed, never return unpushed numbers.
            if retry + 1 < retries:
                time.sleep(random.uniform(0.02, min(2, .1 * (retry + 1))))
        raise ValueError('Ledger push retry limit reached; allocation not confirmed')
