"""Linux-only private execution journal. Never dispatches or mutates a target.

Immutable numbered event files are authoritative; snapshot.json is only a cache.
Callers must hold the writer context for the full operation. A new context cannot
resume unfinished side effects without external reconciliation evidence.
"""
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import tempfile
import time

ACTIVE = {'running', 'waiting_approval'}
TERMINAL = {'succeeded', 'not_applicable', 'cancelled'}
NEXT = {'pending': {'running', 'blocked', 'waiting_approval', 'not_applicable', 'cancelled'},
        'running': {'succeeded', 'failed', 'blocked', 'waiting_approval', 'cancelled'},
        'waiting_approval': {'running', 'blocked', 'failed', 'cancelled'},
        'failed': {'running', 'cancelled'}, 'blocked': {'running', 'cancelled'}}
IDENTITY = {'instance', 'scope', 'origin', 'configuration_sha', 'tool_sha', 'source_sha'}


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def private(path, directory=False):
    info = path.lstat()
    kind = stat.S_ISDIR if directory else stat.S_ISREG
    if (not kind(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != (0o700 if directory else 0o600)
            or (not directory and info.st_nlink != 1)):
        raise ValueError('Unsafe task state ownership, type or permissions')


def location(root, task):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', task):
        raise ValueError('Invalid task ID')
    root = Path(root).absolute()
    for p in (root, *root.parents):
        if p.is_symlink() or (p / '.git').exists():
            raise ValueError('Task state must be outside repositories and symlinks')
    return root / task


def load(path):
    """Replay atomically committed events, rejecting gaps and altered snapshots."""
    private(path.parent, True)
    private(path, True)
    events = sorted(path.glob('[0-9]*.json'))
    state, previous, hashes = None, None, {}
    for number, p in enumerate(events, 1):
        if p.name != f'{number:08d}.json':
            raise ValueError('Missing or invalid task history')
        private(p)
        try:
            record = json.loads(p.read_bytes())
            body = {k: record[k] for k in ('sequence', 'previous', 'event', 'state')}
            if (record['sequence'] != number or record['previous'] != previous
                    or record['sha256'] != digest(body)):
                raise ValueError('Corrupt task history')
            state = record['state']
            if (state['sequence'] != number or state['task_id'] != path.name
                    or digest(state['plan']) != state['plan_sha256']):
                raise ValueError('Corrupt task plan')
            if number > 1 and (state['plan'] != old['plan']
                               or state['identity'] != old['identity']):
                raise ValueError('Task identity changed')
            previous = record['sha256']
            hashes[number] = digest(state)
            old = state
        except (KeyError, TypeError, json.JSONDecodeError) as error:
            raise ValueError('Invalid task event') from error
    snapshot = path / 'snapshot.json'
    if snapshot.exists():
        private(snapshot)
        try:
            cached = json.loads(snapshot.read_bytes())
            if digest(cached) != hashes.get(cached['sequence']):
                raise ValueError('Snapshot has no matching event')
        except (KeyError, TypeError, json.JSONDecodeError) as error:
            raise ValueError('Invalid task snapshot') from error
    return state, previous


def read_task(root, task):
    """Read only committed facts, even while the writer holds its lock."""
    state, _ = load(location(root, task))
    if state is None:
        raise ValueError('Task has no committed plan')
    return copy.deepcopy(state)


class TaskStore:
    def __init__(self, root, task, *, monotonic=time.monotonic, wall=time.time):
        self.path = location(root, task)
        self.monotonic, self.wall = monotonic, wall
        self.state, self.previous, self.fd = None, None, None

    def __enter__(self):
        import fcntl
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        private(self.path.parent, True)
        self.path.mkdir(mode=0o700, exist_ok=True)
        private(self.path, True)
        self.fd = os.open(self.path / 'writer.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            private(self.path / 'writer.lock')
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.state, self.previous = load(self.path)
            self.last_mono, self.last_wall = self.monotonic(), self.wall()
            if self.state:
                unfinished = [s for s in self.state['steps'] if s['status'] in ACTIVE]
                if unfinished or any(s['status'] not in {'succeeded', 'not_applicable', 'cancelled'}
                                     for s in self.state['steps']):
                    self.state['unknown_intervals'] = True
                    for step in unfinished:
                        step.update(status='blocked', reason='interrupted_reconcile_required',
                                    reconciliation_required=True)
                        if step['attempts']:
                            step['attempts'][-1].update(status='blocked',
                                reason='interrupted_reconcile_required', ended_utc=None)
                    self._commit('interrupted')
            return self
        except BaseException:
            os.close(self.fd)
            self.fd = None
            raise

    def __exit__(self, *_):
        os.close(self.fd)
        self.fd = None

    def _atomic(self, destination, value, *, immutable=False):
        fd, temporary = tempfile.mkstemp(prefix='.pending-', dir=self.path)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(encoded(value))
                stream.flush()
                os.fsync(stream.fileno())
            if immutable:
                os.link(temporary, destination)
                os.unlink(temporary)
            else:
                if destination.is_symlink():
                    raise ValueError('Symlink snapshot refused')
                os.replace(temporary, destination)
            directory = os.open(self.path, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def _snapshot(self):
        self._atomic(self.path / 'snapshot.json', self.state)

    def _commit(self, event):
        if self.fd is None:
            raise ValueError('Writer context required')
        self.state['sequence'] += 1
        record = {'sequence': self.state['sequence'], 'previous': self.previous,
                  'event': event, 'state': self.state}
        record['sha256'] = digest(record)
        try:
            self._atomic(self.path / f'{self.state["sequence"]:08d}.json', record, immutable=True)
            self.previous = record['sha256']
            self._snapshot()
        except BaseException:
            # No further side effects can follow an uncertain journal commit.
            self.state = None
            raise

    def create(self, identity, plan):
        if self.fd is None or self.state is not None:
            raise ValueError('Task already exists or writer context missing')
        if (not isinstance(identity, dict) or not {'instance', 'scope'} <= identity.keys()
                or identity.keys() - IDENTITY):
            raise ValueError('Only public task identity fields are accepted')
        for key, value in identity.items():
            pattern = r'[0-9a-f]{40}' if key.endswith('_sha') else r'[A-Za-z0-9_.:/+\-]{1,200}'
            if not isinstance(value, str) or not re.fullmatch(pattern, value):
                raise ValueError('Invalid public identity value')
        if not isinstance(plan, list) or not plan:
            raise ValueError('Nonempty fixed plan required')
        ids = set()
        for item in plan:
            if (not isinstance(item, dict) or item.keys() != {'id', 'name'}
                    or not isinstance(item['id'], str)
                    or not re.fullmatch(r'[a-z][a-z0-9_-]{0,63}', item['id'])
                    or item['id'] in ids or not isinstance(item['name'], str)
                    or not item['name'].strip() or len(item['name']) > 100
                    or any(ord(c) < 32 for c in item['name'])):
                raise ValueError('Invalid or duplicate fixed step')
            ids.add(item['id'])
        self.state = {'sequence': 0, 'task_id': self.path.name, 'identity': copy.deepcopy(identity),
                      'plan': copy.deepcopy(plan), 'plan_sha256': digest(plan),
                      'created_utc': self.last_wall, 'updated_utc': self.last_wall,
                      'observed_seconds': 0, 'unknown_intervals': False,
                      'wall_clock_uncertain': False,
                      'steps': [dict(item, number=n, status='pending', attempts=[],
                                     execution_seconds=0, waiting_seconds=0,
                                     reconciliation_required=False)
                                for n, item in enumerate(plan, 1)]}
        self._commit('created')

    def _tick(self):
        now, wall = self.monotonic(), self.wall()
        elapsed = now - self.last_mono
        if not math.isfinite(elapsed) or elapsed < 0 or not math.isfinite(wall):
            raise ValueError('Invalid task clock')
        if wall < self.last_wall:
            self.state['wall_clock_uncertain'] = True
        if any(s['status'] not in TERMINAL for s in self.state['steps']):
            self.state['observed_seconds'] += elapsed
        self.state['updated_utc'] = wall
        for step in self.state['steps']:
            if step['status'] in ACTIVE:
                field = 'execution_seconds' if step['status'] == 'running' else 'waiting_seconds'
                step[field] += elapsed
                if step['attempts']:
                    step['attempts'][-1][field] += elapsed
        self.last_mono, self.last_wall = now, wall

    def transition(self, step_id, status, *, reason=None, evidence=None):
        if self.state is None or self.fd is None:
            raise ValueError('Committed task and writer context required')
        step = next((s for s in self.state['steps'] if s['id'] == step_id), None)
        if step is None or status not in NEXT.get(step['status'], set()):
            raise ValueError('Invalid step transition')
        if reason is not None and not re.fullmatch(r'[a-z][a-z0-9_]{0,79}', reason):
            raise ValueError('Safe reason code required; no raw logs')
        if evidence is not None and not re.fullmatch(r'[0-9a-f]{64}', evidence):
            raise ValueError('Evidence digest required')
        if status in {'blocked', 'failed', 'not_applicable', 'cancelled'} and not reason:
            raise ValueError('Reason required')
        if status == 'succeeded' and not evidence:
            raise ValueError('Success evidence required')
        if status == 'running' and (step['status'] in {'blocked', 'failed'}
                                    or step['reconciliation_required']) and not evidence:
            raise ValueError('Reconciliation evidence required before retry')
        self._tick()
        if status == 'running' and (step['status'] != 'waiting_approval'
                                    or not step['attempts']):
            step['attempts'].append({'number': len(step['attempts']) + 1,
                                     'execution_seconds': 0, 'waiting_seconds': 0,
                                     'started_utc': self.last_wall,
                                     'reconciliation_evidence': evidence})
        if step['attempts']:
            step['attempts'][-1].update(status=status, reason=reason, evidence=evidence)
            if status not in ACTIVE:
                step['attempts'][-1]['ended_utc'] = self.last_wall
        step.update(status=status, reason=reason, evidence=evidence,
                    reconciliation_required=status in {'blocked', 'failed'})
        self._commit('transition')

    def checkpoint(self):
        if self.state is None or self.fd is None:
            raise ValueError('Committed task and writer context required')
        self._tick()
        self._commit('checkpoint')

    def view(self):
        if self.state is None:
            raise ValueError('Task state unavailable')
        return copy.deepcopy(self.state)
