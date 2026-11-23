"""Real local bare remotes only: never contacts GitHub or the live SQLite ledger."""
import concurrent.futures
import importlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import test_revision_versions as fixtures
import importlib.util
from unittest.mock import patch
import revision_ledger


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


class GitLedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.remote = self.root / 'remote.git'
        subprocess.run(['git', 'init', '--bare', str(self.remote)], check=True, capture_output=True)
        self.seed = self.root / 'seed'
        subprocess.run(['git', 'init', str(self.seed)], check=True, capture_output=True)
        git(self.seed, 'config', 'user.name', 'Test')
        git(self.seed, 'config', 'user.email', 'test@example.invalid')
        git(self.seed, 'checkout', '--orphan', 'cloudmeet-revision-ledger')
        self.policy = fixtures.RevisionTests().policy()
        self.request = fixtures.RevisionTests().request
        self.db = self.root / 'fixture.sqlite'
        revision_ledger.initialize(self.db, self.policy)
        self.first = revision_ledger.allocate(self.db, self.policy, self.request())

    def module(self):
        # Assertion failure rather than import error documents the missing feature.
        spec = importlib.util.find_spec('revision_git_ledger')
        self.assertIsNotNone(spec, 'Git ledger allocator implementation is required')
        return importlib.import_module('revision_git_ledger')

    def publish_fixture(self, module):
        before = self.db.read_bytes()
        state = module.export_sqlite(self.db, self.policy)
        self.assertEqual(before, self.db.read_bytes())
        (self.seed / 'ledger.json').write_text(json.dumps(state))
        git(self.seed, 'add', 'ledger.json')
        git(self.seed, 'commit', '-m', 'fixture migration')
        git(self.seed, 'push', str(self.remote), 'HEAD:refs/heads/cloudmeet-revision-ledger')
        return git(self.seed, 'rev-parse', 'HEAD')

    def test_migration_preserves_records_failed_consumption_rerun_child_verification(self):
        m = self.module()
        anchor = self.publish_fixture(m)
        args = (str(self.remote), self.policy)
        self.assertEqual(m.allocate(*args, self.request(), anchor=anchor, create=False), self.first)
        second = m.allocate(*args, self.request('101'), anchor=anchor)
        self.assertEqual(second['versions']['revision'], 2)
        self.assertEqual(m.allocate(*args, self.request('101'), anchor=anchor, attempt=2), second)
        self.assertEqual(m.allocate(*args, self.request('102'), anchor=anchor)['versions']['revision'], 3)
        with self.assertRaises(ValueError):
            m.allocate(*args, self.request('103'), anchor=anchor, create=False)
        with self.assertRaises(ValueError):
            m.allocate(*args, dict(self.request('101'), task='changed'), anchor=anchor)

    def test_concurrent_pushes_and_duplicate_run_reuse(self):
        m = self.module()
        anchor = self.publish_fixture(m)
        def allocate(run):
            return m.allocate(str(self.remote), self.policy, self.request(str(run)), anchor=anchor, retries=20)
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            results = list(pool.map(allocate, [101, 102, 103, 104, 101]))
        self.assertEqual(sorted(set(r['versions']['revision'] for r in results)), [2, 3, 4, 5])
        self.assertEqual(results[0], results[-1])

    def test_missing_branch_anchor_policy_and_rewritten_history_fail_closed(self):
        m = self.module()
        with self.assertRaises(Exception):
            m.allocate(str(self.remote), self.policy, self.request(), anchor='a' * 40)
        anchor = self.publish_fixture(m)
        for changes in [dict(anchor='a' * 40), dict(anchor=''), dict(policy=dict(self.policy, namespace='changed'))]:
            options = dict(remote=str(self.remote), policy=self.policy, request=self.request(), anchor=anchor)
            options.update(changes)
            with self.assertRaises((ValueError, subprocess.CalledProcessError)):
                m.allocate(**options)
        state = json.loads((self.seed / 'ledger.json').read_text())
        state['records'] = []
        state['attempts'] = []
        (self.seed / 'ledger.json').write_text(json.dumps(state))
        git(self.seed, 'add', 'ledger.json')
        git(self.seed, 'commit', '-m', 'invalid truncate')
        git(self.seed, 'push', str(self.remote), 'HEAD:refs/heads/cloudmeet-revision-ledger')
        with self.assertRaisesRegex(ValueError, 'append-only'):
            m.allocate(str(self.remote), self.policy, self.request('101'), anchor=anchor)

    def test_export_r1_to_r14_and_next_is_r15(self):
        m = self.module()
        originals = [self.first]
        for n in range(101, 114):
            originals.append(revision_ledger.allocate(self.db, self.policy, self.request(str(n))))
        anchor = self.publish_fixture(m)
        self.assertEqual(m.export_sqlite(self.db, self.policy)['records'], originals)
        self.assertEqual(m.allocate(str(self.remote), self.policy, self.request('200'), anchor=anchor)['versions']['revision'], 15)

    def test_ambiguous_push_success_is_reused_after_refetch(self):
        m = self.module()
        anchor = self.publish_fixture(m)
        original = m.git
        pushes = []
        def ambiguous(root, *args, **kwargs):
            result = original(root, *args, **kwargs)
            if args[0] == 'push':
                pushes.append(args)
                self.assertEqual(result.returncode, 0)
                return subprocess.CompletedProcess(args, 1, '', 'connection lost after remote commit')
            return result
        with patch.object(m, 'git', side_effect=ambiguous):
            record = m.allocate(str(self.remote), self.policy, self.request('101'), anchor=anchor, retries=2)
        self.assertEqual(record['versions']['revision'], 2)
        self.assertEqual(len(pushes), 1)
        self.assertEqual(m.allocate(str(self.remote), self.policy, self.request('102'), anchor=anchor)['versions']['revision'], 3)

    def test_push_failure_never_returns_unpublished_assignment(self):
        m = self.module()
        anchor = self.publish_fixture(m)
        original = m.git
        def reject(root, *args, **kwargs):
            if args[0] == 'push':
                return subprocess.CompletedProcess(args, 1, '', 'denied')
            return original(root, *args, **kwargs)
        with patch.object(m, 'git', side_effect=reject):
            with self.assertRaisesRegex(ValueError, 'retry limit'):
                m.allocate(str(self.remote), self.policy, self.request('101'), anchor=anchor, retries=2)
        self.assertEqual(m.allocate(str(self.remote), self.policy, self.request('102'), anchor=anchor)['versions']['revision'], 2)


if __name__ == '__main__':
    unittest.main()
