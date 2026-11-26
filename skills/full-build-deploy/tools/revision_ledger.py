#!/usr/bin/env python3
"""Persistent allocation on the dedicated controller runner, never in the Git tree."""
import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3

from revision_versions import derive, digest, validate_record, validate_request


def initialize(path, policy):
    derive(policy, 1)
    # Explicit bootstrap only; allocate must NEVER recreate a lost ledger.
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    with closing(sqlite3.connect(path)) as con, con:
        con.executescript('''
        CREATE TABLE identity(policy_hash TEXT NOT NULL, namespace TEXT NOT NULL);
        CREATE TABLE allocations(run_id TEXT PRIMARY KEY, revision INTEGER UNIQUE NOT NULL,
                                 record TEXT NOT NULL);
        CREATE TRIGGER allocations_no_update BEFORE UPDATE ON allocations BEGIN
          SELECT RAISE(ABORT, 'append only'); END;
        CREATE TRIGGER allocations_no_delete BEFORE DELETE ON allocations BEGIN
          SELECT RAISE(ABORT, 'append only'); END;
        CREATE TABLE attempts(run_id TEXT NOT NULL REFERENCES allocations(run_id),
                              attempt INTEGER NOT NULL, PRIMARY KEY(run_id,attempt));
        CREATE TRIGGER attempts_no_update BEFORE UPDATE ON attempts BEGIN
          SELECT RAISE(ABORT, 'append only'); END;
        CREATE TRIGGER attempts_no_delete BEFORE DELETE ON attempts BEGIN
          SELECT RAISE(ABORT, 'append only'); END;
        ''')
        con.execute('INSERT INTO identity VALUES (?,?)', (digest(policy), policy['namespace']))


def allocate(path, policy, request, attempt=1, create=True):
    validate_request(request)
    if type(attempt) is not int or attempt < 1:
        raise ValueError('Positive attempt required')
    if not path.is_file() or path.is_symlink():
        raise ValueError('Pre-initialized persistent ledger required; never auto-recreate')
    con = sqlite3.connect(path.as_uri() + '?mode=rw', uri=True, timeout=30)
    try:
        con.execute('PRAGMA synchronous=FULL')
        con.execute('BEGIN IMMEDIATE')
        identity = con.execute('SELECT policy_hash, namespace FROM identity').fetchall()
        if identity != [(digest(policy), policy['namespace'])]:
            raise ValueError('Ledger policy changed; explicit namespace migration required')
        rows = con.execute('SELECT run_id,revision,record FROM allocations ORDER BY revision').fetchall()
        for expected, (run_id, revision, payload) in enumerate(rows, 1):
            if revision != expected:
                raise ValueError('Missing/corrupt allocation history')
            record = json.loads(payload)
            validate_record(record, policy, record['request']['configuration_sha'], run_id)
            if record['versions']['revision'] != revision:
                raise ValueError('Ledger revision mismatch')
        prior = next((json.loads(row[2]) for row in rows if row[0] == request['run_id']), None)
        if prior:
            if prior['request'] != request:
                raise ValueError('Run identity reused with different immutable inputs')
            con.execute('INSERT OR IGNORE INTO attempts VALUES (?,?)', (request['run_id'], attempt))
            con.commit()
            return prior
        if not create:
            raise ValueError('Parent allocation absent; inherited jobs cannot allocate')
        versions = derive(policy, len(rows) + 1)
        record = dict(namespace=policy['namespace'], policy_sha256=digest(policy), request=request, versions=versions)
        record['allocation_sha256'] = digest(record)
        con.execute('INSERT INTO allocations VALUES (?,?,?)',
                    (request['run_id'], versions['revision'], json.dumps(record, sort_keys=True)))
        con.execute('INSERT INTO attempts VALUES (?,?)', (request['run_id'], attempt))
        con.commit()
        return record
    finally:
        con.close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=['initialize', 'allocate'])
    p.add_argument('--ledger', type=Path, required=True)
    p.add_argument('--policy', type=Path, required=True)
    p.add_argument('--request', type=Path)
    args = p.parse_args()
    policy = json.loads(args.policy.read_text())
    if args.command == 'initialize':
        initialize(args.ledger.resolve(), policy)
    else:
        print(json.dumps(allocate(args.ledger.resolve(), policy, json.loads(args.request.read_text())), sort_keys=True))


if __name__ == '__main__':
    main()
